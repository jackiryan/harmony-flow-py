ARG SERVICE_IMAGE=harmony-flow:latest
FROM ${SERVICE_IMAGE}

USER root

RUN uv sync --all-groups

COPY ./tests tests

ENTRYPOINT ["uv", "run", "pytest", "tests/"]