from typing import Tuple

from rdflib import Graph, Namespace, URIRef

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.dataclasses.algebraic_validation import AlgebraicValidationContext
from buildingmotif.namespaces import RDF, S223, bind_prefixes
from buildingmotif.shacl import ShiftyBackend

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


def setup_building_motif_s223() -> Tuple[BuildingMOTIF, Library]:
    BuildingMOTIF.clean()  # clean the singleton, but keep the instance
    bm = BuildingMOTIF("sqlite://", shacl_engine="shifty")
    bm.setup_tables()
    s223 = Library.load(
        ontology_graph="libraries/ashrae/223p/ontology/223p.ttl",
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


def test_223p_template(bm, s223, library, template, resolved_shape_graph):
    # set the module to this file; this helps the monkeypatch determine which BuildingMOTIF instance to use
    BuildingMOTIF.instance = bm
    try:
        MODEL = Namespace("urn:ex/")
        m = Model.create(MODEL)
        _, g = template.inline_dependencies().fill(MODEL, include_optional=False)
        assert isinstance(g, Graph), "was not a graph"
        bind_prefixes(g)
        plug_223_connection_points(g)
        m.add_graph(g)
        sc = s223.get_shape_collection()
        backend = ShiftyBackend()
        compiled_graph = backend.compile_model_graph(m.graph, [sc])
        ctx = AlgebraicValidationContext.from_compiled([sc], resolved_shape_graph, compiled_graph, m)
    except Exception as e:
        bm.session.rollback()
        raise e
    assert ctx.valid, ctx.report_string


def pytest_generate_tests(metafunc):
    # setup building motif
    bm, s223 = setup_building_motif_s223()
    BuildingMOTIF.instance = bm
    if "test_223p_template" == metafunc.function.__name__:
        resolved_shape_graph = s223.get_shape_collection().resolve_imports(
            error_on_missing_imports=False
        ).graph
        params = []
        ids = []
        for library_name in libraries:
            library = Library.load(
                directory=library_name,
                run_shacl_inference=False,
                infer_templates=False,
            )
            templates = sorted(library.get_templates(), key=lambda t: t.name)
            params.extend(
                [(bm, s223, library, template, resolved_shape_graph) for template in templates]
            )

        # remove all templates in 'to skip'
        params = [p for p in params if p[3].name not in to_skip[p[2].name]]
        # library name - template name
        ids = [f"{p[2].name}-{p[3].name}" for p in params]
        metafunc.parametrize("bm,s223,library,template,resolved_shape_graph", params, ids=ids)
    BuildingMOTIF.clean()
