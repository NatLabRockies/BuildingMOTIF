import pathlib
from typing import Any, Dict, Tuple

import pytest
import rdflib
import yaml
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.namespaces import bind_prefixes

# all the Brick libraries to test
libraries = [
    "libraries/ashrae/guideline36",
    "libraries/pointlist-test",
    "libraries/chiller-plant",
]


def _cheap_template_names(library_path: str):
    """Return sorted list of template names from YAML keys and owl:Class∩sh:NodeShape
    shapes in TTL files. No DB or BuildingMOTIF setup required."""
    path = pathlib.Path(library_path)
    names: set = set()
    for f in path.rglob("*.yml"):
        contents = yaml.safe_load(open(f))
        if contents:
            names.update(contents.keys())
    for f in path.rglob("*.ttl"):
        g = rdflib.Graph()
        g.parse(str(f))
        classes = set(g.subjects(rdflib.RDF.type, rdflib.OWL.Class))
        shapes = set(g.subjects(rdflib.RDF.type, rdflib.SH.NodeShape))
        for c in classes & shapes:
            names.add(str(c))
    return sorted(names)


def _setup_building_motif_brick() -> Tuple[BuildingMOTIF, Library]:
    """
    Setup the building motif and load the Brick ontology and all its dependencies.
    This instance is provided to the test_brick_template function and wipes all state beyond
    this initial setup to provide each test with a clean environment.
    """
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    bm = BuildingMOTIF("sqlite://", shacl_engine="pyshifty")
    bm.setup_tables()
    brick = Library.from_ontology(
        "libraries/brick/Brick.ttl", run_shacl_inference=False
    )
    dependency_graphs = [
        "libraries/brick/imports/ref-schema.ttl",
        "libraries/qudt/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl",
        "libraries/qudt/VOCAB_QUDT-DIMENSION-VECTORS.ttl",
        "libraries/qudt/VOCAB_QUDT-UNITS-ALL.ttl",
        "libraries/qudt/SCHEMA-FACADE_QUDT.ttl",
        "libraries/qudt/SCHEMA_QUDT_NoOWL.ttl",
        "libraries/qudt/VOCAB_QUDT-PREFIXES.ttl",
        "libraries/qudt/SHACL-SCHEMA-SUPPLEMENT_QUDT.ttl",
        "libraries/qudt/VOCAB_QUDT-SYSTEM-OF-UNITS-ALL.ttl",
        "libraries/brick/imports/rec.ttl",
        "libraries/brick/imports/recimports.ttl",
        "libraries/brick/imports/brickpatches.ttl",
    ]
    for dep in dependency_graphs:
        Library.from_ontology(dep, infer_templates=False, run_shacl_inference=False)
    bm.session.commit()
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    return bm, brick


@pytest.fixture(scope="session")
def brick_setup() -> Tuple[BuildingMOTIF, Library, Dict[Tuple[str, str], Any]]:
    """Session-scoped fixture: loads Brick + test libraries once, builds template lookup."""
    bm, brick = _setup_building_motif_brick()
    BuildingMOTIF.instance = bm
    template_map: Dict[Tuple[str, str], Any] = {}
    for lib_name in libraries:
        lib = Library.from_directory(lib_name, run_shacl_inference=False)
        for t in lib.get_templates():
            template_map[(lib_name, t.name)] = t
    BuildingMOTIF.clean()
    return bm, brick, template_map


def test_brick_template(brick_setup, library_name, template_name):
    bm, brick, template_map = brick_setup
    BuildingMOTIF.instance = bm
    template = template_map[(library_name, template_name)]
    try:
        MODEL = Namespace("urn:ex/")
        m = Model.create(MODEL)
        _, g = template.inline_dependencies().fill(MODEL, include_optional=False)
        assert isinstance(g, Graph), "was not a graph"
        bind_prefixes(g)
        m.add_graph(g)
        ctx = m.validate(
            [brick.get_shape_collection()],
            error_on_missing_imports=False,
        )
    except Exception as e:
        bm.session.rollback()
        raise e
    assert ctx.valid, ctx.report_string


def pytest_generate_tests(metafunc):
    if "test_brick_template" == metafunc.function.__name__:
        params = []
        ids = []
        for lib_name in libraries:
            lib_short = pathlib.Path(lib_name).name
            for tmpl_name in _cheap_template_names(lib_name):
                params.append((lib_name, tmpl_name))
                ids.append(f"{lib_short}-{tmpl_name}")
        metafunc.parametrize("library_name,template_name", params, ids=ids)
