import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Type

import pyshacl  # type: ignore
from rdflib import Graph

from buildingmotif.namespaces import BRICK, OWL, SH

if TYPE_CHECKING:
    from buildingmotif.dataclasses.shape_collection import ShapeCollection


ValidationResult = Tuple[bool, Graph, str]
DEFAULT_SHACL_ENGINE = "pyshifty"
_SHACL_ENGINE_ALIASES = {"shifty": "pyshifty"}


def normalize_shacl_engine(engine: Optional[str]) -> str:
    """Return the canonical SHACL engine name or raise for unsupported engines."""
    if not engine:
        return DEFAULT_SHACL_ENGINE
    engine = _SHACL_ENGINE_ALIASES.get(engine, engine)
    if engine not in _SHACL_BACKENDS:
        choices = ", ".join(sorted(_SHACL_BACKENDS))
        raise ValueError(
            f"Unsupported SHACL engine {engine!r}. Choose one of: {choices}"
        )
    return engine


def require_shifty():
    """Import and return the ``shifty`` module (from the ``pyshifty`` package).

    ``pyshifty`` is a required dependency of BuildingMOTIF, so this normally just
    returns the already-imported module. It exists so that, if ``shifty`` is
    somehow missing from the environment, callers get a single clear, actionable
    error that names the distribution -- rather than a bare
    ``ModuleNotFoundError: No module named 'shifty'`` surfacing from deep inside
    the repair engine.
    """
    try:
        import shifty  # type: ignore

        return shifty
    except ImportError as exc:  # pragma: no cover - required dependency
        raise ImportError(
            "The 'shifty' SHACL engine requires the 'pyshifty' package, which is "
            "a required dependency of BuildingMOTIF but is not importable in this "
            "environment. Reinstall BuildingMOTIF (e.g. `poetry install`) to "
            "restore it."
        ) from exc


def _shifty_shapes_input(shape_graph: Graph) -> bytes:
    """Serialize a shapes graph to Turtle text before handing it to ``shifty``.

    ``shifty``'s Python binding lowers an ``rdflib.Graph`` argument to
    N-Triples before passing it to the native engine (see ``shifty/__init__.py``
    ``_to_rdf_input``) -- and N-Triples has no ``@prefix`` declarations at all.
    A ``sh:sparql``/``sh:rule`` body resolves ``sh:prefixes`` against *the
    prefixes declared in the document shifty parses*, so a shapes graph handed
    over as a bare ``Graph`` object silently loses the ability to resolve any
    prefixed name inside its embedded SPARQL query text -- the constraint or
    rule then just never fires, with **no error and no diagnostic**, because a
    query it cannot resolve is treated as an unsupported feature the engine
    ignores by default. Passing Turtle text instead of a ``Graph`` keeps the
    (already-declared) prefix table shifty's own parser depends on.

    A *data* graph usually carries no SPARQL query literals and so needs none of
    this -- but it does when it is handed over with no separate shapes argument,
    because then it is also the shapes graph. :func:`_shifty_data_input` covers
    that case.

    Verified empirically against pyshifty 0.2.7: an ``sh:rule``/``sh:construct``
    with a query body that uses a prefixed name (e.g. ``ex:Foo``) infers 0
    triples when the shapes graph is passed as a ``Graph`` object, and the
    correct triples when passed as this function's Turtle text -- identical
    input graph, only the wire representation differs.

    Turtle text alone isn't a complete fix: BuildingMOTIF's storage layer
    (``GraphConnection``/``BuildingMOTIFOxigraphGraph``) doesn't persist a
    source file's ``@prefix`` bindings at all -- only triples -- so a shapes
    graph loaded from a library and read back out has already lost them by
    the time it reaches this function, regardless of how it's serialized here.
    :func:`buildingmotif.namespaces.bind_prefixes` re-declares BuildingMOTIF's
    own well-known prefixes (``brick:``, ``s223:``, ``qudt:``, ...), which
    covers a constraint written against one of BuildingMOTIF's own ontologies
    -- the realistic case, and the same mechanism
    :meth:`buildingmotif.dataclasses.library.Library.load` already applies for
    the same reason. It does **not** cover a fully custom, downstream-defined
    namespace: that prefix binding is gone the moment its shape collection is
    persisted, and restoring it would mean capturing/round-tripping namespace
    bindings through the storage layer, well beyond this function.

    Returns ``bytes``, not ``str``: shifty's ``_to_rdf_input`` treats a bare
    ``str`` as a filesystem path first (``pathlib.Path(s).is_file()``) and
    only falls back to raw Turtle text if that path doesn't exist. A large
    serialized shapes graph is long enough to raise ``OSError: File name too
    long`` from that existence check on some platforms, rather than failing
    over gracefully -- ``bytes`` skips the path-guessing branch entirely and
    is always treated as raw Turtle.
    """
    from buildingmotif.namespaces import bind_prefixes
    from buildingmotif.utils import copy_graph

    prefixed = copy_graph(shape_graph)
    bind_prefixes(prefixed)
    return prefixed.serialize(format="turtle", encoding="utf-8")


