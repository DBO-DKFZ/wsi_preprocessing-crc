import json
import os
from argparse import ArgumentParser
from pathlib import Path

script_dir = os.path.dirname(os.path.realpath(__file__))


def main(config_path):
    with open(config_path) as json_file:
        config = json.load(json_file)
    tile_path = config["output_path"]

    total_tumor = 0
    total_tiles = 0
    slides = sorted([f for f in os.listdir(tile_path) if os.path.isdir(os.path.join(tile_path, f))])
    for i in range(len(slides)):
        slide = slides[i]
        slide_path = os.path.join(tile_path, slide)
        n_tumor = len(os.listdir(os.path.join(slide_path, "tumor")))
        n_other = len(os.listdir(os.path.join(slide_path, "non_tumor")))
        n_total = n_tumor + n_other
        frac = n_tumor / n_total * 100
        print(f"{i}: {n_tumor}/{n_total}, {frac:.4f}% tumor tiles of total tiles, name: {slide}")
        total_tumor += n_tumor
        total_tiles += n_total
    frac = total_tumor / total_tiles * 100
    print(f"Total: {total_tumor}/{total_tiles}, {frac:.4f}% tumor tiles of total tiles")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--config_path", default=script_dir + "/resources/config.json")
    args = parser.parse_args()

    main(args.config_path)
