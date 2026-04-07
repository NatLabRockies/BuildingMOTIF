"""
Generates tests automatically
"""

import glob
from pathlib import Path

import pytest

from buildingmotif import BuildingMOTIF


@pytest.fixture
def bm():
    """
    BuildingMotif instance for tests involving dataclasses and API calls
    """
    BuildingMOTIF.clean()
    bm = BuildingMOTIF("sqlite://", shacl_engine="pyshifty")
    # add tables to db
    bm.setup_tables()

    yield bm
    bm.close()
    # clean up the singleton so that tables are re-created correctly later
    BuildingMOTIF.clean()


def pytest_generate_tests(metafunc):
    """
    Generates BuildingMOTIF tests for a variety of contexts
    """

    # validates that example files pass validation
    if "notebook" in metafunc.fixturenames:
        notebook_files = [
            Path(notebook)
            for notebook in glob.glob("notebooks/**/*.ipynb", recursive=True)
        ]

        metafunc.parametrize("notebook", notebook_files, ids=map(str, notebook_files))
