# python:3.9 was previously used, but the project requires >=3.10; use a supported version
FROM python:3.11

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project
ADD buildingmotif /opt/buildingmotif
ADD libraries /opt/libraries
ADD migrations /opt/migrations
COPY alembic.ini /opt/
COPY pyproject.toml /opt/
COPY uv.lock /opt/
COPY LICENSE /opt/
ADD docs /opt/docs
ADD buildingmotif/api/start.sh /opt/start.sh
WORKDIR /opt/

# Install dependencies into the project virtual environment (.venv)
RUN uv sync --locked
RUN chmod +x /opt/start.sh

CMD /opt/start.sh
