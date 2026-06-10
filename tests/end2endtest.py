import pytest
import hashlib
from pathlib import Path
import earthaccess
from oscar_mapper import generate_png

EXPECTED_PNG_CHECKSUM = "104030f2d9e87e068430838f1fc64056570bec16cc12292f3b7dd76f241aea5a"

@pytest.fixture(scope="session")
def oscar_granule(tmp_path_factory):
    """
    Downloads the test granule once per test session.
    It caches the file in a temporary pytest directory.
    """
    temp_dir = tmp_path_factory.mktemp("test_data")
    
    earthaccess.login()
    
    results = earthaccess.search_data(
            short_name="OSCAR_L4_OC_NRT_V2.0",
            temporal="2026-06-04",
            count=1 
        )
    
    if not results:
        pytest.fail("can't access granule")
    
    downloaded_files = earthaccess.download(results, local_path=str(temp_dir))
    
    return downloaded_files[0]

def test_netcdf_in_expected_png_out(oscar_granule, tmp_path):
    """
    End-to-End test: Verifies the core module takes a NetCDF and produces
    the exact expected PNG.
    """
    output_png_path = tmp_path / "test_output.png"
    
    generate_png(input_nc_path=oscar_granule, output_img_path=str(output_png_path))

    assert output_png_path.exists(), "Core module failed: PNG was not created."
    
    hasher = hashlib.sha256()
    with open(output_png_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
            
    actual_checksum = hasher.hexdigest()
    
    assert actual_checksum == EXPECTED_PNG_CHECKSUM, (
        f"Output PNG checksum mismatch!\n"
        f"Expected: {EXPECTED_PNG_CHECKSUM}\n"
        f"Actual:   {actual_checksum}"
    )