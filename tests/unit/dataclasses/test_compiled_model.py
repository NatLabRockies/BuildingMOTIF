import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model, RepairConfig, ValidationContext
from buildingmotif.dataclasses.compiled_model import CompiledModel
from buildingmotif.namespaces import SH, A
from tests.unit.helpers import shapes_as_library


def test_validate(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    brick = Library.from_ontology(
        "tests/unit/fixtures/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.from_ontology(
        "tests/unit/fixtures/compilation/shapes.ttl"
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
    s223 = Library.from_ontology(
        "libraries/ashrae/223p/ontology/223p.ttl"
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


def test_add_graph_updates_compiled_model_graph(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    shape_collection = Library.from_ontology(
        "tests/unit/fixtures/compilation/shapes.ttl"
    ).get_shape_collection()
    compiled_model = model.compile([shape_collection])

    extra = Graph()
    triple = (
        URIRef("urn:model1/added"),
        RDFS.label,
        Literal("added to compiled model"),
    )
    extra.add(triple)

    assert triple not in compiled_model.graph
    compiled_model.add_graph(extra)
    assert triple in compiled_model.graph


def test_defining_shape_collection(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    shape_collection = Library.from_ontology(
        "tests/unit/fixtures/compilation/shapes.ttl"
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
    brick = Library.from_ontology(
        "https://brickschema.org/schema/1.4/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.from_ontology(
        "tests/unit/fixtures/compilation/shapes.ttl"
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
    shape_collection = Library.from_ontology(shape_graph).get_shape_collection()
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
        shape_collections, shapes, data, model_arg, libraries=None, repair_config=None
    ):
        calls.append(
            (
                "algebraic",
                shape_collections,
                shapes,
                data,
                model_arg,
                libraries,
                repair_config,
            )
        )
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
    assert calls[1] == ("algebraic", [], shape_graph, data_graph, model, None, None)


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

    with pytest.warns(UserWarning, match="only used by the 'pyshifty' engine"):
        context = compiled_model.validate(repair_libraries=[])

    assert isinstance(context, ValidationContext)
    assert context.valid
    assert context.report is report_graph
    assert len(calls) == 1


def test_repair_config_warns_for_non_pyshifty(clean_building_motif, monkeypatch):
    """repair_config is a pyshifty-only knob, so it warns on other engines even
    when no repair_libraries are passed."""
    model = Model.create("urn:model/")
    compiled_model = CompiledModel(model, [], Graph(), shacl_engine="pyshacl")
    report_graph = Graph()

    class FakePyshaclBackend:
        def validate_compiled_model(self, compiled_graph, shape_collections, **kwargs):
            return (True, report_graph, "ok"), Graph()

    monkeypatch.setattr(
        "buildingmotif.dataclasses.compiled_model.get_shacl_backend",
        lambda engine: FakePyshaclBackend(),
    )

    with pytest.warns(UserWarning, match="only used by the 'pyshifty' engine"):
        context = compiled_model.validate(repair_config=RepairConfig())

    assert isinstance(context, ValidationContext)


def test_shape_to_df(clean_building_motif_topquadrant):
    model = Model.from_file("tests/unit/fixtures/compilation/brick_model.ttl")
    brick = Library.from_ontology(
        "https://brickschema.org/schema/1.4/Brick.ttl"
    ).get_shape_collection()
    shape_collection = Library.from_ontology(
        "tests/unit/fixtures/compilation/shapes.ttl"
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


def test_validate_model_against_shapes_matches_the_engine(bm: BuildingMOTIF):
    """It used to build a ValidationContext unconditionally, so one
    CompiledModel returned different context types from its two validation
    methods (API-CLEANUP #12)."""
    from buildingmotif.dataclasses.algebraic_validation import (
        AlgebraicValidationContext,
    )

    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:S a sh:NodeShape ;
             sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    model = Model.create("urn:bldg/")
    model.add_graph(
        Graph().parse(
            data="@prefix ex: <http://ex/> .\n<urn:bldg/x> a ex:Foo .", format="turtle"
        )
    )
    model.manifest.add(shapes_as_library(shapes))

    for engine, expected in (
        ("pyshifty", AlgebraicValidationContext),
        ("pyshacl", ValidationContext),
    ):
        compiled = model.compile(
            model.manifest.shape_collections(), shacl_engine=engine
        )
        results = compiled.validate_model_against_shapes(
            [URIRef("http://ex/S")], URIRef("http://ex/Foo")
        )
        assert results, f"{engine} produced no results"
        for result in results.values():
            assert isinstance(
                result, expected
            ), f"{engine} returned {type(result).__name__}"
            # whichever it is, the common read surface works
            assert isinstance(result.conforms, bool)


def test_shape_map_reports_conformance_and_cardinality(clean_building_motif):
    """A shape map is an extraction *and* a verdict.

    A SPARQL projection of the same shape can only return the rows that matched.
    The shape map additionally says, per focus node, whether it conformed, how
    many qualifying values were wanted against how many were found, and which
    values it rejected -- so a focus that is missing a required value is still
    reported rather than silently dropping out of the result.
    """
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <urn:ex/> .
        ex:shape a sh:NodeShape ;
            sh:targetClass ex:Box ;
            sh:property [
                sh:path ex:hasThing ;
                sh:name "thing" ;
                sh:qualifiedValueShape [ sh:class ex:Thing ] ;
                sh:qualifiedMinCount 1
            ] ;
            sh:property [
                sh:path ex:hasWidget ;
                sh:name "widget" ;
                sh:qualifiedValueShape [ sh:class ex:Widget ] ;
                sh:qualifiedMinCount 1
            ] .
        """,
        format="turtle",
    )
    shape_collection = Library.from_ontology(shape_graph).get_shape_collection()
    model = Model.create("urn:model/")
    model.add_graph(
        Graph().parse(
            data="""
            @prefix ex: <urn:ex/> .
            @prefix m: <urn:model/> .
            m:good a ex:Box ; ex:hasThing m:t ; ex:hasWidget m:w .
            m:bad  a ex:Box ; ex:hasWidget m:w .
            m:t a ex:Thing .
            m:w a ex:Widget .
            """,
            format="turtle",
        )
    )
    compiled_model = model.compile([shape_collection])

    shape_map = compiled_model.shape_map(URIRef("urn:ex/shape"))
    assert not shape_map.conforms

    by_focus = {str(m.focus.to_rdflib()): m for m in shape_map}
    assert set(by_focus) == {"urn:model/good", "urn:model/bad"}
    assert by_focus["urn:model/good"].conforms
    assert not by_focus["urn:model/bad"].conforms

    # the failing focus still reports the slot it *did* fill...
    bad = {b.name: b for b in by_focus["urn:model/bad"].values()}
    assert bad["widget"].ok
    assert [v.to_rdflib() for v in bad["widget"].values] == [URIRef("urn:model/w")]
    # ...and describes the one it did not
    assert not bad["thing"].ok
    assert bad["thing"].missing == 1
    assert bad["thing"].values == []

    # the dataframe defaults to the conforming focus nodes -- the rows a SPARQL
    # projection of the same shape would return
    df = compiled_model.shape_to_df(URIRef("urn:ex/shape"))
    assert set(df.columns) == {"target", "thing", "widget"}
    assert set(df["target"]) == {"urn:model/good"}

    # ...and can be widened to the ones the shape selected but does not satisfy
    everything = compiled_model.shape_to_df(
        URIRef("urn:ex/shape"), include_nonconforming=True
    )
    assert set(everything["target"]) == {"urn:model/good", "urn:model/bad"}
    bad_row = everything[everything["target"] == "urn:model/bad"]
    assert bad_row["widget"].values[0] == "urn:model/w"
    assert pd.isna(bad_row["thing"].values[0])


def test_shape_to_df_names_a_single_slot_shape(clean_building_motif):
    """Column names survive a shape with exactly one property shape.

    pyshifty 0.4.2 resolves this qualified-value slot directly. The companion
    test covers the direct value-constraint plus cardinality spelling.
    """
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <urn:ex/> .
        ex:shape a sh:NodeShape ;
            sh:targetClass ex:Box ;
            sh:property [
                sh:path ex:hasThing ;
                sh:name "thing" ;
                sh:qualifiedValueShape [ sh:class ex:Thing ] ;
                sh:qualifiedMinCount 1
            ] .
        """,
        format="turtle",
    )
    shape_collection = Library.from_ontology(shape_graph).get_shape_collection()
    model = Model.create("urn:model/")
    model.add_graph(
        Graph().parse(
            data="""
            @prefix ex: <urn:ex/> .
            @prefix m: <urn:model/> .
            m:b a ex:Box ; ex:hasThing m:t .
            m:t a ex:Thing .
            """,
            format="turtle",
        )
    )
    compiled_model = model.compile([shape_collection])

    df = compiled_model.shape_to_df(URIRef("urn:ex/shape"))
    assert set(df.columns) == {"target", "thing"}
    assert df.loc[df["target"] == "urn:model/b", "thing"].values[0] == "urn:model/t"


def test_shape_to_df_preserves_a_single_class_cardinality_slot(clean_building_motif):
    """pyshifty 0.4.2 preserves a lone class-and-cardinality slot intact."""
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <urn:ex/> .
        ex:shape a sh:NodeShape ;
            sh:targetClass ex:Box ;
            sh:property [
                sh:path ex:hasThing ;
                sh:name "thing" ;
                sh:class ex:Thing ;
                sh:minCount 1
            ] .
        """,
        format="turtle",
    )
    shape_collection = Library.from_ontology(shape_graph).get_shape_collection()
    model = Model.create("urn:model/")
    model.add_graph(
        Graph().parse(
            data="""
            @prefix ex: <urn:ex/> .
            @prefix m: <urn:model/> .
            m:b a ex:Box ; ex:hasThing m:t .
            m:t a ex:Thing .
            """,
            format="turtle",
        )
    )
    compiled_model = model.compile([shape_collection])

    mapping = next(iter(compiled_model.shape_map(URIRef("urn:ex/shape"))))
    bindings = list(mapping.values())
    assert len(bindings) == 1
    assert bindings[0].name == "thing"
    assert [value.to_rdflib() for value in bindings[0].values] == [
        URIRef("urn:model/t")
    ]

    df = compiled_model.shape_to_df(URIRef("urn:ex/shape"))
    assert set(df.columns) == {"target", "thing"}
    assert df.loc[df["target"] == "urn:model/b", "thing"].values[0] == "urn:model/t"


def test_class_cardinality_slot_reports_rejected_values(clean_building_motif):
    """pyshifty 0.4.2 keeps rejected values out of an unfilled slot."""
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <urn:ex/> .
        ex:shape a sh:NodeShape ;
            sh:targetClass ex:Box ;
            sh:property [
                sh:path ex:hasThing ;
                sh:name "thing" ;
                sh:class ex:Thing ;
                sh:minCount 1
            ] .
        """,
        format="turtle",
    )
    shape_collection = Library.from_ontology(shape_graph).get_shape_collection()
    model = Model.create("urn:model/")
    model.add_graph(
        Graph().parse(
            data="""
            @prefix ex: <urn:ex/> .
            @prefix m: <urn:model/> .
            m:b a ex:Box ; ex:hasThing m:t .
            m:t a ex:Other .
            """,
            format="turtle",
        )
    )
    compiled_model = model.compile([shape_collection])

    mapping = next(iter(compiled_model.shape_map(URIRef("urn:ex/shape"))))
    bindings = list(mapping.values())
    assert len(bindings) == 1
    assert bindings[0].name == "thing"
    assert not bindings[0].ok
    assert bindings[0].values == []
    assert [value.to_rdflib() for value in bindings[0].rejected_values] == [
        URIRef("urn:model/t")
    ]

    df = compiled_model.shape_to_df(URIRef("urn:ex/shape"), include_nonconforming=True)
    assert set(df.columns) == {"target", "thing"}
    row = df[df["target"] == "urn:model/b"]
    assert len(row) == 1
    assert pd.isna(row["thing"].values[0])
