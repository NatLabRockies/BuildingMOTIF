import pytest
from rdflib import SH, BNode, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model
from buildingmotif.dataclasses.library import Library
from buildingmotif.namespaces import BRICK, A
from buildingmotif.shape_builder import NodeShape, PropertyShape


@pytest.fixture
def constraints_library(bm: BuildingMOTIF):
    return Library.from_ontology("constraints/constraints.ttl")


# test #1
# - create empty model
# - create shape that looks for one equip
# - assert fails validation
# - add equip to model
# - assert passes validation
def test_node_shape(constraints_library: Library):
    model_namespace = Namespace("http://example.org/")
    shapes_namespace = Namespace("http://exampleshapes.org/")
    model = Model.create(name=model_namespace)

    # Make shape which looks for one brick:AHU
    ahu_shape = (
        NodeShape(shapes_namespace["ahu_shape"])
        .of_class(BRICK["AHU"], active=True)
        .count(exactly=1)
        .always_run()
    )
    ahu_shape.add_property(SH["targetNode"], BNode())
    model.get_manifest().add_graph(ahu_shape)

    # Validate shape against model, expected to fail
    validation_context = model.validate(
        [model.get_manifest(), constraints_library.get_shape_collection()]
    )
    assert validation_context.valid == False  # noqa

    # Add AHU to graph
    model.add_triples((model_namespace["AHU_1"], A, BRICK["AHU"]))

    # Validate shape against model, expected to pass
    validation_context = model.validate(
        [model.get_manifest(), constraints_library.get_shape_collection()]
    )
    assert validation_context.valid == True  # noqa


# Test 2
# - Create Model with AHU
# - Create AHU shape
# - Add PropertyShape and attach to AHU Shape
# - Validate and Fail
# - Add point
# - Validate and Pass
def test_property_shape(constraints_library: Library):
    model_namespace = Namespace("http://example.org/")
    shapes_namespace = Namespace("http://exampleshapes.org/")
    model = Model.create(name=model_namespace)

    # Add AHU to graph
    model.add_triples((model_namespace["AHU_1"], A, BRICK["AHU"]))

    # Make shape which looks for one brick:AHU with an OATS
    ahu_shape = (
        NodeShape(shapes_namespace["ahu_shape"])
        .of_class(BRICK["AHU"], active=True)
        .count(1)
        .has_property(
            PropertyShape()
            .has_path(BRICK["hasPoint"])
            .matches_class(BRICK["Outside_Air_Temperature_Sensor"], exactly=1)
        )
    )

    application_shape = (
        NodeShape(shapes_namespace["application_shape"])
        .of_class(BRICK["AHU"], active=True)
        .count(1)
        .always_run()
    )

    # Add shapes to graph
    model.get_manifest().add_graph(ahu_shape)
    model.get_manifest().add_graph(application_shape)

    # Validate shape against model, expected to fail
    validation_context = model.validate(
        [model.get_manifest(), constraints_library.get_shape_collection()]
    )
    assert validation_context.valid == False  # noqa

    model.add_triples(
        (model_namespace["OATS_1"], A, BRICK["Outside_Air_Temperature_Sensor"]),
        (model_namespace["AHU_1"], BRICK["hasPoint"], model_namespace["OATS_1"]),
    )

    # Validate shape against model, expected to pass
    validation_context = model.validate(
        [model.get_manifest(), constraints_library.get_shape_collection()]
    )
    assert validation_context.valid == True  # noqa
