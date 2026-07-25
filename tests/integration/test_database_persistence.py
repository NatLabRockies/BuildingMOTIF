from rdflib import RDF, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import FOAF

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model

EXAMPLE_TRIPLE = (URIRef("http://example.org/alex"), RDF.type, FOAF.Person)


def test_database_persistence(tmpdir):
    # create bm
    db_path = f"sqlite:///{tmpdir}/db.db"

    bm = BuildingMOTIF(db_path)

    bm.setup_tables()

    # create objects
    library = Library.create("my_library")
    template = library.create_template("my_template")
    template.body.add(EXAMPLE_TRIPLE)
    shape = library.get_shape_collection()
    shape.graph.add(EXAMPLE_TRIPLE)
    model = Model.create(uri="https://example.com")
    model.graph.add(EXAMPLE_TRIPLE)

    # snapshot graph contents before closing (store-backed views become
    # inaccessible once the Oxigraph store is closed)
    template_body_snapshot = Graph() + template.body
    shape_graph_snapshot = Graph() + shape.graph
    model_graph_snapshot = Graph() + model.graph

    # close bm
    bm.session.commit()
    bm.close()
    BuildingMOTIF.clean()

    # reopen bm and ensure the object are preserved
    BuildingMOTIF(db_path)
    reloaded_library = Library.load(library.id)
    reloaded_template = reloaded_library.get_templates()[0]
    reloaded_model = Model.load(model.id)
    reloaded_shape = reloaded_library.get_shape_collection()

    assert reloaded_library == library
    assert reloaded_template == template
    assert isomorphic(reloaded_template.body, template_body_snapshot)
    assert reloaded_shape == shape
    assert isomorphic(reloaded_shape.graph, shape_graph_snapshot)
    assert reloaded_model == model
    assert isomorphic(reloaded_model.graph, model_graph_snapshot)
