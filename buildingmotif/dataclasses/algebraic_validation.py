"""Algebraic validation report and template-guided graph repair.

This module is an alternative to :mod:`buildingmotif.dataclasses.validation` that
consumes the *algebraic* output of the ``pyshifty`` SHACL engine instead of
re-parsing a flattened W3C SHACL validation report.

The pyshifty theory (``shifty-theory.pdf`` §9, "Symbolic repair: abduction over
φ") frames repair as the abductive dual of validation: for each failing
``(focus, statement)`` it synthesizes a pyshifty repair tree — an
AND/OR/Repeat tree of typed *holes* describing every edit that would make the
focus conform — and ships a *gate* (``§9.6``) that re-validates a candidate
``ΔG`` over the whole graph and reports whether it is *sound* (introduces no new
violation) and makes *progress* (removes at least one).

pyshifty's own hole-filling (:meth:`pyshifty.Hole.candidates`) is reuse-first but
deliberately naive: it offers any term drawn from the data graph and lets the
caller decide. BuildingMOTIF can do better. It already owns two things pyshifty
does not: a *library of templates* (the project's domain vocabulary) and a *VF2
monomorphism search* over those templates
(:class:`buildingmotif.template_matcher.TemplateMatcher`). This module fuses the
two: it uses templates + monomorphism as a *smart candidate generator*
(reuse-first via subgraph matching, mint-correct via template grounding) and
uses pyshifty's gate as the *rigorous arbiter*. Every proposed repair is gated;
proposals are ranked by maximal reuse / minimal additions.

The library decides nothing: :class:`AlgebraicValidationContext` only *proposes*
ranked, gated repairs. Applying one is always the caller's choice.
"""
import logging
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from itertools import product
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    Union,
    runtime_checkable,
)

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.term import Node
from rdflib.util import from_n3

from buildingmotif.namespaces import BRICK, OWL, PARAM, RDF, RDFS
from buildingmotif.shacl import _shifty_data_input, _shifty_shapes_input, require_shifty
from buildingmotif.utils import copy_graph, replace_nodes

if TYPE_CHECKING:
    from buildingmotif.dataclasses import Library, Model, ShapeCollection, Template

logger = logging.getLogger(__name__)

# namespace for nodes minted by the repair engine (concrete, gate-able IRIs)
REPAIR = Namespace("urn:buildingmotif:repair#")


class GateOutcome(Protocol):
    """Structural type for the verdict shifty's gate returns for a candidate
    ``ΔG`` (:meth:`shifty.RepairSession.gate`). Only the two soundness flags the
    repair layer reads are pinned here."""

    @property
    def is_sound(self) -> bool:
        """True iff the candidate ΔG introduces no new violation."""
        ...

    @property
    def is_progress(self) -> bool:
        """True iff the candidate ΔG removes at least one violation."""
        ...


_mint_counter = 0


@runtime_checkable
class SparqlDiagnostic(Protocol):
    """The part of pyshifty's ``SparqlDiagnostic`` this module reads.

    Declared as a Protocol so the public surface types as something with
    attributes rather than ``object`` (which types as having *none*, so every
    consumer -- including our own tests -- had to fight the checker). Reads
    remain defensive ``getattr`` calls at runtime, because the concrete shape
    is pyshifty's to change across versions.
    """

    @property
    def query(self) -> str:
        """The SPARQL actually executed."""
        ...

    @property
    def bindings(self) -> Sequence[Tuple[str, object]]:
        """``$this`` and any prebound variables."""
        ...

    @property
    def results(self) -> Sequence[object]:
        """The solution rows the query produced."""
        ...


@runtime_checkable
class MissingObligation(Protocol):
    """The part of pyshifty's ``MissingObligation`` this module reads.

    One cardinality deficit on one edge: ``required_count`` values were wanted
    along ``path`` from ``node``, each satisfying ``qualifier``, and only
    ``observed_count`` were found.
    """

    @property
    def node(self) -> object:
        """The node the deficit is about."""
        ...

    @property
    def path(self) -> object:
        """The path the values were counted along."""
        ...

    @property
    def qualifier(self) -> object:
        """The constraint each counted value has to satisfy."""
        ...

    @property
    def missing(self) -> int:
        """How many values short the node is."""
        ...

    @property
    def observed_count(self) -> int:
        """How many qualifying values the data actually supplied."""
        ...

    @property
    def required_count(self) -> int:
        """How many qualifying values the shape asked for."""
        ...


@runtime_checkable
class ShiftyFailure(Protocol):
    """The part of pyshifty's ``Failure`` this module reads.

    ``Failure`` is pyshifty's name for one focus node failing one statement --
    what :meth:`shifty.RepairSession.witnesses` returns. Spelled
    ``ShiftyFailure`` here to keep it distinct from
    :class:`buildingmotif.dataclasses.validation_result.Failure`, which is
    BuildingMOTIF's own engine-independent failure protocol -- the one
    :class:`RepairWitness` *satisfies*, as opposed to the one it *wraps*.
    """

    @property
    def focus(self) -> object:
        """The failing node."""
        ...

    @property
    def shape_iri(self) -> object:
        """The failing statement's source shape IRI.

        ``None`` when the shape was written as a blank node and so has no IRI.
        """
        ...

    @property
    def shape_name(self) -> object:
        """The failing statement's source shape, when named."""
        ...

    def missing_obligations(self) -> Sequence["MissingObligation"]:
        """Cardinality deficits: what the focus is short of, and on which edge.

        Each entry names the ``node`` the deficit is about, the ``path`` its
        values were counted along, and the ``qualifier`` each counted value has
        to satisfy -- enough to describe the edge that would close the deficit
        without walking the repair tree.
        """
        ...

    @property
    def target(self) -> object:
        """The statement that failed."""
        ...

    @property
    def statement(self) -> int:
        """pyshifty's identifier for the failed algebra statement."""
        ...

    @property
    def statement_id(self) -> int:
        """Stable statement id shared with algebraic violations."""
        ...

    @property
    def constraint_id(self) -> int:
        """Stable top-level constraint id shared with algebraic violations."""
        ...

    @property
    def constraint_kind(self) -> object:
        """The top-level algebraic constraint discriminant."""
        ...

    @property
    def constraint(self) -> object:
        """The complete top-level algebraic constraint."""
        ...

    @property
    def selector(self) -> object:
        """How the focus was selected for the failed statement."""
        ...

    def summary(self) -> object:
        """The failure's atoms."""
        ...

    def repair_tree(self) -> object:
        """The tree of repair choices for this failure."""
        ...


