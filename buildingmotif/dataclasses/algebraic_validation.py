"""Algebraic validation report and template-guided graph repair.

This module is an alternative to :mod:`buildingmotif.dataclasses.validation` that
consumes the *algebraic* output of the ``shifty`` SHACL engine
(``pyshifty``) instead of re-parsing a flattened W3C SHACL validation report.

The shifty theory (``shifty-theory.pdf`` §9, "Symbolic repair: abduction over
φ") frames repair as the abductive dual of validation: for each failing
``(focus, statement)`` it synthesizes a :class:`shifty.RepairTree` — an
AND/OR/Repeat tree of typed *holes* describing every edit that would make the
focus conform — and ships a *gate* (``§9.6``) that re-validates a candidate
``ΔG`` over the whole graph and reports whether it is *sound* (introduces no new
violation) and makes *progress* (removes at least one).

shifty's own hole-filling (:meth:`shifty.Hole.candidates`) is reuse-first but
deliberately naive: it offers any term drawn from the data graph and lets the
caller decide. BuildingMOTIF can do better. It already owns two things shifty
does not: a *library of templates* (the project's domain vocabulary) and a *VF2
monomorphism search* over those templates
(:class:`buildingmotif.template_matcher.TemplateMatcher`). This module fuses the
two: it uses templates + monomorphism as a *smart candidate generator*
(reuse-first via subgraph matching, mint-correct via template grounding) and
uses shifty's gate as the *rigorous arbiter*. Every proposed repair is gated;
proposals are ranked by maximal reuse / minimal additions.

The library decides nothing: :class:`AlgebraicValidationContext` only *proposes*
ranked, gated repairs. Applying one is always the caller's choice.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from itertools import product
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.term import Node
from rdflib.util import from_n3

from buildingmotif.namespaces import PARAM, SH
from buildingmotif.utils import copy_graph, replace_nodes

if TYPE_CHECKING:
    from buildingmotif.dataclasses import Library, Model, ShapeCollection, Template

# namespace for nodes minted by the repair engine (concrete, gate-able IRIs)
REPAIR = Namespace("urn:buildingmotif:repair#")

_mint_counter = 0


def _mint_uri() -> URIRef:
    """Mint a fresh, concrete IRI for a repair-introduced individual."""
    global _mint_counter
    _mint_counter += 1
    return REPAIR[f"n{_mint_counter}"]


def _node_to_nt(node: Node) -> str:
    """Render an rdflib node in the N-Triples term syntax shifty expects."""
    return node.n3()


def _nt_to_node(term: str) -> Node:
    """Parse an N-Triples term (as emitted by shifty) into an rdflib node."""
    return from_n3(term.strip())


def _triples_to_graph(triples) -> Graph:
    """Build a graph from shifty (s, p, o) N-Triples-string tuples."""
    g = Graph()
    for s_nt, p_nt, o_nt in triples:
        g.add((_nt_to_node(s_nt), _nt_to_node(p_nt), _nt_to_node(o_nt)))
    return g


def _make_resolve_library() -> "Library":
    """Create a throwaway library for ephemeral repair/resolve templates."""
    from secrets import token_hex

    from buildingmotif.dataclasses import Library

    return Library.create(f"resolve_{token_hex(4)}")


@dataclass
class RepairProposal:
    """One soundness-gated repair candidate for a single :class:`RepairWitness`.

    A proposal carries both representations requested by the design: the shifty
    ``ΔG`` (``additions`` / ``deletions`` graphs plus the gate's ``outcome``) and
    the means to lift the additions back into a BuildingMOTIF
    :class:`~buildingmotif.dataclasses.template.Template` via :meth:`as_template`.
    """

    # the focus node this proposal repairs
    focus: Optional[URIRef]
    # triples this proposal would add / remove
    additions: Graph
    # triples this proposal would delete
    deletions: Graph
    # the gate's verdict (None for a blocked, non-actionable proposal)
    outcome: Optional["object"]
    # provenance: "template:<name>", "shifty-candidate", "hand", or "blocked"
    origin: str
    # existing model nodes this proposal reuses rather than mints
    reused_nodes: Set[Node] = field(default_factory=set)
    # human-readable note (e.g. the BlockReason for a blocked proposal)
    note: str = ""

    @property
    def is_sound(self) -> bool:
        """True iff the gate proved this ΔG introduces no new violation."""
        return bool(self.outcome is not None and self.outcome.is_sound)

    @property
    def is_progress(self) -> bool:
        """True iff the gate proved this ΔG removes at least one violation."""
        return bool(self.outcome is not None and self.outcome.is_progress)

    @property
    def is_blocked(self) -> bool:
        """True iff no data repair is possible in scope (the gate had nothing
        to evaluate)."""
        return self.origin == "blocked"

    @property
    def num_additions(self) -> int:
        return len(self.additions)

    @property
    def _rank_key(self) -> Tuple:
        """Sort key (descending desirability when reversed): sound and
        progress-making first, then maximal reuse / minimal additions, then a
        stable preference for template-derived proposals."""
        origin_pref = (
            0
            if (self.origin.startswith("template:") or self.origin == "synthesized")
            else 1
        )
        return (
            self.is_sound,
            self.is_progress,
            -self.num_additions,
            len(self.reused_nodes),
            -origin_pref,
        )

    def as_template(self, lib: Optional["Library"] = None) -> Optional["Template"]:
        """Lift this repair's additions into a BuildingMOTIF template.

        Works for *any* proposal -- not just the best one per failure -- so a
        caller can turn whichever sound alternative they prefer into a reusable
        template. (Pure-deletion repairs have nothing to add and return
        ``None``; use :attr:`deletions` / :meth:`apply` for those.)

        The focus node and any reused existing nodes stay concrete (the repair
        targets a specific focus, matching the legacy single-diff behavior);
        each repair-minted individual becomes a fresh, uniquely named parameter
        for the user to fill. The result plugs into the existing
        merge/evaluation workflow
        (:func:`buildingmotif.dataclasses.validation.merge_templates_for_focus`).

        :param lib: the library to create the template in. If ``None``, a fresh
            throwaway ``resolve_*`` library is created (mirroring
            :meth:`AlgebraicValidationContext.as_templates`).
        :type lib: Optional[Library]
        :return: the lifted template, or ``None`` if there is nothing to add
        :rtype: Optional[Template]
        """
        from buildingmotif.utils import _gensym, _guarantee_unique_template_name

        if len(self.additions) == 0:
            return None
        if lib is None:
            lib = _make_resolve_library()
        body = copy_graph(self.additions)
        # parameterize minted repair individuals (unique names so merging
        # several proposals for the same focus never collides)
        minted = {
            n
            for n in body.all_nodes()
            if isinstance(n, URIRef) and str(n).startswith(str(REPAIR))
        }
        replacements: Dict[Node, Node] = {n: _gensym("repaired") for n in minted}
        if replacements:
            replace_nodes(body, replacements)
        name = "Model" if self.focus is None else str(self.focus).split("/")[-1]
        template_name = _guarantee_unique_template_name(lib, f"repair_{name}")
        return lib.create_template(template_name, body)

    def to_delta(self):
        """Return this proposal as a shifty :class:`shifty.RepairDelta`."""
        import shifty  # type: ignore

        return shifty.delta_from_graph(
            add=self.additions if len(self.additions) else None,
            delete=self.deletions if len(self.deletions) else None,
        )

    def apply(self, session) -> Graph:
        """Materialize ``G ⊕ ΔG`` as a fresh graph (does not mutate state)."""
        return session.apply(self.to_delta())

    def advance(self, session):
        """Return a new :class:`shifty.RepairSession` over ``G ⊕ ΔG``."""
        return session.advance(self.to_delta())


@dataclass(eq=False)
class RepairWitness:
    """The new per-failure validation-report unit: why one focus node failed one
    statement, together with its (template-guided, gated) repair proposals.

    Wraps a shifty ``FocusWitness`` and defers candidate generation to the
    owning context's :class:`TemplateGuidedRepair` engine.

    ``eq=False`` keeps instances hashable by identity so they can live in the
    set-valued ``diffset`` that mirrors
    :class:`buildingmotif.dataclasses.validation.ValidationContext`.
    """

    focus: Optional[URIRef]
    # the raw shifty FocusWitness
    witness: "object"
    # back-reference to the owning context (holds the session + repair engine)
    context: "AlgebraicValidationContext"

    def _get_summary(self):
        try:
            return self.witness.summary()
        except Exception:
            return None

    @property
    def failed_component(self) -> Optional[URIRef]:
        """Best-effort SHACL constraint component for legacy compatibility.

        Derived from the *structured* witness leaves (``FocusWitness.summary()``
        ``WitnessKind`` discriminants), which pyshifty keeps stable -- rather
        than from any rendered/display string, whose format is not guaranteed.
        """
        summary = self._get_summary()
        kinds = {
            str(getattr(atom, "kind", "")).split(".")[-1]
            for atom in (summary or [])
        }
        if "CountLow" in kinds:
            return SH.MinCountConstraintComponent
        if "CountHigh" in kinds:
            return SH.MaxCountConstraintComponent
        if "Not" in kinds:
            return SH.NotConstraintComponent
        if "Closed" in kinds:
            return SH.ClosedConstraintComponent
        return None

    @cached_property
    def repair_tree(self):
        """The shifty :class:`shifty.RepairTree` for this failure."""
        return self.witness.repair_tree()

    @property
    def is_blocked(self) -> bool:
        """True if no data repair is possible in scope (opaque SPARQL,
        identity, or coinductive back-edge)."""
        try:
            return bool(self.repair_tree.is_blocked)
        except Exception:
            return False

    def explain(self) -> str:
        """The repair tree rendered as indented text."""
        try:
            return self.repair_tree.explain()
        except Exception:
            return ""

    def reason(self) -> str:
        """Human-readable explanation of this failure (mirrors
        :meth:`buildingmotif.dataclasses.validation.GraphDiff.reason`)."""
        summary = self._get_summary()
        if isinstance(summary, (list, tuple)) and summary:
            parts = []
            for atom in summary:
                kind = str(getattr(atom, "kind", "")).split(".")[-1]
                path = getattr(atom, "path", None)
                detail = getattr(atom, "detail", None)
                seg = f"{self.focus} {kind}".strip()
                if path:
                    seg += f" on path {path}"
                if detail:
                    seg += f" ({detail})"
                parts.append(seg)
            return "; ".join(parts)
        if summary:
            return str(summary)
        try:
            target = self.witness.target()
        except Exception:
            target = ""
        return f"{self.focus} failed {target}".strip()

    def proposals(self, limit: int = 8) -> List[RepairProposal]:
        """Ranked, soundness-gated repair proposals for this failure."""
        return self.context.engine.propose(self, limit=limit)

    def repair_templates(
        self,
        lib: Optional["Library"] = None,
        progress_only: bool = True,
        limit: int = 8,
    ) -> List["Template"]:
        """Lift *every* sound repair for this failure into BuildingMOTIF templates.

        Where :meth:`AlgebraicValidationContext.as_templates` keeps only the
        single best repair per failure, this returns one template per gated
        proposal -- the full set of *alternative* sound fixes -- so a caller can
        review them and pick whichever they want. Each is built with
        :meth:`RepairProposal.as_template`; pure-deletion proposals (nothing to
        add) are skipped.

        :param lib: library to create the templates in; a fresh ``resolve_*``
            library is created when ``None`` (all templates share it)
        :type lib: Optional[Library]
        :param progress_only: if True (default), only keep proposals that
            actually remove the violation; if False, keep every sound proposal
        :type progress_only: bool
        :param limit: maximum number of proposals to consider for this failure
        :type limit: int
        :return: one template per qualifying sound repair (the alternatives)
        :rtype: List[Template]
        """
        if lib is None:
            lib = _make_resolve_library()
        templates: List["Template"] = []
        for proposal in self.proposals(limit=limit):
            if proposal.is_blocked or not proposal.is_sound:
                continue
            if progress_only and not proposal.is_progress:
                continue
            templ = proposal.as_template(lib)
            if templ is not None:
                templates.append(templ)
        return templates


class TemplateGuidedRepair:
    """The repair engine: turns a :class:`RepairWitness` into ranked, gated
    :class:`RepairProposal` objects.

    For each base plan over the repair tree's decision points it fills the open
    holes from four candidate sources, in priority order:

    1. **recursive synthesis** — for a hole that must conform to one or more
       sub-shapes (:attr:`shifty.Hole.conforms_to_shapes`), build the value out
       structurally: reuse an existing node that already conforms, else mint a
       fresh node and recursively repair it against each sub-shape via
       :meth:`shifty.RepairSession.repair_node_against` (bounded by ``BUILD_FUEL``).
       This materializes deep, correctly-typed values (e.g. a ``sh:node`` over a
       multi-step path) that flat candidates cannot.
    2. **template reuse** — existing model nodes that are monomorphic to a
       library template (via :class:`~buildingmotif.template_matcher.TemplateMatcher`),
    3. **template mint** — a freshly grounded template instance, which also pulls
       in domain structure beyond the bare shape requirement,
    4. **shifty native candidates** — so we never do worse than stock shifty.

    Every assembled ``ΔG`` is gated; only sound deltas survive.
    """

    MAX_BRANCHES = 4
    MAX_TEMPLATES = 25
    # depth budget for recursive ConformsTo synthesis (cf. shifty BUILD_FUEL)
    BUILD_FUEL = 6

    def __init__(
        self,
        session,
        templates: List["Template"],
        model_graph: Graph,
        ontology_graph: Graph,
        candidate_limit: int = 16,
    ):
        self.session = session
        self.templates = templates
        self.model_graph = model_graph
        self.ontology_graph = ontology_graph
        self.candidate_limit = candidate_limit

    # -- plan construction ------------------------------------------------

    def _base_specs(self, rt):
        """Yield (repeat_counts, any_choices) plan specs over the tree's
        decision points. ``Repeat`` nodes use their minimum count (>=1);
        ``Any`` nodes are enumerated as separate base plans."""
        import shifty  # type: ignore

        repeats: List[Tuple[int, int]] = []
        anys: List[Tuple[int, int]] = []
        for c in rt.choices():
            if c.kind == shifty.ChoiceKind.Repeat:
                count = c.min if (c.min and c.min > 0) else 1
                repeats.append((c.node_id, count))
            elif c.kind == shifty.ChoiceKind.Any:
                anys.append((c.node_id, c.branches or 1))
        if not anys:
            yield (repeats, [])
            return
        ranges = [range(min(b, self.MAX_BRANCHES)) for (_, b) in anys]
        for combo in product(*ranges):
            yield (repeats, [(anys[i][0], combo[i]) for i in range(len(anys))])

    def _build_plan(self, spec):
        import shifty  # type: ignore

        repeats, anys = spec
        plan = shifty.RepairPlan()
        for node_id, count in repeats:
            plan.count(node_id, count)
        for node_id, branch in anys:
            plan.choose(node_id, branch)
        return plan

    # -- candidate generation --------------------------------------------

    def _ground_template(self, tmpl: "Template", root: URIRef) -> Optional[Graph]:
        """Concretely ground a template at ``root`` (binding remaining params to
        minted IRIs) and return its body graph, or None if it cannot ground."""
        from buildingmotif.dataclasses import Template

        bindings: Dict[str, Node] = {}
        if "name" in tmpl.parameters:
            bindings["name"] = root
        else:
            return None
        for param in tmpl.parameters:
            if param == "name":
                continue
            bindings[param] = _mint_uri()
        result = tmpl.evaluate(bindings, warn_unused=False)
        if isinstance(result, Template):
            return None
        return result

    # -- recursive ConformsTo synthesis ----------------------------------

    @staticmethod
    def _hole_shapes(hole) -> List[int]:
        """The sub-shape ids a hole's value must conform to (``[]`` if none).

        Reads :attr:`shifty.Hole.conforms_to_shapes` (the multi-shape surface);
        ``conforms_to`` is the deprecated single-shape view and is not used.
        """
        try:
            return list(hole.conforms_to_shapes or [])
        except Exception:
            return []

    def _first_conforming(self, hole, shape_ids: List[int]) -> Optional[str]:
        """Reuse-first: the first candidate term that *already* conforms to every
        required sub-shape (``repair_node_against`` returns ``None``)."""
        try:
            candidates = list(hole.candidates(self.candidate_limit))
        except Exception:
            return None
        for cand in candidates:
            try:
                if all(
                    self.session.repair_node_against(cand, sid) is None
                    for sid in shape_ids
                ):
                    return cand
            except Exception:
                continue
        return None

    def _fill_leaf(self, hole) -> Tuple[Optional[str], Graph]:
        """Fill a value-type / constant leaf hole: reuse-first candidate (e.g.
        the required ``rdf:type`` constant), else a freshly minted node."""
        try:
            candidates = list(hole.candidates(self.candidate_limit))
        except Exception:
            candidates = []
        if candidates:
            return candidates[0], Graph()
        return _node_to_nt(_mint_uri()), Graph()

    def _synthesize_value(
        self, node_nt: str, shape_ids: List[int], fuel: int
    ) -> Optional[Graph]:
        """Return the additions that make ``node_nt`` conform to all
        ``shape_ids``, recursively, or ``None`` if it cannot be built in budget."""
        additions = Graph()
        for sid in shape_ids:
            try:
                sub_tree = self.session.repair_node_against(node_nt, sid)
            except Exception:
                return None
            if sub_tree is None:
                continue  # already conforms
            built = self._synthesize_tree(sub_tree, fuel)
            if built is None:
                return None
            additions += built
        return additions

    def _synthesize_tree(self, rt, fuel: int) -> Optional[Graph]:
        """Greedily fold one repair (sub)tree into a concrete additions graph,
        recursing through nested ConformsTo holes until ``fuel`` runs out."""
        import shifty  # type: ignore

        if fuel <= 0:
            return None
        plan = shifty.RepairPlan()
        for c in rt.choices():
            if c.kind == shifty.ChoiceKind.Repeat:
                plan.count(c.node_id, c.min if (c.min and c.min > 0) else 1)
            elif c.kind == shifty.ChoiceKind.Any:
                plan.choose(c.node_id, 0)
        try:
            inst = rt.instantiate(plan)
        except Exception:
            return None
        extra = Graph()
        for h in inst.open_holes:
            shapes = self._hole_shapes(h)
            if shapes:
                reuse = self._first_conforming(h, shapes)
                if reuse is not None:
                    plan.bind(h.id, reuse)
                    continue
                child = _mint_uri()
                built = self._synthesize_value(_node_to_nt(child), shapes, fuel - 1)
                if built is None:
                    return None
                extra += built
                plan.bind(h.id, _node_to_nt(child))
            else:
                value, built = self._fill_leaf(h)
                if value is None:
                    return None
                extra += built
                plan.bind(h.id, value)
        try:
            inst2 = rt.instantiate(plan)
        except Exception:
            return None
        if not inst2.is_complete:
            return None
        return _triples_to_graph(inst2.delta.add) + extra

    def _recursive_combo(self, open_holes):
        """A whole-combo fill that builds every ConformsTo hole out by recursive
        synthesis (reuse-first, else mint+recurse). Returns ``None`` when no open
        hole carries sub-shapes, so it only fires when relevant."""
        if not any(self._hole_shapes(h) for h in open_holes):
            return None
        bindings: Dict[int, str] = {}
        extra = Graph()
        reused: Set[Node] = set()
        for h in open_holes:
            shapes = self._hole_shapes(h)
            if shapes:
                reuse = self._first_conforming(h, shapes)
                if reuse is not None:
                    bindings[h.id] = reuse
                    reused.add(_nt_to_node(reuse))
                    continue
                child = _mint_uri()
                built = self._synthesize_value(
                    _node_to_nt(child), shapes, self.BUILD_FUEL
                )
                if built is None:
                    return None
                extra += built
                bindings[h.id] = _node_to_nt(child)
            else:
                value, built = self._fill_leaf(h)
                if value is None:
                    return None
                extra += built
                bindings[h.id] = value
        return bindings, extra, "synthesized", reused

    def _reuse_candidates(self, tmpl: "Template") -> List[Node]:
        """Existing model nodes that play ``tmpl``'s ``name`` parameter in some
        monomorphic embedding of ``tmpl`` into the model graph.

        The search is *not* anchored to the focus: a reuse *value* (the node we
        bind a hole to) generally lives elsewhere in the graph than the focus
        that needs it.
        """
        from buildingmotif.template_matcher import TemplateMatcher

        if "name" not in tmpl.parameters:
            return []
        found: List[Node] = []
        seen: Set[Node] = set()
        try:
            matcher = TemplateMatcher(self.model_graph, tmpl, self.ontology_graph)
            for mapping in matcher.mappings_iter():
                for building_node, template_node in mapping.items():
                    if template_node == PARAM["name"] and building_node not in seen:
                        seen.add(building_node)
                        found.append(building_node)
                if len(found) >= self.candidate_limit:
                    break
        except Exception:
            return found
        return found

    def _fill_strategies(self, open_holes):
        """Yield (hole_id -> value_nt, extra_graph, origin, reused_set) bindings
        that bind *every* open hole, drawn from the four candidate sources."""
        hole_ids = [h.id for h in open_holes]

        # source 1: recursive ConformsTo synthesis (when holes carry sub-shapes)
        combo = self._recursive_combo(open_holes)
        if combo is not None:
            yield combo

        # source 2+3: templates (reuse, then mint)
        for tmpl in self.templates[: self.MAX_TEMPLATES]:
            if "name" not in tmpl.parameters:
                continue
            # reuse: existing nodes monomorphic to the template
            reuse = self._reuse_candidates(tmpl)
            if len(reuse) >= len(hole_ids):
                chosen = reuse[: len(hole_ids)]
                yield (
                    {hid: _node_to_nt(n) for hid, n in zip(hole_ids, chosen)},
                    Graph(),
                    f"template:{tmpl.name}",
                    set(chosen),
                )
            # mint: a fresh, correctly typed instance per hole
            bindings: Dict[int, str] = {}
            extra = Graph()
            ok = True
            for hid in hole_ids:
                root = _mint_uri()
                grounded = self._ground_template(tmpl, root)
                if grounded is None:
                    ok = False
                    break
                extra += grounded
                bindings[hid] = _node_to_nt(root)
            if ok:
                yield (bindings, extra, f"template:{tmpl.name}", set())

        # source 4: shifty native candidates (reuse-first), zipped per hole
        per_hole: Dict[int, List[str]] = {}
        for h in open_holes:
            try:
                per_hole[h.id] = list(h.candidates(self.candidate_limit))
            except Exception:
                per_hole[h.id] = []
        depth = max((len(v) for v in per_hole.values()), default=0)
        for i in range(min(depth, self.candidate_limit)):
            bindings = {}
            ok = True
            for hid in hole_ids:
                cands = per_hole.get(hid, [])
                if not cands:
                    ok = False
                    break
                bindings[hid] = cands[min(i, len(cands) - 1)]
            if ok:
                yield (bindings, Graph(), "shifty-candidate", set())

    # -- the gate + assembly ---------------------------------------------

    def _gate(
        self, focus, additions: Graph, deletions: Graph, origin: str, reused: Set[Node]
    ) -> Optional[RepairProposal]:
        """Gate one ΔG; return a sound proposal or None."""
        import shifty  # type: ignore

        if len(additions) == 0 and len(deletions) == 0:
            return None
        try:
            delta = shifty.delta_from_graph(
                add=additions if len(additions) else None,
                delete=deletions if len(deletions) else None,
            )
            outcome = self.session.gate(delta)
        except Exception:
            return None
        if not outcome.is_sound:
            return None
        return RepairProposal(
            focus=focus,
            additions=additions,
            deletions=deletions,
            outcome=outcome,
            origin=origin,
            reused_nodes=reused,
        )

    def propose(self, witness: "RepairWitness", limit: int = 8) -> List[RepairProposal]:
        focus = witness.focus
        rt = witness.repair_tree

        if witness.is_blocked:
            return [
                RepairProposal(
                    focus=focus,
                    additions=Graph(),
                    deletions=Graph(),
                    outcome=None,
                    origin="blocked",
                    note="No data repair is possible in scope "
                    "(opaque SPARQL / identity / coinductive).",
                )
            ]

        proposals: List[RepairProposal] = []
        for spec in self._base_specs(rt):
            base_plan = self._build_plan(spec)
            try:
                inst = rt.instantiate(base_plan)
            except Exception:
                continue
            open_holes = list(inst.open_holes)

            if not open_holes:
                # fully determined by the plan (e.g. a pure deletion repair)
                additions = _triples_to_graph(inst.delta.add)
                deletions = _triples_to_graph(inst.delta.delete)
                p = self._gate(focus, additions, deletions, "shifty-candidate", set())
                if p is not None:
                    proposals.append(p)
                continue

            for bindings, extra, origin, reused in self._fill_strategies(open_holes):
                plan = self._build_plan(spec)
                for hid, value in bindings.items():
                    plan.bind(hid, value)
                try:
                    inst2 = rt.instantiate(plan)
                except Exception:
                    continue
                if not inst2.is_complete:
                    continue
                additions = _triples_to_graph(inst2.delta.add) + extra
                deletions = _triples_to_graph(inst2.delta.delete)
                p = self._gate(focus, additions, deletions, origin, reused)
                if p is not None:
                    proposals.append(p)

        proposals.sort(key=lambda p: p._rank_key, reverse=True)
        # de-duplicate by (additions, deletions) signature
        unique: List[RepairProposal] = []
        seen: Set[Tuple] = set()
        for p in proposals:
            sig = (
                tuple(sorted(map(str, p.additions))),
                tuple(sorted(map(str, p.deletions))),
            )
            if sig in seen:
                continue
            seen.add(sig)
            unique.append(p)
        return unique[:limit]


@dataclass
class AlgebraicValidationContext:
    """Validation report built from shifty's algebraic + repair output.

    A drop-in companion to
    :class:`buildingmotif.dataclasses.validation.ValidationContext`: it exposes
    ``conforms``/``valid``, a textual report, the per-failure horizon as
    :class:`RepairWitness` objects, and ``as_templates`` — but every repair is
    computed by abduction over the algebra and gated for soundness, rather than
    re-derived from a flattened W3C report.
    """

    shape_collections: List["ShapeCollection"]
    shapes_graph: Graph
    data_graph: Graph
    model: "Model"
    # candidate libraries for template-guided repair (default: model's libraries)
    libraries: List["Library"] = field(default_factory=list)

    def __post_init__(self):
        import shifty  # type: ignore

        self._session = shifty.RepairSession(self.shapes_graph, self.data_graph)
        self._algebra = shifty.validate_algebra(
            self.data_graph,
            self.shapes_graph,
            minimum_severity="violation",
        )
        # ontology used by the monomorphism search (class hierarchy lives here)
        self._ontology = self.shapes_graph + self.data_graph
        templates: List["Template"] = []
        for lib in self.libraries:
            try:
                templates.extend(lib.get_templates())
            except Exception:
                continue
        self.engine = TemplateGuidedRepair(
            self._session, templates, self.data_graph, self._ontology
        )

    @classmethod
    def from_compiled(
        cls,
        shape_collections: List["ShapeCollection"],
        shapes_graph: Graph,
        data_graph: Graph,
        model: "Model",
        libraries: Optional[List["Library"]] = None,
    ) -> "AlgebraicValidationContext":
        """Build a context from the graphs produced by
        :meth:`buildingmotif.shacl.ShiftyBackend.validation_graphs`."""
        return cls(
            shape_collections,
            shapes_graph,
            copy_graph(data_graph),
            model,
            list(libraries or []),
        )

    @property
    def session(self):
        """The underlying shifty :class:`shifty.RepairSession`."""
        return self._session

    @property
    def valid(self) -> bool:
        return bool(self._algebra.conforms)

    @property
    def conforms(self) -> bool:
        return bool(self._algebra.conforms)

    @property
    def report_string(self) -> str:
        return self._algebra.results_text

    @cached_property
    def witnesses(self) -> List[RepairWitness]:
        """The violation horizon: one :class:`RepairWitness` per failing
        ``(focus, statement)``. Empty iff the graph conforms."""
        out: List[RepairWitness] = []
        for w in self._session.witnesses():
            focus = w.focus
            focus_node = (
                _nt_to_node(focus) if isinstance(focus, str) and focus else None
            )
            if isinstance(focus_node, Literal):
                focus_node = None
            out.append(RepairWitness(focus_node, w, self))  # type: ignore
        return out

    def witnesses_by_focus(self) -> Dict[Optional[URIRef], List[RepairWitness]]:
        grouped: Dict[Optional[URIRef], List[RepairWitness]] = defaultdict(list)
        for rw in self.witnesses:
            grouped[rw.focus].append(rw)
        return dict(grouped)

    @cached_property
    def diffset(self) -> Dict[Optional[URIRef], Set[RepairWitness]]:
        """Per-focus failures, shaped like
        :attr:`buildingmotif.dataclasses.validation.ValidationContext.diffset`
        (a dict of focus node to a set of failures) for drop-in compatibility.
        Here each failure is a :class:`RepairWitness`."""
        return {focus: set(rws) for focus, rws in self.witnesses_by_focus().items()}

    # -- ValidationContext-compatible surface -----------------------------

    def get_broken_entities(self) -> Set[Optional[URIRef]]:
        return set(self.diffset.keys())

    def get_diffs_for_entity(
        self, entity: Optional[URIRef]
    ) -> List[RepairWitness]:
        return list(self.diffset.get(entity, set()))

    def get_reasons_with_severity(
        self, severity: Union[URIRef, str]
    ) -> Dict[Optional[URIRef], List["object"]]:
        """Group the algebra's findings by focus, keeping only the reasons at the
        given severity (``SH.Violation``/``"Violation"``, ``SH.Warning``, or
        ``SH.Info``). Mirrors
        :meth:`buildingmotif.dataclasses.validation.ValidationContext.get_reasons_with_severity`;
        each value is the list of shifty ``Reason`` objects at that severity."""
        if isinstance(severity, URIRef):
            severity_name = str(severity).split("#")[-1]
        else:
            severity_name = str(severity)
        if severity_name not in {"Violation", "Warning", "Info"}:
            raise ValueError(
                f"Invalid severity: {severity}. Must be one of "
                "SH.Violation, SH.Warning, or SH.Info"
            )
        out: Dict[Optional[URIRef], List["object"]] = defaultdict(list)
        for v in self._algebra.violations:
            fn = v.focus_node
            focus = _nt_to_node(fn) if isinstance(fn, str) and fn else None
            for reason in v.reasons:
                if str(reason.severity).split("#")[-1] == severity_name:
                    out[focus].append(reason)
        return dict(out)

    def proposals(self, limit: int = 8) -> Dict[Optional[URIRef], List[RepairProposal]]:
        """All ranked, gated repair proposals, grouped by focus node."""
        out: Dict[Optional[URIRef], List[RepairProposal]] = {}
        for rw in self.witnesses:
            out.setdefault(rw.focus, []).extend(rw.proposals(limit=limit))
        return out

    def as_templates(self, limit_per_witness: int = 1) -> List["Template"]:
        """Lift the *best* sound repair per failure into BuildingMOTIF templates,
        merged per focus node.

        This is the opinionated, "just fix it" entry point: it takes the
        top-ranked sound repair for each failing statement and joins the repairs
        for a shared focus into a single template (via the legacy merge logic in
        :func:`buildingmotif.dataclasses.validation.merge_templates_for_focus`).
        For *all* sound alternatives instead of just the best, see
        :meth:`all_repair_templates` (or :meth:`RepairWitness.repair_templates`
        for a single failure).

        :param limit_per_witness: how many of the top sound repairs to take from
            each failure before merging, defaults to 1 (the single best)
        :type limit_per_witness: int
        :return: the merged reconciling templates, one group per focus
        :rtype: List[Template]
        """
        from buildingmotif.dataclasses.validation import merge_templates_for_focus

        lib = _make_resolve_library()
        templates: List["Template"] = []
        for focus, rws in self.witnesses_by_focus().items():
            focus_templates: List["Template"] = []
            for rw in rws:
                best = [
                    p
                    for p in rw.proposals(limit=limit_per_witness)
                    if p.is_sound and not p.is_blocked
                ]
                for proposal in best[:limit_per_witness]:
                    templ = proposal.as_template(lib)
                    if templ is not None:
                        focus_templates.append(templ)
            templates.extend(merge_templates_for_focus(focus, focus_templates))
        return templates

    def all_repair_templates(
        self,
        progress_only: bool = True,
        limit_per_witness: int = 8,
    ) -> Dict[Optional[URIRef], List["Template"]]:
        """Lift *every* sound repair into BuildingMOTIF templates, grouped by focus.

        The counterpart to :meth:`as_templates`. Where ``as_templates`` keeps
        only the single best repair per failure (and merges them), this returns
        **all** sound, gated repairs as separate, un-merged templates -- the full
        menu of *alternatives* for each failing focus -- so a caller can inspect
        them and choose. Every template comes from a real
        :class:`RepairProposal`, so each one, on its own, is a soundness-gated
        fix (it will not introduce a new violation).

        All templates share one freshly created ``resolve_*`` library.

        :param progress_only: if True (default), keep only repairs that remove
            the violation; if False, keep every sound repair
        :type progress_only: bool
        :param limit_per_witness: max proposals to consider per failure,
            defaults to 8
        :type limit_per_witness: int
        :return: mapping from focus node to its list of alternative repair
            templates (focus ``None`` holds graph-level repairs)
        :rtype: Dict[Optional[URIRef], List[Template]]
        """
        lib = _make_resolve_library()
        grouped: Dict[Optional[URIRef], List["Template"]] = {}
        for rw in self.witnesses:
            templates = rw.repair_templates(
                lib=lib, progress_only=progress_only, limit=limit_per_witness
            )
            if templates:
                grouped.setdefault(rw.focus, []).extend(templates)
        return grouped