def _resolved_shape_graph(
    shape_collections: List["ShapeCollection"],
    error_on_missing_imports: bool,
    resolved_shapes: Optional[Graph],
) -> Graph:
    """The shapes graph, with ``owl:imports`` resolved.

    ``resolved_shapes`` is the whole answer when it is given: validating
    against a manifest takes the shapes graph from
    :py:meth:`Manifest.shapes_graph`, whose members already include everything
    they import. The per-collection path remains for an explicit list of shape
    collections, which carries no such guarantee and so still has to resolve
    each collection's imports.
    """
    if resolved_shapes is not None:
        return resolved_shapes
    graph = Graph()
    for shape_collection in shape_collections:
        graph += shape_collection.resolve_imports(
            error_on_missing_imports=error_on_missing_imports
        ).graph
    return graph


def _has_sparql_bodies(graph: Graph) -> bool:
    """Whether ``graph`` carries SHACL-SPARQL bodies.

    A ``sh:select``/``sh:construct``/``sh:ask`` body resolves its prefixed names
    against the prefix declarations of the document shifty parses, so a graph
    holding one has to reach shifty with those declarations intact. A graph
    holding none has nothing to resolve and can be handed over untouched.
    """
    return any(
        (None, predicate, None) in graph
        for predicate in (SH.select, SH.construct, SH.ask)
    )


def _shifty_data_input(data_graph: Graph):
    """The data graph, prepared for a call that passes shifty *no* shapes graph.

    With no shapes argument the data graph is also the shapes graph, so any
    SHACL-SPARQL body inside it has to resolve its prefixed names -- which means
    it has to arrive carrying its prefix declarations, exactly as
    :func:`_shifty_shapes_input` guarantees for a real shapes graph.

    This matters because BuildingMOTIF's storage layer does not persist a source
    file's ``@prefix`` bindings. ``Library.from_ontology("Brick-full.ttl")`` runs
    SHACL inference over a Brick graph that has already lost its ``ref:``
    binding, and Brick's own ``sh:construct`` rules and ``sh:select``
    constraints use ``ref:hasExternalReference``. Under pyshifty < 0.4.1 those
    queries were **silently skipped** -- the rules never fired and nothing said
    so; 0.4.1 raises ``Prefix not found`` instead, which is what surfaced it.

    Re-binding costs a copy and a serialization (~1.3s on Brick, against ~3.3s
    for the inference itself), so it is only paid for a graph that actually
    carries SPARQL bodies. An ordinary model graph has none and is passed
    through as-is.
    """
    if _has_sparql_bodies(data_graph):
        return _shifty_shapes_input(data_graph)
    return data_graph


@dataclass
class ValidationGraphs:
    data_graph: Graph
    shape_graph: Optional[Graph]
    context_graph: Graph