@runtime_checkable
class AlgebraicViolation(Protocol):
    """The native pyshifty violation paired with a repair witness."""

    @property
    def focus_node(self) -> object:
        """The node at which the algebra statement failed."""
        ...

    @property
    def shape_name(self) -> object:
        """The named shape/statement, when pyshifty has one."""
        ...

    @property
    def statement_id(self) -> int:
        """Stable statement id shared with the repair witness."""
        ...

    @property
    def constraint_id(self) -> int:
        """Stable top-level constraint id shared with the repair witness."""
        ...

    @property
    def reasons(self) -> Sequence[object]:
        """Structured validation reasons for this violation."""
        ...


def _mint_uri() -> URIRef:
    """Mint a fresh, concrete IRI for a repair-introduced individual."""
    global _mint_counter
    _mint_counter += 1
    return REPAIR[f"n{_mint_counter}"]


def _node_to_nt(node: Node) -> str:
    """Render an rdflib node in the N-Triples term syntax pyshifty expects."""
    return node.n3()


def _nt_to_node(term: str) -> Node:
    """Parse an N-Triples term (as emitted by pyshifty) into an rdflib node."""
    return from_n3(term.strip())


def _focus_to_node(focus: object) -> Optional[Node]:
    """Normalize pyshifty focus terms to legacy ValidationContext keys."""
    node = _nt_to_node(focus) if isinstance(focus, str) and focus else None
    return None if isinstance(node, Literal) else node


def _engine_term_to_node(term: object) -> Optional[Node]:
    """Normalize an RDF term exposed by pyshifty.

    Focus/value/path fields use N-Triples terms, while ``Violation.shape_name``
    is a bare IRI. Keep that wire-format distinction here instead of leaking it
    into every public diagnostic property.
    """
    if isinstance(term, Node):
        return term
    if not isinstance(term, str) or not term:
        return None
    try:
        return _nt_to_node(term)
    except Exception:
        return URIRef(term)


def _triples_to_graph(triples) -> Graph:
    """Build a graph from pyshifty (s, p, o) N-Triples-string tuples."""
    g = Graph()
    for s_nt, p_nt, o_nt in triples:
        g.add((_nt_to_node(s_nt), _nt_to_node(p_nt), _nt_to_node(o_nt)))
    return g


def _render_sparql_diagnostic(diag: "SparqlDiagnostic") -> str:
    """Render a pyshifty ``SparqlDiagnostic`` (``Reason.sparql_diagnostic``) as
    human-readable text: the query actually executed, its ``$this``/prebound
    variables, and the solution rows it produced.

    Mirrors the detail ``shifty.validate(...)``'s own ``results_text`` already
    prints for a failed ``sh:sparql`` constraint on the W3C-report path -- this
    is what makes the same detail available on the *algebraic* path (i.e. from
    :class:`AlgebraicReason`/:class:`RepairWitness`), where a SPARQL failure
    would otherwise be reported as opaque with no further explanation.
    """
    lines = [f"query: {getattr(diag, 'query', '')}"]
    bindings = getattr(diag, "bindings", None)
    if bindings:
        bound = ", ".join(f"${name} = {value}" for name, value in bindings)
        lines.append(f"bound: {bound}")
    results = getattr(diag, "results", None)
    if results:
        rows = [
            "(" + ", ".join(f"{name} = {value}" for name, value in row) + ")"
            if row
            else "()"
            for row in results
        ]
        lines.append(f"results: {'; '.join(rows)}")
    else:
        lines.append("results: (no rows)")
    fallback_reason = getattr(diag, "fallback_reason", None)
    if fallback_reason:
        lines.append(f"fallback: {fallback_reason}")
    return " | ".join(lines)


def _ontology_projection(ontology: Graph) -> Graph:
    """Project an ontology down to the triples the monomorphism search reads.

    :class:`~buildingmotif.template_matcher.TemplateMatcher` consults the ontology
    for exactly three things -- ``rdfs:subClassOf`` (``parents``),
    ``rdfs:subPropertyOf`` (``superproperties``), and ``(node, rdf:type,
    owl:Class)`` (``defined_in``). Node *types* are read from the data/template
    graphs, not from here. Restricting the graph to those triples is therefore
    semantics-preserving, and it makes every ``transitive_objects`` walk cheaper
    -- which matters because the matcher rebuilds its ontology cache for each of
    the ``2^|nodes|`` template subgraphs it enumerates.

    Note that a *partial* projection is not safe: dropping the ``owl:Class``
    declarations (keeping only ``subClassOf``) makes ``defined_in`` false for
    every class, which silently turns the class check into a permissive one.
    """
    projected = Graph()
    for triple in ontology.triples((None, RDFS.subClassOf, None)):
        projected.add(triple)
    for triple in ontology.triples((None, RDFS.subPropertyOf, None)):
        projected.add(triple)
    for triple in ontology.triples((None, RDF.type, OWL.Class)):
        projected.add(triple)
    return projected


def _without_redundant_point_inverse_axioms(graph: Graph) -> Graph:
    g = copy_graph(graph)
    g.remove((BRICK.isPointOf, OWL.inverseOf, BRICK.hasPoint))
    g.remove((BRICK.hasPoint, OWL.inverseOf, BRICK.isPointOf))
    return g


def _make_resolve_library() -> "Library":
    """Create a throwaway library for ephemeral repair/resolve templates."""
    from secrets import token_hex

    from buildingmotif.dataclasses import Library

    return Library.create(f"resolve_{token_hex(4)}")


@dataclass(frozen=True)
class RepairConfig:
    """Search budgets for :class:`TemplateGuidedRepair`.

    Candidate generation is heuristic and deliberately incomplete (see
    ``algebraic-repair.md`` §7-8): these budgets bound it. The defaults reproduce
    the historical hard-coded values. Raising them widens the search at a
    superlinear cost -- in particular ``max_templates``, because template reuse
    runs a :class:`~buildingmotif.template_matcher.TemplateMatcher` monomorphism
    search *per template*, which is exponential in template size.

    :param max_templates: how many templates to try *after* relevance filtering
        (:meth:`TemplateGuidedRepair._select_templates` first keeps only templates
        that could fill the failing hole), or ``None`` for no limit. The engine
        rarely reaches this cap because the filter usually cuts the candidate set
        to a handful; when it does bind it drops in library order, so prefer a
        smaller, purpose-built library over raising it.
    :param max_branches: how many branches to enumerate at each ``Any`` node
    :param build_fuel: recursion depth budget for ConformsTo synthesis
    :param candidate_limit: how many candidate terms to pull per hole
    """

    max_templates: Optional[int] = 25
    max_branches: int = 4
    build_fuel: int = 6
    candidate_limit: int = 16


