import pathlib
from typing import Any, Dict, Tuple

import pytest
import yaml
from rdflib import Graph, Namespace, URIRef

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.namespaces import RDF, S223, bind_prefixes

libraries = [
    "libraries/ashrae/223p/nrel-templates",
]

# these templates require extra information to be properly 'filled' by
# BuildingMOTIF, so we can skip them. They are all used as dependencies
# in other templates.
to_skip = {
    # the final folder name in the path is the library name
    "nrel-templates": [
        "differential-sensor",
        "sensor",
        "duct",
        "pipe",
        "junction",
        "air-inlet-cp",
        "air-outlet-cp",
        "water-inlet-cp",
        "water-outlet-cp",
    ],
}


def _cheap_template_names(library_path: str):
    """Return sorted list of template names from YAML keys only (no TTL infer for 223p).
    No DB or BuildingMOTIF setup required."""
    path = pathlib.Path(library_path)
    lib_short = path.name
    names = []
    for f in path.rglob("*.yml"):
        contents = yaml.safe_load(open(f))
        if contents:
            names.extend(contents.keys())
    skip = to_skip.get(lib_short, [])
    return sorted(n for n in names if n not in skip)


def _setup_building_motif_s223() -> Tuple[BuildingMOTIF, Library]:
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    bm = BuildingMOTIF("sqlite://", shacl_engine="pyshifty")
    bm.setup_tables()
    s223 = Library.from_ontology(
        "libraries/ashrae/223p/ontology/223p.ttl",
        run_shacl_inference=False,
    )
    bm.session.commit()
    BuildingMOTIF.clean()
    return bm, s223


def plug_223_connection_points(g: Graph):
    """
    223P models won't validate if they have unconnected connection points.
    This function creates a basic s223:Equipment for each unconnected connection point
    and connects them to the connection point.
    """
    query = """
    PREFIX s223: <http://data.ashrae.org/standard223#>
    SELECT ?cp WHERE {
        { ?cp rdf:type s223:OutletConnectionPoint }
        UNION
        { ?cp rdf:type s223:InletConnectionPoint }
        UNION
        { ?cp rdf:type s223:BidirectionalConnectionPoint }
        FILTER NOT EXISTS {
            ?cp s223:cnx ?x
        }
        FILTER NOT EXISTS {
            ?y s223:hasConnectionPoint ?x
        }
    }"""
    for row in g.query(query):
        cp = row[0]
        e = URIRef(f"urn:__plug__/{str(cp)[-8:]}")
        g.add((cp, S223.cnx, e))
        g.add((e, RDF.type, S223.Connectable))


@pytest.fixture(scope="session")
def s223_setup() -> Tuple[BuildingMOTIF, Library, Dict[Tuple[str, str], Any]]:
    """Session-scoped fixture: loads 223p + test libraries once, builds template lookup."""
    bm, s223 = _setup_building_motif_s223()
    BuildingMOTIF.instance = bm
    template_map: Dict[Tuple[str, str], Any] = {}
    for lib_name in libraries:
        lib = Library.from_directory(
            lib_name,
            run_shacl_inference=False,
            infer_templates=False,
        )
        for t in lib.get_templates():
            template_map[(lib_name, t.name)] = t
    BuildingMOTIF.clean()
    return bm, s223, template_map


def test_223p_template(s223_setup, library_name, template_name):
    bm, s223, template_map = s223_setup
    BuildingMOTIF.instance = bm
    template = template_map[(library_name, template_name)]
    try:
        MODEL = Namespace("urn:ex/")
        m = Model.create(MODEL)
        _, g = template.inline_dependencies().fill(MODEL, include_optional=False)
        assert isinstance(g, Graph), "was not a graph"
        bind_prefixes(g)
        plug_223_connection_points(g)
        m.add_graph(g)
        ctx = m.validate([s223.get_shape_collection()], error_on_missing_imports=False)
    except Exception as e:
        bm.session.rollback()
        raise e
    assert ctx.valid, ctx.report_string


def pytest_generate_tests(metafunc):
    if "test_223p_template" == metafunc.function.__name__:
        params = []
        ids = []
        for lib_name in libraries:
            lib_short = pathlib.Path(lib_name).name
            for tmpl_name in _cheap_template_names(lib_name):
                params.append((lib_name, tmpl_name))
                ids.append(f"{lib_short}-{tmpl_name}")
        metafunc.parametrize("library_name,template_name", params, ids=ids)
