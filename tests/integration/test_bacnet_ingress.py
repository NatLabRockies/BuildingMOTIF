import shlex
import subprocess

import pytest
from rdflib import Namespace

from buildingmotif.dataclasses import Model
from buildingmotif.ingresses import BACnetNetwork, BACnetToBrickIngress
from buildingmotif.namespaces import BACNET, BRICK, RDF


@pytest.mark.bacnet
def test_bacnet_ingress(bm):
    BLDG = Namespace("urn:building/")
    m = Model.create(BLDG, "test building for bacnet scan")
    bacnet = BACnetNetwork("172.24.0.2/24")
    tobrick = BACnetToBrickIngress(bm, bacnet)
    m.add_graph(tobrick.graph(BLDG))

    devices = list(m.graph.subjects(RDF["type"], BACNET["BACnetDevice"]))
    assert len(devices) == 1, f"Did not find exactly 1 device (found {len(devices)})"
    assert devices[0] == BLDG["599"]  # type: ignore

    objects = list(m.graph.subjects(RDF["type"], BRICK["Point"]))
    assert (
        len(objects) == 4
    ), f"Did not find exactly 4 points; found {len(objects)} instead"


@pytest.mark.bacnet
def test_bacnet_scan_cli(bm, tmp_path):
    BLDG = Namespace("urn:building/")
    m = Model.create(BLDG, "test building for bacnet scan")
    d = tmp_path / "scans"
    d.mkdir()
    output_file = d / "output.json"
    subprocess.run(
        shlex.split(f'buildingmotif scan -o "{str(output_file)}" -ip 172.24.0.2/24')
    )
    assert output_file.exists()
    bacnet = BACnetNetwork.load(output_file)
    tobrick = BACnetToBrickIngress(bm, bacnet)
    m.add_graph(tobrick.graph(BLDG))

    devices = list(m.graph.subjects(RDF["type"], BACNET["BACnetDevice"]))
    assert len(devices) == 1, f"Did not find exactly 1 device (found {len(devices)})"
    assert devices[0] == BLDG["599"]  # type: ignore

    objects = list(m.graph.subjects(RDF["type"], BRICK["Point"]))
    assert (
        len(objects) == 4
    ), f"Did not find exactly 4 points; found {len(objects)} instead"
