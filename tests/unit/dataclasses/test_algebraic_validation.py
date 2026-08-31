"""Tests for the algebraic validation report and template-guided repair
(:mod:`buildingmotif.dataclasses.algebraic_validation`).

These exercise the thesis of the design: pyshifty's gate is a rigorous soundness
oracle, and BuildingMOTIF templates + VF2 monomorphism are a smarter candidate
generator than pyshifty's naive ``Hole.candidates`` -- so the template-guided path
produces *sound + progress-making* repairs where stock pyshifty cannot.
"""
import warnings

import rdflib
import shifty
from rdflib import RDF, RDFS, Graph, Literal, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import (
    AlgebraicValidationContext,
    Library,
    Model,
    RepairConfig,
)
from buildingmotif.dataclasses.template import Template
from buildingmotif.namespaces import BRICK, OWL, PARAM, SH, A

EX = Namespace("http://ex/")
BLDG = Namespace("urn:bldg/")


def _thing_template(lib: Library) -> Template:
    """A template that mints a correctly typed ``ex:Thing`` rooted at ``name``."""
    body = Graph()
    body.add((PARAM["name"], A, EX.Thing))
    return lib.create_template("thing", body)


def _mincount_class_shapes() -> Graph:
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        ex:S a sh:NodeShape ; sh:targetNode bldg:x ;
          sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:class ex:Thing ] .
        """,
        format="turtle",
    )


def test_template_mint_beats_naive_shifty_candidate(bm: BuildingMOTIF):
    """A minCount+class failure: the template-guided proposal mints a *typed*
    instance (sound + progress) and ranks first, whereas pyshifty's own
    candidates are at best sound-but-not-progress."""
    lib = Library.create("repairlib")
    _thing_template(lib)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    assert not ctx.conforms
    witnesses = ctx.witnesses
    assert len(witnesses) == 1
    rw = witnesses[0]
    assert rw.focus == BLDG["x"]
    assert not rw.is_blocked

    proposals = rw.proposals()
    assert proposals, "expected at least one gated proposal"
    # every returned proposal is sound (the gate rejected the rest)
    assert all(p.is_sound for p in proposals)
    # the best proposal makes progress and materializes a correctly typed value
    best = proposals[0]
    assert best.is_progress
    assert best.origin.startswith("template:") or best.origin == "synthesized"
    assert any(o == EX.Thing for (_, _, o) in best.additions)

    # the naive shifty candidates (flat reuse-first guesses) still cannot make
    # progress on a typed-value requirement on their own...
    flat = [p for p in proposals if p.origin == "pyshifty-candidate"]
    assert flat, "shifty should still offer flat candidates"
    assert not any(p.is_progress for p in flat)
    # ...but recursive synthesis makes progress even without any templates
    ctx_no_tmpl = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[]
    )
    no_tmpl = ctx_no_tmpl.witnesses[0].proposals()
    synthesized = [p for p in no_tmpl if p.origin == "synthesized"]
    assert synthesized, "recursive synthesis should produce a candidate"
    assert synthesized[0].is_sound and synthesized[0].is_progress
    assert any(o == EX.Thing for (_, _, o) in synthesized[0].additions)


def test_recursive_synthesis_builds_deep_sh_node(bm: BuildingMOTIF):
    """A nested ``sh:node`` over a multi-step path is repaired by recursive
    synthesis: the engine mints a node and recursively builds it out against the
    sub-shape (no templates required), gated sound."""
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix : <urn:shapes/> .
        : a owl:Ontology .
        ex:Sub a sh:NodeShape ;
            sh:property [ sh:path ex:q ; sh:minCount 1 ; sh:class ex:Widget ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:root ;
            sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:node ex:Sub ] .
        """,
        format="turtle",
    )
    data = Graph().parse(
        data="@prefix ex: <http://ex/> .\nex:root a ex:Root .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    best = ctx.witnesses[0].proposals()[0]
    assert best.origin == "synthesized"
    assert best.is_sound and best.is_progress
    # the deep chain is fully materialized: root -p-> n -q-> w, w a Widget
    assert any(p == EX.p for (_, p, _) in best.additions)
    assert any(p == EX.q for (_, p, _) in best.additions)
    assert any(o == EX.Widget for (_, _, o) in best.additions)
    # applying it clears the violation with nothing new introduced
    assert best.outcome is not None
    assert best.outcome.is_sound and best.outcome.is_progress
    assert len(best.advance(ctx.session).witnesses()) == 0


def test_reuse_existing_node_via_monomorphism(bm: BuildingMOTIF):
    """If the model already contains a node monomorphic to the template, the
    engine reuses it rather than minting a new one."""
    lib = Library.create("repairlib")
    _thing_template(lib)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data=(
            "@prefix bldg: <urn:bldg/> .\n@prefix ex: <http://ex/> .\n"
            "bldg:x a bldg:Foo . bldg:existing a ex:Thing ."
        ),
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    best = ctx.witnesses[0].proposals()[0]
    assert best.is_sound and best.is_progress
    # the top proposal reuses the existing typed instance (no new typed node)
    assert BLDG["existing"] in best.reused_nodes
    assert (BLDG["x"], EX.p, BLDG["existing"]) in best.additions


def test_deletion_direction_for_sh_not(bm: BuildingMOTIF):
    """An ``sh:not`` violation is repaired by *deletion*, gated sound."""
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        ex:S a sh:NodeShape ; sh:targetNode bldg:acct ;
          sh:not [ sh:path ex:status ; sh:hasValue "banned" ] .
        """,
        format="turtle",
    )
    data = Graph().parse(
        data=(
            "@prefix bldg: <urn:bldg/> .\n@prefix ex: <http://ex/> .\n"
            'bldg:acct ex:status "banned" .'
        ),
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    assert not ctx.conforms
    proposals = ctx.witnesses[0].proposals()
    assert proposals
    best = proposals[0]
    assert best.is_sound and best.is_progress
    assert (BLDG["acct"], EX.status, Literal("banned")) in best.deletions
    assert len(best.additions) == 0


def test_get_broken_entities_maps_graph_level_failure_to_model(bm: BuildingMOTIF):
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:S a sh:NodeShape ; sh:targetNode "literal-focus" ;
          sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    data = Graph()
    model = Model.create(BLDG)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)

    assert not ctx.conforms
    assert isinstance(ctx.report, Graph)
    assert len(ctx.report) > 0
    assert set(ctx.diffset) == {None}
    assert ctx.get_broken_entities() == {"Model"}


def test_brick_point_inverse_axioms_do_not_break_has_point_templates(
    bm: BuildingMOTIF,
):
    shapes = Graph().parse(
        data=f"""
        @prefix brick: <{BRICK}> .
        @prefix owl: <{OWL}> .
        @prefix sh: <{SH}> .
        brick:hasPoint owl:inverseOf brick:isPointOf .
        brick:isPointOf owl:inverseOf brick:hasPoint .
        brick:Point a sh:NodeShape ;
          sh:targetClass brick:Point ;
          sh:property [ sh:path brick:isPointOf ; sh:maxCount 0 ] .
        """,
        format="turtle",
    )
    data = Graph().parse(
        data=f"""
        @prefix brick: <{BRICK}> .
        @prefix bldg: <{BLDG}> .
        bldg:root brick:hasPoint bldg:point .
        bldg:point a brick:Point .
        """,
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)

    assert ctx.conforms
    assert ctx.get_broken_entities() == set()


def test_get_reasons_with_severity_wraps_pyshifty_reasons(bm: BuildingMOTIF):
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)

    reasons = ctx.get_reasons_with_severity("Violation")
    reason = reasons[BLDG["x"]][0]
    assert callable(reason.reason)
    assert reason.reason() == (
        "<urn:bldg/x> at least 1 value(s) required along <http://ex/p>, found 0"
    )
    assert reason.message == "at least 1 value(s) required along <http://ex/p>, found 0"


def test_class_failure_separates_validation_reason_from_repair_summary(
    bm: BuildingMOTIF,
):
    """Repair atoms describe edit alternatives, not source constraints.

    A wrong-typed value can be repaired either by removing the property value
    (a CountHigh atom) or typing it correctly (a CountLow atom). The focus
    interface must still report the actual sh:class failure rather than
    mislabelling it as a count violation.
    """
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="""
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        bldg:x a bldg:Foo ; ex:p bldg:wrong_type .
        """,
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    witness = ctx.witnesses[0]

    assert witness.focus == BLDG["x"]
    assert witness.target_shape == EX.S
    assert "must be an instance of <http://ex/Thing>" in witness.reason()
    assert "CountHigh" not in witness.reason()
    assert "max 0" not in witness.reason()

    kinds = {str(atom.kind).split(".")[-1] for atom in witness.repair_summary}
    assert kinds == {"CountHigh", "CountLow"}

    # W3C component metadata is still unavailable and remains unknown rather
    # than being guessed from repair atoms.
    assert witness.failed_component is None
    assert witness.failed_shape is None

    reason = witness.validation_reasons[0]
    assert reason.target_shape == EX.S
    assert reason.path == "<http://ex/p>"
    assert reason.value == "<urn:bldg/wrong_type>"

    # Native algebraic provenance is available at two levels: the witness
    # carries the statement-level constraint shared with the violation, while
    # each reason identifies the specific nested algebra node that failed.
    assert witness.constraint is not None
    assert witness.constraint.id == witness.constraint_id
    assert witness.constraint.kind == witness.constraint_kind
    assert reason.constraint is not None
    assert reason.constraint is reason.source_constraint
    assert reason.constraint.id == reason.constraint_id
    assert reason.constraint.kind == reason.constraint_kind
    assert "<http://ex/Thing>" in reason.constraint.definition
    assert reason.statement_id == witness.statement_id
    assert reason.constraint_id != witness.constraint_id
    assert witness.source_constraints == (reason.constraint,)

    # Repair-leaf provenance stays on the repair atoms and is not substituted
    # for either of the validation-level constraints above.
    assert all(atom.constraint_id is not None for atom in witness.repair_summary)
    assert all(atom.constraint_kind is not None for atom in witness.repair_summary)

    assert witness.violation is not None
    assert ctx.algebra is ctx._algebra
    assert ctx.violations == (witness.violation,)
    assert witness.violation_alignment == "stable-id"
    assert witness.statement_id == 0
    assert witness.statement == witness.statement_id
    assert witness.violation.statement_id == witness.statement_id
    assert witness.violation.constraint_id == witness.constraint_id
    assert witness.selector is not None
    assert witness.selector.kind == shifty.TargetKind.Node
    assert witness.target == "node(<urn:bldg/x>)"
    assert witness.graph is ctx.data_graph
    assert witness.shapes_graph is ctx.shapes_graph


def test_stable_ids_survive_normalized_statement_deduplication(
    bm: BuildingMOTIF,
):
    """Validation and repair share identity after algebra normalization.

    The two source shapes compile to the same selector/constraint statement,
    which pyshifty deduplicates. This guards against treating a raw statement
    vector index as an index into the normalized provenance schema.
    """
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .

        ex:S1 a sh:NodeShape ;
            sh:targetNode ex:x ;
            sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        ex:S2 a sh:NodeShape ;
            sh:targetNode ex:x ;
            sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    data = Graph().parse(
        data="@prefix ex: <http://ex/> . ex:x ex:q ex:y .",
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)

    assert len(ctx.violations) == 1
    assert len(ctx.witnesses) == 1
    violation = ctx.violations[0]
    witness = ctx.witnesses[0]
    assert witness.violation is violation
    assert witness.violation_alignment == "stable-id"
    assert (witness.statement_id, witness.constraint_id,) == (
        violation.statement_id,
        violation.constraint_id,
    )


def _sparql_age_shape() -> Graph:
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        ex:S a sh:NodeShape ; sh:targetNode bldg:x ;
          sh:sparql [
            a sh:SPARQLConstraint ;
            sh:message "{$this} must have a positive age." ;
            sh:prefixes ex: ;
            sh:select \"\"\"
                SELECT $this ?age
                WHERE {
                    OPTIONAL { $this ex:age ?age . }
                    FILTER (!BOUND(?age) || ?age <= 0)
                }
            \"\"\" ;
          ] .
        """,
        format="turtle",
    )


