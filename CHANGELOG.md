# Changelog

The `harmony-flow` module follows semantic versioning. All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- [issue/1](https://github.com/jackiryan/harmony-flow-py/issues/1): Added `plot_granule.py` CLI to automate Earthdata retrieval and process OSCAR NetCDF granules into PNG images.
- [issue/1](https://github.com/jackiryan/harmony-flow-py/issues/1): Added end-to-end texture conversion tests in `test_convert.py`.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added local Docker testing scripts (`bin/build-test`, `bin/run-test`) and a dedicated test container (`docker/tests.Dockerfile`).
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added GitHub Actions workflow (`publish_release.yml`) for automated Docker image building and registry publishing.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Added `docker/service_version.txt` to strictly track semantic versions.
### Changed
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Refactored test architecture to securely layer testing dependencies via `uv` on top of the remote production base image.
- [issue/2](https://github.com/jackiryan/harmony-flow-py/issues/2): Updated `.gitignore` to exclude large test artifacts (`*.nc`, `*.png`, etc.).
### Deprecated
### Removed
### Fixed
### Security

[Unreleased]: https://github.com/jackiryan/harmony-flow/