import sqlite3

import pytest
from rdflib import URIRef

from buildingmotif.dataclasses import Library, Model
from buildingmotif.dataclasses.compiled_model import CompiledModel


def test_compiled_model_validation(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    brick = Library.load(
        ontology_graph="tests/unit/fixtures/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.load(
        ontology_graph="tests/unit/fixtures/compilation/shapes.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([shape_collection, brick])

    assert isinstance(
        compiled_model, CompiledModel
    ), "Compiled model is not an instance of CompiledModel"
    assert compiled_model.model, "Model is not set in CompiledModel"

    validation_context = compiled_model.validate()
    assert validation_context is not None
    assert not validation_context.valid


def test_compiled_model_compilation(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/s223_model.ttl")
    s223 = Library.load(
        ontology_graph="libraries/ashrae/223p/ontology/223p.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([s223])

    # check that pt1:DumbSwitch has a connectedTo relationship to pt2:Luminaire
    res = compiled_model.graph.query(
        """ASK {
        <http://data.ashrae.org/standard223/1.0/data/patterns-scenario3#ElectricBreaker_1> <http://data.ashrae.org/standard223#connectedTo> <http://data.ashrae.org/standard223/1.0/data/patterns-scenario3#Luminaire> .
    }"""
    )
    compiled_model.graph.serialize("/tmp/compiled_model.ttl", format="turtle")
    assert bool(
        res
    ), "DumbSwitch is not connectedTo Luminaire, so s223 inference did not run to completion"


def test_defining_shape_collection(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    shape_collection = Library.load(
        ontology_graph="tests/unit/fixtures/compilation/shapes.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([shape_collection])

    shape_uri = URIRef("urn:shape1/vav_shape")
    sc = compiled_model.defining_shape_collection(shape_uri)
    assert sc is not None
    assert (
        sc.id == shape_collection.id
    ), "Defining shape collection for urn:shape1/vav_shape is not the same as the one that was compiled"

    shape_uri = URIRef("urn:shape1/does_not_exist")
    sc = compiled_model.defining_shape_collection(shape_uri)
    assert (
        sc is None
    ), "Defining shape collection for urn:shape1/does_not_exist should be None"


def test_shape_to_table(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    brick = Library.load(
        ontology_graph="https://brickschema.org/schema/1.4/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.load(
        ontology_graph="tests/unit/fixtures/compilation/shapes.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([shape_collection, brick])

    conn = sqlite3.connect(":memory:")

    with pytest.raises(ValueError):
        shape_uri = URIRef("urn:shape1/does_not_exist")
        compiled_model.shape_to_table(shape_uri, "does_not_exist", conn)

    shape_uri = URIRef("urn:shape1/vav_shape")
    compiled_model.shape_to_table(shape_uri, "vav", conn)
    rows = conn.execute("SELECT target, hasAirFlowSensor FROM vav").fetchall()
    assert len(rows) == 2
    assert ("urn:model1/vav1", "urn:model1/afs1") in rows
    assert ("urn:model1/vav2", "urn:model1/afs2") in rows


def test_shape_to_df(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    brick = Library.load(
        ontology_graph="https://brickschema.org/schema/1.4/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.load(
        ontology_graph="tests/unit/fixtures/compilation/shapes.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([shape_collection, brick])

    with pytest.raises(ValueError):
        shape_uri = URIRef("urn:shape1/does_not_exist")
        compiled_model.shape_to_df(shape_uri)

    shape_uri = URIRef("urn:shape1/vav_shape")
    df = compiled_model.shape_to_df(shape_uri)
    assert df is not None
    assert set(df.columns) == {"target", "hasAirFlowSensor"}
    assert len(df) == 2
    assert (
        df[df["target"] == "urn:model1/vav1"]["hasAirFlowSensor"].values[0]
        == "urn:model1/afs1"
    )
    assert (
        df[df["target"] == "urn:model1/vav2"]["hasAirFlowSensor"].values[0]
        == "urn:model1/afs2"
    )
