import pytest

from buildingmotif import BuildingMOTIF


@pytest.fixture(autouse=True)
def restore_singleton():
    """Drop the singleton after every test in this directory.

    The tests here deliberately manage ``BuildingMOTIF.instance`` by hand: the
    session-scoped setup fixtures build one instance with Brick (or 223P)
    already loaded, clear the singleton, and each test re-installs that
    instance with ``BuildingMOTIF.instance = bm``. Nothing put it back
    afterwards, so the last test to run in a process left a live singleton
    holding libraries named after the ontologies it had loaded -- e.g.
    ``https://brickschema.org/schema/1.4/Brick``.

    Any later test whose fixture calls ``BuildingMOTIF(...)`` then got that
    instance back rather than a fresh one, because construction is a no-op when
    the singleton exists. Sequentially the unit tests all run first so this was
    invisible; under ``pytest -n auto`` a worker can run a library test before a
    unit test, and ``tests/unit/dataclasses/test_library.py::test_libraries``
    would fail with ``UNIQUE constraint failed: library.name`` while creating
    its Brick stand-in.
    """
    yield
    BuildingMOTIF.clean()
