"""Tests for BuildingMOTIF instance setup: table creation and the context
manager that ties the SQL session to a block."""

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model

BLDG = Namespace("urn:bldg/")


@pytest.fixture
def db_uri(tmp_path):
    """A file-backed SQLite URI, with the singleton reset afterwards."""
    yield f"sqlite:///{tmp_path}/bm.db"
    BuildingMOTIF.clean()


def _some_graph() -> Graph:
    return Graph().parse(
        data="@prefix brick: <https://brickschema.org/schema/Brick#> .\n"
        "<urn:bldg/vav1> a brick:VAV .",
        format="turtle",
    )


def test_file_backed_db_creates_tables_without_setup_tables(db_uri):
    """A file-backed database is usable straight out of the constructor.

    This used to raise a bare ``OperationalError: no such table`` from the
    driver, because tables were only created automatically for in-memory
    SQLite.
    """
    bm = BuildingMOTIF(db_uri)
    try:
        model = Model.create("urn:bldg/")
        assert model.id is not None
    finally:
        bm.close()


def test_setup_tables_is_idempotent(db_uri):
    """Calling setup_tables() explicitly still works and changes nothing --
    existing code and the CLI both do this."""
    bm = BuildingMOTIF(db_uri)
    try:
        Model.create("urn:bldg/")
        bm.setup_tables()
        bm.setup_tables()
        assert Model.load(name="urn:bldg/").id is not None
    finally:
        bm.close()


def test_create_tables_false_leaves_schema_alone(db_uri):
    """``create_tables=False`` is the opt-out for schema managed by Alembic."""
    bm = BuildingMOTIF(db_uri, create_tables=False)
    try:
        with pytest.raises(Exception):
            Model.create("urn:bldg/")
    finally:
        bm.close()


def test_context_manager_commits_and_persists(db_uri):
    """Leaving the block cleanly commits, so a later instance sees the work."""
    with BuildingMOTIF(db_uri):
        model = Model.create("urn:bldg/")
        model.add_graph(_some_graph())

    with BuildingMOTIF(db_uri):
        reloaded = Model.load(name="urn:bldg/")
        assert len(reloaded.graph) > 0
        assert (BLDG["vav1"], None, None) in reloaded.graph


def test_context_manager_returns_the_instance(db_uri):
    with BuildingMOTIF(db_uri) as bm:
        assert isinstance(bm, BuildingMOTIF)
        assert bm is BuildingMOTIF.instance  # type: ignore[attr-defined]


def test_context_manager_resets_singleton_on_exit(db_uri):
    """After the block the singleton is cleared, so the next constructor call
    builds a fresh instance rather than handing back the closed one."""
    with BuildingMOTIF(db_uri) as bm:
        first = bm
    assert not hasattr(BuildingMOTIF, "instance")

    with BuildingMOTIF(db_uri) as second:
        assert second is not first


def test_context_manager_rolls_back_on_exception(db_uri):
    """An exception inside the block rolls the SQL session back, so the model
    row never lands, and the exception still propagates."""
    with pytest.raises(RuntimeError, match="boom"):
        with BuildingMOTIF(db_uri):
            Model.create("urn:bldg/")
            raise RuntimeError("boom")

    with BuildingMOTIF(db_uri):
        from buildingmotif.database.errors import ModelNotFound

        with pytest.raises(ModelNotFound):
            Model.load(name="urn:bldg/")
