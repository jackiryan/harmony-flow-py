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
```

To run a script using the module within the managed environment:

```bash
uv run python your_script.py
```

### Frontend Installation

The frontend example can be installed in a TBD manner.

## Releasing a new version of the service:

Once a new Docker image has been published with a new semantic version tag, that service version can be released to a Harmony environment by following the directions in the [Harmony Managing Existing Services Guide](https://github.com/nasa/harmony/blob/main/docs/guides/managing-existing-services.md).

## Get in touch:

You can reach out to the maintainer of this repository via email:

* Jacqueline.Ryan@jpl.nasa.gov