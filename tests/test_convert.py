"""Unit tests for harmony_flow.convert."""

import logging
from unittest.mock import MagicMock

import h5netcdf
import numpy as np
import pytest
import rasterio
import xarray as xr

import hashlib
import earthaccess
from typing import Any
from pathlib import Path

from harmony_flow import convert
from harmony_flow.convert import (
    _extract_2d,
    _find_coord,
    _normalize_to_uint8,
    _write_world_file,
    create_image_texture,
    open_dataset,
    process_dataset,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_dataset(
    lat_ascending: bool = False,
    lon_dim_first: bool = False,
    n_time: int | None = None,
    shape: tuple[int, int] = (4, 8),
) -> xr.Dataset:
    """Return a synthetic xr.Dataset with 'u' and 'v' float32 variables."""
    n_lat, n_lon = shape
    lat = np.linspace(-80, 80, n_lat) if lat_ascending else np.linspace(80, -80, n_lat)
    lon = np.linspace(0, 357.5, n_lon)
    rng = np.random.default_rng(42)

    if lon_dim_first:
        spatial_dims: tuple[str, ...] = ("longitude", "latitude")
        spatial_shape = (n_lon, n_lat)
    else:
        spatial_dims = ("latitude", "longitude")
        spatial_shape = (n_lat, n_lon)

    dims = spatial_dims
    data_shape: tuple[int, int] | tuple[int, int, int] = spatial_shape
    coords: dict = {"latitude": lat, "longitude": lon}
    if n_time is not None:
        dims = ("time",) + spatial_dims
        data_shape = (n_time,) + spatial_shape
        coords = {"latitude": lat, "longitude": lon, "time": np.arange(n_time)}

    u = rng.standard_normal(data_shape).astype(np.float32)
    v = rng.standard_normal(data_shape).astype(np.float32)
    return xr.Dataset({"u": (dims, u), "v": (dims, v)}, coords=coords)


def _write_netcdf(path, shape=(4, 8)):
    """Write a minimal CF-style NetCDF4/HDF5 file with u/v variables."""
    n_lat, n_lon = shape
    lat = np.linspace(80.0, -80.0, n_lat, dtype=np.float32)
    lon = np.linspace(0.0, 357.5, n_lon, dtype=np.float32)
    rng = np.random.default_rng(0)
    u_data = rng.standard_normal((n_lat, n_lon)).astype(np.float32)
    v_data = rng.standard_normal((n_lat, n_lon)).astype(np.float32)

    with h5netcdf.File(str(path), "w") as f:
        f.dimensions = {"latitude": n_lat, "longitude": n_lon}
        lat_v = f.create_variable("latitude", ("latitude",), dtype=np.float32)
        lat_v[:] = lat
        lon_v = f.create_variable("longitude", ("longitude",), dtype=np.float32)
        lon_v[:] = lon
        u_v = f.create_variable("u", ("latitude", "longitude"), dtype=np.float32)
        u_v[:] = u_data
        v_v = f.create_variable("v", ("latitude", "longitude"), dtype=np.float32)
        v_v[:] = v_data

    return path


# ---------------------------------------------------------------------------
# _find_coord
# ---------------------------------------------------------------------------


class TestFindCoord:
    def test_finds_latitude(self):
        ds = xr.Dataset(coords={"latitude": np.linspace(-80, 80, 4)})
        result = _find_coord(ds, ("latitude", "lat", "y"))
        np.testing.assert_array_equal(result, ds.coords["latitude"].values)

    def test_finds_lat_alias(self):
        ds = xr.Dataset(coords={"lat": np.linspace(-80, 80, 4)})
        assert _find_coord(ds, ("latitude", "lat", "y")) is not None

    def test_finds_y_alias(self):
        ds = xr.Dataset(coords={"y": np.linspace(-80, 80, 4)})
        assert _find_coord(ds, ("latitude", "lat", "y")) is not None

    def test_finds_longitude(self):
        ds = xr.Dataset(coords={"longitude": np.linspace(0, 360, 8)})
        result = _find_coord(ds, ("longitude", "lon", "x"))
        assert result is not None

    def test_returns_none_when_absent(self):
        assert _find_coord(xr.Dataset(), ("latitude", "lat", "y")) is None

    def test_first_candidate_wins(self):
        """When multiple candidate names are present, the first is returned."""
        ds = xr.Dataset(
            coords={
                "lat": np.array([1.0, 2.0]),
                "y": np.array([10.0, 20.0]),
            }
        )
        result = _find_coord(ds, ("latitude", "lat", "y"))
        np.testing.assert_array_equal(result, ds.coords["lat"].values)


# ---------------------------------------------------------------------------
# _extract_2d
# ---------------------------------------------------------------------------


class TestExtract2d:
    def test_lat_lon_ordered_shape_is_preserved(self):
        ds = _make_dataset(shape=(4, 8))
        assert _extract_2d(ds["u"]).shape == (4, 8)

    def test_lon_lat_ordered_is_transposed_to_lat_lon(self):
        # Stored as (lon=8, lat=4); output must be (lat=4, lon=8).
        ds = _make_dataset(lon_dim_first=True, shape=(4, 8))
        assert _extract_2d(ds["u"]).shape == (4, 8)

    def test_single_time_dim_is_squeezed(self):
        ds = _make_dataset(n_time=1, shape=(4, 8))
        arr = _extract_2d(ds["u"])
        assert arr.ndim == 2
        assert arr.shape == (4, 8)

    def test_multiple_time_steps_selects_first(self):
        ds = _make_dataset(n_time=5, shape=(4, 8))
        arr = _extract_2d(ds["u"])
        assert arr.shape == (4, 8)
        expected = ds["u"].isel(time=0).values
        np.testing.assert_array_equal(arr, expected)

    def test_time_lon_lat_gives_lat_lon_output(self):
        ds = _make_dataset(n_time=3, lon_dim_first=True, shape=(4, 8))
        assert _extract_2d(ds["u"]).shape == (4, 8)

    def test_returns_numpy_array(self):
        ds = _make_dataset()
        assert isinstance(_extract_2d(ds["u"]), np.ndarray)


# ---------------------------------------------------------------------------
# _normalize_to_uint8
# ---------------------------------------------------------------------------


class TestNormalizeToUint8:
    def test_output_dtype_is_uint8(self):
        assert _normalize_to_uint8(np.array([0.0, 0.5, 1.0])).dtype == np.uint8

    def test_min_maps_to_0_and_max_to_255(self):
        out = _normalize_to_uint8(np.array([0.0, 0.5, 1.0]))
        assert out[0] == 0
        assert out[2] == 255

    def test_midpoint_is_approximately_127(self):
        out = _normalize_to_uint8(np.array([0.0, 0.5, 1.0]))
        assert abs(int(out[1]) - 127) <= 1

    def test_all_nan_returns_zeros(self):
        out = _normalize_to_uint8(np.full((3, 3), np.nan))
        np.testing.assert_array_equal(out, np.zeros((3, 3), dtype=np.uint8))

    def test_nan_pixels_map_to_zero(self):
        out = _normalize_to_uint8(np.array([np.nan, 0.0, 1.0]))
        assert out[0] == 0
        assert out[2] == 255

    def test_uniform_finite_value_maps_to_128(self):
        out = _normalize_to_uint8(np.full((4,), 3.14))
        np.testing.assert_array_equal(out, np.full((4,), 128, dtype=np.uint8))

    def test_inf_maps_to_zero(self):
        out = _normalize_to_uint8(np.array([np.inf, 0.0, 1.0]))
        assert out[0] == 0

    def test_negative_values_are_handled(self):
        out = _normalize_to_uint8(np.array([-2.0, 0.0, 2.0]))
        assert out[0] == 0
        assert out[2] == 255

    def test_output_shape_matches_input(self):
        arr = np.random.default_rng(0).standard_normal((6, 10)).astype(np.float32)
        assert _normalize_to_uint8(arr).shape == arr.shape


# ---------------------------------------------------------------------------
# _write_world_file
# ---------------------------------------------------------------------------


class TestWriteWorldFile:
    _TRANSFORM = rasterio.transform.from_bounds(-180, -90, 180, 90, 8, 4)

    def test_creates_file(self, tmp_path):
        path = tmp_path / "test.pgw"
        _write_world_file(path, self._TRANSFORM)
        assert path.exists()

    def test_file_has_six_lines(self, tmp_path):
        path = tmp_path / "test.pgw"
        _write_world_file(path, self._TRANSFORM)
        assert len(path.read_text().splitlines()) == 6

    def test_pixel_width_matches_transform(self, tmp_path):
        path = tmp_path / "test.pgw"
        _write_world_file(path, self._TRANSFORM)
        assert float(path.read_text().splitlines()[0]) == pytest.approx(self._TRANSFORM.a)

    def test_pixel_height_matches_transform(self, tmp_path):
        path = tmp_path / "test.pgw"
        _write_world_file(path, self._TRANSFORM)
        assert float(path.read_text().splitlines()[3]) == pytest.approx(self._TRANSFORM.e)

    def test_x_uses_pixel_center_convention(self, tmp_path):
        path = tmp_path / "test.pgw"
        t = self._TRANSFORM
        _write_world_file(path, t)
        expected = t.c + t.a / 2.0
        assert float(path.read_text().splitlines()[4]) == pytest.approx(expected)

    def test_y_uses_pixel_center_convention(self, tmp_path):
        path = tmp_path / "test.pgw"
        t = self._TRANSFORM
        _write_world_file(path, t)
        expected = t.f + t.e / 2.0
        assert float(path.read_text().splitlines()[5]) == pytest.approx(expected)

    def test_rotation_values_are_zero(self, tmp_path):
        path = tmp_path / "test.pgw"
        _write_world_file(path, self._TRANSFORM)
        lines = path.read_text().splitlines()
        assert float(lines[1]) == pytest.approx(0.0)  # row rotation
        assert float(lines[2]) == pytest.approx(0.0)  # column rotation


# ---------------------------------------------------------------------------
# process_dataset
# ---------------------------------------------------------------------------


class TestProcessDataset:
    def test_creates_png_file(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(_make_dataset(), ["u", "v"], dst_png, tmp_path / "out.pgw")
        assert dst_png.exists()

    def test_creates_world_file(self, tmp_path):
        dst_pgw = tmp_path / "out.pgw"
        process_dataset(_make_dataset(), ["u", "v"], tmp_path / "out.png", dst_pgw)
        assert dst_pgw.exists()

    def test_png_has_three_bands(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(_make_dataset(), ["u", "v"], dst_png, tmp_path / "out.pgw")
        with rasterio.open(dst_png) as src:
            assert src.count == 3

    def test_png_dtype_is_uint8(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(_make_dataset(), ["u", "v"], dst_png, tmp_path / "out.pgw")
        with rasterio.open(dst_png) as src:
            assert src.dtypes[0] == "uint8"

    def test_png_dimensions_match_lat_lon_shape(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(_make_dataset(shape=(6, 10)), ["u", "v"], dst_png, tmp_path / "out.pgw")
        with rasterio.open(dst_png) as src:
            assert src.height == 6
            assert src.width == 10

    def test_png_dimensions_correct_when_lon_dim_first(self, tmp_path):
        # Input stored as (lon=10, lat=6); PNG must still be (height=6, width=10).
        dst_png = tmp_path / "out.png"
        process_dataset(
            _make_dataset(lon_dim_first=True, shape=(6, 10)),
            ["u", "v"],
            dst_png,
            tmp_path / "out.pgw",
        )
        with rasterio.open(dst_png) as src:
            assert src.height == 6
            assert src.width == 10

    def test_blue_band_is_all_zeros(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(_make_dataset(), ["u", "v"], dst_png, tmp_path / "out.pgw")
        with rasterio.open(dst_png) as src:
            np.testing.assert_array_equal(src.read(3), np.zeros((4, 8), dtype=np.uint8))

    def test_ascending_latitude_is_flipped_north_up(self, tmp_path):
        """Row 0 of the PNG must correspond to the northernmost latitude."""
        n_lat, n_lon = 4, 4
        lat_asc = np.linspace(-3.0, 3.0, n_lat)  # south → north
        lon = np.linspace(0.0, 3.0, n_lon)
        # u equals latitude so northern pixels have the highest value.
        u = np.broadcast_to(lat_asc[:, np.newaxis], (n_lat, n_lon)).copy().astype(np.float32)
        # Give v a non-uniform value so it can be normalised without hitting the
        # constant-value fallback.
        v = np.zeros((n_lat, n_lon), dtype=np.float32)
        v[0, 0] = 1.0
        ds = xr.Dataset(
            {"u": (("latitude", "longitude"), u), "v": (("latitude", "longitude"), v)},
            coords={"latitude": lat_asc, "longitude": lon},
        )
        dst_png = tmp_path / "flip.png"
        process_dataset(ds, ["u", "v"], dst_png, tmp_path / "flip.pgw")
        with rasterio.open(dst_png) as src:
            red = src.read(1)
        # After min→0/max→255 normalisation: northernmost row = 255, southernmost = 0.
        assert red[0, 0] == 255
        assert red[-1, 0] == 0

    def test_descending_latitude_needs_no_flip(self, tmp_path):
        """Descending (north→south) latitude is already north-up; no flip should occur."""
        n_lat, n_lon = 4, 4
        lat_desc = np.linspace(3.0, -3.0, n_lat)  # north → south
        lon = np.linspace(0.0, 3.0, n_lon)
        u = np.broadcast_to(lat_desc[:, np.newaxis], (n_lat, n_lon)).copy().astype(np.float32)
        v = np.zeros((n_lat, n_lon), dtype=np.float32)
        v[0, 0] = 1.0
        ds = xr.Dataset(
            {"u": (("latitude", "longitude"), u), "v": (("latitude", "longitude"), v)},
            coords={"latitude": lat_desc, "longitude": lon},
        )
        dst_png = tmp_path / "no_flip.png"
        process_dataset(ds, ["u", "v"], dst_png, tmp_path / "no_flip.pgw")
        with rasterio.open(dst_png) as src:
            red = src.read(1)
        assert red[0, 0] == 255
        assert red[-1, 0] == 0

    def test_works_with_time_dimension(self, tmp_path):
        dst_png = tmp_path / "out.png"
        process_dataset(
            _make_dataset(n_time=3, shape=(4, 8)),
            ["u", "v"],
            dst_png,
            tmp_path / "out.pgw",
        )
        with rasterio.open(dst_png) as src:
            assert src.height == 4
            assert src.width == 8

    def test_raises_for_fewer_than_two_variables(self, tmp_path):
        with pytest.raises(ValueError, match="at least 2"):
            process_dataset(_make_dataset(), ["u"], tmp_path / "out.png", tmp_path / "out.pgw")

    def test_logger_receives_info_call(self, tmp_path):
        logger = MagicMock(spec=logging.Logger)
        process_dataset(
            _make_dataset(), ["u", "v"], tmp_path / "out.png", tmp_path / "out.pgw", logger
        )
        logger.info.assert_called_once()


# ---------------------------------------------------------------------------
# open_dataset
# ---------------------------------------------------------------------------


class TestOpenDataset:
    def test_returns_xr_dataset(self, tmp_path):
        path = _write_netcdf(tmp_path / "test.nc")
        ds = open_dataset(path, "h5netcdf")
        assert isinstance(ds, xr.Dataset)
        assert "u" in ds and "v" in ds

    def test_is_chunked_for_numeric_file(self, tmp_path):
        path = _write_netcdf(tmp_path / "test.nc")
        ds = open_dataset(path, "h5netcdf")
        assert ds["u"].chunks is not None

    def test_not_chunked_when_object_dtype_detected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(convert, "has_object_dtype_variables", lambda _: True)
        path = _write_netcdf(tmp_path / "test.nc")
        ds = open_dataset(path, "h5netcdf")
        assert ds["u"].chunks is None


# ---------------------------------------------------------------------------
# create_image_texture
# ---------------------------------------------------------------------------


class TestCreateImageTexture:
    def test_returns_list_of_one_three_tuple(self, tmp_path):
        path = _write_netcdf(tmp_path / "test.nc")
        result = create_image_texture(path, ["u", "v"])
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_png_file_is_created(self, tmp_path):
        path = _write_netcdf(tmp_path / "test.nc")
        png_path, _, _ = create_image_texture(path, ["u", "v"])[0]
        assert png_path.exists()
        assert png_path.suffix == ".png"

    def test_world_file_is_created(self, tmp_path):
        path = _write_netcdf(tmp_path / "test.nc")
        _, world_path, _ = create_image_texture(path, ["u", "v"])[0]
        assert world_path.exists()
        assert world_path.suffix == ".pgw"

    def test_output_paths_share_stem_with_input(self, tmp_path):
        path = _write_netcdf(tmp_path / "mydata.nc")
        png_path, world_path, _ = create_image_texture(path, ["u", "v"])[0]
        assert png_path.stem == "mydata"
        assert world_path.stem == "mydata"

    def test_e2e_oscar_granule_to_png(self, tmp_path: Path) -> None:
        """
        End-to-End test: Downloads the 06/04/2026 OSCAR granule, processes it,
        and validates the generated PNG against a known checksum.
        """
        EXPECTED_PNG_CHECKSUM: str = (
            "e6734772b49c0bf34a04c7c8c8ede6fbc32a6c221b4cd3705ced47be5a4d82fd"
        )

        earthaccess.login(strategy="environment")
        results: list[Any] = earthaccess.search_data(
            short_name="OSCAR_L4_OC_NRT_V2.0", temporal="2026-06-04", count=1
        )
        assert results

        # saves to the pytest temp directory
        downloaded_files: list[str] = earthaccess.download(results, local_path=str(tmp_path))
        assert downloaded_files

        oscar_granule: Path = Path(downloaded_files[0])

        # runs the core module to create the PNG, world file, and metadata JSON
        service_results: list[tuple[Path, Path, Path]] = create_image_texture(
            src_granule=oscar_granule, var_list=["u", "v"]
        )

        # verification of outputs
        assert len(service_results) == 1

        dst_image: Path
        dst_world: Path
        dst_mdata: Path
        dst_image, dst_world, dst_mdata = service_results[0]

        assert dst_image.exists()
        assert dst_world.exists()
        assert dst_mdata.exists()

        # checksum validation of the output PNG
        hasher = hashlib.sha256()
        with open(dst_image, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)

        actual_checksum: str = hasher.hexdigest()

        assert actual_checksum == EXPECTED_PNG_CHECKSUM
