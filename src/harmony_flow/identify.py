import os
import struct

import h5py


def identify_file(src_path: str) -> str:
    """
    Detects file format from magic bytes and returns the appropriate xarray engine.

    Args:
        src_path (str): Path to the source file

    Returns:
        str: "zarr", "h5netcdf", "netcdf4", or "rasterio"

    Raises:
        ValueError: If the file format is not supported/recognised.
        NotImplementedError: If the file is HDF4, which is not supported by xarray.
    """
    # Check for zarr
    if os.path.isdir(src_path):
        # These markers are specific to virtual zarrs from icechunk
        zarr_markers = {"manifests", "refs", "snapshots", "transactions"}
        contents = set(os.listdir(src_path))
        if contents & zarr_markers:
            return "zarr"
        raise ValueError(f"Directory does not appear to be a Zarr store: {src_path}")

    with open(src_path, "rb") as f:
        header = f.read(8)

    # NetCDF classic or 64-bit offset -> netcdf4 engine
    if header[:3] == b"CDF":
        version = header[3]
        if version in (1, 2):
            return "netcdf4"

    # HDF5 signature, covers both NetCDF-4 and plain HDF5 -> h5netcdf engine
    if header[:8] == b"\x89HDF\r\n\x1a\n":
        return "h5netcdf"

    # TIFF / GeoTIFF -> rasterio engine
    if header[:2] in (b"II", b"MM"):
        magic = struct.unpack_from("<H", header, 2)[0] if header[0:1] == b"I" \
            else struct.unpack_from(">H", header, 2)[0]
        # 42 = regular TIFF, 43 = BigTIFF
        if magic in (42, 43):
            return "rasterio"

    # HDF4 -> no native xarray engine
    if header[:4] == b"\x0e\x03\x13\x01":
        raise NotImplementedError(
            "HDF4 files are not directly supported by harmony-flow."
        )

    raise ValueError(f"Unrecognised file format for: {src_path}")


def has_object_dtype_variables(filepath: str) -> bool:
    """
    Peek into a NetCDF-4/HDF5 file and return True if any dataset
    has an object dtype (variable-length strings, ragged arrays, etc.)
    that would cause dask's auto-rechunking to fail.
    """
    def _check_group(group):
        for _, item in group.items():
            if isinstance(item, h5py.Dataset):
                if item.dtype.kind == 'O' or h5py.check_vlen_dtype(item.dtype):
                    return True
            elif isinstance(item, h5py.Group):
                if _check_group(item):
                    return True
        return False

    with h5py.File(filepath, 'r') as f:
        return _check_group(f)
