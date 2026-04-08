import os
import tempfile

import pytest

from buildingmotif import BuildingMOTIF
from buildingmotif.shacl_backends import shacl_backend_available


@pytest.fixture
def clean_building_motif():
    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        temp_db_path = os.path.join(tempdir, "temp.db")
        uri = f"sqlite:///{temp_db_path}"
        building_motif = BuildingMOTIF(uri)
        # add tables to db
        building_motif.setup_tables()

        yield building_motif

        building_motif.session.commit()
        building_motif.close()
        BuildingMOTIF.clean()


@pytest.fixture
def clean_building_motif_topquadrant():
    if not shacl_backend_available("topquadrant"):
        pytest.skip("TopQuadrant SHACL engine is not installed")
    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        temp_db_path = os.path.join(tempdir, "temp.db")
        uri = f"sqlite:///{temp_db_path}"
        building_motif = BuildingMOTIF(uri, shacl_engine="topquadrant")
        # add tables to db
        building_motif.setup_tables()

        yield building_motif

        building_motif.session.commit()
        building_motif.close()
        BuildingMOTIF.clean()
