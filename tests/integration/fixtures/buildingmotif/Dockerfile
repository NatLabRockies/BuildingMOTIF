FROM python:3.11

WORKDIR /home/buildingmotif

RUN pip install poetry==1.8.2 && poetry config virtualenvs.create false

COPY pyproject.toml .
COPY poetry.lock .

RUN poetry install --no-root

COPY buildingmotif buildingmotif
COPY tests tests
COPY notebooks notebooks
COPY migrations migrations
COPY libraries libraries
COPY docs docs

RUN poetry install
