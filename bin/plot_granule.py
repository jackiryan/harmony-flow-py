"""Download Earthdata granules and process them via harmony_flow.

This script searches for a specific dataset collection and date, downloads
a single granule, runs the create_image_texture business logic, and renames
the output PNG based on smart defaults or user overrides.
"""

import argparse
import shutil
import tempfile
import warnings
from pathlib import Path

import earthaccess
from harmony_flow.convert import create_image_texture


def download_and_process(
    shortname: str,
    temporal: str,
    variables: list[str],
    output_override: str | None,
    output_dir: str,
) -> None:
    earthaccess.login()

    warnings.filterwarnings("ignore", "As of version 1.0*", FutureWarning)
    results = earthaccess.search_data(short_name=shortname, temporal=temporal, count=1)

    if not results:
        raise ValueError(f"No granules found for {shortname} on {temporal}")

    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        downloaded_files = earthaccess.download(results, local_path=tmp_dir)
        src_granule = Path(downloaded_files[0])

        service_results = create_image_texture(src_granule=src_granule, var_list=variables)

        if not service_results:
            raise RuntimeError("Processing failed: No outputs returned from create_image_texture.")

        src_png, src_pgw, src_xml = service_results[0]
        var_suffix = "_".join(variables)
        out_stem = output_override if output_override else f"{shortname}_{temporal}_{var_suffix}"

        dst_png = out_dir_path / f"{out_stem}.png"
        dst_pgw = out_dir_path / f"{out_stem}.pgw"
        dst_xml = out_dir_path / f"{out_stem}.png.aux.xml"

        shutil.copy2(src_png, dst_png)
        shutil.copy2(src_pgw, dst_pgw)
        shutil.copy2(src_xml, dst_xml)

        print(f"Successfully created {dst_png} and associated files")


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Earthdata granules and process them into image textures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python plot_granule.py OSCAR_L4_OC_NRT_V2.0 -t 2026-06-04
    uv run python plot_granule.py OSCAR_L4_OC_NRT_V2.0 -t 2026-06-04 -v ug vg -d ./output
""",
    )

    parser.add_argument(
        "shortname", type=str, help="Collection shortname as listed on Earthdata Search or CMR"
    )
    parser.add_argument(
        "-t",
        "--temporal",
        type=str,
        required=True,
        help="The specific date string to pull data for (e.g., YYYY-MM-DD)",
    )
    parser.add_argument("-o", "--output", type=str, default=None, help="Custom output PNG name.")
    parser.add_argument(
        "-d",
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save the output file (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--variables",
        type=str,
        nargs=2,
        default=["u", "v"],
        help=(
            "NetCDF variables to process for Red and Green channels "
            "(exactly 2 required; default: u v)"
        ),
    )

    return parser.parse_args()


if __name__ == "__main__":
    args: argparse.Namespace = cli()

    download_and_process(
        shortname=args.shortname,
        temporal=args.temporal,
        variables=args.variables,
        output_override=args.output,
        output_dir=args.output_dir,
    )
