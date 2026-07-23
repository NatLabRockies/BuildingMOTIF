import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

import pyshacl  # type: ignore
from rdflib import Graph

from buildingmotif.namespaces import OWL

if TYPE_CHECKING:
    from buildingmotif.dataclasses.shape_collection import ShapeCollection


ValidationResult = Tuple[bool, Graph, str]
SHACL_ENGINES = {"pyshacl", "topquadrant", "shifty"}


def normalize_shacl_engine(engine: Optional[str]) -> str:
    """Return the canonical SHACL engine name or raise for unsupported engines."""
    if not engine:
        return "pyshacl"
    if engine not in SHACL_ENGINES:
        choices = ", ".join(sorted(SHACL_ENGINES))
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
    ) -> ValidationGraphs:
        from buildingmotif.utils import (
            copy_graph,
            rewrite_shape_graph,
            skolemize_shapes,
        )

        graph = copy_graph(compiled_graph)
        for shape_collection in shape_collections:
            graph += shape_collection.resolve_imports(
                error_on_missing_imports=error_on_missing_imports
            ).graph

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
    ) -> Tuple[ValidationResult, Graph]:
        graphs = self.validation_graphs(
            compiled_graph, shape_collections, error_on_missing_imports
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


class ShiftyBackend(ShaclBackend):
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        shifty = require_shifty()

        if shape_graph is None or len(shape_graph) == 0:  # type: ignore
            return shifty.infer(data_graph).graph()  # type: ignore
        return shifty.infer(data_graph, shape_graph).graph()  # type: ignore

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        shifty = require_shifty()

        if shape_graph is None or len(shape_graph) == 0:  # type: ignore
            return shifty.validate(  # type: ignore
                data_graph,
                minimum_severity="violation",
            )
        return shifty.validate(  # type: ignore
            data_graph,
            shape_graph,
            minimum_severity="violation",
        )

    def compile(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        return self.infer(data_graph, shape_graph) - (shape_graph or Graph())

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
    ) -> ValidationGraphs:
        # As in compile_model_graph, the shapes and data are handed to shifty
        # un-skolemized and un-rewritten (no sh:node inlining): shifty consumes
        # the native SHACL algebra directly rather than a flattened shape graph.
        from buildingmotif.utils import copy_graph

        shape_graph = Graph()
        for shape_collection in shape_collections:
            shape_graph += shape_collection.resolve_imports(
                error_on_missing_imports=error_on_missing_imports
            ).graph

        data_graph = copy_graph(compiled_graph)
        return ValidationGraphs(data_graph, shape_graph, shape_graph)


def get_shacl_backend(engine: Optional[str]) -> ShaclBackend:
    engine = normalize_shacl_engine(engine)
    if engine == "pyshacl":
        return PyshaclBackend()
    if engine == "topquadrant":
        return TopQuadrantBackend()
    if engine == "shifty":
        return ShiftyBackend()
    raise AssertionError(f"Unhandled SHACL engine {engine!r}")
