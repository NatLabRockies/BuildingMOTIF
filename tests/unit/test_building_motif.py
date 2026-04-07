import logging
import os
import tempfile

import pytest
from rdflib import OWL, RDF, Graph, URIRef

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model


def test_list_ontology_closure_for_library(bm):
    Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape2.ttl")

    closure = bm.list_ontology_closure(library=lib)

    assert closure == ["https://brickschema.org/schema/1.4/Brick"]


def test_list_ontology_closure_for_model_includes_model_and_manifest_imports(bm):
    extra_graph = Graph()
    extra_graph.parse(
        data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <urn:extra/> a owl:Ontology .
        """,
        format="ttl",
    )
    Library.load(ontology_graph=extra_graph, infer_templates=False)
    Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape2.ttl")

    model = Model.create("urn:model/")
    model.graph.add((URIRef("urn:model/"), OWL.imports, URIRef("urn:extra/")))
    model.update_manifest(lib.get_shape_collection())

    closure = bm.list_ontology_closure(model=model)

    assert set(closure) == {
        "https://brickschema.org/schema/1.4/Brick",
        "urn:extra/",
    }


def test_list_missing_ontologies_globally_and_by_scope(bm):
    missing_library_graph = Graph()
    missing_library_graph.parse(
        data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <urn:missing-library/> a owl:Ontology ;
            owl:imports <urn:missing/lib> .
        """,
        format="ttl",
    )
    lib = Library.load(ontology_graph=missing_library_graph, infer_templates=False)

    model = Model.create("urn:missing-model/")
    model.graph.add(
        (URIRef("urn:missing-model/"), OWL.imports, URIRef("urn:missing/model"))
    )

    manifest = model.get_manifest()
    manifest.graph.add((URIRef("urn:missing-manifest/"), RDF.type, OWL.Ontology))
    manifest.graph.add(
        (
            URIRef("urn:missing-manifest/"),
            OWL.imports,
            URIRef("urn:missing/manifest"),
        )
    )

    assert set(bm.list_missing_ontologies()) == {
        "urn:missing/lib",
        "urn:missing/model",
        "urn:missing/manifest",
    }
    assert bm.list_missing_ontologies(library=lib) == ["urn:missing/lib"]
    assert set(bm.list_missing_ontologies(model=model)) == {
        "urn:missing/model",
        "urn:missing/manifest",
    }


def test_list_ontology_closure_requires_scope(bm):
    with pytest.raises(ValueError, match="either 'library' or 'model'"):
        bm.list_ontology_closure()


def test_building_motif_does_not_install_root_handlers():
    root_logger = logging.getLogger()
    original_handler_ids = [id(handler) for handler in root_logger.handlers]

    BuildingMOTIF.clean()
    with tempfile.TemporaryDirectory() as tempdir:
        uri = f"sqlite:///{os.path.join(tempdir, 'temp.db')}"
        building_motif = BuildingMOTIF(uri)
        building_motif.setup_tables()

        assert [id(handler) for handler in root_logger.handlers] == original_handler_ids

        building_motif.close()
        BuildingMOTIF.clean()

    assert [id(handler) for handler in root_logger.handlers] == original_handler_ids
