from pathlib import Path
from typing import Optional

import pytest
from rdflib import RDF, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import FOAF

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library
from tests.unit.conftest import MockLibrary


def test_create(clean_building_motif):
    lib = Library.create("my_library")

    assert lib.name == "my_library"
    assert isinstance(lib.id, int)

    also_lib = Library.load(lib.id)

    assert also_lib.name == "my_library"
    assert also_lib.id == lib.id


def test_update_name(clean_building_motif):
    lib = Library.create("my_library")

    assert lib.name == "my_library"

    lib.name = "a_new_name"
    assert lib.name == "a_new_name"


def test_update_id(clean_building_motif):
    lib = Library.create("my_library")

    with pytest.raises(AttributeError):
        lib.id = 1


def test_get_templates(clean_building_motif):
    lib = Library.create("my_library")
    t1 = lib.create_template("my_template")
    t2 = lib.create_template("your_template")

    results = lib.get_templates()
    assert len(results) == 2
    assert [r.id for r in results] == [t1.id, t2.id]


def test_get_template_by_name_is_scoped_to_library(clean_building_motif):
    lib = Library.create("my_library")
    other_lib = Library.create("your_library")
    templ = lib.create_template("shared_template")
    other_templ = other_lib.create_template("shared_template")

    assert lib.get_template_by_name("shared_template").id == templ.id
    assert other_lib.get_template_by_name("shared_template").id == other_templ.id


def test_get_shape_collection(clean_building_motif):
    lib = Library.create("my_library")
    shape_collection = lib.get_shape_collection()
    shape_collection.graph.add(
        (URIRef("http://example.org/alex"), RDF.type, FOAF.Person)
    )

    assert lib.get_shape_collection() == shape_collection
    assert isomorphic(
        shape_collection.load(shape_collection.id).graph, shape_collection.graph
    )


def test_load_library_from_ontology(bm: BuildingMOTIF):
    lib = Library.load(ontology_graph="tests/unit/fixtures/Brick1.3rc1-equip-only.ttl")
    assert lib is not None
    assert len(lib.get_templates()) == 5
    # spot check a certain template
    templ = lib.get_template_by_name("https://brickschema.org/schema/Brick#AHU")
    assert templ is not None
    assert templ.parameters == {"name"}
    # check that Brick was loaded as a shape collection
    shapeg = lib.get_shape_collection()
    assert shapeg is not None
    assert len(shapeg.graph) > 1


def test_load_library_from_ontology_with_error(bm: BuildingMOTIF):
    with pytest.raises(Exception):
        Library.load(ontology_graph="tests/unit/fixtures/bad_shape_template.ttl")


def test_load_shapes_with_directory_library(bm: BuildingMOTIF):
    lib = Library.load(directory="tests/unit/fixtures/library-shape-test")
    assert lib is not None
    assert len(lib.get_templates()) == 2


def test_load_library_from_directory(bm: BuildingMOTIF):
    lib = Library.load(directory="tests/unit/fixtures/templates")
    assert lib is not None
    assert len(lib.get_templates()) == 7
    # spot check a certain template
    templ = lib.get_template_by_name("zone")
    assert templ is not None
    assert templ.parameters == {"name", "cav"}


def test_load_library_from_directory_with_shapes(bm: BuildingMOTIF):
    lib = Library.load(directory="tests/unit/fixtures/matching")
    assert lib is not None
    shapeg = lib.get_shape_collection()
    assert shapeg is not None
    assert len(shapeg.graph) > 1


def test_load_library_overwrite_graph(bm: BuildingMOTIF):
    g1 = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix : <urn:shape/> .
: a owl:Ontology .
:abc a sh:NodeShape, owl:Class .
    """
    g = Graph()
    g.parse(data=g1, format="ttl")
    lib = Library.load(ontology_graph=g)
    assert lib is not None
    assert len(lib.get_templates()) == 1

    g1 = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix : <urn:shape/> .
: a owl:Ontology .
:abc a sh:NodeShape, owl:Class .
:def a sh:NodeShape, owl:Class .
    """
    g = Graph()
    g.parse(data=g1, format="ttl")
    lib = Library.load(ontology_graph=g, overwrite=False)
    assert (
        len(lib.get_templates()) == 1
    ), "Library is overwritten when it shouldn't have been"

    lib = Library.load(ontology_graph=g, overwrite=True)
    bm.session.commit()
    assert lib is not None
    assert len(lib.get_templates()) == 2, "Library is overwritten improperly"


def test_load_library_overwrite_directory(bm: BuildingMOTIF):
    first = "tests/unit/fixtures/overwrite-test/1/A"
    second = "tests/unit/fixtures/overwrite-test/2/A"

    lib = Library.load(directory=first)
    assert lib is not None
    assert len(lib.get_templates()) == 1

    lib = Library.load(directory=second, overwrite=False)
    assert lib is not None
    assert len(lib.get_templates()) == 1, "Library overwritten when overwrite=False"

    lib = Library.load(directory=second, overwrite=True)
    bm.session.commit()
    assert lib is not None
    assert len(lib.get_templates()) == 2, "Library overwritten improperly"


def test_load_library_no_ipynb_checkpoints(bm: BuildingMOTIF):
    lib = Library.load(directory="tests/unit/fixtures/ipynb_checkpoint_test")
    assert lib is not None
    assert len(lib.get_templates()) == 1
    # if the checkpoint file was loaded, BuildingMOTIF would complain about
    # duplicate templates


def test_libraries(monkeypatch, bm: BuildingMOTIF, library: str):
    """
    Test that the libraries can be loaded and used.
    """
    original_load = Library.load

    def mock_load(
        db_id: Optional[int] = None,
        ontology_graph: Optional[str] = None,
        directory: Optional[str] = None,
        name: Optional[str] = None,
    ):
        if name is not None:
            try:
                db_library = bm.table_connection.get_db_library_by_name(name)
                return MockLibrary(_id=db_library.id, _name=db_library.name, _bm=bm)
            except Exception:
                return MockLibrary.create(name)
        else:
            original_load(db_id, ontology_graph, directory, name)

    monkeypatch.setattr(Library, "load", mock_load)
    # Brick dependencies always resolve for the test library
    MockLibrary.create("https://brickschema.org/schema/1.4/Brick")
    lib = Library._load_from_directory(Path(library), overwrite=False)
    assert lib is not None


def test_builtin_ontologies(bm: BuildingMOTIF, builtin_ontology):
    lib = Library.load(ontology_graph=builtin_ontology)
    assert lib is not None


def test_builtin_libraries(bm: BuildingMOTIF, builtin_library):
    lib = Library.load(directory=builtin_library)
    assert lib is not None
