import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Type

import pyshacl  # type: ignore
from rdflib import Graph

from buildingmotif.namespaces import BRICK, OWL

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
        return self.compile(compiled_graph, skolemize_shapes(shape_graph))

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


class PyshiftyBackend(ShaclBackend):
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        import shifty  # type: ignore

        if shape_graph is None or len(shape_graph) == 0:  # type: ignore
            return shifty.infer(data_graph).graph()  # type: ignore
        return shifty.infer(data_graph, shape_graph).graph()  # type: ignore

    def validate(
        self, data_graph: Graph, shape_graph: Optional[Graph] = None
    ) -> ValidationResult:
        import shifty  # type: ignore

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
        compiled_graph = self.infer(data_graph, shape_graph) - (shape_graph or Graph())
        return _remove_redundant_point_inverses(compiled_graph)

    def compile_model_graph(
        self, model_graph: Graph, shape_collections: List["ShapeCollection"]
    ) -> Graph:
        from buildingmotif.utils import copy_graph

        shape_graph = Graph()
        for shape_collection in shape_collections:
            shape_graph += shape_collection.graph

        return self.compile(copy_graph(model_graph), shape_graph)

    def validation_graphs(
        self,
        compiled_graph: Graph,
        shape_collections: List["ShapeCollection"],
        error_on_missing_imports: bool = True,
    ) -> ValidationGraphs:
        from buildingmotif.utils import copy_graph

        shape_graph = Graph()
        for shape_collection in shape_collections:
            shape_graph += shape_collection.resolve_imports(
                error_on_missing_imports=error_on_missing_imports
            ).graph

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
