import sqlite3
from types import SimpleNamespace

import pytest
from rdflib import Graph, URIRef

from buildingmotif.dataclasses import Library, Model, ValidationContext
from buildingmotif.dataclasses.compiled_model import CompiledModel
from buildingmotif.namespaces import A, SH


def test_validate(clean_building_motif_topquadrant):
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


def test_shape_to_table_empty_result_preserves_columns(clean_building_motif):
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <urn:ex/> .
        ex:shape a sh:NodeShape ;
            sh:targetClass ex:Missing ;
            sh:property [
                sh:path ex:hasThing ;
                sh:class ex:Thing ;
                sh:name "thing"
            ] .
        """,
        format="turtle",
    )
    shape_collection = Library.load(ontology_graph=shape_graph).get_shape_collection()
    model = Model.create("urn:model/")
    compiled_model = model.compile([shape_collection])

    df = compiled_model.shape_to_df(URIRef("urn:ex/shape"))
    assert set(df.columns) == {"target", "thing"}
    assert df.empty

    conn = sqlite3.connect(":memory:")
    compiled_model.shape_to_table(URIRef("urn:ex/shape"), "empty_shape", conn)
    assert conn.execute("SELECT target, thing FROM empty_shape").fetchall() == []


def test_pyshifty_validate_uses_algebraic_context_for_sparql_ask_validator(
    clean_building_motif, monkeypatch
):
    model = Model.create("urn:model/")
    compiled_model = CompiledModel(model, [], Graph(), shacl_engine="pyshifty")
    data_graph = Graph()
    shape_graph = Graph()
    shape_graph.add((URIRef("urn:validator"), A, SH.SPARQLAskValidator))
    report_graph = Graph()
    calls = []

    class FakePyshiftyBackend:
        def validation_graphs(self, compiled_graph, shape_collections, **kwargs):
            calls.append(("pyshifty", compiled_graph, shape_collections, kwargs))
            return SimpleNamespace(
                data_graph=data_graph,
                shape_graph=shape_graph,
                context_graph=shape_graph,
            )

    def fake_get_shacl_backend(engine):
        assert engine == "pyshifty"
        return FakePyshiftyBackend()

    def fake_from_compiled(
        shape_collections, shapes, data, model_arg, libraries=None
    ):
        calls.append(("algebraic", shape_collections, shapes, data, model_arg, libraries))
        return report_graph

    monkeypatch.setattr(
        "buildingmotif.dataclasses.compiled_model.get_shacl_backend",
        fake_get_shacl_backend,
    )
    monkeypatch.setattr(
        "buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext.from_compiled",
        fake_from_compiled,
    )

    context = compiled_model.validate()

    assert context is report_graph
    assert calls[0][0] == "pyshifty"
    assert calls[1] == ("algebraic", [], shape_graph, data_graph, model, None)


def test_repair_libraries_warns_and_uses_legacy_context_for_non_pyshifty(
    clean_building_motif, monkeypatch
):
    model = Model.create("urn:model/")
    compiled_model = CompiledModel(model, [], Graph(), shacl_engine="pyshacl")
    report_graph = Graph()
    calls = []

    class FakePyshaclBackend:
        def validate_compiled_model(self, compiled_graph, shape_collections, **kwargs):
            calls.append((compiled_graph, shape_collections, kwargs))
            return (True, report_graph, "ok"), Graph()

    monkeypatch.setattr(
        "buildingmotif.dataclasses.compiled_model.get_shacl_backend",
        lambda engine: FakePyshaclBackend(),
    )

    with pytest.warns(UserWarning, match="repair_libraries is only used"):
        context = compiled_model.validate(repair_libraries=[])

    assert isinstance(context, ValidationContext)
    assert context.valid
    assert context.report is report_graph
    assert len(calls) == 1


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
