import logging
import os
import secrets
from abc import ABC, abstractmethod
from importlib.util import find_spec
from pathlib import Path
from typing import Optional, Tuple

import pyshacl  # type: ignore
from rdflib import BNode, Graph

from buildingmotif.namespaces import CONSTRAINT, RDF, SH


def _maybe_dump_pyshifty_graphs(
    stage: str,
    data_graph: Graph,
    shape_graph: Optional[Graph] = None,
) -> None:
    """
    Optionally dump the exact graphs provided to pyshifty when debugging.

    Set BUILDINGMOTIF_PYSHIFTY_DEBUG_DIR to a writable directory to enable this.
    """
    debug_dir = os.getenv("BUILDINGMOTIF_PYSHIFTY_DEBUG_DIR")
    if not debug_dir:
        return

    try:
        out_dir = Path(debug_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dump_id = secrets.token_hex(4)
        data_path = out_dir / f"{stage}-{dump_id}-data.ttl"
        meta_path = out_dir / f"{stage}-{dump_id}-meta.txt"
        latest_data_path = out_dir / f"{stage}-latest-data.ttl"
        latest_meta_path = out_dir / f"{stage}-latest-meta.txt"
        data_graph.serialize(destination=str(data_path), format="turtle")
        data_graph.serialize(destination=str(latest_data_path), format="turtle")

        meta_lines = [
            f"stage={stage}",
            f"dump_id={dump_id}",
            f"data_triples={len(data_graph)}",
            f"data_path={data_path}",
            f"latest_data_path={latest_data_path}",
        ]

        if shape_graph is not None:
            shape_path = out_dir / f"{stage}-{dump_id}-shape.ttl"
            latest_shape_path = out_dir / f"{stage}-latest-shape.ttl"
            shape_graph.serialize(destination=str(shape_path), format="turtle")
            shape_graph.serialize(destination=str(latest_shape_path), format="turtle")
            meta_lines.extend(
                [
                    f"shape_triples={len(shape_graph)}",
                    f"shape_path={shape_path}",
                    f"latest_shape_path={latest_shape_path}",
                ]
            )

        meta_text = "\n".join(meta_lines) + "\n"
        meta_path.write_text(meta_text)
        latest_meta_path.write_text(meta_text)
        logging.warning("Dumped pyshifty %s graphs to %s", stage, meta_path)
    except Exception as err:
        logging.warning("Failed to dump pyshifty %s graphs: %s", stage, err)


def _graph_uses_buildingmotif_constraints(graph: Optional[Graph]) -> bool:
    """Return True when the graph uses BuildingMOTIF custom SHACL components."""
    if graph is None:
        return False

    constraint_ns = str(CONSTRAINT)
    for subj, pred, obj in graph:
        if str(subj).startswith(constraint_ns):
            return True
        if str(pred).startswith(constraint_ns):
            return True
        if str(obj).startswith(constraint_ns):
            return True
    return False


def _pyshifty_report_needs_pyshacl_fallback(report_graph: Graph) -> bool:
    """
    Pyshifty can return reports whose source shapes are anonymous placeholders,
    which makes downstream diff interpretation impossible. Fall back to PySHACL
    for a richer report in that case.
    """
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        source_shape = report_graph.value(result, SH.sourceShape)
        if isinstance(source_shape, BNode):
            return True
    return False


class BaseSHACLBackend(ABC):
    name = "base"

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate(
        self,
        data_graph: Graph,
        shape_graph: Optional[Graph] = None,
    ) -> Tuple[bool, Graph, str]:
        raise NotImplementedError

    @abstractmethod
    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        raise NotImplementedError


class PySHACLBackend(BaseSHACLBackend):
    name = "pyshacl"

    @classmethod
    def is_available(cls) -> bool:
        return True

    def validate(
        self,
        data_graph: Graph,
        shape_graph: Optional[Graph] = None,
    ) -> Tuple[bool, Graph, str]:
        data_graph = data_graph + (shape_graph or Graph())
        return pyshacl.validate(
            data_graph,
            shacl_graph=shape_graph,
            ont_graph=shape_graph,
            advanced=True,
            js=True,
            allow_warnings=True,
        )  # type: ignore

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


class PyShiftyBackend(BaseSHACLBackend):
    name = "pyshifty"

    @classmethod
    def is_available(cls) -> bool:
        return find_spec("shifty") is not None

    def validate(
        self,
        data_graph: Graph,
        shape_graph: Optional[Graph] = None,
    ) -> Tuple[bool, Graph, str]:
        import shifty  # type: ignore

        if _graph_uses_buildingmotif_constraints(shape_graph):
            logging.info(
                "BuildingMOTIF custom constraint components are not handled by "
                "pyshifty; using PySHACL instead."
            )
            return PySHACLBackend().validate(data_graph, shape_graph)

        _maybe_dump_pyshifty_graphs("validate", data_graph, shape_graph or Graph())
        valid, report_g, report_str = shifty.validate(
            data_graph,
            shape_graph or Graph(),
            run_inference=True,
        )
        if valid or not _pyshifty_report_needs_pyshacl_fallback(report_g):
            return valid, report_g, report_str
        logging.info(
            "Pyshifty produced an incomplete validation report; using "
            "PySHACL to generate interpretable diagnostics."
        )
        return PySHACLBackend().validate(data_graph, shape_graph)

    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        import shifty  # type: ignore

        if _graph_uses_buildingmotif_constraints(shape_graph):
            logging.info(
                "BuildingMOTIF custom constraint components are not handled by "
                "pyshifty inference; using PySHACL instead."
            )
            return PySHACLBackend().infer(data_graph, shape_graph)

        _maybe_dump_pyshifty_graphs("infer", data_graph, shape_graph or Graph())
        inferred_graph = shifty.infer(
            data_graph,
            shape_graph or Graph(),
            union=False,
        )
        return data_graph + inferred_graph


class TopQuadrantBackend(BaseSHACLBackend):
    name = "topquadrant"

    @classmethod
    def is_available(cls) -> bool:
        return find_spec("brick_tq_shacl") is not None

    def validate(
        self,
        data_graph: Graph,
        shape_graph: Optional[Graph] = None,
    ) -> Tuple[bool, Graph, str]:
        from brick_tq_shacl.topquadrant_shacl import (
            validate as tq_validate,  # type: ignore
        )

        return tq_validate(data_graph, shape_graph or Graph())  # type: ignore

    def infer(self, data_graph: Graph, shape_graph: Optional[Graph] = None) -> Graph:
        from brick_tq_shacl.topquadrant_shacl import infer as tq_infer

        return tq_infer(data_graph, shape_graph or Graph())  # type: ignore


def shacl_backend_available(engine: Optional[str]) -> bool:
    if engine == "topquadrant":
        return TopQuadrantBackend.is_available()
    if engine == "pyshifty":
        return PyShiftyBackend.is_available()
    return PySHACLBackend.is_available()


def get_shacl_backend(engine: Optional[str] = "topquadrant") -> BaseSHACLBackend:
    requested_name = engine or "pyshifty"

    if requested_name == "topquadrant":
        if TopQuadrantBackend.is_available():
            return TopQuadrantBackend()
        logging.info("TopQuadrant SHACL engine not available. Using PySHACL instead.")
        return PySHACLBackend()

    if requested_name == "pyshifty":
        if PyShiftyBackend.is_available():
            return PyShiftyBackend()
        logging.info("PyShifty SHACL engine not available. Using PySHACL instead.")
        return PySHACLBackend()

    return PySHACLBackend()


def shacl_validate(
    data_graph: Graph,
    shape_graph: Optional[Graph] = None,
    engine: Optional[str] = "topquadrant",
) -> Tuple[bool, Graph, str]:
    return get_shacl_backend(engine).validate(data_graph, shape_graph)


def shacl_inference(
    data_graph: Graph,
    shape_graph: Optional[Graph] = None,
    engine: Optional[str] = "topquadrant",
) -> Graph:
    return get_shacl_backend(engine).infer(data_graph, shape_graph)