@dataclass(frozen=True)
class AlgebraicReason:
    """One structured reason from pyshifty's algebraic validation."""

    raw: "object"
    focus: Optional[Node] = None
    target_shape: Optional[Node] = None

    def __getattr__(self, name):
        return getattr(self.raw, name)

    @property
    def source_constraint(self) -> Optional[object]:
        """The native algebraic constraint that produced this reason.

        This is algebraic provenance, not a W3C SHACL source component.
        """
        return getattr(self.raw, "constraint", None)

    @property
    def constraint(self) -> Optional[object]:
        """The complete native algebra node that produced this reason."""
        return self.source_constraint

    @property
    def statement_id(self) -> Optional[int]:
        """The enclosing top-level statement's stable id."""
        value = getattr(self.raw, "statement_id", None)
        return value if isinstance(value, int) else None

    @property
    def constraint_id(self) -> Optional[int]:
        """The specific, potentially nested algebra node's stable id."""
        value = getattr(self.raw, "constraint_id", None)
        return value if isinstance(value, int) else None

    @property
    def constraint_kind(self) -> Optional[object]:
        """The specific algebra node's enumerated semantic kind."""
        return getattr(self.raw, "constraint_kind", None)

    def reason(self) -> str:
        diagnostic = getattr(self.raw, "sparql_diagnostic", None)
        # For ordinary core constraints the engine-generated message describes
        # the precise failing operation ("must be an instance of ..."), while a
        # property shape's author message may describe the property as a whole
        # ("at most one Unit") and therefore misstate a nested class failure.
        # Opaque SPARQL constraints are the inverse case: their author message
        # is the meaningful explanation and the diagnostic supplies evidence.
        if diagnostic is not None:
            message = getattr(self.raw, "author_message", None) or getattr(
                self.raw, "message", None
            )
        else:
            message = getattr(self.raw, "message", None) or getattr(
                self.raw, "author_message", None
            )
        value = getattr(self.raw, "value", None)
        # a message built from a `{$this}`-style sh:message template already
        # names the focus -- prepending value would just repeat it
        if message and value and str(value) not in str(message):
            text = f"{value} {message}"
        elif message:
            text = str(message)
        else:
            text = str(self.raw)
        # present only for a failed sh:sparql/custom SPARQL-based constraint;
        # surfaces the query/bindings/results instead of leaving it a dead end
        if diagnostic is not None:
            text = f"{text} [{_render_sparql_diagnostic(diagnostic)}]"
        return text

    def __str__(self) -> str:
        return self.reason()

    def __hash__(self):
        return hash(self.reason())


@dataclass(frozen=True)
class MissingEdge:
    """One cardinality deficit, in BuildingMOTIF terms.

    The BuildingMOTIF-side view of a pyshifty :class:`MissingObligation`: the
    RDF terms are rdflib nodes rather than pyshifty's N-Triples strings, so a
    caller can use them against the model graph directly.

    A deficit describes the edge that would close it. For example, "VAV1 needs 1
    more value along ``brick:hasPoint`` satisfying ``brick:Air_Flow_Sensor``" is
    ``node=VAV1``, ``path=brick:hasPoint``, ``missing=1``, with the qualifier
    naming the class.
    """

    #: the node the deficit is about
    node: Optional[Node]
    #: the path its values were counted along
    path: Optional[Node]
    #: the native algebraic constraint each counted value must satisfy. Left as
    #: pyshifty's own ``Constraint`` -- it is an algebra node, not an RDF term,
    #: and has no lossless rdflib equivalent.
    qualifier: Optional[object]
    #: how many more qualifying values are needed
    missing: int
    #: how many qualifying values the data supplied
    observed_count: int
    #: how many qualifying values the shape asked for
    required_count: int

    def __str__(self) -> str:
        node = self.node.n3() if self.node is not None else "the focus"
        path = self.path.n3() if self.path is not None else "an unnamed path"
        return (
            f"{node} needs {self.missing} more value(s) along {path} "
            f"({self.observed_count} of {self.required_count} present)"
        )


