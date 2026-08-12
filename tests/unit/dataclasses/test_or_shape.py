"""Tests for how a `sh:or` disjunction surfaces in validation results.

The legacy GraphDiff API cannot express "satisfy one of these" -- every
template it produces for a focus is joined into a conjunction -- so OrShape
resolves to nothing rather than inventing a repair. The algebraic engine models
the disjunction natively and offers the branches as separate proposals.
"""

from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model
from buildingmotif.dataclasses.algebraic_validation import AlgebraicValidationContext
from buildingmotif.dataclasses.validation import OrShape
from tests.unit.helpers import shapes_as_library

BLDG = Namespace("urn:bldg/")
EX = Namespace("http://ex/")


def _or_shapes() -> Graph:
    """A meter must have EITHER an electric reading OR a gas reading."""
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:MeterShape a sh:NodeShape ; sh:targetClass ex:Meter ;
          sh:or ( [ sh:property [ sh:path ex:elec ; sh:minCount 1 ] ]
                  [ sh:property [ sh:path ex:gas  ; sh:minCount 1 ] ] ) .
        """,
        format="turtle",
    )


def _failing_model(extra_shapes: str = "") -> Model:
    model = Model.create("urn:bldg/")
    model.add_graph(
        Graph().parse(
            data="@prefix ex: <http://ex/> .\n<urn:bldg/m1> a ex:Meter .",
            format="turtle",
        )
    )
    model.manifest.add(shapes_as_library(_or_shapes(), "urn:test/or-shapes"))
    if extra_shapes:
        model.manifest.add(
            shapes_as_library(
                Graph().parse(data=extra_shapes, format="turtle"),
                "urn:test/extra-shapes",
            )
        )
    return model


# -- legacy path ---------------------------------------------------------


def test_or_violation_is_reported(bm: BuildingMOTIF):
    ctx = _failing_model().validate(shacl_engine="pyshacl")
    assert not ctx.valid
    diffs = [d for s in ctx.diffset.values() for d in s if isinstance(d, OrShape)]
    assert diffs, "expected an OrShape diff"


def test_as_templates_does_not_raise_on_a_disjunction(bm: BuildingMOTIF):
    """This used to raise NotImplementedError from GraphDiff.resolve()."""
    ctx = _failing_model().validate(shacl_engine="pyshacl")
    assert ctx.as_templates() == []


def test_a_disjunction_does_not_discard_other_repairs(bm: BuildingMOTIF):
    """The real cost of the crash: one unresolvable diff lost every repair in
    the report, including the ones that were perfectly resolvable."""
    model = _failing_model(
        extra_shapes="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:SerialShape a sh:NodeShape ; sh:targetClass ex:Meter ;
          sh:property [ sh:path ex:serial ; sh:minCount 1 ] .
        """
    )
    ctx = model.validate(shacl_engine="pyshacl")
    templates = ctx.as_templates()
    assert templates, "the resolvable serial-number failure should still produce one"
    bodies = "\n".join(t.body.serialize(format="turtle") for t in templates)
    assert "serial" in bodies


def test_or_reason_describes_branches_not_blank_node_ids(bm: BuildingMOTIF):
    """`sh:or` branches are usually inline blank nodes, so printing the term
    gave an opaque identifier like `nb1f2...`. Describe what each constrains."""
    ctx = _failing_model().validate(shacl_engine="pyshacl")
    diff = next(d for s in ctx.diffset.values() for d in s if isinstance(d, OrShape))
    reason = diff.reason()
    # the branches are named by what they constrain. (The prefix is whatever
    # the stored shape graph resolves to -- a custom `ex:` binding does not
    # survive persistence -- so assert on the local names, not the prefix.)
    assert "elec" in reason and "gas" in reason, reason
    assert "urn:bldg/m1" in reason
    assert "nb" not in reason.replace(
        "urn:bldg", ""
    ), f"leaked a blank node id: {reason}"


# -- algebraic path ------------------------------------------------------


def test_algebraic_engine_offers_the_branches_as_alternatives(bm: BuildingMOTIF):
    """pyshifty models `sh:or` as an `Any` node and enumerates the branches as
    separate, individually gated proposals -- the thing the legacy API has no
    way to express."""
    ctx = _failing_model().validate(shacl_engine="pyshifty")
    assert isinstance(ctx, AlgebraicValidationContext)
    assert not ctx.conforms

    predicates: set = set()
    for witness in ctx.witnesses:
        for proposal in witness.proposals(limit=8):
            if not proposal.is_sound:
                continue
            predicates.update(str(p) for _, p, _ in proposal.additions)

    assert str(EX.elec) in predicates, "expected a proposal satisfying the elec branch"
    assert str(EX.gas) in predicates, "expected a proposal satisfying the gas branch"


