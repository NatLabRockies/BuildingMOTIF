import random

import pytest
import rdflib
from rdflib import RDF, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import FOAF

from buildingmotif.dataclasses.library import Library
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.namespaces import BMOTIF, BRICK, PARAM


def test_create_shape_collection(clean_building_motif):
    shape_collection = ShapeCollection.create()

    assert isinstance(shape_collection, ShapeCollection)
    assert isinstance(shape_collection.graph, rdflib.Graph)


def test_load_shape(clean_building_motif):
    shape_collection = ShapeCollection.create()
    shape_collection.graph.add(
        (URIRef("http://example.org/alex"), RDF.type, FOAF.Person)
    )

    result = ShapeCollection.load(shape_collection.id)
    assert result.id == shape_collection.id
    assert isomorphic(result.graph, shape_collection.graph)


def test_get_shapes_of_definition_type(clean_building_motif):
    shape_collection = ShapeCollection.create()
    shape_collection.graph.parse(
        data="""
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:model#> .
    @prefix bmotif: <https://nrel.gov/BuildingMOTIF#> .

    :shape1 a owl:Class, bmotif:Definition_Type ;
    .

    :shape2 a owl:Class, bmotif:Sequence_Of_Operations ;
    .

    :shape3 a owl:Class, bmotif:Analytics_Application ;
    .
    """
    )

    assert set(
        shape_collection.get_shapes_of_definition_type(BMOTIF.Definition_Type)
    ) == {
        URIRef("urn:model#shape1"),
        URIRef("urn:model#shape2"),
        URIRef("urn:model#shape3"),
    }

    assert shape_collection.get_shapes_of_definition_type(
        BMOTIF.Sequence_Of_Operations
    ) == [URIRef("urn:model#shape2")]

    assert shape_collection.get_shapes_of_definition_type(
        BMOTIF.Analytics_Application
    ) == [URIRef("urn:model#shape3")]


def test_get_shapes_of_domain(clean_building_motif):
    shape_collection = ShapeCollection.create()
    shape_collection.graph.parse(
        data="""
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:model#> .
    @prefix bmotif: <https://nrel.gov/BuildingMOTIF#> .

    :shape1 a bmotif:HVAC ;
    .

    :shape2 a bmotif:Lighting ;
    .

    :shape3 a bmotif:Electrical ;
    .
    """
    )

    assert shape_collection.get_shapes_of_domain(BMOTIF.HVAC) == [
        URIRef("urn:model#shape1")
    ]

    assert shape_collection.get_shapes_of_domain(BMOTIF.Lighting) == [
        URIRef("urn:model#shape2")
    ]

    assert set(shape_collection.get_shapes_of_domain(BMOTIF.Electrical)) == {
        URIRef("urn:model#shape3"),
        URIRef("urn:model#shape2"),
    }


def test_shape_collection_resolve_imports(clean_building_motif):
    Library.load(ontology_graph="tests/unit/fixtures/Brick.ttl")
    Library.load(ontology_graph="constraints/constraints.ttl")
    lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/import_test.ttl")
    sc = lib.get_shape_collection()
    new_sc = sc.resolve_imports()
    assert new_sc is not None
    assert len(new_sc.graph) > len(sc.graph)


def test_get_shapes_for_class(clean_building_motif):
    brick = Library.load(
        ontology_graph="tests/unit/fixtures/Brick1.3rc1-equip-only.ttl"
    )
    lib = Library.load(ontology_graph="tests/unit/fixtures/shapes/shape1.ttl")
    sc = lib.get_shape_collection()
    shapes = sc.get_shapes_about_class(BRICK["VAV"], [brick.get_shape_collection()])
    assert len(shapes) == 2
    shapes = sc.get_shapes_about_class(
        BRICK["Terminal_Unit"], [brick.get_shape_collection()]
    )
    assert len(shapes) == 1


