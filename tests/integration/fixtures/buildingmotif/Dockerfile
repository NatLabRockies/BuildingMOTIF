FROM python:3.10

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /home/buildingmotif

# install dependencies first (without the project) for better layer caching
COPY pyproject.toml .
COPY uv.lock .

RUN uv sync --no-install-project --locked

COPY buildingmotif buildingmotif
COPY tests tests
COPY notebooks notebooks
COPY migrations migrations
COPY libraries libraries
COPY docs docs
COPY LICENSE .

RUN uv sync --locked
