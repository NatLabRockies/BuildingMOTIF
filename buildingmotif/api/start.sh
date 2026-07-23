#!/bin/bash
set -ex
uv run alembic upgrade head
uv run python buildingmotif/api/app.py
