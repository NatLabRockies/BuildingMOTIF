import sys
from types import SimpleNamespace

import pytest
from rdflib import Graph, Literal, Namespace, URIRef

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model, ShapeCollection
from buildingmotif.namespaces import BRICK, SH, XSD, A
from buildingmotif.utils import (
    PARAM,
    _guarantee_unique_template_name,
    _param_name,
    _strip_param,
    get_parameters,
    get_template_parts_from_shape,
    graph_hash,
    replace_nodes,
    rewrite_shape_graph,
    shacl_inference,
    shacl_validate,
    skip_uri,
)

PREAMBLE = """@prefix bacnet: <http://data.ashrae.org/bacnet/2020#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix bsh: <https://brickschema.org/schema/BrickShape#> .
@prefix dcterms: <http://purl.org/dc/terms#> .
@prefix ifc: <https://brickschema.org/extension/ifc#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix qudtqk: <http://qudt.org/vocab/quantitykind/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sdo: <http://schema.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix tag: <https://brickschema.org/schema/BrickTag#> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix vcard: <http://www.w3.org/2006/vcard/ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix : <urn:model#> .
"""
MODEL = Namespace("urn:model#")


def test_get_template_parts_from_shape():
    shape_graph = Graph()
    shape_graph.parse(
        data=PREAMBLE
        + """
    :shape1 a owl:Class, sh:NodeShape ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:class brick:Temperature_Sensor ;
            sh:minCount 1 ;
        ] .
    """
    )
    body, deps = get_template_parts_from_shape(MODEL["shape1"], shape_graph)
    assert len(deps) == 0
    assert (PARAM["name"], A, MODEL["shape1"]) in body

    shape_graph = Graph()
    shape_graph.parse(
        data=PREAMBLE
        + """
    :shape1 a owl:Class, sh:NodeShape ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:node brick:Temperature_Sensor ;
            sh:minCount 1 ;
        ] .
    """
    )

    body, deps = get_template_parts_from_shape(MODEL["shape1"], shape_graph)
    assert len(deps) == 1
    assert deps[0]["template"] == str(BRICK.Temperature_Sensor)
    assert list(deps[0]["args"].keys()) == ["name"]
    assert (PARAM["name"], A, MODEL["shape1"]) in body
    # assert (PARAM['name'], BRICK.hasPoint,


def test_replace_nodes():
    g = Graph()
    g.parse(
        data=PREAMBLE
        + """
    :a :b :c .
    :d :e :f .
    """
    )
    replace_nodes(
        g,
        {
            MODEL["a"]: MODEL["a1"],
            MODEL["b"]: MODEL["b1"],
            MODEL["f"]: MODEL["f1"],
        },
    )

    assert (MODEL["a1"], MODEL["b1"], MODEL["c"]) in g
    assert (MODEL["d"], MODEL["e"], MODEL["f1"]) in g
    assert len(list(g.triples((None, None, None)))) == 2

    g = Graph()
    g.parse(
        data=PREAMBLE
        + """
    :a :ab :ac .
    """
    )
    replace_nodes(
        g,
        {
            MODEL["a"]: MODEL["a1"],
        },
    )

    assert (MODEL["a1"], MODEL["ab"], MODEL["ac"]) in g
    assert len(list(g.triples((None, None, None)))) == 1


def test_get_parameters():
    body = Graph()
    body.parse(
        data="""
    @prefix P: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    P:name a brick:VAV ;
        brick:hasPoint P:1, P:2, P:3, P:4 .
    """
    )
    assert get_parameters(body) == {"name", "1", "2", "3", "4"}


