# System
import os
import sys
from pathlib import Path
from argparse import ArgumentParser
import time

# Advanced
import xml.etree.ElementTree as ET
import json
import multiprocessing
from tqdm import tqdm

# Numpy
import numpy as np
import matplotlib.pyplot as plt

# Image Processing
from PIL import Image
import cv2

# # Fix to get the dlls to load properly under python >= 3.8 and windows
script_dir = os.path.dirname(os.path.realpath(__file__))
try:
    openslide_dll_path = os.path.join(script_dir, "..", "openslide-win64-20171122", "bin")
    os.add_dll_directory(openslide_dll_path)
    # print(openslide_dll_path)

except Exception as e:
    pass

import openslide

# Custom
import tissue_detection

_MULTIPROCESS = False


class WSIHandler:

    def __init__(self, config_path='resources/config.json'):
        self.slide = None
        self.output_path = None
        self.total_width = 0
        self.total_height = 0
        self.levels = 0
        self.current_level = 0
        self.annotation_list = None
        self.annotation_dict = None
        self.config = self.load_config(config_path)
        self.annotated_only = self.config["save_annotated_only"]
        self.scanner = None

        self.res_x = None
        self.res_y = None

    def load_config(self, config_path):
        assert os.path.exists(config_path), "Cannot find " + config_path
        with open(config_path) as json_file:
            config = json.load(json_file)

        assert 1 >= config["tissue_coverage"] >= 0, "Tissue coverage must be between 1 and 0"
        assert config["blocked_threads"] >= 0
        assert config["patches_per_tile"] >= 1, "Patches per tile must be >= 1"
        assert 0 <= config["overlap"] < 1, "Overlap must be between 1 and 0"
        assert config["annotation_overlap"] >= 0 and config["overlap"] < 1, "Annotation overlap must be between 1 and 0"

        return config

    def load_slide(self, slide_path):
        self.slide = openslide.OpenSlide(slide_path)
        self.total_width = self.slide.dimensions[0]
        self.total_height = self.slide.dimensions[1]
        self.levels = self.slide.level_count - 1

        processing_level = self.config["processing_level"]

        if self.levels < self.config["processing_level"]:
            print("###############################################")
            print("WARNING: Processing level above highest available slide level. Maximum slide level is " + str(
                self.levels) + ", processing level is " + str(
                self.config["processing_level"]) + ". Setting processing level to " + str(self.levels))
            print("###############################################")
            processing_level = self.levels

        return processing_level

    def load_annotation(self, annotation_path):
        annotation_dict = {}
        file_format = Path(annotation_path).suffix

        # CuPath exports
        if file_format == '.geojson' or file_format == '.txt':
            with open(annotation_path) as annotation_file:
                annotations = json.load(annotation_file)
            # Only working for features of the type polygon
            for polygon_nb in range(len(annotations["features"])):
                annotation_dict.update({polygon_nb: annotations["features"][polygon_nb]["geometry"]["coordinates"][0]})

        # xml for CAMELYON17
        elif file_format == '.xml':
            tree = ET.parse(annotation_path)
            root = tree.getroot()

            for elem in root:
                polygon_nb = 0
                for subelem in elem:
                    items = subelem.attrib
                    if "Type" in items.keys():
                        if items["Type"] == "Polygon":
                            annotation_dict.update({polygon_nb: None})
                            polygon_list = []
                            for coordinates in subelem:
                                for coord in coordinates:
                                    polygon_list.append([float(coord.attrib['X']), float(coord.attrib['Y'])])
                            annotation_dict[polygon_nb] = polygon_list
                            polygon_nb += 1
        else:
            return None

        return annotation_dict

    def get_img(self, level=None, show=False):
        if level is None:
            level = self.levels

        dims = self.slide.level_dimensions[level]
        image = np.array(self.slide.read_region((0, 0), level, dims))

        if show:
            plt.imshow(image)
            plt.title("Slide image")
            plt.show()

        return image, level

    def apply_tissue_detection(self, level=None, show=False):

        if level is not None:
            image, level = self.get_img(level, show)
        else:
            image, level = self.get_img(show=show)

        tissue_mask = tissue_detection.tissue_detection(image)

        if show:
            plt.imshow(tissue_mask)
            plt.title("Tissue Mask")
            plt.show()

        return tissue_mask, level

    def determine_tile_size(self, level):

        tile_size_0 = self.config["patches_per_tile"] * self.config["patch_size"]
        downscale_factor = int(self.slide.level_downsamples[level])
        tile_size = int(tile_size_0 / downscale_factor)

        assert self.config["patches_per_tile"] >= 1, "Patches per tile must be greater than 1."

        return tile_size

    def get_relevant_tiles(self, tissue_mask, tile_size, min_coverage, level, show=False):

        # TODO: Handling border cases using the residue
        rows, row_residue = divmod(tissue_mask.shape[0], tile_size)
        cols, col_residue = divmod(tissue_mask.shape[1], tile_size)

        colored = cv2.cvtColor(tissue_mask, cv2.COLOR_GRAY2RGB)

        if self.annotation_dict is not None:
            annotation_mask = np.zeros(shape=(tissue_mask.shape[0], tissue_mask.shape[1]))
            scaling_factor = self.slide.level_downsamples[level]
            scaled_list = [
                [[point[0] / scaling_factor, point[1] / scaling_factor] for point in self.annotation_dict[polygon]]
                for polygon in self.annotation_dict]

            for polygon in scaled_list:
                cv2.fillPoly(annotation_mask, [np.array(polygon).astype(np.int32)], 1)

        relevant_tiles_dict = {}
        tile_nb = 0

        for row in range(rows):
            for col in range(cols):

                tile = tissue_mask[row * tile_size:row * tile_size + tile_size,
                       col * tile_size:col * tile_size + tile_size]
                tissue_coverage = np.count_nonzero(tile) / tile.size
                annotated = False

                if self.annotation_dict is not None:
                    if np.count_nonzero(annotation_mask[
                                        row * tile_size:row * tile_size + tile_size,
                                        col * tile_size:col * tile_size + tile_size]) > 0:
                        annotated = True

                if tissue_coverage >= min_coverage:
                    relevant_tiles_dict.update({tile_nb: {"x": col * tile_size, "y": row * tile_size,
                                                          "size": tile_size, "level": level, "annotated": annotated}})

                    if annotated:
                        tissue_mask = cv2.rectangle(colored, (col * tile_size, row * tile_size),
                                                    (col * tile_size + tile_size, row * tile_size + tile_size),
                                                    (0, 255, 0),
                                                    3)
                    else:
                        tissue_mask = cv2.rectangle(colored, (col * tile_size, row * tile_size),
                                                    (col * tile_size + tile_size, row * tile_size + tile_size),
                                                    (255, 0, 0),
                                                    1)
                    tile_nb += 1

        if show:
            plt.imshow(colored)
            plt.title("Tiled image")
            plt.show()

        return relevant_tiles_dict

    def check_for_label(self, label_dict, annotation_mask):

        label_percentage = np.count_nonzero(annotation_mask) / annotation_mask.size

        for label in label_dict:
            if label_dict[label]["type"] == "==":
                if label_dict[label]["threshold"] == label_percentage:
                    return label
            elif label_dict[label]["type"] == ">=":
                if label_percentage >= label_dict[label]["threshold"]:
                    return label
            elif label_dict[label]["type"] == "<=":
                if label_percentage <= label_percentage[label]["threshold"]:
                    return label

        return None

    def make_dirs(self, output_path, slide_name, label_dict, annotated):
        slide_path = os.path.join(output_path, slide_name)
        if not annotated:
            unlabeled_path = os.path.join(slide_path, "unlabeled")
            if not os.path.exists(unlabeled_path):
                os.makedirs(unlabeled_path)
        else:
            if not os.path.exists(slide_path):
                os.makedirs(slide_path)
            for label in label_dict:
                sub_path = os.path.join(slide_path, label)
                if not os.path.exists(sub_path):
                    os.makedirs(sub_path)

        self.output_path = slide_path

    def normalize_tile_size(self, tile):

        normalizing_factor_x = self.config["microns_per_pixel"]/self.res_x
        normalizing_factor_y = self.config["microns_per_pixel"] / self.res_y

        tile_height = tile.shape[1]
        tile_width = tile.shape[0]

        scaled_height = int(tile_height/normalizing_factor_y)
        scaled_width = int(tile_width/normalizing_factor_x)

        resized_tile = cv2.resize(tile, (scaled_width, scaled_height))
        new_tile_size = scaled_height

        return resized_tile, new_tile_size

    def extract_calibrated_patches(self, tile_dict, level, annotations, label_dict, overlap=0, annotation_overlap=0,
                        patch_size=256,
                        slide_name=None, output_format="png"):

        scaling_factor = int(self.slide.level_downsamples[level])

        for tile_key in tile_dict:
            tile_x = tile_dict[tile_key]["x"] * scaling_factor
            tile_y = tile_dict[tile_key]["y"] * scaling_factor

            tile_size_px = tile_dict[tile_key]["size"] * scaling_factor
            tile_size_mu_m = tile_size_px * self.res_x

            tile = np.array(self.slide.read_region((tile_x, tile_y), level=0, size=(tile_size_px, tile_size_px)))
            tile = tile[:, :, 0:3]




    def extract_patches(self, tile_dict, level, annotations, label_dict, overlap=0, annotation_overlap=0,
                        patch_size=256,
                        slide_name=None, output_format="png"):
        # TODO: Only working with binary labels right now
        px_overlap = int(patch_size * overlap)
        patch_dict = {}

        scaling_factor = int(self.slide.level_downsamples[level])
        patch_nb = 0

        for tile_key in tile_dict:
            # skip unannotated tiles in case only annotated patches should be saved
            if self.annotated_only and not tile_dict[tile_key]["annotated"]:
                pass
            else:
                # ToDo: rows and cols arent calculated correctly, instead a quick fix by using breaks was applied

                tile_x = tile_dict[tile_key]["x"] * scaling_factor
                tile_y = tile_dict[tile_key]["y"] * scaling_factor
                tile_size = tile_dict[tile_key]["size"] * scaling_factor
                tile = np.array(self.slide.read_region((tile_x, tile_y), level=0, size=(tile_size, tile_size)))
                tile = tile[:, :, 0:3]

                # resize tiles to match desired output mpp
                tile, tile_size = self.normalize_tile_size(tile)

                # overlap separately  for annotated and unannotated patches
                if tile_dict[tile_key]["annotated"]:
                    px_overlap = int(patch_size * annotation_overlap)
                    rows = int(np.ceil((tile_size + annotation_overlap) / (patch_size - px_overlap)))
                    cols = int(np.ceil((tile_size + annotation_overlap) / (patch_size - px_overlap)))

                else:
                    px_overlap = int(patch_size * overlap)
                    rows = int(np.ceil((tile_size + overlap) / (patch_size - px_overlap)))
                    cols = int(np.ceil((tile_size + overlap) / (patch_size - px_overlap)))

                # create annotation mask
                if annotations is not None:
                    # Translate from world coordinates to tile coordinates
                    tile_annotation_list = [[[point[0] - tile_x, point[1] - tile_y] for point in annotations[polygon]]
                                            for
                                            polygon in annotations]

                    # Create mask from polygons
                    tile_annotation_mask = np.zeros(shape=(tile_size, tile_size))

                    for polygon in tile_annotation_list:
                        cv2.fillPoly(tile_annotation_mask, [np.array(polygon).astype(np.int32)], 1)

                stop_y = False

                for row in range(rows):
                    stop_x = False

                    for col in range(cols):

                        # Calculate patch coordinates
                        patch_x = int(col * (patch_size - px_overlap))
                        patch_y = int(row * (patch_size - px_overlap))

                        if patch_y + patch_size >= tile_size:
                            stop_y = True
                            patch_y = tile_size - patch_size

                        if patch_x + patch_size >= tile_size:
                            stop_x = True
                            patch_x = tile_size - patch_size

                        global_x = patch_x + tile_x
                        global_y = patch_y + tile_y

                        patch = tile[patch_y:patch_y + patch_size, patch_x:patch_x + patch_size, :]

                        # check if the patch is annotated
                        annotated = False
                        if annotations is not None:
                            patch_mask = tile_annotation_mask[patch_y:patch_y + patch_size,
                                         patch_x:patch_x + patch_size]
                            label = self.check_for_label(label_dict, patch_mask)
                            if label is not None:
                                if self.config["label_dict"][label]["annotated"]:
                                    annotated = True

                        else:
                            label = 'unlabeled'

                        if label is not None:
                            if self.annotated_only and annotated or not self.annotated_only:
                                if slide_name is not None:

                                    file_name = slide_name + "_" + str(global_x) + "_" + str(
                                        global_y) + "." + output_format
                                else:
                                    file_name = str(patch_nb) + "_" + str(global_x) + "_" + str(
                                        global_y) + "." + output_format

                                patch = Image.fromarray(patch)
                                patch.save(os.path.join(self.output_path, label, file_name), format=output_format)

                                patch_dict.update(
                                    {patch_nb: {"x_pos": global_x, "y_pos": global_y, "patch_size": patch_size,
                                                "label": label, "slide_name": slide_name,
                                                "patch_path": os.path.join(label, file_name)}})

                                patch_nb += 1
                        if stop_x:
                            break
                    if stop_y:
                        break

        return patch_dict

    def save_patch_configuration(self, patch_dict):

        file = os.path.join(self.output_path, "tile_information.json")

        with open(file, "w") as json_file:
            json.dump(patch_dict, json_file, indent=4)

    def save_thumbnail(self, mask, slide_name, level, output_format="png"):

        remap_color = ((0, 0, 0), (255, 255, 255))

        process_level = level
        img = self.slide.read_region([0, 0], process_level, self.slide.level_dimensions[process_level])

        # Remove Alpha
        img = np.array(img)[:, :, 0:3]

        if remap_color is not None:
            indizes = np.all(img == remap_color[0], axis=2)
            img[indizes] = remap_color[1]

            copy_img = img[mask.astype(bool), :]

            median_filtered_img = cv2.medianBlur(img, 11)
            median_filtered_img[mask.astype(bool)] = copy_img

            img = median_filtered_img

        file_name = os.path.join(self.config["output_path"], slide_name, "thumbnail." + output_format)
        plt.imsave(file_name, img, format=output_format)

    def init_generic_tiff(self):

        unit_dict = {"milimeter": 1000, "centimeter": 10000, "meter": 1000000}
        self.scanner = "generic-tiff"

        assert self.slide.properties["tiff.ResolutionUnit"] in unit_dict.keys(), \
            "Unknown unit " + self.slide.properties["tiff.ResolutionUnit"]

        factor = unit_dict[self.slide.properties["tiff.ResolutionUnit"]]

        # convert to mpp
        self.res_x = factor / float(self.slide.properties["tiff.XResolution"])
        self.res_y = factor / float(self.slide.properties["tiff.YResolution"])

    def init_aperio(self):
        self.scanner = "aperio"

        self.res_x = float(self.slide.properties["openslide.mpp-x"])
        self.res_y = float(self.slide.properties["openslide.mpp-y"])

    def init_patch_calibration(self):

        properties = list(self.slide.properties)

        # check scanner type
        if self.slide.properties["openslide.vendor"] == "aperio":
            self.init_aperio()
        elif self.slide.properties["openslide.vendor"] == "generic-tiff":
            self.init_generic_tiff()

        # future vendors
        # elif ...

        assert self.scanner, "Not integrated scanner type, aborting"

    def process_slide(self, slide):
        slide_name = os.path.basename(slide)
        slide_name = os.path.splitext(slide_name)[0]

        print("Processing", slide_name, "process id is", os.getpid())

        annotation_path = os.path.join(self.config["annotation_dir"],
                                       slide_name + "." + self.config["annotation_file_format"])

        if os.path.exists(annotation_path):
            annotated = True
            self.annotation_dict = self.load_annotation(annotation_path)
        else:
            annotated = False
            self.annotation_dict = None

        slide_path = os.path.join(self.config["slides_dir"], slide)
        level = self.load_slide(slide_path)
        self.init_patch_calibration()

        mask, level = self.apply_tissue_detection(level=level,
                                                  show=self.config["show_mode"])
        tile_size = self.determine_tile_size(level)

        tile_dict = self.get_relevant_tiles(mask, tile_size=tile_size,
                                            min_coverage=self.config["tissue_coverage"],
                                            level=level,
                                            show=self.config["show_mode"])

        self.make_dirs(output_path=self.config["output_path"],
                       slide_name=slide_name,
                       label_dict=self.config["label_dict"], annotated=annotated)

        self.extract_calibrated_patches(tile_dict,
                                          level,
                                          self.annotation_dict,
                                          self.config["label_dict"],
                                          overlap=self.config["overlap"],
                                          annotation_overlap=self.config["annotation_overlap"],
                                          patch_size=self.config["patch_size"],
                                          slide_name=slide_name,
                                          output_format=self.config["output_format"])

        patch_dict = self.extract_patches(tile_dict,
                                          level,
                                          self.annotation_dict,
                                          self.config["label_dict"],
                                          overlap=self.config["overlap"],
                                          annotation_overlap=self.config["annotation_overlap"],
                                          patch_size=self.config["patch_size"],
                                          slide_name=slide_name,
                                          output_format=self.config["output_format"])

        self.save_patch_configuration(patch_dict)

        self.save_thumbnail(mask, level=level,
                            slide_name=slide_name,
                            output_format=self.config["output_format"])

        print("Finished slide ", slide_name)

    def slides2patches(self):
        extensions = [".tif", ".svs"]
        slide_list = []

        for extension in extensions:
            for file in Path(self.config["slides_dir"]).resolve().glob('**/*' + extension):
                slide_list.append(file)

        annotation_list = os.listdir(self.config["annotation_dir"])
        self.annotation_list = [os.path.splitext(annotation)[0] for annotation in annotation_list]

        missing_annotations = []
        annotated_slides = [name if os.path.splitext(os.path.basename(name))[0] in self.annotation_list
                            else missing_annotations.append(os.path.splitext(os.path.basename(name))[0]) for name in
                            slide_list]
        annotated_slides = list(filter(None.__ne__, annotated_slides))

        print("###############################################")
        print("Found", len(annotated_slides), "annotated slides")
        print("###############################################")
        print("Found", len(missing_annotations), "unannotated slides")
        print("###############################################")

        if self.config["skip_unlabeled_slides"]:
            slide_list = annotated_slides
            print("Processing annotated slides only")

        if not len(slide_list) == 0:
            slide_list = sorted(slide_list)
            if _MULTIPROCESS:
                available_threads = multiprocessing.cpu_count() - self.config["blocked_threads"]
                pool = multiprocessing.Pool(available_threads)
                pool.map(self.process_slide, slide_list)

            else:
                for slide in slide_list:
                    self.process_slide(slide)

            # Save used config file
            file = os.path.join(self.config["output_path"], "config.json")
            with open(file, "w") as json_file:
                json.dump(self.config, json_file, indent=4)

            print("Finished tiling process!")

        else:
            print("###############################################")
            print("WARNING: No slides processed!")
            print("###############################################")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--config_path", default=script_dir + "/resources/config.json")
    args = parser.parse_args()

    slide_handler = WSIHandler(config_path=args.config_path)
    slide_handler.slides2patches()