def test_each_branch_proposal_is_separately_sound(bm: BuildingMOTIF):
    """Crucially the branches are *alternatives*: each repairs the violation on
    its own, so none of them asserts both."""
    ctx = _failing_model().validate(shacl_engine="pyshifty")
    assert isinstance(ctx, AlgebraicValidationContext)
    for witness in ctx.witnesses:
        for proposal in witness.proposals(limit=8):
            if not (proposal.is_sound and proposal.is_progress):
                continue
            predicates = {str(p) for _, p, _ in proposal.additions}
            assert not (
                str(EX.elec) in predicates and str(EX.gas) in predicates
            ), "a single proposal should satisfy one branch, not conjoin them"


# -- decompiling sh:or into alternative templates ------------------------


def _disjunctive_shape_collection():
    from buildingmotif.dataclasses import ShapeCollection

    sc = ShapeCollection.create()
    sc.add_graph(
        Graph().parse(
            data="""
            @prefix sh:  <http://www.w3.org/ns/shacl#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix ex:  <http://ex/> .
            ex:Meter a owl:Class, sh:NodeShape ;
              sh:property [ sh:path ex:serial ; sh:minCount 1 ;
                            sh:datatype ex:Serial ; sh:name "serial" ] ;
              sh:or (
                [ sh:property [ sh:path ex:elecReading ; sh:minCount 1 ;
                                sh:class ex:ElecPoint ; sh:name "elec" ] ]
                [ sh:property [ sh:path ex:gasReading ; sh:minCount 1 ;
                                sh:class ex:GasPoint ; sh:name "gas" ] ]
              ) .
            """,
            format="turtle",
        )
    )
    return sc


def test_or_branches_become_alternative_templates(bm: BuildingMOTIF):
    """A template generates a fragment and cannot be disjunctive, so a shape
    with `sh:or` decompiles into one template per way of satisfying it."""
    from buildingmotif.dataclasses import Library

    lib = Library.create("meters")
    _disjunctive_shape_collection().infer_templates(lib)
    names = {t.name for t in lib.get_templates()}

    assert "http://ex/Meter" in names, "the base template still exists"
    assert "http://ex/Meter-alt1" in names
    assert "http://ex/Meter-alt2" in names


def test_alternatives_follow_declaration_order(bm: BuildingMOTIF):
    """`sh:or` takes an rdf:List, which is ordered; that authoring order is the
    only ranking the shape carries, so alt1 is the first branch written."""
    from buildingmotif.dataclasses import Library

    lib = Library.create("meters")
    _disjunctive_shape_collection().infer_templates(lib)

    alt1 = lib.get_template_by_name("http://ex/Meter-alt1")
    alt2 = lib.get_template_by_name("http://ex/Meter-alt2")
    assert "elec0" in alt1.parameters, "first declared branch is elec"
    assert "gas0" in alt2.parameters, "second declared branch is gas"


def test_each_alternative_carries_the_common_requirements(bm: BuildingMOTIF):
    """An alternative is the shape's non-disjunctive part plus exactly one
    branch, so filling any single one satisfies the whole shape."""
    from buildingmotif.dataclasses import Library

    lib = Library.create("meters")
    _disjunctive_shape_collection().infer_templates(lib)

    for name in ("http://ex/Meter-alt1", "http://ex/Meter-alt2"):
        params = lib.get_template_by_name(name).parameters
        assert "serial0" in params, f"{name} lost the common serial requirement"
        assert "name" in params


def test_no_alternative_conjoins_the_branches(bm: BuildingMOTIF):
    """The whole point: alternatives, not a conjunction."""
    from buildingmotif.dataclasses import Library

    lib = Library.create("meters")
    _disjunctive_shape_collection().infer_templates(lib)

    for t in lib.get_templates():
        params = t.parameters
        assert not (
            "elec0" in params and "gas0" in params
        ), f"{t.name} asserts both branches at once"


def test_shape_without_or_gains_no_alternatives(bm: BuildingMOTIF):
    from buildingmotif.dataclasses import Library, ShapeCollection

    sc = ShapeCollection.create()
    sc.add_graph(
        Graph().parse(
            data="""
            @prefix sh:  <http://www.w3.org/ns/shacl#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix ex:  <http://ex/> .
            ex:Simple a owl:Class, sh:NodeShape ;
              sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:class ex:T ] .
            """,
            format="turtle",
        )
    )
    lib = Library.create("simple")
    sc.infer_templates(lib)
    assert {t.name for t in lib.get_templates()} == {"http://ex/Simple"}