def test_inline_sh_nodes(shacl_engine):
    shape_g = Graph()
    shape_g.parse(
        data="""@prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix : <urn:ex/> .

    :shape1 a sh:NodeShape;
        sh:node :shape2, :shape3 .

    :shape2 a sh:NodeShape ;
        sh:property [
            sh:path :path1 ;
            sh:class :class1 ;
        ] ;
    .
    :shape3 a sh:NodeShape ;
        sh:class :class2 ;
        sh:property [
            sh:path :path1 ;
            sh:node :shape4 ;
        ] ;
    .

    :shape4 a sh:NodeShape ;
        sh:property [
            sh:path :path2 ;
            sh:minCount 1 ;
        ] ;
    .
    """
    )
    # should pass
    valid, _, report = shacl_validate(shape_g)
    assert valid, report

    shape1_cbd = shape_g.cbd(URIRef("urn:ex/shape1"))
    assert len(shape1_cbd) == 3

    shape_g = rewrite_shape_graph(shape_g)
    # should pass
    valid, _, report = shacl_validate(shape_g)
    assert valid, report

    shape1_cbd = shape_g.cbd(URIRef("urn:ex/shape1"))
    assert len(shape1_cbd) == 8


def test_inline_sh_and(bm: BuildingMOTIF, shacl_engine):
    bm.shacl_engine = shacl_engine
    sg = Graph()
    sg.parse(
        data=PREAMBLE
        + """
    :shape1 a sh:NodeShape, owl:Class ;
        sh:and ( :shape2 :shape3 :shape4 ) .
    :shape2 a sh:NodeShape ;
        sh:class brick:Class2 .
    :shape3 a sh:NodeShape ;
        sh:class brick:Class3 .
    :shape4 a sh:NodeShape ;
        sh:property [
            sh:path brick:relationship ;
            sh:class brick:Class4 ;
            sh:minCount 1 ;
        ] .
    """
    )

    data = Graph()
    data.parse(
        data=PREAMBLE
        + """
    :x a :shape1, brick:Class2 .
    """
    )
    model = Model.create(MODEL)
    model.add_graph(data)

    new_sg = rewrite_shape_graph(sg)

    sc = ShapeCollection.create()
    sc.add_graph(new_sg)

    ctx = model.validate([sc])
    assert not ctx.valid

    if shacl_engine == "pyshacl":
        assert (
            "Value class is not in classes (brick:Class2, brick:Class3)"
            in ctx.report_string
            or "Value class is not in classes (brick:Class3, brick:Class2)"
            in ctx.report_string
            or "Value class is not in classes (<https://brickschema.org/schema/Brick#Class3>, <https://brickschema.org/schema/Brick#Class2>)"
            in ctx.report_string
            or "Value class is not in classes (<https://brickschema.org/schema/Brick#Class2>, <https://brickschema.org/schema/Brick#Class3>)"
            in ctx.report_string
        ), ctx.report_string
        assert (
            "Less than 1 values on <urn:model#x>->brick:relationship"
            in ctx.report_string
            or "Less than 1 values on <urn:model#x>-><https://brickschema.org/schema/Brick#relationship>"
            in ctx.report_string
        )
    elif shacl_engine == "topquadrant":
        assert (None, SH.resultPath, BRICK.relationship) in ctx.report
        assert (
            None,
            SH.resultMessage,
            Literal("Property needs to have at least 1 value"),
        ) in ctx.report

        assert (
            None,
            SH.resultMessage,
            Literal("Value must be an instance of brick:Class3"),
        ) in ctx.report
        assert (None, SH.sourceShape, URIRef("urn:model#shape1")) in ctx.report


