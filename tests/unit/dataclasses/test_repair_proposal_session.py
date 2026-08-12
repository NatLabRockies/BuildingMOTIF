"""RepairProposal.apply()/advance() should not make the caller fetch the
session and hand it back to the object that came out of it."""

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, RepairProposal
from buildingmotif.dataclasses.algebraic_validation import AlgebraicValidationContext
from tests.unit.helpers import shapes_as_library

BLDG = Namespace("urn:bldg/")


def _failing_context(bm: BuildingMOTIF) -> AlgebraicValidationContext:
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Foo ;
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
    ctx = model.validate()
    assert isinstance(ctx, AlgebraicValidationContext)
    return ctx


def _a_sound_proposal(ctx) -> RepairProposal:
    for witness in ctx.witnesses:
        for proposal in witness.proposals():
            if proposal.is_sound:
                return proposal
    raise AssertionError("expected at least one sound proposal")


def test_apply_defaults_to_the_originating_session(bm: BuildingMOTIF):
    ctx = _failing_context(bm)
    graph = _a_sound_proposal(ctx).apply()
    assert isinstance(graph, Graph)
    assert len(graph) > 0


def test_advance_defaults_to_the_originating_session(bm: BuildingMOTIF):
    ctx = _failing_context(bm)
    assert _a_sound_proposal(ctx).advance() is not None


def test_an_explicit_session_still_wins(bm: BuildingMOTIF):
    ctx = _failing_context(bm)
    proposal = _a_sound_proposal(ctx)
    assert set(proposal.apply(ctx.session)) == set(proposal.apply())


def test_a_hand_built_proposal_says_what_is_missing(bm: BuildingMOTIF):
    """A proposal not produced by the engine has no session to fall back on."""
    proposal = RepairProposal(
        focus=None,
        additions=Graph(),
        deletions=Graph(),
        outcome=None,
        origin="hand",
    )
    with pytest.raises(ValueError, match="no repair session"):
        proposal.apply()


def test_the_session_is_not_part_of_proposal_identity(bm: BuildingMOTIF):
    """It is provenance, so it must stay out of equality and repr."""
    ctx = _failing_context(bm)
    proposal = _a_sound_proposal(ctx)
    assert "_session" not in repr(proposal)
