#!/usr/bin/env bash

STATUS=0

uv run pytest tests/ || STATUS=$?

exit $STATUS