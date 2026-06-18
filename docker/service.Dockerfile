# Copyright 2026, by the California Institute of Technology.
# ALL RIGHTS RESERVED. United States Government Sponsorship acknowledged.
# Any commercial use must be negotiated with the Office of Technology
# Transfer at the California Institute of Technology.
#
# This software may be subject to U.S. export control laws. By accepting
# this software, the user agrees to comply with all applicable U.S. export
# laws and regulations. User has the responsibility to obtain export
# licenses, or other export authority as may be required before exporting
# such information to foreign countries or providing access to foreign
# persons.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libhdf5-dev \
        libnetcdf-dev \
        libexpat1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --quiet --disabled-password --shell /bin/sh --home /home/dockeruser --gecos "" --uid 1000 dockeruser
WORKDIR /app

# Copy dependency files first so this layer is cached unless deps change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project
COPY README.md ./
COPY src/ src/
COPY docker/ docker/
RUN uv sync --frozen --no-dev

# harmony_service is not a distributed package, so add src/ to PYTHONPATH
ENV PYTHONPATH="/app/src"
ENV PATH="/app/.venv/bin:${PATH}"

COPY docker/docker-entrypoint.sh docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh

RUN chown -R dockeruser:dockeruser /app

USER dockeruser
ENTRYPOINT ["./docker-entrypoint.sh"]