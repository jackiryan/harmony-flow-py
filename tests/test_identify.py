import os
import struct

import h5py
import numpy as np
import pytest

from harmony_flow.identify import has_object_dtype_variables, identify_file

ZARR_DIR = os.path.join(os.path.dirname(__file__), "data", "OSCAR_L4_OC_NRT_V2.0_2026_03_16")


# ---------------------------------------------------------------------------
# identify_file
# ---------------------------------------------------------------------------

class TestIdentifyFile:
    def test_zarr_directory(self):
        assert identify_file(ZARR_DIR) == "zarr"

    def test_non_zarr_directory_raises(self, tmp_path):
        (tmp_path / "some_file.txt").write_text("hello")
        with pytest.raises(ValueError, match="does not appear to be a Zarr store"):
            identify_file(str(tmp_path))

    def test_netcdf_classic(self, tmp_path):
        f = tmp_path / "classic.nc"
        f.write_bytes(b"CDF\x01" + b"\x00" * 4)
        assert identify_file(str(f)) == "netcdf4"

    def test_netcdf_64bit_offset(self, tmp_path):
        f = tmp_path / "offset.nc"
        f.write_bytes(b"CDF\x02" + b"\x00" * 4)
        assert identify_file(str(f)) == "netcdf4"

    def test_hdf5_returns_h5netcdf(self, tmp_path):
        f = tmp_path / "test.h5"
        with h5py.File(str(f), "w") as hf:
            hf.create_dataset("data", data=[1, 2, 3])
        assert identify_file(str(f)) == "h5netcdf"

    def test_tiff_little_endian(self, tmp_path):
        f = tmp_path / "test.tif"
        header = b"II" + struct.pack("<H", 42) + b"\x00" * 2
        f.write_bytes(header)
        assert identify_file(str(f)) == "rasterio"

    def test_tiff_big_endian(self, tmp_path):
        f = tmp_path / "test.tif"
        header = b"MM" + struct.pack(">H", 42) + b"\x00" * 2
        f.write_bytes(header)
        assert identify_file(str(f)) == "rasterio"

    def test_bigtiff_little_endian(self, tmp_path):
        f = tmp_path / "test.tif"
        header = b"II" + struct.pack("<H", 43) + b"\x00" * 2
        f.write_bytes(header)
        assert identify_file(str(f)) == "rasterio"

    def test_hdf4_raises_not_implemented(self, tmp_path):
        f = tmp_path / "test.hdf"
        f.write_bytes(b"\x0e\x03\x13\x01" + b"\x00" * 4)
        with pytest.raises(NotImplementedError, match="HDF4"):
            identify_file(str(f))

    def test_unrecognised_format_raises(self, tmp_path):
        f = tmp_path / "unknown.bin"
        f.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07")
        with pytest.raises(ValueError, match="Unrecognised file format"):
            identify_file(str(f))


# ---------------------------------------------------------------------------
# has_object_dtype_variables
# ---------------------------------------------------------------------------

class TestHasObjectDtypeVariables:
    def _make_hdf5(self, tmp_path, name="test.h5"):
        return tmp_path / name

    def test_no_object_dtype(self, tmp_path):
        f = tmp_path / "numeric.h5"
        with h5py.File(str(f), "w") as hf:
            hf.create_dataset("temps", data=np.array([1.0, 2.0, 3.0]))
        assert has_object_dtype_variables(str(f)) is False

    def test_vlen_string_dataset_detected(self, tmp_path):
        f = tmp_path / "strings.h5"
        vlen_str = h5py.string_dtype()
        with h5py.File(str(f), "w") as hf:
            hf.create_dataset("labels", data=["a", "bb", "ccc"], dtype=vlen_str)
        assert has_object_dtype_variables(str(f)) is True

    def test_nested_group_object_dtype_detected(self, tmp_path):
        f = tmp_path / "nested.h5"
        vlen_str = h5py.string_dtype()
        with h5py.File(str(f), "w") as hf:
            grp = hf.create_group("metadata")
            grp.create_dataset("names", data=["x", "y"], dtype=vlen_str)
            hf.create_dataset("values", data=np.array([10, 20]))
        assert has_object_dtype_variables(str(f)) is True

    def test_nested_group_no_object_dtype(self, tmp_path):
        f = tmp_path / "nested_clean.h5"
        with h5py.File(str(f), "w") as hf:
            grp = hf.create_group("group1")
            grp.create_dataset("data", data=np.arange(5))
        assert has_object_dtype_variables(str(f)) is False

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.h5"
        with h5py.File(str(f), "w"):
            pass
        assert has_object_dtype_variables(str(f)) is False
