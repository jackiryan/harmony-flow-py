# Changelog

The `harmony-flow` module follows semantic versioning. All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- [issue/1](https://github.com/jackiryan/harmony-flow-py/issues/1): Added `plot_granule.py` CLI to automate Earthdata retrieval and process OSCAR NetCDF granules into PNG images.
- [issue/1](https://github.com/jackiryan/harmony-flow-py/issues/1): Added end-to-end texture conversion tests in `test_convert.py`.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added local Docker testing scripts (`bin/build-test`, `bin/run-test`) and a dedicated test container (`docker/tests.Dockerfile`).
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added GitHub Actions workflow (`publish_release.yml`) for automated Docker image building and registry publishing.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added `docker/service_version.txt` to strictly track semantic versions.
- [issue/5](https://github.com/jackiryan/harmony-flow-py/issues/5): Added a frontend visualization to show the intended use case of the harmony service.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Added Harmony API client (`HarmonyClient`) for dynamic texture generation with job polling and progress tracking.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Added UI controls for collection selection (NRT/FINAL/INTERIM), variable selection (u/v vs ug/vg), and date picking with native date picker.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Added authenticated PNG fetching via `fetchImageBlob()` to handle bearer token requirements and CORS restrictions.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Added dynamic date generation per collection to replace static metadata.json.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Added world file (.pgw) fetching from Harmony job results to extract pixel-0 center longitude for correct geographic alignment.
### Changed
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Refactored test architecture to securely layer testing dependencies via `uv` on top of the remote production base image.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Updated `.gitignore` to exclude large test artifacts (`*.nc`, `*.png`, etc.).
- [issue/5](https://github.com/jackiryan/harmony-flow-py/issues/5): Updated `README.md` frontend installation section with prerequisites and setup instructions for running the local visualization.
- [issue/10](https://github.com/jackiryan/harmony-flow-py/issues/10): Updated DataTileSource loader to use `((lon360 - lon0) % 360 + 360) % 360` for longitude adjustment to support non-zero west edge grids.
### Deprecated
### Removed
### Fixed
### Security

[Unreleased]: https://github.com/jackiryan/harmony-flow/