@dataclass
class RepairProposal:
    """One soundness-gated repair candidate for a single :class:`RepairWitness`.

    A proposal carries both representations requested by the design: the pyshifty
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
    outcome: Optional[GateOutcome]
    # provenance: "template:<name>", "pyshifty-candidate", "hand", or "blocked"
    origin: str
    # existing model nodes this proposal reuses rather than mints
    reused_nodes: Set[Node] = field(default_factory=set)
    # human-readable note (e.g. the BlockReason for a blocked proposal)
    note: str = ""
    # the pyshifty RepairSession this proposal came out of, so apply()/advance()
    # do not make the caller fetch it and hand it back. Excluded from equality
    # and repr: it is provenance, not part of the proposal's identity.
    _session: Optional[object] = field(default=None, repr=False, compare=False)

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
        shifty = require_shifty()

        return shifty.delta_from_graph(
            add=self.additions if len(self.additions) else None,
            delete=self.deletions if len(self.deletions) else None,
        )

    def _resolve_session(self, session):
        """The session to operate on: the caller's, else the one this proposal
        came from."""
        resolved = session if session is not None else self._session
        if resolved is None:
            raise ValueError(
                "this RepairProposal has no repair session to apply against; "
                "pass one explicitly (e.g. ctx.session)"
            )
        return resolved

    def apply(self, session=None) -> Graph:
        """Materialize ``G ⊕ ΔG`` as a fresh graph (does not mutate state).

        :param session: the pyshifty ``RepairSession`` to apply against.
            Defaults to the session this proposal was generated from, so the
            usual call is just ``proposal.apply()`` -- the caller no longer has
            to fetch ``ctx.session`` and hand it back to the object that came
            out of it.
        :raises ValueError: if no session was supplied and this proposal has
            none (only possible for one built by hand)
        """
        return self._resolve_session(session).apply(self.to_delta())

    def advance(self, session=None):
        """Return a new pyshifty repair session over ``G ⊕ ΔG``.

        :param session: as for :py:meth:`apply`; defaults to the session this
            proposal came from.
        """
        return self._resolve_session(session).advance(self.to_delta())


@dataclass(eq=False)
class RepairWitness:
    """The new per-failure validation-report unit: why one focus node failed one
    statement, together with its (template-guided, gated) repair proposals.

    Wraps a shifty ``Failure`` and defers candidate generation to the
    owning context's :class:`TemplateGuidedRepair` engine.

    ``eq=False`` keeps instances hashable by identity so they can live in the
    set-valued ``diffset`` that mirrors
    :class:`buildingmotif.dataclasses.validation.ValidationContext`.
    """

    focus: Optional[URIRef]
    # the raw pyshifty Failure
    witness: "ShiftyFailure"
    # back-reference to the owning context (holds the session + repair engine)
    context: "AlgebraicValidationContext"
    # the matching violation from the context's separate validate_algebra()
    # pass. It is the source of validation reasons; witness.summary() remains
    # repair information and is deliberately kept separate.
    violation: Optional["AlgebraicViolation"] = None
    # "stable-id" for the native (focus, statement_id, constraint_id) join.
    alignment: str = "unavailable"

    @cached_property
    def missing_edges(self) -> Tuple["MissingEdge", ...]:
        """The edges that would close this failure's cardinality deficits.

        Each entry says "``node`` needs ``missing`` more values along ``path``,
        each satisfying ``qualifier``" -- the building-terms statement of what
        is wrong, in the same vocabulary the model is written in, without
        walking a repair tree or reading a SHACL report.

        Empty for a failure that is not a cardinality deficit (a datatype or
        node-kind violation, say): those have a wrong value rather than a
        missing one, and are described by :attr:`validation_reasons`.
        """
        try:
            obligations = self.witness.missing_obligations()
        except Exception:
            logger.debug(
                "missing_obligations() raised for focus %s", self.focus, exc_info=True
            )
            return ()
        return tuple(
            MissingEdge(
                node=_engine_term_to_node(getattr(obligation, "node", None)),
                path=_engine_term_to_node(getattr(obligation, "path", None)),
                qualifier=getattr(obligation, "qualifier", None),
                missing=getattr(obligation, "missing", 0),
                observed_count=getattr(obligation, "observed_count", 0),
                required_count=getattr(obligation, "required_count", 0),
            )
            for obligation in obligations
        )

    @cached_property
    def repair_summary(self) -> Tuple:
        """Structured atoms summarizing the available repair operations.

        These are *not* validation findings. For example, a failed ``sh:class``
        constraint may summarize both deleting an existing edge (``CountHigh``)
        and adding a missing type (``CountLow``). Use :attr:`validation_reasons`
        or :meth:`reason` to explain why the focus failed.
        """
        try:
            summary = self.witness.summary()
            if isinstance(summary, (list, tuple)):
                return tuple(summary)
            return (summary,) if summary is not None else ()
        except Exception:
            logger.debug(
                "witness.summary() raised for focus %s", self.focus, exc_info=True
            )
            return ()

    def _get_summary(self):
        """Deprecated internal alias retained for repair-generation code."""
        return self.repair_summary

    @cached_property
    def validation_reasons(self) -> Tuple[AlgebraicReason, ...]:
        """Canonical validation findings for this focus/statement."""
        if self.violation is None:
            return ()
        return tuple(
            AlgebraicReason(reason, self.focus, self.target_shape)
            for reason in getattr(self.violation, "reasons", ())
        )

    @property
    def reasons(self) -> Tuple:
        """Raw pyshifty reasons, retained for compatibility.

        Prefer :attr:`validation_reasons`, whose entries expose provenance and
        implement ``reason()``.
        """
        return tuple(reason.raw for reason in self.validation_reasons)

    @property
    def target_shape(self) -> Optional[Node]:
        """The named shape whose statement this focus failed.

        Read off the repair witness itself (``shape_iri``, falling back to
        ``shape_name``), so it is available for *every* witness --
        including one whose :attr:`violation` could not be paired. Pairing is a
        join between two independently computed pyshifty results and can come up
        empty (:attr:`alignment` ``"unavailable"``); shape identity is carried on
        the witness and does not depend on it.

        ``None`` only when the failing shape is genuinely anonymous -- a shape
        written as a blank node has no IRI to report.
        """
        for attr in ("shape_iri", "shape_name"):
            shape = _engine_term_to_node(getattr(self.witness, attr, None))
            if shape is not None:
                return shape
        if self.violation is None:
            return None
        return _engine_term_to_node(getattr(self.violation, "shape_name", None))

    @property
    def statement_id(self) -> Optional[int]:
        """The failed statement's stable native identifier."""
        statement = getattr(self.witness, "statement_id", None)
        return statement if isinstance(statement, int) else None

    @property
    def constraint_id(self) -> Optional[int]:
        """The top-level algebraic constraint id shared with the violation."""
        value = getattr(self.witness, "constraint_id", None)
        return value if isinstance(value, int) else None

    @property
    def constraint_kind(self) -> Optional[object]:
        """The top-level algebraic constraint's enumerated semantic kind."""
        return getattr(self.witness, "constraint_kind", None)

    @property
    def constraint(self) -> Optional[object]:
        """The complete top-level algebraic constraint for this witness."""
        return getattr(self.witness, "constraint", None)

    @property
    def selector(self) -> Optional[object]:
        """The native algebra selector describing how the focus was chosen."""
        return getattr(self.witness, "selector", None)

    @property
    def target(self) -> Optional[object]:
        """The native rendered target of the failed algebra statement."""
        try:
            return self.witness.target
        except Exception:
            logger.debug(
                "target: could not read witness.target for focus %s",
                self.focus,
                exc_info=True,
            )
            return None

    @property
    def statement(self) -> Optional[int]:
        """The failed statement index, matching pyshifty's native surface."""
        value = getattr(self.witness, "statement", self.statement_id)
        return value if isinstance(value, int) else self.statement_id

    @property
    def graph(self) -> Graph:
        """The complete compiled graph against which this witness exists."""
        return self.context.data_graph

    @property
    def shapes_graph(self) -> Graph:
        """The complete algebra/schema graph used to validate this witness."""
        return self.context.shapes_graph

    @property
    def source_constraints(self) -> Tuple[object, ...]:
        """Native algebraic source constraints exposed by pyshifty, if any."""
        sources: List[object] = []
        for reason in self.validation_reasons:
            source = reason.source_constraint
            if source is not None and not any(source == seen for seen in sources):
                sources.append(source)
        return tuple(sources)

    @property
    def failed_component(self) -> Optional[URIRef]:
        """Legacy SHACL component metadata, only when pyshifty provides it."""
        components = {
            _engine_term_to_node(
                getattr(reason.raw, "source_constraint_component", None)
            )
            for reason in self.validation_reasons
        }
        components.discard(None)
        component = next(iter(components)) if len(components) == 1 else None
        return component if isinstance(component, URIRef) else None

    @property
    def violation_alignment(self) -> str:
        """How the repair witness was correlated with its validation result.

        pyshifty 0.2.8+ exposes a stable
        ``(focus, statement_id, constraint_id)`` key on both independently
        computed results. ``unavailable`` means that key was absent,
        non-unique, or did not match.
        """
        return self.alignment

    @property
    def failed_shape(self) -> Optional[Node]:
        """Legacy source-shape metadata, only when pyshifty provides it."""
        shapes = {
            _engine_term_to_node(getattr(reason.raw, "source_shape", None))
            for reason in self.validation_reasons
        }
        shapes.discard(None)
        return next(iter(shapes)) if len(shapes) == 1 else None

    @cached_property
    def repair_tree(self):
        """The pyshifty repair tree for this failure."""
        return self.witness.repair_tree()

    @property
    def is_blocked(self) -> bool:
        """True if no data repair is possible in scope (opaque SPARQL,
        identity, or coinductive back-edge)."""
        try:
            return bool(self.repair_tree.is_blocked)
        except Exception:
            logger.debug(
                "is_blocked: could not read repair_tree.is_blocked for focus %s",
                self.focus,
                exc_info=True,
            )
            return False

    @property
    def sparql_diagnostics(self) -> List[SparqlDiagnostic]:
        """The pyshifty ``SparqlDiagnostic`` for every SPARQL-based leaf of this
        failure that could be aligned with :attr:`reasons` -- query text, its
        ``$this``/prebound variables, and the solution rows it produced.

        Empty when this failure has no SPARQL-based leaf, or when
        :attr:`reasons` couldn't be aligned with :meth:`_get_summary` (a
        mismatched count means the two pyshifty calls diverged for this focus,
        so no enrichment is safer than a wrong pairing)."""
        diagnostics: List[SparqlDiagnostic] = []
        for reason in self.reasons:
            diagnostic = getattr(reason, "sparql_diagnostic", None)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return diagnostics

    def explain(self) -> str:
        """The repair tree rendered as indented text, with any SPARQL-based
        leaf's query/bindings/results appended (see :attr:`sparql_diagnostics`)
        -- otherwise a SPARQL constraint failure explains as an opaque dead
        end."""
        try:
            text = self.repair_tree.explain()
        except Exception:
            logger.debug(
                "explain: repair_tree.explain() raised for focus %s",
                self.focus,
                exc_info=True,
            )
            text = ""
        rendered = [_render_sparql_diagnostic(d) for d in self.sparql_diagnostics]
        if rendered:
            text = "\n".join([text, *rendered]) if text else "\n".join(rendered)
        return text

    def reason(self) -> str:
        """Human-readable validation reasons for this focus/statement.

        Repair alternatives live on :attr:`repair_summary`,
        :attr:`repair_tree`, and :meth:`explain`; they are intentionally not
        rendered as validation findings here.
        """
        if self.validation_reasons:
            return "; ".join(reason.reason() for reason in self.validation_reasons)
        return f"{self.focus} failed {self.target or ''}".strip()

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
       sub-shapes (:attr:`pyshifty.Hole.conforms_to_shapes`), build the value out
       structurally: reuse an existing node that already conforms, else mint a
       fresh node and recursively repair it against each sub-shape via
       pyshifty's repair-node-against operation (bounded by ``BUILD_FUEL``).
       This materializes deep, correctly-typed values (e.g. a ``sh:node`` over a
       multi-step path) that flat candidates cannot.
    2. **template reuse** — existing model nodes that are monomorphic to a
       library template (via :class:`~buildingmotif.template_matcher.TemplateMatcher`),
    3. **template mint** — a freshly grounded template instance, which also pulls
       in domain structure beyond the bare shape requirement,
    4. **pyshifty native candidates** — so we never do worse than stock pyshifty.

    Every assembled ``ΔG`` is gated; only sound deltas survive.

    The search budgets live in :class:`RepairConfig`.
    """

    def __init__(
        self,
        session,
        templates: List["Template"],
        model_graph: Graph,
        ontology_graph: Graph,
        config: Optional[RepairConfig] = None,
    ):
        self.session = session
        self.templates = templates
        self.model_graph = model_graph
        self.ontology_graph = ontology_graph
        self.config = config or RepairConfig()
        # memoized per-template monomorphism results and per-shape-set obligations
        self._reuse_cache: Dict[int, List[Node]] = {}
        self._required_types_cache: Dict[frozenset, Set[URIRef]] = {}
        self._parents_cache: Dict[Node, Set[Node]] = {}
        self._warned_truncation = False

    @property
    def candidate_limit(self) -> int:
        return self.config.candidate_limit

    @cached_property
    def _matching_ontology(self) -> Graph:
        """The ontology restricted to the triples the matcher reads."""
        return _ontology_projection(self.ontology_graph)

    def _parents(self, ntype: Node) -> Set[Node]:
        """Transitive ``rdfs:subClassOf`` ancestors of ``ntype`` (including
        itself), over the projected ontology; memoized."""
        if ntype not in self._parents_cache:
            self._parents_cache[ntype] = set(
                self._matching_ontology.transitive_objects(ntype, RDFS.subClassOf)
            )
        return self._parents_cache[ntype]

    # -- relevance filtering (keep only templates that can fill a hole) ----

    def _template_name_types(self, tmpl: "Template") -> Set[URIRef]:
        """The ``rdf:type``\\ s the template asserts directly on its ``name``
        parameter. Empty when ``name`` is typed only through a dependency -- in
        which case relevance is undecidable and we keep the template."""
        if "name" not in tmpl.parameters:
            return set()
        return {
            o
            for o in tmpl.body.objects(PARAM["name"], RDF.type)
            if isinstance(o, URIRef)
        }

    def _required_types(self, open_holes) -> Set[URIRef]:
        """The set of ``rdf:type`` classes the open ConformsTo holes demand.

        Recovered by synthesizing a probe value against each hole's shape-set
        (reusing :meth:`_synthesize_value`) and reading the types off the result.
        Returns the empty set when there are no ConformsTo holes *or* when an
        obligation cannot be built -- both mean "cannot filter", so the caller
        falls back to trying every (budgeted) template. Memoized by shape-set."""
        shape_sets = frozenset(
            tuple(sorted(self._hole_shapes(h)))
            for h in open_holes
            if self._hole_shapes(h)
        )
        if not shape_sets:
            return set()
        if shape_sets in self._required_types_cache:
            return self._required_types_cache[shape_sets]
        required: Set[URIRef] = set()
        for shape_ids in shape_sets:
            probe = _node_to_nt(_mint_uri())
            built = self._synthesize_value(
                probe, list(shape_ids), self.config.build_fuel
            )
            if built is None:
                # obligation not buildable in budget: do not filter on it
                self._required_types_cache[shape_sets] = set()
                return set()
            for t in built.objects(None, RDF.type):
                if isinstance(t, URIRef):
                    required.add(t)
        self._required_types_cache[shape_sets] = required
        return required

    def _template_relevant(self, tmpl: "Template", required: Set[URIRef]) -> bool:
        """Whether ``tmpl`` could plausibly fill a hole requiring ``required``.

        A template is relevant if the class it puts on ``name`` is *comparable*
        (in either direction along ``rdfs:subClassOf``) to a required class:
        a subclass can be **minted** to satisfy ``sh:class``, and a superclass can
        **reuse** an existing, more-specific model node that satisfies it. A
        template that does not type ``name`` directly is kept (undecidable)."""
        name_types = self._template_name_types(tmpl)
        if not name_types:
            return True
        for t in name_types:
            for r in required:
                if r == t or r in self._parents(t) or t in self._parents(r):
                    return True
        return False

    def _apply_template_budget(self, templates: List["Template"]) -> List["Template"]:
        """Apply ``max_templates`` to an already-relevance-filtered list, warning
        once if it still has to drop templates."""
        limit = self.config.max_templates
        if limit is None or len(templates) <= limit:
            return templates
        if not self._warned_truncation:
            self._warned_truncation = True
            warnings.warn(
                f"RepairConfig.max_templates={limit} is dropping "
                f"{len(templates) - limit} of {len(templates)} candidate repair "
                "templates that survived relevance filtering. The kept slice is "
                "by library order, not rank, so a better fix may be dropped. Pass "
                "a smaller, purpose-built library to repair_libraries, or raise "
                "max_templates (None = no limit) at the cost of a per-template "
                "monomorphism search.",
                stacklevel=2,
            )
        return templates[:limit]

    def _select_templates(self, open_holes) -> List["Template"]:
        """The templates to try for these holes: those relevant to the holes'
        required types (when determinable), then capped by ``max_templates``.

        Relevance filtering is what keeps the cap from binding arbitrarily -- a
        large ``repair_libraries`` is cut to the handful of templates that could
        actually fill the failing hole *before* the budget applies."""
        required = self._required_types(open_holes)
        candidates = (
            [t for t in self.templates if self._template_relevant(t, required)]
            if required
            else self.templates
        )
        return self._apply_template_budget(candidates)

    @property
    def _templates_to_try(self) -> List["Template"]:
        """All templates under the ``max_templates`` budget, without relevance
        filtering. Kept for the no-ConformsTo-holes fallback (and as the
        engine-wide view of the budget); the per-hole path uses
        :meth:`_select_templates`, which filters for relevance first."""
        return self._apply_template_budget(self.templates)

    # -- plan construction ------------------------------------------------

    def _base_specs(self, rt):
        """Yield (repeat_counts, any_choices) plan specs over the tree's
        decision points. ``Repeat`` nodes use their minimum count (>=1);
        ``Any`` nodes are enumerated as separate base plans."""
        shifty = require_shifty()

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
        ranges = [range(min(b, self.config.max_branches)) for (_, b) in anys]
        for combo in product(*ranges):
            yield (repeats, [(anys[i][0], combo[i]) for i in range(len(anys))])

    def _build_plan(self, spec):
        shifty = require_shifty()

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
        bindings: Dict[str, Node] = {}
        if "name" in tmpl.parameters:
            bindings["name"] = root
        else:
            return None
        for param in tmpl.parameters:
            if param == "name":
                continue
            bindings[param] = _mint_uri()
        filled = tmpl.substitute(bindings)
        if not filled.is_complete:
            return None
        return filled.to_graph()

    # -- recursive ConformsTo synthesis ----------------------------------

    @staticmethod
    def _hole_shapes(hole) -> List[int]:
        """The sub-shape ids a hole's value must conform to (``[]`` if none).

        Reads :attr:`pyshifty.Hole.conforms_to_shapes` (the multi-shape surface);
        ``conforms_to`` is the deprecated single-shape view and is not used.
        """
        try:
            return list(hole.conforms_to_shapes or [])
        except Exception:
            logger.debug(
                "_hole_shapes: could not read hole.conforms_to_shapes", exc_info=True
            )
            return []

    def _first_conforming(self, hole, shape_ids: List[int]) -> Optional[str]:
        """Reuse-first: the first candidate term that *already* conforms to every
        required sub-shape (``repair_node_against`` returns ``None``)."""
        try:
            candidates = list(hole.candidates(self.candidate_limit))
        except Exception:
            logger.debug("_first_conforming: hole.candidates() raised", exc_info=True)
            return None
        for cand in candidates:
            try:
                if all(
                    self.session.repair_node_against(cand, sid) is None
                    for sid in shape_ids
                ):
                    return cand
            except Exception:
                logger.debug(
                    "_first_conforming: repair_node_against(%s) raised",
                    cand,
                    exc_info=True,
                )
                continue
        return None

    def _fill_leaf(self, hole) -> Tuple[Optional[str], Graph]:
        """Fill a value-type / constant leaf hole: reuse-first candidate (e.g.
        the required ``rdf:type`` constant), else a freshly minted node."""
        try:
            candidates = list(hole.candidates(self.candidate_limit))
        except Exception:
            logger.debug("_fill_leaf: hole.candidates() raised", exc_info=True)
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
                logger.debug(
                    "_synthesize_value: repair_node_against(%s, shape=%s) raised",
                    node_nt,
                    sid,
                    exc_info=True,
                )
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
        shifty = require_shifty()

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
            logger.debug("_synthesize_tree: rt.instantiate(plan) raised", exc_info=True)
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
            logger.debug(
                "_synthesize_tree: rt.instantiate(bound plan) raised", exc_info=True
            )
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
                    _node_to_nt(child), shapes, self.config.build_fuel
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
        # (model_graph, ontology) are fixed for the engine's lifetime, so a
        # template's reuse set is invariant across witnesses/plans -- memoize it.
        key = id(tmpl)
        if key in self._reuse_cache:
            return self._reuse_cache[key]
        found: List[Node] = []
        seen: Set[Node] = set()
        try:
            matcher = TemplateMatcher(self.model_graph, tmpl, self._matching_ontology)
            for mapping in matcher.mappings_iter():
                for building_node, template_node in mapping.items():
                    if template_node == PARAM["name"] and building_node not in seen:
                        seen.add(building_node)
                        found.append(building_node)
                if len(found) >= self.candidate_limit:
                    break
        except Exception:
            logger.debug(
                "_reuse_candidates: monomorphism search failed for template %s",
                getattr(tmpl, "name", tmpl),
                exc_info=True,
            )
            return found
        self._reuse_cache[key] = found
        return found

    def _fill_strategies(self, open_holes):
        """Yield (hole_id -> value_nt, extra_graph, origin, reused_set) bindings
        that bind *every* open hole, drawn from the four candidate sources."""
        hole_ids = [h.id for h in open_holes]

        # source 1: recursive ConformsTo synthesis (when holes carry sub-shapes)
        combo = self._recursive_combo(open_holes)
        if combo is not None:
            yield combo

        # source 2+3: templates (reuse, then mint), filtered to those relevant to
        # the holes' required types so the max_templates budget rarely binds
        for tmpl in self._select_templates(open_holes):
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

        # source 4: pyshifty native candidates (reuse-first), zipped per hole
        per_hole: Dict[int, List[str]] = {}
        for h in open_holes:
            try:
                per_hole[h.id] = list(h.candidates(self.candidate_limit))
            except Exception:
                logger.debug(
                    "_fill_strategies: hole.candidates() raised for hole %s",
                    getattr(h, "id", h),
                    exc_info=True,
                )
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
                yield (bindings, Graph(), "pyshifty-candidate", set())

    # -- the gate + assembly ---------------------------------------------

    def _gate(
        self, focus, additions: Graph, deletions: Graph, origin: str, reused: Set[Node]
    ) -> Optional[RepairProposal]:
        """Gate one ΔG; return a sound proposal or None."""
        shifty = require_shifty()

        if len(additions) == 0 and len(deletions) == 0:
            return None
        try:
            delta = shifty.delta_from_graph(
                add=additions if len(additions) else None,
                delete=deletions if len(deletions) else None,
            )
            outcome = self.session.gate(delta)
        except Exception:
            logger.debug(
                "_gate: shifty gate raised for focus %s (origin %s, +%d/-%d triples)",
                focus,
                origin,
                len(additions),
                len(deletions),
                exc_info=True,
            )
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
            _session=self.session,
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
                    _session=self.session,
                )
            ]

        proposals: List[RepairProposal] = []
        for spec in self._base_specs(rt):
            base_plan = self._build_plan(spec)
            try:
                inst = rt.instantiate(base_plan)
            except Exception:
                logger.debug(
                    "propose: rt.instantiate(base_plan) raised for focus %s",
                    focus,
                    exc_info=True,
                )
                continue
            open_holes = list(inst.open_holes)

            if not open_holes:
                # fully determined by the plan (e.g. a pure deletion repair)
                additions = _triples_to_graph(inst.delta.add)
                deletions = _triples_to_graph(inst.delta.delete)
                p = self._gate(focus, additions, deletions, "pyshifty-candidate", set())
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
                    logger.debug(
                        "propose: rt.instantiate(bound plan) raised for focus %s "
                        "(origin %s)",
                        focus,
                        origin,
                        exc_info=True,
                    )
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
    """Validation report built from pyshifty's algebraic + repair output.

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
    # Candidate libraries for template-guided repair. Defaults to *empty*, not
    # to the model's libraries: template guidance is opt-in via the
    # `repair_libraries` argument of `Model.validate` / `CompiledModel.validate`.
    # With no libraries the engine still proposes repairs, but only from
    # recursive synthesis and pyshifty's own candidates -- the template reuse
    # and mint sources contribute nothing.
    libraries: List["Library"] = field(default_factory=list)
    # search budgets for the repair engine (default: RepairConfig())
    repair_config: Optional[RepairConfig] = None

    def __post_init__(self):
        shifty = require_shifty()

        self.shapes_graph = _without_redundant_point_inverse_axioms(self.shapes_graph)
        # Turtle text, not the bare Graph -- see _shifty_shapes_input for why a
        # Graph object silently loses the prefixes any sh:sparql/sh:rule body
        # needs to resolve its query text.
        #
        # An *empty* shapes graph has to be omitted rather than passed along:
        # shifty rejects an explicitly supplied zero-triple shapes graph
        # ("explicit shapes graph is empty; omit the shapes argument or pass
        # None to use shapes embedded in the data graph") instead of reporting
        # vacuous conformance. Omitting it asks shifty to take the shapes from
        # the data graph, which is the same thing BuildingMOTIF means by an
        # empty shape-collection list. `PyshiftyBackend.validate`/`.infer` guard
        # this the same way.
        shapes_input = (
            _shifty_shapes_input(self.shapes_graph)
            if len(self.shapes_graph)  # type: ignore[arg-type]
            else None
        )
        self._shapes_input = shapes_input
        if shapes_input is None:
            # The data graph is also the shapes graph here, so it has to carry
            # its prefix declarations for any SHACL-SPARQL body inside it --
            # see _shifty_data_input.
            data_as_shapes = _shifty_data_input(self.data_graph)
            self._session = shifty.RepairSession(data_as_shapes, self.data_graph)
            self._algebra = shifty.validate_algebra(
                data_as_shapes,
                minimum_severity="violation",
            )
        else:
            self._session = shifty.RepairSession(shapes_input, self.data_graph)
            self._algebra = shifty.validate_algebra(
                self.data_graph,
                shapes_input,
                minimum_severity="violation",
            )
        # ontology used by the monomorphism search (class hierarchy lives here)
        self._ontology = self.shapes_graph + self.data_graph
        templates: List["Template"] = []
        for lib in self.libraries:
            try:
                templates.extend(lib.get_templates())
            except Exception:
                logger.debug(
                    "AlgebraicValidationContext: could not load templates from "
                    "library %s; skipping it for repair guidance",
                    getattr(lib, "name", lib),
                    exc_info=True,
                )
                continue
        self.engine = TemplateGuidedRepair(
            self._session,
            templates,
            self.data_graph,
            self._ontology,
            config=self.repair_config,
        )

    @classmethod
    def from_compiled(
        cls,
        shape_collections: List["ShapeCollection"],
        shapes_graph: Graph,
        data_graph: Graph,
        model: "Model",
        libraries: Optional[List["Library"]] = None,
        repair_config: Optional[RepairConfig] = None,
    ) -> "AlgebraicValidationContext":
        """Build a context from the graphs produced by
        :meth:`buildingmotif.shacl.PyshiftyBackend.validation_graphs`."""
        return cls(
            shape_collections,
            shapes_graph,
            copy_graph(data_graph),
            model,
            list(libraries or []),
            repair_config,
        )

    @property
    def session(self):
        """The underlying pyshifty repair session."""
        return self._session

    @cached_property
    def evidence_session(self):
        """A pyshifty ``EvidenceSession`` over the same data and shapes.

        Built lazily and kept for the life of the context, because constructing
        one parses and lowers the schema. Only :meth:`preview` needs it today,
        so a context that never previews a repair never pays for it.
        """
        shifty = require_shifty()

        shapes = (
            self._shapes_input if self._shapes_input is not None else self.data_graph
        )
        return shifty.EvidenceSession(shapes, self.data_graph)

    def preview(self, proposal: "RepairProposal"):
        """The validation run this model *would* have if ``proposal`` were applied.

        Answers "what does this repair actually fix?" without mutating anything
        and without rebuilding a context: the session keeps its own snapshot, so
        the current context stays valid and comparable afterwards.

        Use this instead of ``proposal.advance()`` when the question is whether
        to accept a proposal. ``advance()`` builds a whole new repair session
        over ``G ⊕ ΔG`` (and a caller then usually rebuilds the
        :class:`AlgebraicValidationContext` on top of it); ``preview`` reuses
        the prepared schema and returns just the run.

        A deletion takes its derivations with it: SHACL-AF rules are re-run over
        the *pre-inference* graph, so removing a triple also removes what that
        triple had inferred, rather than stranding it.

        :param proposal: the candidate repair to evaluate
        :type proposal: RepairProposal
        :return: the native ``shifty.EvidenceRun`` over ``G ⊕ ΔG``
        """
        return self.evidence_session.revalidate(proposal.to_delta())

    @property
    def algebra(self) -> object:
        """The complete native result returned by ``validate_algebra()``."""
        return self._algebra

    @property
    def violations(self) -> Tuple[AlgebraicViolation, ...]:
        """All native algebraic violations, independent of repair pairing."""
        return tuple(self._algebra.violations)  # type: ignore[return-value]

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
    def report(self) -> Graph:
        """Legacy-compatible W3C SHACL report graph.

        **This costs a second full validation pass.** The algebraic engine does
        not produce a W3C report as a by-product, so reading this re-runs
        ``shifty.validate()`` over the same data and shapes to synthesize one.
        It is a ``cached_property``, so the cost is paid once per context -- but
        contexts are meant to be re-created on every iteration of the
        validate/repair loop, so "once per context" can still mean once per
        iteration.

        Prefer :py:attr:`report_string` (free -- it comes straight off the
        algebra), :py:attr:`conforms`, or :py:attr:`witnesses` unless you
        specifically need W3C report *triples*.
        """
        import shifty  # type: ignore

        # `_shapes_input` is already None for an empty shapes graph -- see
        # __post_init__ for why that case must omit the argument rather than
        # pass an empty graph.
        if self._shapes_input is None:
            _, report_graph, _ = shifty.validate(
                _shifty_data_input(self.data_graph),
                minimum_severity="violation",
            )
        else:
            _, report_graph, _ = shifty.validate(
                self.data_graph,
                self._shapes_input,
                minimum_severity="violation",
            )
        return report_graph

    @staticmethod
    def _correlation_key(item: object, focus_attr: str) -> Optional[Tuple]:
        """Return pyshifty's stable validation/repair join key, if available."""
        focus = _focus_to_node(getattr(item, focus_attr, None))
        statement_id = getattr(item, "statement_id", None)
        constraint_id = getattr(item, "constraint_id", None)
        if statement_id is None or constraint_id is None:
            return None
        try:
            hash((focus, statement_id, constraint_id))
        except TypeError:
            return None
        return (focus, statement_id, constraint_id)

    @cached_property
    def _violations_by_key(self) -> Dict[Tuple, List[AlgebraicViolation]]:
        """Native violations indexed by their stable algebraic identity."""
        grouped: Dict[Tuple, List[AlgebraicViolation]] = defaultdict(list)
        for violation in self.violations:
            key = self._correlation_key(violation, "focus_node")
            if key is not None:
                grouped[key].append(violation)
        return dict(grouped)

    def _violation_for(
        self,
        witness: ShiftyFailure,
    ) -> Tuple[Optional[AlgebraicViolation], str]:
        """Pair a repair witness with its validation violation.

        The independently computed APIs are joined only by their shared native
        algebraic identity. A missing, unmatched, or non-unique key is never
        silently downgraded to positional correlation.
        """
        key = self._correlation_key(witness, "focus")
        if key is not None:
            matches = self._violations_by_key.get(key, [])
            if len(matches) == 1:
                return matches[0], "stable-id"
        return None, "unavailable"

    @cached_property
    def witnesses(self) -> List[RepairWitness]:
        """The violation horizon: one :class:`RepairWitness` per failing
        ``(focus, statement)``. Empty iff the graph conforms."""
        out: List[RepairWitness] = []
        raw_witnesses = self._session.witnesses()
        for w in raw_witnesses:
            focus = _focus_to_node(w.focus)
            violation, alignment = self._violation_for(w)
            out.append(
                RepairWitness(focus, w, self, violation, alignment)  # type: ignore
            )
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

    def get_broken_entities(self) -> Set[Union[URIRef, str]]:
        return {focus or "Model" for focus in self.diffset}

    def get_diffs_for_entity(self, entity: Optional[URIRef]) -> Set[RepairWitness]:
        """The failures recorded against a single focus node. Returns a set, to
        match
        :meth:`buildingmotif.dataclasses.validation.ValidationContext.get_diffs_for_entity`
        (:class:`RepairWitness` hashes by identity)."""
        return self.diffset.get(entity, set())

    def get_reasons_with_severity(
        self, severity: Union[URIRef, str]
    ) -> Dict[Optional[URIRef], List[AlgebraicReason]]:
        """Group the algebra's findings by focus, keeping only the reasons at the
        given severity (``SH.Violation``/``"Violation"``, ``SH.Warning``, or
        ``SH.Info``). Mirrors
        :meth:`buildingmotif.dataclasses.validation.ValidationContext.get_reasons_with_severity`;
        each value is the list of legacy-compatible pyshifty reasons at that severity."""
        if isinstance(severity, URIRef):
            severity_name = str(severity).split("#")[-1]
        else:
            severity_name = str(severity)
        if severity_name not in {"Violation", "Warning", "Info"}:
            raise ValueError(
                f"Invalid severity: {severity}. Must be one of "
                "SH.Violation, SH.Warning, or SH.Info"
            )
        out: Dict[Optional[URIRef], List[AlgebraicReason]] = defaultdict(list)
        for v in self._algebra.violations:
            focus = _focus_to_node(v.focus_node)
            target_shape = _engine_term_to_node(getattr(v, "shape_name", None))
            for reason in v.reasons:
                if str(reason.severity).split("#")[-1] == severity_name:
                    out[focus].append(AlgebraicReason(reason, focus, target_shape))
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