def test_sparql_constraint_reason_includes_diagnostic(bm: BuildingMOTIF):
    """A failed ``sh:sparql`` constraint is opaque on the repair-tree side (no
    algebraic witness) -- but the *separate* ``validate_algebra()`` call this
    same context also runs computes a pyshifty ``SparqlDiagnostic``
    (query/bindings/results) for the same failure.
    :class:`AlgebraicValidationContext` correlates the two so ``reason()`` /
    ``explain()`` (and :meth:`get_reasons_with_severity`) surface the
    diagnostic instead of a bare "opaque SPARQL" dead end."""
    shapes = _sparql_age_shape()
    data = Graph().parse(
        data="""
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        bldg:x a bldg:Foo ; ex:age -5 .
        """,
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    assert not ctx.conforms

    witnesses = ctx.witnesses
    assert len(witnesses) == 1
    rw = witnesses[0]
    assert rw.is_blocked  # opaque SPARQL: no algebraic repair possible

    diagnostics = rw.sparql_diagnostics
    assert len(diagnostics) == 1
    assert "ex/age" in diagnostics[0].query
    assert diagnostics[0].bindings  # at least $this is prebound

    # reason()/explain() no longer stop at "opaque SPARQL -- no algebraic witness"
    assert "query:" in rw.reason()
    assert "query:" in rw.explain()
    assert rw.failed_component is None
    assert rw.failed_shape is None
    assert rw.target_shape == EX.S

    # the structured get_reasons_with_severity surface carries it too
    reasons = ctx.get_reasons_with_severity("Violation")
    reason = reasons[BLDG["x"]][0]
    assert reason.reason().startswith("<urn:bldg/x> must have a positive age. [query:")
    assert "ex/age" in reason.reason()
    assert reason.source_constraint is not None
    assert reason.constraint_kind == shifty.ConstraintKind.Sparql


def test_as_templates_resolves_violation(bm: BuildingMOTIF):
    """``as_templates`` lifts the best sound repair into a BuildingMOTIF
    template whose body fixes the failure when merged into the model."""
    lib = Library.create("repairlib")
    _thing_template(lib)
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    templates = ctx.as_templates()
    assert templates, "expected at least one reconciling template"
    # applying the repair makes the model conform
    patched = Graph()
    patched += data
    for templ in templates:
        patched += templ.substitute(
            {p: rdflib.URIRef(f"urn:bldg/fill_{p}") for p in templ.parameters}
        ).to_graph()
    re_ctx = AlgebraicValidationContext.from_compiled([], shapes, patched, model)
    assert re_ctx.conforms


def test_any_sound_repair_can_be_lifted_to_template(bm: BuildingMOTIF):
    """Any sound proposal -- not just the best -- can be lifted via
    ``RepairProposal.as_template`` (with no library supplied), and every lifted
    alternative resolves the violation."""
    lib = Library.create("repairlib")
    _thing_template(lib)
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    witness = ctx.witnesses[0]
    sound_progress = [p for p in witness.proposals() if p.is_sound and p.is_progress]
    # there is more than one sound, progress-making alternative (synthesized +
    # template), and each can be lifted on its own without passing a library
    assert len(sound_progress) >= 2
    for proposal in sound_progress:
        templ = proposal.as_template()  # lib defaults to a fresh resolve library
        assert templ is not None
        patched = Graph() + data
        patched += templ.substitute(
            {p: rdflib.URIRef(f"urn:bldg/fill_{p}") for p in templ.parameters}
        ).to_graph()
        assert AlgebraicValidationContext.from_compiled(
            [], shapes, patched, model
        ).conforms


def test_all_repair_templates_returns_alternatives(bm: BuildingMOTIF):
    """``all_repair_templates`` returns every sound repair as a separate
    template, grouped by focus (unlike ``as_templates``, which keeps only the
    best per failure)."""
    lib = Library.create("repairlib")
    _thing_template(lib)
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    grouped = ctx.all_repair_templates()
    assert set(grouped.keys()) == {BLDG["x"]}
    alternatives = grouped[BLDG["x"]]
    # more alternatives than the single best that as_templates would keep
    assert len(alternatives) >= 2
    assert len(alternatives) > len(ctx.as_templates())
    # and per-witness access agrees
    witness_alts = ctx.witnesses[0].repair_templates()
    assert witness_alts
    assert len(witness_alts) == len(alternatives)


def test_auto_route_pyshifty_engine_returns_algebraic_context(bm: BuildingMOTIF):
    """Model.validate with pyshifty returns the algebraic context and diffset."""
    bm.shacl_engine = "pyshifty"
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix bldg: <urn:bldg/> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix : <urn:shapes/> .
        : a owl:Ontology .
        :zone a sh:NodeShape ; sh:targetClass bldg:Zone ;
          sh:property [ sh:path rdfs:label ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    shape_lib = Library.from_ontology(shape_graph)

    model = Model.create(BLDG)
    model.add_triples((BLDG["z1"], A, BLDG["Zone"]))

    ctx = model.validate([shape_lib.get_shape_collection()])
    assert isinstance(ctx, AlgebraicValidationContext)
    assert not ctx.valid
    # legacy-compatible diffset surface
    assert len(ctx.diffset) == 1
    witness = next(iter(ctx.diffset.values())).pop()
    assert witness.failed_component is None
    assert witness.validation_reasons
    assert BLDG["z1"] in ctx.get_broken_entities()

    # repairing the label makes it conform
    model.add_triples((BLDG["z1"], rdflib.RDFS.label, Literal("zone one")))
    ctx2 = model.validate([shape_lib.get_shape_collection()])
    assert ctx2.valid


def test_sparql_constraint_fires_after_shape_collection_round_trips_through_storage(
    bm: BuildingMOTIF,
):
    """A ``sh:sparql`` constraint whose query body uses a prefixed name (here
    ``brick:``) must still fire after its shape collection has gone through
    BuildingMOTIF's normal load -> storage -> ``Model.validate`` path -- not
    just when the shapes graph is a freshly-parsed, in-memory ``rdflib.Graph``
    with its original ``@prefix`` bindings still attached.

    This is the regression case for a real silent-failure bug: BuildingMOTIF's
    storage layer does not persist a source file's namespace bindings (only
    triples), and pyshifty's Python binding lowers a bare ``Graph`` argument to
    N-Triples (no ``@prefix`` lines at all) before handing it to the native
    engine. Together, those two facts meant a `sh:sparql`/`sh:rule` constraint
    using a prefixed name in its query text would silently never fire once its
    shapes came from a stored library -- no error, no diagnostic, just a
    vacuous ``conforms``. See ``buildingmotif.shacl._shifty_shapes_input``."""
    bm.shacl_engine = "pyshifty"
    shape_graph = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix brick: <https://brickschema.org/schema/Brick#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix : <urn:shapes/> .
        : a owl:Ontology .
        :S a sh:NodeShape ; sh:targetClass brick:Zone_Air_Temperature_Sensor ;
          sh:sparql [
            a sh:SPARQLConstraint ;
            sh:message "{$this} must not report a negative temperature." ;
            sh:prefixes brick: ;
            sh:select \"\"\"
                SELECT $this ?val
                WHERE {
                    $this a brick:Zone_Air_Temperature_Sensor .
                    OPTIONAL { $this brick:value ?val . }
                    FILTER (BOUND(?val) && ?val < 0)
                }
            \"\"\" ;
          ] .
        """,
        format="turtle",
    )
    # loaded through Library.load, so the shape collection is persisted via
    # BuildingMOTIF's normal storage path (not just an in-memory Graph)
    shape_lib = Library.from_ontology(shape_graph)

    model = Model.create(BLDG)
    model.add_triples((BLDG["x"], A, BRICK["Zone_Air_Temperature_Sensor"]))
    model.add_triples((BLDG["x"], BRICK["value"], Literal(-40)))

    ctx = model.validate([shape_lib.get_shape_collection()])
    assert isinstance(ctx, AlgebraicValidationContext)
    assert not ctx.valid
    witnesses = ctx.witnesses
    assert len(witnesses) == 1
    rw = witnesses[0]
    assert rw.is_blocked  # opaque SPARQL: no algebraic repair possible
    # the diagnostic proves the constraint actually executed against the
    # data (found the -40 value), rather than silently no-oping
    assert rw.sparql_diagnostics
    assert "Brick" in rw.sparql_diagnostics[0].query

    # a model with a non-negative reading conforms
    model2 = Model.create(Namespace("urn:bldg2/"))
    model2.add_triples((BLDG["x"], A, BRICK["Zone_Air_Temperature_Sensor"]))
    model2.add_triples((BLDG["x"], BRICK["value"], Literal(72)))
    ctx2 = model2.validate([shape_lib.get_shape_collection()])
    assert ctx2.valid


def test_repair_config_defaults_match_historical_budgets():
    """The defaults reproduce the previously hard-coded class constants, so
    lifting them out of :class:`TemplateGuidedRepair` is behavior-preserving."""
    config = RepairConfig()
    assert config.max_templates == 25
    assert config.max_branches == 4
    assert config.build_fuel == 6
    assert config.candidate_limit == 16


def test_repair_config_is_threaded_to_the_engine(bm: BuildingMOTIF):
    """A caller-supplied config reaches the engine -- including ``candidate_limit``,
    which was previously unreachable because the context never passed it on."""
    lib = Library.create("repairlib")
    _thing_template(lib)
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    config = RepairConfig(
        max_templates=1, max_branches=2, build_fuel=1, candidate_limit=4
    )
    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib], repair_config=config
    )
    assert ctx.engine.config is config
    assert ctx.engine.candidate_limit == 4
    # repair still produces a sound, progress-making fix under a custom budget
    assert any(p.is_progress for p in ctx.witnesses[0].proposals())


def test_max_templates_none_disables_the_cap(bm: BuildingMOTIF):
    """``max_templates=None`` means no limit, and does not warn."""
    lib = Library.create("repairlib")
    for i in range(30):
        body = Graph()
        body.add((PARAM["name"], A, EX.Thing))
        lib.create_template(f"thing-{i}", body)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [],
        shapes,
        data,
        model,
        libraries=[lib],
        repair_config=RepairConfig(max_templates=None),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any truncation warning fails the test
        assert len(ctx.engine._templates_to_try) == 30


def test_max_templates_truncation_warns_once(bm: BuildingMOTIF):
    """Truncation is by library order rather than relevance, so it warns -- but
    only once per engine, no matter how many witnesses ask for proposals."""
    lib = Library.create("repairlib")
    for i in range(30):
        body = Graph()
        body.add((PARAM["name"], A, EX.Thing))
        lib.create_template(f"thing-{i}", body)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for witness in ctx.witnesses:
            witness.proposals()
        assert len(ctx.engine._templates_to_try) == 25
    truncation = [w for w in caught if "max_templates" in str(w.message)]
    assert len(truncation) == 1
    assert "25" in str(truncation[0].message)


def _mincount_class_shapes_with_subclass() -> Graph:
    """Like :func:`_mincount_class_shapes` but with ``ex:Special`` a subclass of
    the required ``ex:Thing`` -- so a reuse of an existing ``ex:Special`` node
    satisfies the ``sh:class ex:Thing`` obligation."""
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        ex:Special rdfs:subClassOf ex:Thing .
        ex:S a sh:NodeShape ; sh:targetNode bldg:x ;
          sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:class ex:Thing ] .
        """,
        format="turtle",
    )


def test_relevance_filter_keeps_max_templates_from_binding(bm: BuildingMOTIF):
    """A large library with a single relevant template is cut to that template
    *before* the ``max_templates`` budget applies -- so the default cap does not
    bind and no truncation warning fires, even with 60 templates."""
    lib = Library.create("repairlib")
    _thing_template(lib)  # the one relevant template (name a ex:Thing)
    for i in range(60):
        body = Graph()
        body.add((PARAM["name"], A, EX[f"Unrelated{i}"]))
        lib.create_template(f"noise-{i}", body)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    witness = ctx.witnesses[0]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        proposals = witness.proposals()
    # 61 templates in the library, but the cap (25) never binds: only 1 relevant
    assert not [w for w in caught if "max_templates" in str(w.message)]
    # a template-origin repair still lands
    template_progress = [
        p for p in proposals if p.is_progress and p.origin.startswith("template:")
    ]
    assert template_progress
    assert all("thing" in p.origin for p in template_progress)


def test_relevance_filter_keeps_superclass_templates_for_reuse(bm: BuildingMOTIF):
    """A template typed with a *superclass* of the required class must survive
    the filter: monomorphism can reuse an existing, more-specific model node
    that satisfies the obligation."""
    lib = Library.create("repairlib")
    # template roots name at ex:Thing; requirement is also ex:Thing, but the
    # reuse target in the model is the subclass ex:Special
    _thing_template(lib)
    for i in range(30):
        body = Graph()
        body.add((PARAM["name"], A, EX[f"Unrelated{i}"]))
        lib.create_template(f"noise-{i}", body)

    shapes = _mincount_class_shapes_with_subclass()
    data = Graph().parse(
        data=(
            "@prefix bldg: <urn:bldg/> .\n@prefix ex: <http://ex/> .\n"
            "bldg:x a bldg:Foo .\nbldg:reuse_me a ex:Special ."
        ),
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    witness = ctx.witnesses[0]
    import shifty  # local, mirrors engine usage

    rt = witness.repair_tree
    plan = shifty.RepairPlan()
    for choice in rt.choices():
        if choice.kind == shifty.ChoiceKind.Repeat:
            plan.count(choice.node_id, choice.min if choice.min else 1)
        elif choice.kind == shifty.ChoiceKind.Any:
            plan.choose(choice.node_id, 0)
    open_holes = list(rt.instantiate(plan).open_holes)

    selected = {t.name for t in ctx.engine._select_templates(open_holes)}
    assert "thing" in selected
    assert not any(name.startswith("noise-") for name in selected)


def test_ontology_projection_preserves_matching_semantics(bm: BuildingMOTIF):
    """The projected ontology yields the same monomorphisms as the full one --
    it keeps ``subClassOf``/``subPropertyOf``/``owl:Class`` (all the matcher
    reads) and drops the rest."""
    from buildingmotif.dataclasses.algebraic_validation import _ontology_projection
    from buildingmotif.template_matcher import TemplateMatcher

    ontology = Graph().parse(
        data="""
        @prefix ex: <http://ex/> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:Special a owl:Class ; rdfs:subClassOf ex:Thing ; rdfs:label "noise" .
        ex:Thing a owl:Class .
        ex:unrelated ex:predicate ex:junk .
        """,
        format="turtle",
    )
    projected = _ontology_projection(ontology)
    # the label / unrelated triples are gone; the hierarchy + class decls remain
    assert len(projected) < len(ontology)
    assert (EX.Special, RDFS.subClassOf, EX.Thing) in projected
    assert (EX.Special, RDF.type, OWL.Class) in projected

    lib = Library.create("l")
    body = Graph()
    body.add((PARAM["name"], A, EX.Thing))
    tmpl = lib.create_template("thing-t", body)

    model_graph = Graph()
    model_graph.add((BLDG["s"], A, EX.Special))  # subclass instance

    full = TemplateMatcher(model_graph, tmpl, ontology)
    proj = TemplateMatcher(model_graph, tmpl, projected)
    assert full.largest_mapping_size == proj.largest_mapping_size


def test_empty_shape_collection_list_validates(bm: BuildingMOTIF):
    """An empty shapes graph means "take the shapes from the data graph".

    pyshifty rejects an *explicitly supplied* zero-triple shapes graph rather
    than reporting vacuous conformance, so the context has to omit the argument
    instead of handing over an empty graph. It used to pass it unconditionally,
    which raised ``ValueError: explicit shapes graph is empty``.
    """
    data = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        @prefix bldg: <urn:bldg/> .
        ex:S a sh:NodeShape ; sh:targetNode bldg:x ;
          sh:property [ sh:path ex:p ; sh:minCount 1 ] .
        bldg:x a ex:Foo .
        """,
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], Graph(), data, model)

    # the shapes embedded in the data graph still apply
    assert not ctx.conforms
    assert ctx.witnesses
    # and the W3C report path, which takes the same shapes input, also works
    assert len(ctx.report) > 0


def test_missing_edges_name_the_edge_that_would_close_the_deficit(bm: BuildingMOTIF):
    """A cardinality deficit describes itself in building terms.

    pyshifty's ``MissingObligation`` carries the node, the path its values were
    counted along, and how many are short -- so a caller can say "x needs 1 more
    ex:p" without walking a repair tree or reading a SHACL report.
    """
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    (rw,) = ctx.witnesses

    (edge,) = rw.missing_edges
    assert edge.node == BLDG["x"]
    assert edge.path == EX.p
    assert edge.missing == 1
    assert edge.observed_count == 0
    assert edge.required_count == 1
    assert "needs 1 more value(s)" in str(edge)


def test_target_shape_comes_off_the_witness_not_the_pairing(bm: BuildingMOTIF):
    """Shape identity does not depend on the violation join.

    ``target_shape`` used to read the *paired* violation, so it went ``None``
    whenever the (focus, statement_id, constraint_id) join came up empty. The
    witness carries ``shape_iri`` itself, so it is available either way.
    """
    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)
    (rw,) = ctx.witnesses
    assert rw.target_shape == EX.S

    # ...including when nothing was paired at all
    unpaired = type(rw)(rw.focus, rw.witness, ctx, None, "unavailable")
    assert unpaired.violation is None
    assert unpaired.target_shape == EX.S


def test_preview_reports_the_run_a_repair_would_produce(bm: BuildingMOTIF):
    """``preview`` answers "what would this fix?" without mutating anything."""
    lib = Library.create("previewlib")
    _thing_template(lib)

    shapes = _mincount_class_shapes()
    data = Graph().parse(
        data="@prefix bldg: <urn:bldg/> .\nbldg:x a bldg:Foo .", format="turtle"
    )
    model = Model.create(BLDG)
    model.add_graph(data)

    ctx = AlgebraicValidationContext.from_compiled(
        [], shapes, data, model, libraries=[lib]
    )
    assert not ctx.conforms
    best = ctx.witnesses[0].proposals()[0]

    run = ctx.preview(best)
    # the proposal is gated as progress-making, so the previewed run is clean
    assert run.conforms

    # preview is pure: the context it came from is unchanged
    assert not ctx.conforms
    assert ctx.witnesses


def _vav_shapes() -> Graph:
    """A VAV shape with two slots on the *same* path, named."""
    return Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix brick: <https://brickschema.org/schema/Brick#> .
        @prefix : <urn:app/> .
        : a owl:Ontology .
        :VAVShape a sh:NodeShape, owl:Class ;
            sh:targetClass brick:VAV ;
            sh:property [ sh:path brick:hasPoint ; sh:name "air flow sensor" ;
                sh:qualifiedValueShape [ sh:class brick:Air_Flow_Sensor ] ;
                sh:qualifiedMinCount 1 ] ;
            sh:property [ sh:path brick:hasPoint ; sh:name "damper position" ;
                sh:qualifiedValueShape [ sh:class brick:Damper_Position_Command ] ;
                sh:qualifiedMinCount 1 ] .
        """,
        format="turtle",
    )


def _vav_data() -> Graph:
    """vav1 has points but one is mislabelled; vav2 has nothing at all."""
    return Graph().parse(
        data="""
        @prefix brick: <https://brickschema.org/schema/Brick#> .
        @prefix : <urn:bldg/> .
        :vav1 a brick:VAV ; brick:hasPoint :sen_a, :cmd_b .
        :sen_a a brick:Temperature_Sensor .
        :cmd_b a brick:Damper_Position_Command .
        :vav2 a brick:VAV .
        """,
        format="turtle",
    )


def _slot_edges(ctx, focus):
    """The named *top-level* slot edges for one focus.

    Nested edges (amendments of a near miss) carry the same slot name and are
    excluded here; :func:`_amend_edges` returns those.
    """
    return [
        e
        for rw in ctx.diffset[focus]
        for e in rw.missing_edges
        if e.slot is not None and e.nested_under is None
    ]


def _amend_edges(ctx, focus):
    """The nested edges for one focus: "this value is one type away"."""
    return [
        e
        for rw in ctx.diffset[focus]
        for e in rw.missing_edges
        if e.nested_under is not None
    ]


def test_near_misses_name_the_reusable_nodes(bm: BuildingMOTIF):
    """A failing slot reports the nodes already on its path that don't qualify.

    ``vav1`` has ``sen_a`` wired up by the right predicate but typed wrong -- one
    triple from conforming. That is a categorically different repair from
    ``vav2``, which has nothing on the path at all and needs a new node. The
    report has to be able to tell them apart.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (airflow,) = _slot_edges(ctx, BLDG["vav1"])
    assert airflow.slot == "air flow sensor"
    assert airflow.needs.iri == str(BRICK.Air_Flow_Sensor)
    assert airflow.near_misses == (BLDG["sen_a"],)

    # vav2 has nothing to reuse -- both slots fail, neither has a candidate
    vav2 = _slot_edges(ctx, BLDG["vav2"])
    assert {e.slot for e in vav2} == {"air flow sensor", "damper position"}
    assert all(e.near_misses == () for e in vav2)


def test_near_misses_exclude_nodes_serving_another_slot(bm: BuildingMOTIF):
    """``cmd_b`` satisfies the damper slot, so it is not an air-flow candidate.

    The engine reports it as a rejected value for the air flow slot -- the path
    reached it, the class test failed -- but proposing to retype it would fix
    one slot by breaking the other.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (airflow,) = _slot_edges(ctx, BLDG["vav1"])
    assert BLDG["cmd_b"] not in airflow.near_misses

    # ...and the slot cmd_b satisfies is not reported as a failure at all
    assert "damper position" not in {e.slot for e in _slot_edges(ctx, BLDG["vav1"])}


def test_missing_edge_renders_prefixed_names(bm: BuildingMOTIF):
    """A report is read by people: ``brick:hasPoint`` beats the full IRI."""
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (airflow,) = _slot_edges(ctx, BLDG["vav1"])
    text = str(airflow)
    assert "brick:hasPoint" in text
    assert "brick:Air_Flow_Sensor" in text
    assert "https://brickschema.org/schema/Brick#" not in text
    assert "[air flow sensor]" in text


def test_nested_obligation_reads_as_an_amendment(bm: BuildingMOTIF):
    """A nested deficit says "retype sen_a", not "walk rdf:type/rdfs:subClassOf*".

    pyshifty emits an obligation per candidate value beneath a failing slot,
    counted along a SHACL property path rather than a predicate. Reported raw it
    reads as ``sen_a needs 1 more value(s) along
    rdf:type/rdfs:subClassOf*`` -- true, and useless to a building modeller. It
    is attributed to the top-level deficit whose near misses name ``sen_a``, so
    it inherits that slot's name and required class.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (amend,) = _amend_edges(ctx, BLDG["vav1"])
    assert amend.node == BLDG["sen_a"]
    assert amend.nested_under == BLDG["vav1"]
    assert amend.slot == "air flow sensor"
    assert amend.needs.iri == str(BRICK.Air_Flow_Sensor)

    text = str(amend)
    assert "brick:Air_Flow_Sensor" in text
    assert "already wired to" in text
    assert "rdfs:subClassOf*" not in text


def test_nested_obligation_path_is_not_forced_into_a_term(bm: BuildingMOTIF):
    """The type path is reported as a label, never as a minted IRI.

    ``rdf:type/rdfs:subClassOf*`` is a property path. Parsing it as an
    N-Triples term yields the nonsense IRI
    ``...22-rdf-syntax-ns#type/rdfs:subClassOf*``, which a caller would then use
    against the model graph and silently match nothing.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (amend,) = _amend_edges(ctx, BLDG["vav1"])
    assert amend.path is None
    assert amend.path_label is not None
    assert "subClassOf" in amend.path_label


def test_nested_obligation_dropped_for_a_node_serving_another_slot(
    bm: BuildingMOTIF,
):
    """``cmd_b`` gets no amendment, and the soundness gate cannot say so.

    The engine emits a nested obligation for ``cmd_b`` too -- the air flow slot
    rejected it, so retyping it would discharge the deficit. Worse, that edit
    *gates sound*: ``rdf:type`` is additive, so ``cmd_b`` stays a
    ``Damper_Position_Command`` and the damper slot never breaks. Only the
    near-miss exclusion keeps it out of the report.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    amended = {e.node for e in _amend_edges(ctx, BLDG["vav1"])}
    assert amended == {BLDG["sen_a"]}

    # the gate really would accept it -- this is a domain judgement, not a
    # soundness one
    delta = shifty.delta_from_graph(
        add=_graph_with((BLDG["cmd_b"], RDF.type, BRICK.Air_Flow_Sensor))
    )
    outcome = ctx.session.gate(delta)
    assert outcome.is_sound and outcome.is_progress


def test_repair_amends_a_near_miss_instead_of_minting(bm: BuildingMOTIF):
    """``sen_a`` is wired to ``vav1`` and mislabelled: label it, don't mint.

    The repair tree cannot express this. It offers ``add vav1 hasPoint ?0`` with
    ``?0 : instance of Air_Flow_Sensor``, so every filler either conforms
    already or is newly minted -- and the edge to ``sen_a`` is already in the
    graph. Left to the tree the engine proposes a phantom second sensor and
    leaves the real, already-wired point mislabelled.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    (witness,) = [rw for rw in ctx.witnesses if rw.focus == BLDG["vav1"]]
    proposals = witness.proposals()

    best = proposals[0]
    assert best.origin == "amend"
    assert best.is_sound and best.is_progress
    assert set(best.additions) == {(BLDG["sen_a"], RDF.type, BRICK.Air_Flow_Sensor)}
    assert best.reused_nodes == {BLDG["sen_a"]}
    assert best.deletions is not None and len(best.deletions) == 0
    assert "already wired up" in best.note

    # it really does fix vav1, on the engine's own account. The model as a
    # whole still fails -- vav2 has no points at all -- so the check is scoped
    # to the focus this proposal is for.
    before = ctx.session.witnesses()
    after = ctx.preview(best).failures_for(BLDG["vav1"].n3())
    assert any(_focus_of(w) == BLDG["vav1"] for w in before)
    assert list(after) == []

    # vav2 has nothing on the path, so nothing to amend -- it still mints, and
    # it does not build a shape map to find that out
    (other,) = [rw for rw in ctx.witnesses if rw.focus == BLDG["vav2"]]
    assert not other.has_amendable_values
    assert all(p.origin != "amend" for p in other.proposals())
    assert witness.has_amendable_values


def test_amendment_is_skipped_for_a_non_class_slot(bm: BuildingMOTIF):
    """A datatype slot has no one-triple amendment, so none is proposed.

    ``needs`` is populated for datatype slots too, and
    ``<node> rdf:type xsd:string`` would be nonsense.
    """
    shapes = Graph().parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix ex: <http://ex/> .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ;
            sh:property [ sh:path ex:label ; sh:name "label" ;
                sh:datatype <http://www.w3.org/2001/XMLSchema#string> ;
                sh:minCount 1 ] .
        """,
        format="turtle",
    )
    data = Graph().parse(
        data="""
        @prefix ex: <http://ex/> .
        @prefix : <urn:bldg/> .
        :x a ex:T ; ex:label 7 .
        """,
        format="turtle",
    )
    model = Model.create(BLDG)
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], shapes, data, model)

    assert not ctx.conforms
    for witness in ctx.witnesses:
        assert all(p.origin != "amend" for p in witness.proposals())


def test_join_is_refused_when_the_two_runs_name_different_shapes(
    bm: BuildingMOTIF,
):
    """A stable-id match on a different shape is dropped, not trusted.

    The join key is three session-local integers computed by two independent
    runs. It holds on pyshifty 0.4.1 -- every other test here relies on it --
    but if it ever stopped holding the failure would be a *mislabelling*: real
    findings wearing another finding's reasons, with nothing raised. The shape
    IRI is derived separately on each side, so it can check the assumption.
    """
    model = Model.create(BLDG)
    data = _vav_data()
    model.add_graph(data)
    ctx = AlgebraicValidationContext.from_compiled([], _vav_shapes(), data, model)

    assert all(rw.violation_alignment == "stable-id" for rw in ctx.witnesses)
    witness = ctx.witnesses[0]
    assert witness.violation is not None

    agree = AlgebraicValidationContext._shapes_agree
    assert agree(witness.witness, witness.violation)

    class _OtherShape:
        shape_name = "urn:app/SomeOtherShape"

    assert not agree(witness.witness, _OtherShape())

    # a side that names no shape is not evidence against the join
    class _Anonymous:
        shape_name = None

    assert agree(witness.witness, _Anonymous())


def _focus_of(witness):
    return rdflib.util.from_n3(witness.focus)


def _graph_with(*triples) -> Graph:
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    return graph
