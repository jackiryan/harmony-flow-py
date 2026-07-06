# Harmony Vector Flow Service (`harmony-flow`)

The Harmony Vector Flow Service (`harmony-flow`) is a [Harmony API](https://harmony.earthdata.nasa.gov/) microservice that creates image textures for use in particle flow visualizations in [OpenLayers web maps](https://openlayers.org/en/latest/examples/wind.html). Similar to other Harmony services like [HyBIG](https://github.com/nasa/harmony-browse-image-generator) or [net2cog](https://github.com/podaac/net2cog), `harmony-flow` takes scientific data formats like [GeoTIFF](https://www.earthdata.nasa.gov/about/esdis/esco/standards-practices/geotiff), [netCDF](https://www.unidata.ucar.edu/software/netcdf), or [HDF5](https://www.hdfgroup.org/solutions/hdf5/) and converts them to PNG format. Unlike these services, however, `harmony-flow` is specifically intended to take two or more variables from the source data and encode them in separate bands that represent $u$ and $v$ vector components of a spatially contiguous motion field. The image output from the service can be interpreted by a [WebGL shader](https://github.com/openlayers/openlayers/blob/main/src/ol/layer/Flow.js) to create a particle flow visualization similar to those found in [windy.com](https://www.windy.com/), [earth.nullschool.net](https://earth.nullschool.net/), and others.

The repository contains code and infrastructure to support both the Harmony Vector Flow Service as well as `harmony-flow` Python module. The Harmony Vector Flow Service is packaged as a Docker container that is deployed to [NASA's Harmony](https://harmony.earthdata.nasa.gov/) system. The business logic is contained in the `harmony-flow` library.

Additionally, for testing and visualization, an example implementation of an OpenLayers frontend is included in this repository with sample data.

### `harmony-flow` Module

The image texture generation logic is packaged in the `harmony-flow` library. Usage and API functions are TBD.

### Python Installation (for developers)

Install [uv](https://docs.astral.sh/uv/) if you haven't already:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install directly from source:

```bash
git clone https://github.com/jackiryan/harmony-flow-py.git
cd harmony-flow-py
uv sync --all-groups
uv run pre-commit install
```

To run a script using the module within the managed environment:

```bash
uv run python tests/create_vds.py -h
```

### Frontend Installation

This repository includes a sample frontend implementation of the intended use case for the PNG images produced by this Harmony service using OpenLayers.

**Prerequisites**
- [Node.js](https://nodejs.org/) v18 or later (includes `npm`)

To run the local visualization demo, you first need to generate a sample texture using `plot_granule.py`, and then serve it using the frontend web server.

**1. Generate the Sample Data**
From the repo root, run `plot_granule.py` to download and process an OSCAR granule directly into the frontend's public directory:
```bash
uv run python bin/plot_granule.py OSCAR_L4_OC_NRT_V2.0 -t 2026-06-04 -d frontend/public
```

**2. Install Dependencies**
Navigate into the frontend directory and install the required Node modules:
```bash
cd frontend
npm install
```

**3. Start the Development Server**
Start the Vite development server:
```bash
npm run dev
```

Once the server starts, open your browser and navigate to:
```
http://localhost:5173/
```

### Releasing a new version of the service:

Once a new Docker image has been published with a new semantic version tag, that service version can be released to a Harmony environment by following the directions in the [Harmony Managing Existing Services Guide](https://github.com/nasa/harmony/blob/main/docs/guides/managing-existing-services.md).

### Docker Development Scripts

To streamline local development and ensure parity with the production environment, several bash scripts are provided in the `bin/` directory. These scripts automatically handle cross-platform architecture targeting and simplify Docker interactions.

From the root of the repository, you can run:

* **`./bin/build-image`**: Compiles the production Docker image locally using `docker/service.Dockerfile`.
* **`./bin/build-test`**: Compiles the isolated local testing container using `docker/tests.Dockerfile`. This securely layers testing dependencies via `uv` on top of the remote production base image.
* **`./bin/run-test`**: Executes the full `pytest` suite natively inside the containerized test environment to guarantee an exact match with production.

## Get in touch:

You can reach out to the maintainer of this repository via email:

* Jacqueline.Ryan@jpl.nasa.gov

## Disclaimer

Copyright 2026, by the California Institute of Technology. ALL RIGHTS RESERVED. United States Government Sponsorship acknowledged. Any commercial use must be negotiated with the Office of Technology Transfer at the California Institute of Technology.

This software may be subject to U.S. export control laws. By accepting this software, the user agrees to comply with all applicable U.S. export laws and regulations. User has the responsibility to obtain export licenses, or other export authority as may be required before exporting such information to foreign countries or providing access to foreign persons.