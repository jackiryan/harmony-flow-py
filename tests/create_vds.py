"""Create Virtual Datasets (VDS) for streaming granule data for unit tests.

This script should only need to be run once to create the VDS found the data/
directory, but may need to be updated as test requirements change.
"""

import argparse
import earthaccess
import icechunk
from obstore.store import HTTPStore
from obspec_utils.registry import ObjectStoreRegistry
from pathlib import Path
from urllib.parse import urlparse
from virtualizarr import open_virtual_mfdataset
from virtualizarr.parsers import DMRPPParser
import warnings


def get_edl_token() -> str | None:
    """Acquire Earthdata Login (EDL) and access token."""
    earthaccess.login()
    # This function is incorrectly documented, it returns a dict
    return earthaccess.get_edl_token().get("access_token")  # type: ignore


def get_file_urls(
    collection_shortname: str,
    temporal: tuple[str] | tuple[str, str],
) -> list[str]:
    """
    Use earthaccess to find a set of granules from a collection.
    See https://earthaccess.readthedocs.io/en/stable/api/#earthaccess.api.search_data
    for more information.
    """
    warnings.filterwarnings("ignore", message="As of version 1.0*")
    results = earthaccess.search_data(
        short_name=collection_shortname,
        temporal=temporal,
    )

    # Virtualizarr uses DMR++ links to construct the VDS (allows for subsetting)
    granule_dmrpp_urls = [
        granule.data_links(access="indirect")[0] + ".dmrpp" for granule in results
    ]
    return granule_dmrpp_urls


def construct_vds_name(
    collection_shortname: str,
    temporal: str,
    output_dir: Path,
) -> Path:
    """
    Give a sensible name to the VDS. Note that virtual zarrs are directories, and not files.
    Example:
    vds_path = tests/data/OSCAR_L4_OC_NRT_V2.0_2026_03_16/

    Args:
        collection_shortname (str): Collection shortname from Earthdata Search or CMR
        temporal (str): The time string for the dataset
        output_dir (pathlib.Path): Path to store the output virtual zarr

    Returns:
        pathlib.Path:
        A Path object pointing to the virtual zarr that will be created
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    vds_path = output_dir.joinpath(f"{collection_shortname}_{temporal.replace('-', '_')}")
    return vds_path


def virtualize_granules(
    granule_urls: list[str],
    vds_path: Path,
    token: str,
) -> None:
    """
    Create a small virtual dataset (zarr store) using DMR++ links from NASA Earthdata.
    Creates a virtual zarr by opening and concatenating the links, and stores the
    virtual chunk reference using icechunk.

    Args:
        granule_urls (list[str]): A list of DMR++ URLs retrieved by earthaccess
        vds_path (Path): Path to store the output virtual zarr
        token (str): NASA Earthdata Login (EDL) token
    """
    warnings.filterwarnings(
        "ignore",
        message="Numcodecs codecs are not in the Zarr version 3 specification*",
        category=UserWarning,
    )

    # Create an HTTPStore to access the granules via their the DMRPP urls
    parsed_url = urlparse(granule_urls[0])
    domain = parsed_url.netloc
    print(domain)
    http_store = HTTPStore.from_url(
        f"https://{domain}",
        client_options={"default_headers": {"Authorization": f"Bearer {token}"}},
    )
    obstore_registry = ObjectStoreRegistry({f"https://{domain}": http_store})

    vds = open_virtual_mfdataset(
        urls=granule_urls,
        registry=obstore_registry,
        parser=DMRPPParser(group="/"),
        concat_dim="time",
        compat="override",
        coords="minimal",
        combine="nested",
        parallel="dask",
    )

    # Using local_filesystem_storage will create an unavoidable warning:
    # WARN icechunk::storage::object_store: ...
    # This warning comes from icechunk's Rust code and can't be filtered, but is not
    # a concern given the access pattern for the virtual zarrs we are creating.
    storage = icechunk.local_filesystem_storage(str(vds_path))
    config = icechunk.RepositoryConfig.default()
    config.set_virtual_chunk_container(
        icechunk.VirtualChunkContainer(
            f"https://{domain}/",
            icechunk.http_store({"getOpts": f"Authorization: Bearer {token}"}),
        )
    )
    repo = icechunk.Repository.open_or_create(storage, config)
    session = repo.writable_session("main")
    vds.virtualize.to_icechunk(session.store)
    session.commit(f"Committed {len(granule_urls)} granules")
    repo.save_config()


def create_vds(
    collection_shortname: str,
    temporal: list[str],
    output_dir: str = "./data/",
    debug: bool = True,
) -> Path:
    """
    Top-level function to create a small virtual dataset (VDS) from NASA
    Earthdata granules. Uses earthaccess to retrieve DMR++ links, virtualizarr
    to create a zarr dataset, and icechunk to store the result.

    Args:
        collection_shortname (str): Collection shortname from Earthdata Search or CMR
        temporal (list[str]): A one or two element list of datetimes in YYYY-mm-dd format
                              used to query NASA Earthdata
        output_dir (str): Path to store the output virtual zarr
        debug (bool): Print debug output

    Returns:
        pathlib.Path:
        A Path object pointing to the virtualized dataset (zarr)
    """
    if debug:
        print("Logging in to NASA Earthdata")
    edl_token = get_edl_token()
    if edl_token is None:
        raise ValueError("Authentication failed: unable to acquire EDL token")

    temporal_tuple: tuple[str] | tuple[str, str] = (
        (temporal[0],) if len(temporal) == 1 else (temporal[0], temporal[1])
    )
    if debug:
        time_str = (
            f"on {temporal[0]}" if len(temporal) == 1 else f"from {temporal[0]} to {temporal[1]}"
        )
        print(f"Searching for granules from {collection_shortname} {time_str}")
    dmrpp_urls = get_file_urls(collection_shortname, temporal_tuple)

    vds_path = construct_vds_name(collection_shortname, temporal[0], Path(output_dir))
    if debug:
        print(f"Found {len(dmrpp_urls)} granules. Constructing VDS {vds_path.name}...")
    virtualize_granules(dmrpp_urls, vds_path, edl_token)

    return vds_path


def cli() -> argparse.Namespace:
    """Parse command line arguments and pass them to the caller"""
    parser = argparse.ArgumentParser(
        description="Create virtual datasets (VDS) for unit testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    # Create OSCAR Ocean Currents (OC) VDS for 2026-03-17
    uv run python tests/create_vds.py OSCAR_L4_OC_NRT_V2.0 -t 2026-03-17 --output-dir tests/data/
""",
    )

    parser.add_argument(
        "shortname",
        type=str,
        help="Collection shortname as listed on Earthdata Search or CMR",
    )
    parser.add_argument(
        "-t",
        "--temporal",
        type=str,
        nargs="+",
        metavar=("BEGIN", "END"),
        required=True,
        help=(
            "For most use cases, specify a YYYY-mm-dd date, please see "
            "https://earthaccess.readthedocs.io/en/stable/api/#earthaccess.api.search_data"
            " for more details (look for temporal in the kwargs)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data/",
        help="Directory to store VDS on the local filesystem. Name is automatically selected.",
    )
    parser.add_argument("--quiet", action="store_false", help="Do not print debug information")

    args = parser.parse_args()
    if len(args.temporal) > 2:
        parser.error("--temporal accepts at most 2 values")
    return args


if __name__ == "__main__":
    args = cli()
    create_vds(args.shortname, args.temporal, args.output_dir, args.quiet)
