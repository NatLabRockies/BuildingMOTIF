# Developer Documentation

## Installing

1. Install prerequisites:
   - [Python >= 3.11.0, < 3.13](https://www.python.org/downloads/)
   - [Poetry](https://python-poetry.org/docs/#installation)
2. Clone this repository.
3. Change directory to the new `/BuildingMOTIF` directory.
4. Create and activate a virtual environment:
   ```
   # for example
   python3 -m venv .venv
   source .venv/bin/activate
   ```
5. Install dependencies and pre-commit.
    ```
    poetry install --with dev # includes development dependencies
    poetry run pre-commit install
    ```

## Developing

### Database
Initialize a database by setting it in the `.env` file, then run the migrations. Note for Windows users, the following commands require a Unix shell, e.g. Bash.
```
set -o allexport; source .env; set +o allexport
poetry run alembic upgrade head
```

After making changes to the tables, you must make a new db migration.
```
poetry run alembic revision -m "Description of Changes." --autogenerate
```

Additional changes may need to be made to the migration, so be sure to check it. [Read here](https://alembic.sqlalchemy.org/en/latest/autogenerate.html#auto-generating-migrations) for more information on alembic autogenerate migrations.

Uping the API
```
poetry run python buildingmotif/api/app.py
```
API will run on localhost:5000

### Using Postgres

**In Development**: While we find SQLite much easier to use for development, there are reasons to use Postgres as the backend database for BuildingMOTIF during development.
We recommend use of the `psycopg2-binary` package for interacting with Postgres for development. *This will be installed automatically as part of installing development dependencies. Make sure you use `poetry install --with dev`*.

**In Production**: To use Postgres as the backend database in a production deployment, we recommend installation of BuildingMOTIF with the `postgres` feature (`pip install BuildingMOTIF[postgres]`).
This will install the `psycopg2` library  which is [recommended over `psycopg2-binary` for production settings](https://pypi.org/project/psycopg2-binary/). If you are using BuildingMOTIF as a dependency in another project, make sure to include the `postgres` feature; for example, to add BuildingMOTIF to a [Poetry-based](https://python-poetry.org) project, use `poetry add BuildingMOTIF[postgres]`.

## Continuous Integration

The CI process for developers' local clones and the remote repository should be the same for reproduceability, i.e. the commands in the following files should be the same (with *slight* differences).

- [.pre-commit-config.yaml](https://github.com/NREL/BuildingMOTIF/blob/develop/.pre-commit-config.yaml)
- [ci.yml](https://github.com/NREL/BuildingMOTIF/tree/develop/.github/workflows/ci.yml)

### Local

Local CI is done automatically when comitting with `.pre-commit-config.yaml`, which runs *static* tests against staged files and generates fixes as possible. If the pre-commit checks fail the generated fixes can be inspected and staged as desired before attempting to commit again.


The command below will test files and generate fixes to formatting errors in files (running without `-a` will only fix staged files) without generating a commit upon successful completion.
```
pre-commit run -a
```

Pre-commit commands can be run individually with the following commands. Configuration of `isort`, `black`, and `mypy` are done in [pyproject.toml](https://github.com/NREL/BuildingMOTIF/blob/develop/pyproject.toml) and configuration of `flake8` is done in [.flake8](https://github.com/NREL/BuildingMOTIF/blob/develop/.flake8).
```
poetry run isort .
poetry run black .
poetry run flake8 buildingmotif
poetry run mypy --install-types --non-interactive --ignore-missing-imports
```

The above does not include *dynamic* testing (unit and integration), which can be run manually with the following command. To run tests with DEBUG prints add the `-o log_cli=true` argument to the command
```
poetry run pytest
```

### Remote

Remote CI is done with a GitHub Action from the `ci.yml` workflow.

## Documenting
Documentation can be built locally with the following commands, which will make the HTML files in the `docs/build/html/` directory.

```
poetry run jupyter-book config sphinx ./docs/
poetry run sphinx-build ./docs ./docs/_build/html -b html
```

## Building and Publishing
```
# build and publish test
poetry publish --build --dry-run

# build and publish
poetry publish --build
```

## Web App

1. [Download Node.js](https://nodejs.org/en/download/)
2. [Install Angular](https://angular.io/guide/setup-local)
3. See [buildingmotif-app/README.md](https://github.com/NREL/BuildingMOTIF/blob/main/buildingmotif-app/README.md)


## Running on Docker
1. Ensure `.env` contains the correct database information.

2. Up containers with docker-compose.
    ```
    docker-compose up --build
    ```
3. The api can now be reached at http://localhost:5000 and the app can be reached but http://localhost:4200.