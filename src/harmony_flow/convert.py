"""Core functionality for generating image textures from a granule file."""

from logging import Logger, LoggerAdapter
from pathlib import Path

import icechunk
import numpy as np
import rasterio
import rasterio.crs
import rasterio.transform
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
        decode_times=xr.coders.CFDatetimeCoder(use_cftime=True),
        decode_timedelta=False,
        concat_characters=True,
    )


def _find_coord(src_ds: xr.Dataset, candidates: tuple[str, ...]) -> np.ndarray | None:
    """Return values of the first coordinate found from the candidate names."""
    return next(
        (src_ds.coords[name].values for name in candidates if name in src_ds.coords),
        None,
    )


def _extract_2d(da: xr.DataArray) -> np.ndarray:
    """
    Reduce a DataArray to 2D and return it in (lat, lon) row-major order.

    Selects index 0 along any non-spatial dimensions (e.g. time, depth),
    then explicitly transposes to (lat, lon) so that rows correspond to
    latitude and columns to longitude, matching rasterio's expected layout.
    """
    lat_dims = {"latitude", "lat", "y"}
    lon_dims = {"longitude", "lon", "x"}
    spatial_dims = lat_dims | lon_dims
    for dim in list(da.dims):
        if dim not in spatial_dims and da.sizes[dim] > 1:
            da = da.isel({dim: 0})
    da = da.squeeze()
    lat_dim = next((d for d in da.dims if d in lat_dims), None)
    lon_dim = next((d for d in da.dims if d in lon_dims), None)
    if lat_dim is not None and lon_dim is not None:
        da = da.transpose(lat_dim, lon_dim)
    return da.values


def _normalize_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Scale finite values linearly to [0, 255] uint8; NaN/inf map to 0."""
    finite = np.isfinite(arr)
    out = np.zeros(arr.shape, dtype=np.uint8)
    if not finite.any():
        return out
    valid = arr[finite]
    vmin, vmax = float(valid.min()), float(valid.max())
    if vmax > vmin:
        scaled = np.where(finite, (arr - vmin) / (vmax - vmin) * 255.0, 0.0)
        out = np.clip(scaled, 0, 255).astype(np.uint8)
    else:
        out[finite] = 128
    return out


def _write_world_file(path: Path, transform: rasterio.transform.Affine) -> None:
    """Write an ESRI world file using pixel-center convention."""
    # rasterio Affine c/f are upper-left corner; world files use pixel center
    x_center = transform.c + transform.a / 2.0
    y_center = transform.f + transform.e / 2.0
    with path.open("w") as wf:
        wf.write(f"{transform.a}\n")  # pixel width (x resolution)
        wf.write(f"{transform.d}\n")  # row rotation (0 for north-up)
        wf.write(f"{transform.b}\n")  # column rotation (0 for north-up)
        wf.write(f"{transform.e}\n")  # pixel height (negative for north-up)
        wf.write(f"{x_center}\n")  # x of upper-left pixel center
        wf.write(f"{y_center}\n")  # y of upper-left pixel center


def process_dataset(
    src_ds: xr.Dataset,
    var_list: list[str],
    dst_image: Path,
    dst_world: Path,
    logger: HarmonyLogger | None = None,
) -> None:
    """
    Encode two dataset variables as R/G channels of a uint8 PNG and write
    a companion ESRI world file with georeferencing information.

    The blue channel is set to zero. Finite values in each variable are
    scaled linearly to [0, 255]; NaN and infinite values map to 0.
    Spatial extent is derived from latitude/longitude coordinates in the
    dataset; if none are found, a global WGS-84 extent is assumed.

    Args:
        src_ds: Open xarray Dataset containing the source data.
        var_list: Two variable names; first → red channel, second → green channel.
        dst_image: Destination path for the output PNG file.
        dst_world: Destination path for the companion ESRI world file (.pgw).
        logger: Optional logger for status messages.
    """
    if len(var_list) < 2:
        raise ValueError(f"var_list must contain at least 2 variable names, got {var_list!r}")

    lon_vals = _find_coord(src_ds, ("longitude", "lon", "x"))
    lat_vals = _find_coord(src_ds, ("latitude", "lat", "y"))

    arr_red = _extract_2d(src_ds[var_list[0]])
    arr_green = _extract_2d(src_ds[var_list[1]])

    # Rasterio expects row 0 = north. Flip if latitude is ascending (south→north).
    if lat_vals is not None and lat_vals.ndim == 1 and len(lat_vals) >= 2:
        if lat_vals[1] > lat_vals[0]:
            arr_red = arr_red[::-1]
            arr_green = arr_green[::-1]

    band_red = _normalize_to_uint8(arr_red)
    band_green = _normalize_to_uint8(arr_green)
    band_blue = np.zeros_like(band_red)

    height, width = band_red.shape

    if lon_vals is not None and lat_vals is not None:
        west = float(lon_vals.min())
        east = float(lon_vals.max())
        south = float(lat_vals.min())
        north = float(lat_vals.max())
    else:
        west, south, east, north = -180.0, -90.0, 180.0, 90.0

    transform = rasterio.transform.from_bounds(west, south, east, north, width, height)

    if logger is not None:
        logger.info(
            "Writing %s (%dx%d px) extent=[%g, %g, %g, %g]",
            dst_image.name,
            width,
            height,
            west,
            south,
            east,
            north,
        )

    with rasterio.open(
        dst_image,
        "w",
        driver="PNG",
        height=height,
        width=width,
        count=3,
        dtype=np.uint8,
        crs=rasterio.crs.CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(band_red, 1)
        dst.write(band_green, 2)
        dst.write(band_blue, 3)

    _write_world_file(dst_world, transform)


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

    process_dataset(src_ds, var_list, dst_image, dst_world, logger)

    return [(dst_image, dst_world, dst_mdata)]
