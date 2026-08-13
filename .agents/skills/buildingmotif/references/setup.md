# Setup, package provenance, and recovery

Use this reference only when BuildingMOTIF must be installed or configured, an import
fails, ontology loading fails, or the task needs persistence/import-resolution details.

## Contents

- [Check package provenance once](#check-package-provenance-once)
- [Recover deterministically](#recover-deterministically)
- [Install BuildingMOTIF](#install-buildingmotif)
- [Manage database lifecycle](#manage-database-lifecycle)
- [Understand OntoEnv and storage](#understand-ontoenv-and-storage)
- [Find builtin and repository-only libraries](#find-builtin-and-repository-only-libraries)
- [Load external ontologies](#load-external-ontologies)
- [Load Brick correctly](#load-brick-correctly)
- [Handle validation imports](#handle-validation-imports)

## Check package provenance once

Treat BuildingMOTIF as an installed Python package, even when the current directory happens
to be a BuildingMOTIF checkout:

```bash
python -c "import buildingmotif, sys; print(sys.executable); print(buildingmotif.__file__)"
```

If the import resolves to the intended environment, return to the user's input. Do not
inspect the checkout branch, `pyproject.toml`, or package tree unless the user is developing
BuildingMOTIF or the installed package lacks a required API.

## Recover deterministically

If the import fails, diagnose the environment once instead of trying variations from
changing working directories:

```bash
pwd
python --version
command -v python
command -v uv
```

Use Python 3.11 or 3.12. Create an isolated environment at an explicit absolute path outside
an ancestor uv workspace, address its interpreter explicitly, and verify it immediately:

```bash
scratch_dir="$(mktemp -d)"
uv venv --python 3.12 "$scratch_dir/.venv"
uv pip install --python "$scratch_dir/.venv/bin/python" \
  "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"
"$scratch_dir/.venv/bin/python" -c \
  "import buildingmotif, sys; print(sys.executable); print(buildingmotif.__file__)"
```

Pass absolute input, ontology, database, and output paths to the build script. Record those
paths in its configuration section. Do not use `uv init` below another project's workspace
for a one-off exploration, and do not assume a tool retained the previous command's working
directory.

## Install BuildingMOTIF

The PyPI release may lag the APIs documented by this skill. Install the moving integration
branch for current work, or pin a commit SHA for reproducibility:

```bash
# Project dependency
uv add "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"

# Include the optional Java-backed TopQuadrant engine
uv add "buildingmotif[topquadrant] @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"

# Existing virtual environment
uv pip install \
  "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"
```

`pyshifty` is a required dependency on this branch. Pin `@<commit-sha>` instead of the
branch name in CI or shared requirements.

## Manage database lifecycle

Missing SQL tables are created automatically. Use a context manager for persistent SQLite
or PostgreSQL databases so SQL metadata commits on success and the singleton is reset:

```python
from buildingmotif import BuildingMOTIF

with BuildingMOTIF("sqlite:///buildingmotif.db") as bm:
    ...
```

Triples write through to the graph store immediately, but the SQL rows that identify them
become durable only when the session commits. Without a context manager, call
`bm.session.commit()` explicitly.

`shacl_engine` defaults to `pyshifty`. Passing another engine returns the legacy validation
context and makes algebraic repair libraries unavailable.

## Understand OntoEnv and storage

BuildingMOTIF uses OntoEnv to resolve `owl:imports`. Import fetching defaults to on through
`ontology_fetch_imports=True`. Models, shapes, templates, and resolved ontology graphs live
in Oxigraph; SQL stores their metadata.

Use:

- `ontology_offline=True` with `ontology_search_directories` for reproducible or air-gapped
  work;
- `ontology_cache_path` to reuse fetched ontologies across sessions;
- per-load `fetch_imports=False` when only the supplied ontology graph is required.

Read `ontology_imports.md` for the complete resolution model and strictness controls.

## Find builtin and repository-only libraries

These paths are packaged with BuildingMOTIF and resolve without a checkout:

| Builtin path | Contents |
|---|---|
| `brick/Brick.ttl` | Brick ontology and decompiled class templates |
| `constraints/constraints.ttl` | BuildingMOTIF constraint shapes |
| `bacnet/brick.yml` | BACnet-to-Brick templates |

Sample libraries such as `ashrae/guideline36`, `chiller-plant`, `pointlist-test`, 223P
templates, and example buildings remain repository-only. Clone the repository and load the
specific directory, use a `git:` entry in `libraries.yml`, or author the required templates
locally. See `templates.md`.

## Load external ontologies

OntoEnv normally resolves imported ontologies automatically. Load a specific file directly
when the task requires a pinned version, offline operation, or direct vocabulary inspection:

| Ontology | Source |
|---|---|
| Brick nightly | <https://github.com/BrickSchema/Brick/releases/tag/nightly> |
| 223P | <https://open223.info/223p.ttl> |
| WaTr | <https://watermetadata.org/water.ttl> |
| QUDT | Canonical namespace IRIs such as <http://qudt.org/vocab/unit/> |

Load a base ontology before a library whose templates depend upon its class templates.

## Load Brick correctly

Load the builtin Brick ontology before dependent libraries and disable SHACL inference so
class templates are decompiled:

```python
from buildingmotif.dataclasses import Library

brick = Library.from_ontology("brick/Brick.ttl", run_shacl_inference=False)
```

Do not substitute `Brick-full.ttl`. A `TemplateNotFound` naming a Brick class while loading
a dependent library usually means Brick was not loaded first.

## Handle validation imports

Self-contained shape graphs validate directly. For shape libraries with imports, OntoEnv
normally supplies the closure. If resolution fails, use a cached/local ontology, add its
directory through `ontology_search_directories`, restore network access, or deliberately
validate the partial graph with `error_on_missing_imports=False` and report that limitation.
Do not treat a clean partial-graph result as proof that the complete imported requirements
conform.
