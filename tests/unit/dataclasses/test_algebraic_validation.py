"""Tests for the algebraic validation report and template-guided repair
(:mod:`buildingmotif.dataclasses.algebraic_validation`).

These exercise the thesis of the design: pyshifty's gate is a rigorous soundness
oracle, and BuildingMOTIF templates + VF2 monomorphism are a smarter candidate
generator than pyshifty's naive ``Hole.candidates`` -- so the template-guided path
produces *sound + progress-making* repairs where stock pyshifty cannot.
"""
import warnings

import pytest
import rdflib
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

pytest.importorskip("shifty")

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
        result = templ.evaluate(
            {p: rdflib.URIRef(f"urn:bldg/fill_{p}") for p in templ.parameters},
            warn_unused=False,
        )
        assert isinstance(result, Graph)
        patched += result
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
        patched += templ.evaluate(
            {p: rdflib.URIRef(f"urn:bldg/fill_{p}") for p in templ.parameters},
            warn_unused=False,
        )
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
    """Model.validate with the pyshifty engine returns the new context and keeps
    the legacy ``diffset`` / ``failed_component`` surface working."""
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
    shape_lib = Library.load(ontology_graph=shape_graph)

    model = Model.create(BLDG)
    model.add_triples((BLDG["z1"], A, BLDG["Zone"]))

    ctx = model.validate([shape_lib.get_shape_collection()])
    assert isinstance(ctx, AlgebraicValidationContext)
    assert not ctx.valid
    # legacy-compatible diffset surface
    assert len(ctx.diffset) == 1
    witness = next(iter(ctx.diffset.values())).pop()
    assert witness.failed_component == SH.MinCountConstraintComponent
    assert BLDG["z1"] in ctx.get_broken_entities()

    # repairing the label makes it conform
    model.add_triples((BLDG["z1"], rdflib.RDFS.label, Literal("zone one")))
    ctx2 = model.validate([shape_lib.get_shape_collection()])
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