class ShaclBackend:
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        raise NotImplementedError

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        raise NotImplementedError

    def compile(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        return self.infer(data_graph, shape_graph)

    def compile_model_graph(
        self, model_graph: Graph, shape_collections: List["ShapeCollection"]
    ) -> Graph:
        from buildingmotif.utils import copy_graph, skolemize_shapes

        shape_graph = Graph()
        for shape_collection in shape_collections:
            shape_graph += shape_collection.graph

        compiled_graph = copy_graph(model_graph).skolemize()
        # keep the source triples: some engines return only what they inferred
        source_graph = copy_graph(compiled_graph)
        return (
            self.compile(compiled_graph, skolemize_shapes(shape_graph)) + source_graph
        )

    def validation_graphs(
        self,
        compiled_graph: Graph,
        shape_collections: List["ShapeCollection"],
        error_on_missing_imports: bool = True,
        resolved_shapes: Optional[Graph] = None,
    ) -> ValidationGraphs:
        """
        :param resolved_shapes: a shapes graph that needs no import resolution
            -- see :func:`_resolved_shape_graph`. Defaults to resolving each
            shape collection's imports separately.
        :type resolved_shapes: Optional[Graph]
        """
        from buildingmotif.utils import (
            copy_graph,
            rewrite_shape_graph,
            skolemize_shapes,
        )

        graph = copy_graph(compiled_graph)
        graph += _resolved_shape_graph(
            shape_collections, error_on_missing_imports, resolved_shapes
        )

        graph = rewrite_shape_graph(graph)
        graph.remove((None, OWL.imports, None))
        graph = skolemize_shapes(graph)
        graph.remove((None, OWL.imports, None))
        return ValidationGraphs(graph, None, graph)

    def validate_compiled_model(
        self,
        compiled_graph: Graph,
        shape_collections: List["ShapeCollection"],
        error_on_missing_imports: bool = True,
        resolved_shapes: Optional[Graph] = None,
    ) -> Tuple[ValidationResult, Graph]:
        graphs = self.validation_graphs(
            compiled_graph,
            shape_collections,
            error_on_missing_imports,
            resolved_shapes=resolved_shapes,
        )
        return (
            self.validate(graphs.data_graph, graphs.shape_graph),
            graphs.context_graph,
        )


class PyshaclBackend(ShaclBackend):
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        pre_compile_length = len(data_graph)  # type: ignore
        pyshacl.validate(
            data_graph=data_graph,
            shacl_graph=shape_graph,
            ont_graph=shape_graph,
            advanced=True,
            inplace=True,
            js=True,
            allow_warnings=True,
        )
        post_compile_length = len(data_graph)  # type: ignore

        attempts = 3
        while attempts > 0 and post_compile_length != pre_compile_length:
            pre_compile_length = len(data_graph)  # type: ignore
            pyshacl.validate(
                data_graph=data_graph,
                shacl_graph=shape_graph,
                ont_graph=shape_graph,
                advanced=True,
                inplace=True,
                js=True,
                allow_warnings=True,
            )
            post_compile_length = len(data_graph)  # type: ignore
            attempts -= 1
        return data_graph - (shape_graph or Graph())

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        data_graph = data_graph + (shape_graph or Graph())
        return pyshacl.validate(
            data_graph,
            shacl_graph=shape_graph,
            ont_graph=shape_graph,
            advanced=True,
            js=True,
            allow_warnings=True,
        )  # type: ignore


class TopQuadrantBackend(PyshaclBackend):
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        try:
            from brick_tq_shacl.topquadrant_shacl import infer as tq_infer

            return tq_infer(data_graph, shape_graph or Graph())  # type: ignore
        except ImportError:
            logging.info(
                "TopQuadrant SHACL engine not available. Using PySHACL instead."
            )
            return super().infer(data_graph, shape_graph)

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        try:
            from brick_tq_shacl.topquadrant_shacl import (
                validate as tq_validate,  # type: ignore
            )

            return tq_validate(data_graph, shape_graph or Graph())  # type: ignore
        except ImportError:
            logging.info(
                "TopQuadrant SHACL engine not available. Using PySHACL instead."
            )
            return super().validate(data_graph, shape_graph)


class PyshiftyBackend(ShaclBackend):
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        shifty = require_shifty()

        if shape_graph is None or len(shape_graph) == 0:  # type: ignore
            return shifty.infer(_shifty_data_input(data_graph)).graph()  # type: ignore
        return shifty.infer(data_graph, _shifty_shapes_input(shape_graph)).graph()  # type: ignore

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        shifty = require_shifty()

        if shape_graph is None or len(shape_graph) == 0:  # type: ignore
            return shifty.validate(  # type: ignore
                _shifty_data_input(data_graph),
                minimum_severity="violation",
            )
        return shifty.validate(  # type: ignore
            data_graph,
            _shifty_shapes_input(shape_graph),
            minimum_severity="violation",
        )

    def compile(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        compiled_graph = self.infer(data_graph, shape_graph) - (shape_graph or Graph())
        return _remove_redundant_point_inverses(compiled_graph)

    def compile_model_graph(
        self, model_graph: Graph, shape_collections: List["ShapeCollection"]
    ) -> Graph:
        # NOTE: unlike ShaclBackend.compile_model_graph, we deliberately do *not*
        # skolemize the model or the shapes here. shifty operates on blank nodes
        # natively (it does its own internal handling), and skolemizing would
        # change the terms it reports in witnesses -- so the graphs handed to
        # shifty must keep their original blank nodes.
        from buildingmotif.utils import copy_graph

        shape_graph = Graph()
        for shape_collection in shape_collections:
            shape_graph += shape_collection.graph

        # keep the source triples: shifty returns only the inferred closure
        source_graph = copy_graph(model_graph)
        return self.compile(copy_graph(model_graph), shape_graph) + source_graph

    def validation_graphs(
        self,
        compiled_graph: Graph,
        shape_collections: List["ShapeCollection"],
        error_on_missing_imports: bool = True,
        resolved_shapes: Optional[Graph] = None,
    ) -> ValidationGraphs:
        # As in compile_model_graph, the shapes and data are handed to shifty
        # un-skolemized and un-rewritten (no sh:node inlining): shifty consumes
        # the native SHACL algebra directly rather than a flattened shape graph.
        from buildingmotif.utils import copy_graph

        shape_graph = _resolved_shape_graph(
            shape_collections, error_on_missing_imports, resolved_shapes
        )

        data_graph = copy_graph(compiled_graph)
        return ValidationGraphs(data_graph, shape_graph, shape_graph)


def _remove_redundant_point_inverses(graph: Graph) -> Graph:
    for point, _, entity in list(graph.triples((None, BRICK.isPointOf, None))):
        if (entity, BRICK.hasPoint, point) in graph:
            graph.remove((point, BRICK.isPointOf, entity))
    return graph


_SHACL_BACKENDS: Dict[str, Type[ShaclBackend]] = {
    "pyshacl": PyshaclBackend,
    "topquadrant": TopQuadrantBackend,
    "pyshifty": PyshiftyBackend,
}

# Derived from the registry so adding a new engine only requires one dict entry.
SHACL_ENGINES = frozenset(_SHACL_BACKENDS)


def get_shacl_backend(engine: Optional[str]) -> ShaclBackend:
    return _SHACL_BACKENDS[normalize_shacl_engine(engine)]()
