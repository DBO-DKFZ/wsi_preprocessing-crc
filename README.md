# Processing and tiling of histological slides

## Download data
- The TCGA colorectal cancer slides from TCGA-COAD and TCGA-READ studies can be downloaded from <https://portal.gdc.cancer.gov/>
- Access to the MCO slides can be requested at <https://www.sredhconsortium.org/sredh-datasets/mco-study-whole-slide-image-dataset>

## Repository setup

We suggest to use `conda` as package manager for your system.

1. Create conda environment:
```bash
conda env create -f environment.yml
```

2. Set environment variables. This can be done by adding the following lines to your `.bashrc` file:
```bash
export TCGA_ROOT_DIR=path/to/tcga/slides
export MCO_ROOT_DIR=path/to/mco/slides
export SLIDE_PROCESS_DIR=path/to/local/storage
```

## Run tiling with provided config files

The main script to run is `tile_generator.py`. We provide configs in the `configs/` folder which generate tables of patch locations with the corresponding pixel sizes. The tables are then stored as `.csv` files for each slide in the configured `output_path`. 
By default multiprocessing is enabled, such that multiple slides can be processed simultaneously.

The tiling of TCGA slides with `patch_size=256` can be started as follows:
```bash
python tile_generator.py --config configs/tcga-crc_256.json
```