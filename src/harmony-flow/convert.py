"""Core functionality for generating image textures from a granule file."""

from logging import Logger
from pathlib import Path
import warnings

import rasterio


def create_image_texture(
        source_granule: Path,
        var_list: list[str],
        logger: Logger,
) -> list[tuple[Path, Path, Path]]:
    """
    Create a PNG image texture from an input NetCDF/HDF-5 granule file.
    Variables will be encoded as bands in the order they appear in the var_list argument.
    For example, if var_list = ["u", "v"], then u will be encoded to the red channel,
    and v to the green channel.

    Args:
        source_granule (pathlib.Path): Path to NetCDF/HDF-5 file to process
        var_list (list[str]): List of variable names to be encoded into the texture
        logger (logging.Logger): A configured Logger object for emitting log messages

    Returns:
        list[tuple[pathlib.Path, pathlib.Path, pathlib.Path]]:
        These are the file paths of:
            - The output browse image
            - Its associated ESRI world file (containing georeferencing information)
            - The auxiliary XML file (containing duplicative georeferencing information)

    """
    warnings.filterwarnings(
        "ignore",
        message="Dataset has no geotransform*",
        category=UserWarning
    )

    dst_image = source_granule.with_suffix(".png")
    dst_world = source_granule.with_suffix(".pgw")

    with rasterio.open(source_granule) as src_ds:
       print(src_ds)

    return [(dst_image, dst_world, dst_world)]