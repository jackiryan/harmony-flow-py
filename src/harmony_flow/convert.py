"""Core functionality for generating image textures from a granule file."""

from logging import Logger, LoggerAdapter
from pathlib import Path

import icechunk
import xarray as xr

from .identify import (
    identify_file,
    has_object_dtype_variables,
)


type HarmonyLogger = Logger | LoggerAdapter[Logger]
type ServiceResult = list[tuple[Path, Path, Path]]


def open_zarr(src_granule: Path) -> xr.Dataset:
    """Open a virtual zarr from the local filesystem using its saved config."""
    storage = icechunk.local_filesystem_storage(str(src_granule))
    repo = icechunk.Repository.open(storage)
    session = repo.readonly_session("main")
    return xr.open_zarr(
        session.store,
        consolidated=False,
        zarr_format=3,
    )


def open_dataset(src_granule: Path, granule_type: str) -> xr.Dataset:
    """Open a granule using xarray with the specified engine and dask chunks if possible."""
    if granule_type in ("netcdf4", "h5netcdf"):
        use_chunks = not has_object_dtype_variables(str(src_granule))
    else:
        use_chunks = True
    return xr.open_dataset(
        src_granule,
        engine=granule_type,
        chunks="auto" if use_chunks else None,
        decode_times=xr.coders.CFDatetimeCoder(use_cftime=False),
        decode_timedelta=False,
        concat_characters=True,
    )


def process_dataset(
    src_ds: xr.Dataset,
    var_list: list[str],
    logger: HarmonyLogger | None = None,
) -> None:
    return


def create_image_texture(
    src_granule: Path,
    var_list: list[str],
    logger: HarmonyLogger | None = None,
) -> ServiceResult:
    """
    Create a PNG image texture from an input NetCDF/HDF-5 granule file.
    Variables will be encoded as bands in the order they appear in the var_list argument.
    For example, if var_list = ["u", "v"], then u will be encoded to the red channel,
    and v to the green channel.

    Args:
        src_granule (pathlib.Path): Path to granule file (or directory for zarr) to process
        var_list (list[str]): List of variable names to be encoded into the texture
        logger (logging.Logger): A configured Logger object for emitting log messages

    Returns:
        ServiceResult:
        A list of three-tuples where each element is a Path:
            - The output browse image
            - Its associated ESRI world file (containing georeferencing information)
            - GDAL-compatible XML metadata

    """
    dst_image = src_granule.with_suffix(".png")
    dst_world = src_granule.with_suffix(".pgw")
    dst_mdata = src_granule.with_suffix(".png.aux.xml")

    granule_type = identify_file(str(src_granule))
    if granule_type == "zarr":
        src_ds = open_zarr(src_granule)
    else:
        src_ds = open_dataset(src_granule, granule_type)

    process_dataset(src_ds, var_list, logger)

    return [(dst_image, dst_world, dst_mdata)]