# Define shape URIs and their expected query clauses for assertions
shape_to_query_fixtures = {
    "sensor": [
        "rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick/ref#BACnetReference> .",
        "<https://brickschema.org/schema/Brick#hasUnits> <http://qudt.org/vocab/unit/DEG_F> .",
    ],
    "vav": [
        "?target <https://brickschema.org/schema/Brick#hasPoint> ?sensor .",
        "?air_flow_sensor rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick#Air_Flow_Sensor> .",
        "OPTIONAL { ?target <https://brickschema.org/schema/Brick#hasPoint> ?dp_sensor .",
        "rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick/ref#BACnetReference> .",
    ],
    "multiple_targets": [
        "BIND(<https://brickschema.org/schema/Brick#ABC> AS ?target) .",
        "BIND(<https://brickschema.org/schema/Brick#DEF> AS ?target) .",
    ],
    "subjectTarget": [
        "?target <https://brickschema.org/schema/Brick#hasPoint> ?ignore ."
    ],
    "objectTarget": [
        "?ignore <https://brickschema.org/schema/Brick#hasPoint> ?target ."
    ],
    "multiple_classes": [
        "?target rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick#Sensor>",
        "?target rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick#VAV>",
        "?target <http://www.w3.org/2000/01/rdf-schema#label> ?label",
    ],
    "test_sh_or": [
        "?target <https://brickschema.org/schema/Brick#hasUnits> <http://qudt.org/vocab/unit/DEG_C>",
        "?target <https://brickschema.org/schema/Brick#hasUnits> <http://qudt.org/vocab/unit/DEG_F>",
    ],
    "optional_property": [
        "OPTIONAL { ?target <https://brickschema.org/schema/Brick#hasUnits> ?unit .",
        "?unit rdf:type/rdfs:subClassOf* <http://qudt.org/schema/qudt/Unit> .",
    ],
    "or_clauses_qualified_shape": [
        "?target rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick#VAV>",
        "?target <https://brickschema.org/schema/Brick#hasPart> ?part",
        "?part rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick#Sensor>",
        "?part <https://brickschema.org/schema/Brick/ref#hasExternalReference>",
        "rdf:type/rdfs:subClassOf* <https://brickschema.org/schema/Brick/ref#BACnetReference>",
        "?part <https://brickschema.org/schema/Brick#hasUnits> <http://qudt.org/vocab/unit/DEG_F>",
    ],
}


@pytest.mark.parametrize("shape_name, query_clauses", shape_to_query_fixtures.items())
def test_shape_to_query(clean_building_motif, shape_name, query_clauses):
    # fix seed for random variable names
    random.seed(0)

    g = Graph()

    lib = Library.load(ontology_graph="tests/unit/fixtures/shape_to_query/shapes.ttl")
    sc = lib.get_shape_collection()

    query = sc.shape_to_query(URIRef(f"urn:shapes_to_query/{shape_name}"))
    for clause in query_clauses:
        assert clause in query, query
    # Validate that the query executes correctly
    g.query(query)


def test_infer_templates_accepts_rdfs_class(clean_building_motif):
    graph = Graph()
    graph.parse(
        data="""
        @prefix : <urn:test#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

        :ontology a owl:Ontology .

        :MyShape a sh:NodeShape, rdfs:Class ;
            sh:targetClass :MyShape ;
            sh:property [
                sh:path :hasChild ;
                sh:minCount 1 ;
                sh:name "child" ;
                sh:class :ChildClass ;
            ] .

        :ChildShape a sh:NodeShape, rdfs:Class ;
            sh:targetClass :ChildClass ;
            sh:property [
                sh:path :label ;
                sh:minCount 1 ;
                sh:datatype xsd:string ;
            ] .

        :ChildClass a rdfs:Class .
        """,
        format="turtle",
    )

    lib = Library.load(
        ontology_graph=graph, infer_templates=True, run_shacl_inference=False
    )
    template = lib.get_template_by_name("urn:test#MyShape")
    assert (PARAM["name"], RDF.type, URIRef("urn:test#MyShape")) in template.body
