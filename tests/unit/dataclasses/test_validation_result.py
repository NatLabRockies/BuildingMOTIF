"""Tests that both validation context classes satisfy the ValidationResult
protocol, so callers can be written against one type instead of branching on
which SHACL engine happens to be configured."""

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, ValidationContext, ValidationResult
from buildingmotif.dataclasses.algebraic_validation import AlgebraicValidationContext
from buildingmotif.namespaces import SH

BLDG = Namespace("urn:bldg/")
EX = Namespace("http://ex/")


def _shapes() -> Graph:
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Foo ;
             sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        """,
        format="turtle",
    )


def _failing_model() -> Model:
    model = Model.create("urn:bldg/")
    model.add_graph(
        Graph().parse(
            data="@prefix ex: <http://ex/> .\n<urn:bldg/x> a ex:Foo .", format="turtle"
        )
    )
    model.get_manifest().add_graph(_shapes())
    return model


@pytest.fixture(params=["pyshifty", "pyshacl"])
def ctx(request, bm: BuildingMOTIF):
    """A failing validation result from each engine that produces one."""
    return _failing_model().validate(shacl_engine=request.param)


def test_both_engines_return_a_validation_result(ctx):
    assert isinstance(ctx, ValidationResult)


def test_engines_return_their_own_context_class(bm: BuildingMOTIF):
    """The protocol is structural -- the concrete classes are unchanged, so
    narrowing to them for engine-specific behavior still works."""
    model = _failing_model()
    assert isinstance(
        model.validate(shacl_engine="pyshifty"), AlgebraicValidationContext
    )
    assert isinstance(model.validate(shacl_engine="pyshacl"), ValidationContext)


def test_valid_and_conforms_agree(ctx):
    """``conforms`` is available on both, matching SHACL's own vocabulary."""
    assert ctx.valid is False
    assert ctx.conforms is False
    assert ctx.valid == ctx.conforms


def test_valid_model_conforms(bm: BuildingMOTIF):
    model = Model.create("urn:bldg/")
    model.add_graph(
        Graph().parse(
            data="@prefix ex: <http://ex/> .\n<urn:bldg/x> a ex:Foo ; ex:p 1 .",
            format="turtle",
        )
    )
    model.get_manifest().add_graph(_shapes())
    for engine in ("pyshifty", "pyshacl"):
        result = model.validate(shacl_engine=engine)
        assert result.conforms, f"{engine} should conform"
        assert result.get_broken_entities() == set()
        assert len(result.diffset) == 0


def test_diffset_is_focus_to_set_of_failures(ctx):
    assert BLDG["x"] in ctx.diffset
    failures = ctx.diffset[BLDG["x"]]
    assert isinstance(failures, set)
    assert len(failures) > 0
    for failure in failures:
        # the Failure protocol: a focus and a human-readable reason
        assert failure.focus == BLDG["x"]
        assert isinstance(failure.reason(), str)
        assert failure.reason()


def test_get_broken_entities(ctx):
    assert ctx.get_broken_entities() == {BLDG["x"]}


def test_get_diffs_for_entity_returns_a_set(ctx):
    """Both engines return a set here; the algebraic side used to return a list."""
    diffs = ctx.get_diffs_for_entity(BLDG["x"])
    assert isinstance(diffs, set)
    assert diffs == ctx.diffset[BLDG["x"]]


def test_get_diffs_for_entity_accepts_none(ctx):
    """``None`` is the key model-level failures live under; the legacy context
    used to reject it in its signature."""
    assert ctx.get_diffs_for_entity(None) == set()


def test_get_diffs_for_unknown_entity_is_empty(ctx):
    assert ctx.get_diffs_for_entity(BLDG["nope"]) == set()


def test_get_reasons_with_severity(ctx):
    reasons = ctx.get_reasons_with_severity(SH.Violation)
    assert BLDG["x"] in reasons
    assert len(reasons[BLDG["x"]]) > 0
    for reason in reasons[BLDG["x"]]:
        assert isinstance(reason.reason(), str)


def test_get_reasons_with_severity_rejects_bad_severity(ctx):
    with pytest.raises(ValueError):
        ctx.get_reasons_with_severity("Nonexistent")


def test_common_attributes_are_present(ctx):
    assert ctx.model.name == "urn:bldg/"
    assert isinstance(ctx.report, Graph)
    assert isinstance(ctx.report_string, str)
    assert isinstance(ctx.shapes_graph, Graph)
    assert isinstance(list(ctx.shape_collections), list)


def test_as_templates_is_callable_with_no_arguments(ctx):
    """Part of the protocol: ``as_templates()`` works without engine-specific
    arguments, even though the algebraic version accepts an extra tuning knob."""
    templates = ctx.as_templates()
    assert isinstance(templates, list)
