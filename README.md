# Processing and tiling of histological slides

[![python](https://img.shields.io/badge/-Python_3.9-blue?logo=python&logoColor=white)](https://www.python.org/)
[![black](https://img.shields.io/badge/Code%20Style-Black-black.svg?labelColor=gray)](https://black.readthedocs.io/en/stable/)

## Repository setup

We suggest to use *miniconda* as package manager for your system. Create and activate conda environment with:

```bash
conda env create -f environment.yml
conda activate wsi-pre2
```

## Run tiling with provided config files

The main script to run is `tile_generator.py`. We provide configs in the `configs/` folder which generate tables of patch locations with the corresponding pixel sizes. The tables are then stored as `.csv` files for each slide in the configured `output_path`. 
By default multiprocessing is enabled, such that multiple slides can be processed simultaneously.

As example the tiling of TCGA slides with `patch_size=256` can be started as follows:
```bash
python tile_generator.py --config configs/tcga-crc_256.json
```

## Config parameters

The table shows descriptions for the most important config parameters:

| Dictionary Entry | Description |
| ----------- | ----------- |
| check_resolution | Perform a resolution check of all slides before extracting patches |
| use_tissue_detection | Toggle the activation of tissue detection |
| remove_top_border | Useful for Camelyon slides. Default is false |
| save_patches | In old pipelines we used to store patches. In this project the default is false |
| zip_patches | Experimental to try if zipped patch image directories increase transfer speeds. Default is false. |
| tissue_coverage | Threshold [0,1] for how much tissue coverage is necessary, default is 0.8|
| processing_level | Level of downscaling by openslide - Lowering the level will increase precision but more time is needed, default is 3 | 
| blocked_threads |Number of threads that wont be used by the program|
| patches_per_tile | Number of patches used for lower resolution operations like tissue detection | 
| overlap | Value [0,1] to set the overlap between neighbouring unannotated patches |
| annotation_overlap | Value [0,1] to set the overlap between neighbouring annotated patches | 
| patch_size | Output pixel size of the quadratic patches |
| calibration | |
| use_non_pixel_lengths | Activate calibration and use micrometers instead of pixels |
| patch_size_microns | Specify the patch size in micrometers. At 0.25 $\mu\text{m}$ / pixel, 64 $\mu\text{m}$ equal 256 pixels |
| resize | Whether to resize the patches in micrometers to the given patch_size |
| dataset | Provide name for the dataset |
| slides_dir | Directory where the different slides and subdirs are located  | 
| slideinfo_file | Provide a .csv file with filenames and labels | 
| annotation_dir | Directory where the annotations are located |
| annotation_file_format | File format of the input annotations ("xml","geojson")| 
| output_path | Output directory to where the resulting files will be stored |
| skip_unlabeled_slides | Boolean to skip slides without an annotation file | 
| save_annotated_only | Boolean to only save annotated patches |
| output_format | Image output format. Either "jpeg" or "png" |
| metadata_format | Format in which slide metadata is stored. Default is "csv" |
| write_slideinfo | Write information about the processed slide | 
| show_mode | Boolean to enable plotting of some intermediate results/visualizations | 
| label_dict |  Structure to set up the operator and the threshold for checking the coverage of a certain class|
| type | Operator type [ "==", ">=", "<="]| 
| threshold | Coverage threshold for the individual class |