def test_inline_sh_node(bm: BuildingMOTIF, shacl_engine):
    bm.shacl_engine = shacl_engine
    sg = Graph()
    sg.parse(
        data=PREAMBLE
        + """
    :shape1 a sh:NodeShape, owl:Class ;
        sh:node :shape2, :shape3, :shape4 .
    :shape2 a sh:NodeShape ;
        sh:class brick:Class2 .
    :shape3 a sh:NodeShape ;
        sh:class brick:Class3 .
    :shape4 a sh:NodeShape ;
        sh:property [
            sh:path brick:relationship ;
            sh:class brick:Class4 ;
            sh:minCount 1 ;
        ] .
    """
    )

    data = Graph()
    data.parse(
        data=PREAMBLE
        + """
    :x a :shape1, brick:Class2 .
    """
    )
    model = Model.create(MODEL)
    model.add_graph(data)

    new_sg = rewrite_shape_graph(sg)

    sc = ShapeCollection.create()
    sc.add_graph(new_sg)

    ctx = model.validate([sc])
    assert not ctx.valid, ctx.report_string
    if shacl_engine == "pyshacl":
        assert (
            "Value class is not in classes (brick:Class2, brick:Class3)"
            in ctx.report_string
            or "Value class is not in classes (brick:Class3, brick:Class2)"
            in ctx.report_string
            or "Value class is not in classes (<https://brickschema.org/schema/Brick#Class3>, <https://brickschema.org/schema/Brick#Class2>)"
            in ctx.report_string
            or "Value class is not in classes (<https://brickschema.org/schema/Brick#Class2>, <https://brickschema.org/schema/Brick#Class3>)"
            in ctx.report_string
        )
        assert (
            "Less than 1 values on <urn:model#x>->brick:relationship"
            in ctx.report_string
            or "Less than 1 values on <urn:model#x>-><https://brickschema.org/schema/Brick#relationship>"
            in ctx.report_string
        )
    elif shacl_engine == "topquadrant":
        assert (None, SH.resultPath, BRICK.relationship) in ctx.report
        assert (
            None,
            SH.resultMessage,
            Literal("Property needs to have at least 1 value"),
        ) in ctx.report

        assert (
            None,
            SH.resultMessage,
            Literal("Value must be an instance of brick:Class3"),
        ) in ctx.report
        assert (None, SH.sourceShape, URIRef("urn:model#shape1")) in ctx.report


def test_param_name():
    good_p = PARAM["abc"]
    assert _param_name(good_p) == "abc"

    bad_p = BRICK["abc"]
    with pytest.raises(AssertionError):
        _param_name(bad_p)


def test_shacl_helpers_validate_engine_choice():
    with pytest.raises(ValueError, match="Unsupported SHACL engine"):
        shacl_validate(Graph(), engine="bad-engine")

    with pytest.raises(ValueError, match="Unsupported SHACL engine"):
        shacl_inference(Graph(), engine="bad-engine")


def test_building_motif_validates_shacl_engine():
    assert BuildingMOTIF("sqlite://").shacl_engine == "pyshifty"
    BuildingMOTIF.clean()

    assert (
        BuildingMOTIF("sqlite://", shacl_engine="pyshifty").shacl_engine == "pyshifty"
    )
    BuildingMOTIF.clean()

    assert BuildingMOTIF("sqlite://", shacl_engine="shifty").shacl_engine == "pyshifty"
    BuildingMOTIF.clean()

    with pytest.raises(ValueError, match="Unsupported SHACL engine"):
        BuildingMOTIF("sqlite://", shacl_engine="bad-engine")
    BuildingMOTIF.clean()

    bm = BuildingMOTIF("sqlite://")
    with pytest.raises(ValueError, match="Unsupported SHACL engine"):
        bm.shacl_engine = "bad-engine"
    BuildingMOTIF.clean()


