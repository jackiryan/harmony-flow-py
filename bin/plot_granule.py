"""Download Earthdata granules and process them via harmony_flow.

This script searches for a specific dataset collection and date, downloads
a single granule, runs the create_image_texture business logic, and renames
the output PNG based on smart defaults or user overrides.
"""

import argparse
import shutil
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

    results = earthaccess.search_data(short_name=shortname, temporal=temporal, count=1)

    if not results:
        raise ValueError(f"No granules found for {shortname} on {temporal}")

    downloaded_files: list[str] = earthaccess.download(results, local_path=".")
    src_granule: Path = Path(downloaded_files[0])

    service_results: list[tuple[Path, Path, Path]] = create_image_texture(
        src_granule=src_granule, var_list=variables
    )

    if not service_results:
        raise RuntimeError("Processing failed: No outputs returned from create_image_texture.")

    dst_image, dst_world, dst_mdata = service_results[0]

    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    if output_override:
        final_png_path = out_dir_path / output_override
    else:
        var_str = "_".join(variables)
        final_png_path = out_dir_path / f"{shortname}_{temporal}_{var_str}.png"

    final_png_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(dst_image, final_png_path)


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Earthdata granules and process them into image textures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python plot_granule.py OSCAR_L4_OC_NRT_V2.0 -t 2026-06-04
    uv run python plot_granule.py OSCAR_L4_OC_NRT_V2.0 -t 2026-06-04 -v ugvg -d ./output
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
        choices=["uv", "ugvg"],
        default="uv",
        help="Current type to process: 'uv' (total) or 'ugvg' (geostrophic). Default is uv.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args: argparse.Namespace = cli()

    var_list = ["u", "v"] if args.variables == "uv" else ["ug", "vg"]

    download_and_process(
        shortname=args.shortname,
        temporal=args.temporal,
        variables=var_list,
        output_override=args.output,
        output_dir=args.output_dir,
    )
