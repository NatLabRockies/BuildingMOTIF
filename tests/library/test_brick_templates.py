from typing import Tuple

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


def setup_building_motif_brick() -> Tuple[BuildingMOTIF, Library]:
    """
    Setup the building motif and load the Brick ontology and all its dependencies.
    This instance is provided to the test_brick_template function and wipes all state beyond
    this initial setup to provide each test with a clean environment.
    """
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    bm = BuildingMOTIF("sqlite://", shacl_engine="topquadrant")
    bm.setup_tables()
    brick = Library.load(
        ontology_graph="libraries/brick/Brick.ttl", run_shacl_inference=False
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
    ]
    for dep in dependency_graphs:
        Library.load(
            ontology_graph=dep, infer_templates=False, run_shacl_inference=False
        )
    bm.session.commit()
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    return bm, brick


def test_brick_template(bm, brick, library, template):
    BuildingMOTIF.instance = bm
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
    # set the module to this file; this helps the monkeypatch determine which BuildingMOTIF instance to use
    bm, brick = setup_building_motif_brick()
    BuildingMOTIF.instance = bm
    if "test_brick_template" == metafunc.function.__name__:
        params = []
        ids = []
        for library_name in libraries:
            library = Library.load(directory=library_name, run_shacl_inference=False)
            templates = sorted(library.get_templates(), key=lambda t: t.name)
            params.extend([(bm, brick, library, template) for template in templates])
            ids.extend([f"{library.name}-{template.name}" for template in templates])
        metafunc.parametrize("bm,brick,library,template", params, ids=ids)
    BuildingMOTIF.clean()