def test_pyshifty_validate_dispatches_to_shifty_module(monkeypatch):
    data_graph = Graph()
    shape_graph = Graph()
    shape_graph.add((URIRef("urn:shape"), SH.targetClass, URIRef("urn:Class")))
    report_graph = Graph()
    calls = []

    def validate(*args, **kwargs):
        calls.append(("validate", args, kwargs))
        return True, report_graph, "ok"

    monkeypatch.setitem(
        sys.modules,
        "shifty",
        SimpleNamespace(validate=validate),
    )

    assert shacl_validate(data_graph, shape_graph, engine="pyshifty") == (
        True,
        report_graph,
        "ok",
    )
    # the shapes graph is handed to shifty as Turtle text (not the bare Graph)
    # so its embedded sh:sparql/sh:rule bodies can resolve sh:prefixes -- see
    # buildingmotif.shacl._shifty_shapes_input
    assert len(calls) == 1
    name, args, kwargs = calls[0]
    called_data, called_shapes = args
    assert name == "validate"
    assert called_data == data_graph
    assert isinstance(called_shapes, bytes)
    assert set(Graph().parse(data=called_shapes, format="turtle")) == set(shape_graph)
    assert kwargs == {"minimum_severity": "violation"}


def test_pyshifty_validate_omits_empty_shape_graph(monkeypatch):
    data_graph = Graph()
    empty_shape_graph = Graph()
    report_graph = Graph()
    calls = []

    def validate(*args, **kwargs):
        calls.append(("validate", args, kwargs))
        return True, report_graph, "ok"

    monkeypatch.setitem(
        sys.modules,
        "shifty",
        SimpleNamespace(validate=validate),
    )

    assert shacl_validate(data_graph, empty_shape_graph, engine="pyshifty") == (
        True,
        report_graph,
        "ok",
    )
    assert calls == [
        (
            "validate",
            (data_graph,),
            {"minimum_severity": "violation"},
        ),
    ]


def test_pyshifty_inference_removes_shape_graph(monkeypatch):
    data_triple = (URIRef("urn:data"), SH.path, URIRef("urn:value"))
    shape_triple = (URIRef("urn:shape"), SH.targetClass, URIRef("urn:Class"))
    data_graph = Graph()
    data_graph.add(data_triple)
    shape_graph = Graph()
    shape_graph.add(shape_triple)
    inferred_graph = data_graph + shape_graph

    def infer(*args):
        # the shapes graph is handed to shifty as Turtle text (not the bare
        # Graph) -- see buildingmotif.shacl._shifty_shapes_input
        called_data, called_shapes = args
        assert called_data == data_graph
        assert isinstance(called_shapes, bytes)
        assert set(Graph().parse(data=called_shapes, format="turtle")) == set(
            shape_graph
        )
        return SimpleNamespace(graph=lambda: inferred_graph)

    monkeypatch.setitem(sys.modules, "shifty", SimpleNamespace(infer=infer))

    closure = shacl_inference(data_graph, shape_graph, engine="pyshifty")
    assert data_triple in closure
    assert shape_triple not in closure


def test_pyshifty_inference_removes_redundant_is_point_of(monkeypatch):
    equipment = URIRef("urn:equipment")
    point = URIRef("urn:point")
    has_point_triple = (equipment, BRICK.hasPoint, point)
    inferred_inverse_triple = (point, BRICK.isPointOf, equipment)
    shape_triple = (URIRef("urn:shape"), SH.targetClass, URIRef("urn:Class"))
    data_graph = Graph()
    data_graph.add(has_point_triple)
    shape_graph = Graph()
    shape_graph.add(shape_triple)
    inferred_graph = data_graph + shape_graph
    inferred_graph.add(inferred_inverse_triple)

    def infer(*args):
        # the shapes graph is handed to shifty as Turtle text (not the bare
        # Graph) -- see buildingmotif.shacl._shifty_shapes_input
        called_data, called_shapes = args
        assert called_data == data_graph
        assert isinstance(called_shapes, bytes)
        assert set(Graph().parse(data=called_shapes, format="turtle")) == set(
            shape_graph
        )
        return SimpleNamespace(graph=lambda: inferred_graph)

    monkeypatch.setitem(sys.modules, "shifty", SimpleNamespace(infer=infer))

    closure = shacl_inference(data_graph, shape_graph, engine="pyshifty")
    assert has_point_triple in closure
    assert shape_triple not in closure
    assert inferred_inverse_triple not in closure


def test_skip_uri():
    assert skip_uri(XSD.integer)
    assert skip_uri(SH.NodeShape)
    assert not skip_uri(BRICK.Sensor)


def test_hash(bm: BuildingMOTIF):
    graph = Graph()
    graph.parse("tests/unit/fixtures/smallOffice_brick.ttl")

    graph.add((MODEL["a"], A, BRICK["AHU"]))

    model = Model.create(MODEL)
    model.add_graph(graph)
    before_hash = graph_hash(model.graph)

    assert graph_hash(model.graph) == before_hash, "Graph did not change but hash did"

    triple_to_add = (MODEL["b"], A, BRICK["Sensor"])
    model.graph.add(triple_to_add)

    after_hash = graph_hash(model.graph)
    assert before_hash != after_hash, "Graph changed, but hashes did not"

    model.graph.remove(triple_to_add)

    after_hash = graph_hash(model.graph)
    assert before_hash == after_hash, "Graph with same state resulted in different hash"


def test_strip_param():
    # if value is 'None', key should remain unchanged
    inputs = {
        "p123": None,
        "urn:___param___#123": "123",
        "urn:___param___/123": None,
        "urn:___param___#urn:___param___#123": "123",
    }
    for input_val, expected in inputs.items():
        output = _strip_param(input_val)
        if expected is None:
            assert (
                input_val == output
            ), f"Input {input_val} should remain unchanged but was {output}"
        else:
            assert (
                expected == output
            ), f"Input {input_val} should be {expected} but was {output}"


def test_guarantee_unique_template_name(bm):
    # make new library
    lib = Library.create("test")
    other_lib = Library.create("other_test")
    # add a template
    lib.create_template("test_template", None)
    other_lib.create_template("other_template", None)

    # create a new template with the same name
    name = _guarantee_unique_template_name(lib, "test_template")
    assert name == "test_template_1"

    lib.create_template(name, None)

    # create a new template with the same name
    name = _guarantee_unique_template_name(lib, "test_template")
    assert name == "test_template_2"

    lib.create_template(name, None)

    # names in other libraries do not collide
    name = _guarantee_unique_template_name(lib, "other_template")
    assert name == "other_template"


def test_pyshifty_inference_keeps_prefixes_when_data_is_also_shapes(
    bm: BuildingMOTIF,
):
    """A SHACL-SPARQL rule inside the data graph still resolves its prefixes.

    With no separate shapes argument the data graph is *also* the shapes graph,
    so a ``sh:construct`` body inside it has to reach shifty with the prefix
    declarations its query text needs. BuildingMOTIF's storage layer does not
    persist those bindings, so they have to be re-applied on the way out --
    otherwise the rule silently never fires (pyshifty < 0.4.1) or the call
    raises ``Prefix not found`` (0.4.1+).

    This is the shape of the bug that stopped Brick's own ``ref:`` rules from
    running during ``Library.from_ontology``.
    """
    graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix brick: <https://brickschema.org/schema/Brick#> .
        @prefix : <urn:rules/> .
        : a owl:Ontology .
        :S a sh:NodeShape ;
            sh:targetClass brick:VAV ;
            sh:rule [
                a sh:SPARQLRule ;
                sh:prefixes : ;
                sh:construct \"\"\"
                    CONSTRUCT { $this a brick:Terminal_Unit }
                    WHERE { $this a brick:VAV }
                \"\"\"
            ] .
        <urn:bldg/vav1> a brick:VAV .
        """,
        format="turtle",
    )
    # the binding the storage layer would have dropped
    graph.namespace_manager.bind("brick", None, replace=True)

    inferred = shacl_inference(graph, engine="pyshifty")

    assert (
        URIRef("urn:bldg/vav1"),
        A,
        BRICK.Terminal_Unit,
    ) in inferred, "the sh:construct rule did not fire -- its prefixes were lost"
