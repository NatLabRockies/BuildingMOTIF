import importlib
import inspect
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import rdflib

from buildingmotif.database.errors import LibraryNotFound
from buildingmotif.utils import copy_graph

if TYPE_CHECKING:
    from buildingmotif import BuildingMOTIF


class BuildingMOTIFGraphStore:
    """Expose BuildingMOTIF's ontology libraries through OntoEnv's graph-store API."""

    def __init__(self, bm: "BuildingMOTIF") -> None:
        self.bm = bm
        self.logger = logging.getLogger(__name__)

    def add_graph(self, iri: str, graph: rdflib.Graph, overwrite: bool = False) -> None:
        from buildingmotif.dataclasses.library import Library
        from buildingmotif.dataclasses.shape_collection import ShapeCollection

        try:
            db_library = self.bm.table_connection.get_db_library_by_name(iri)
        except LibraryNotFound:
            db_library = self.bm.table_connection.create_db_library(iri)
            shape_collection = ShapeCollection.load(db_library.shape_collection.id)
            shape_collection.add_graph(graph)
            return

        shape_collection = ShapeCollection.load(db_library.shape_collection.id)
        if not overwrite and len(shape_collection.graph) > 0:
            return

        if overwrite:
            Library._clear_library(db_library)
            self.bm.graph_connection.add_graph(
                db_library.shape_collection.graph_id, graph, overwrite=True
            )
        else:
            shape_collection.add_graph(graph)

    def get_graph(self, iri: str) -> rdflib.Graph:
        from buildingmotif.dataclasses.shape_collection import ShapeCollection

        try:
            db_library = self.bm.table_connection.get_db_library_by_name(iri)
        except LibraryNotFound:
            for (
                db_shape_collection
            ) in self.bm.table_connection.get_all_db_shape_collections():
                shape_collection = ShapeCollection.load(db_shape_collection.id)
                if str(shape_collection.graph_name) == iri:
                    return shape_collection.graph
            raise

        return ShapeCollection.load(db_library.shape_collection.id).graph

    def remove_graph(self, iri: str) -> None:
        try:
            db_library = self.bm.table_connection.get_db_library_by_name(iri)
        except LibraryNotFound:
            return
        self.bm.table_connection.delete_db_library(db_library.id)

    def graph_ids(self) -> List[str]:
        graph_ids = []
        for db_library in self.bm.table_connection.get_all_db_libraries():
            graph_ids.append(db_library.name)
        return graph_ids

    def size(self) -> Dict[str, int]:
        graphs = [self.get_graph(iri) for iri in self.graph_ids()]
        return {
            "num_graphs": len(graphs),
            "num_triples": sum(len(graph) for graph in graphs),
        }


class OntoEnvDependencyResolver:
    """Delegate ontology dependency closure and rewriting to OntoEnv."""

    def __init__(
        self, bm: "BuildingMOTIF", ontoenv_kwargs: Optional[Dict[str, Any]] = None
    ) -> None:
        self.bm = bm
        self.logger = logging.getLogger(__name__)
        self.graph_store = BuildingMOTIFGraphStore(bm)
        kwargs = {"temporary": True, "graph_store": self.graph_store}
        if ontoenv_kwargs:
            kwargs.update(ontoenv_kwargs)

        if kwargs.get("graph_store") is not self.graph_store:
            raise ValueError("Do not override graph_store when using BuildingMOTIF")
        if kwargs.get("recreate") or kwargs.get("create_or_use_cached"):
            raise ValueError(
                "OntoEnv graph_store mode cannot be combined with recreate or create_or_use_cached"
            )

        self._ontoenv_kwargs = kwargs
        self._env = None
        self._env_is_stale = True

    def _build_ontoenv_kwargs(self) -> Dict[str, Any]:
        ontoenv_module = importlib.import_module("ontoenv")
        kwargs = dict(self._ontoenv_kwargs)
        ontoenv_signature = inspect.signature(ontoenv_module.OntoEnv)
        if "init_from_store" in ontoenv_signature.parameters:
            kwargs["init_from_store"] = True
        return kwargs

    @property
    def env(self):
        if self._env is None or self._env_is_stale:
            self._close_env()
            ontoenv_module = importlib.import_module("ontoenv")
            self._env = ontoenv_module.OntoEnv(**self._build_ontoenv_kwargs())
            self._env_is_stale = False
        return self._env

    def _close_env(self) -> None:
        if self._env is None:
            return
        close = getattr(self._env, "close", None)
        if callable(close):
            close()
        self._env = None

    def invalidate(self) -> None:
        """Mark the cached OntoEnv instance stale after graph-store mutations."""
        self._env_is_stale = True

    def rebuild_from_graph_store(self) -> None:
        """Recreate OntoEnv so it re-reads the current graph-store contents."""
        if self._env is not None:
            refresh = getattr(self._env, "refresh_from_store", None)
            if callable(refresh):
                refresh()
                self._env_is_stale = False
                return
        self.invalidate()
        _ = self.env

    def register_ontology(
        self, iri: str, graph: rdflib.Graph, overwrite: bool = False
    ) -> None:
        self.graph_store.add_graph(iri, graph, overwrite=overwrite)
        self.invalidate()

    def remove_ontology(self, iri: str) -> None:
        self.graph_store.remove_graph(iri)
        self.invalidate()

    def _get_dependencies(
        self,
        graph: rdflib.Graph,
        graph_name: Optional[str] = None,
        recursion_depth: int = -1,
        error_on_missing_imports: bool = True,
    ) -> Tuple[Optional[rdflib.Graph], List[str]]:
        try:
            dependency_graph, closure = self.env.get_dependencies(
                graph,
                graph_name=graph_name,
                recursion_depth=recursion_depth,
                fetch_missing=False,
            )
        except Exception as err:
            if error_on_missing_imports:
                raise
            self.logger.warning(
                "OntoEnv could not resolve imports for %s (%s)",
                graph_name or "<anonymous graph>",
                err,
            )
            return None, []

        return dependency_graph, closure

    @staticmethod
    def _ontology_ids_present(graph: rdflib.Graph) -> set[str]:
        return {
            str(ontology_iri)
            for ontology_iri in graph.subjects(
                predicate=rdflib.RDF.type, object=rdflib.OWL.Ontology
            )
        }

    def resolve_imports(
        self,
        graph: rdflib.Graph,
        graph_name: Optional[str] = None,
        recursion_depth: int = -1,
        error_on_missing_imports: bool = True,
    ) -> Tuple[rdflib.Graph, List[str]]:
        dependency_graph, closure = self._get_dependencies(
            graph,
            graph_name=graph_name,
            recursion_depth=recursion_depth,
            error_on_missing_imports=error_on_missing_imports,
        )
        resolved = copy_graph(graph)
        if dependency_graph is not None:
            resolved += dependency_graph
        return resolved, closure or []

    def get_dependency_graphs(
        self,
        graph: rdflib.Graph,
        graph_name: Optional[str] = None,
        recursion_depth: int = -1,
        error_on_missing_imports: bool = True,
    ) -> Tuple[rdflib.Graph, Dict[str, rdflib.Graph]]:
        resolved, closure = self.resolve_imports(
            graph,
            graph_name=graph_name,
            recursion_depth=recursion_depth,
            error_on_missing_imports=error_on_missing_imports,
        )
        dependency_graphs: Dict[str, rdflib.Graph] = {}
        present_ontologies = self._ontology_ids_present(graph)
        for iri in closure:
            if iri in present_ontologies:
                continue
            try:
                dependency_graphs[iri] = copy_graph(self.env.get_graph(iri))
            except Exception as err:
                if error_on_missing_imports:
                    raise
                self.logger.warning(
                    "OntoEnv resolved %s in the closure but could not retrieve it (%s)",
                    iri,
                    err,
                )
        return resolved, dependency_graphs

    def get_closure(
        self,
        graph: rdflib.Graph,
        graph_name: Optional[str] = None,
        recursion_depth: int = -1,
        error_on_missing_imports: bool = True,
    ) -> List[str]:
        _dependency_graph, closure = self._get_dependencies(
            graph,
            graph_name=graph_name,
            recursion_depth=recursion_depth,
            error_on_missing_imports=error_on_missing_imports,
        )
        return sorted(set(closure or []))

    def get_missing_ontologies(
        self, graphs: List[rdflib.Graph], recursion_depth: int = -1
    ) -> List[str]:
        del recursion_depth
        missing: set[str] = set()
        for graph in graphs:
            missing.update(self.env.missing_imports(graph))
        return sorted(missing)

    def close(self) -> None:
        self._close_env()


def build_dependency_resolver(
    bm: "BuildingMOTIF",
    resolver_name: str = "ontoenv",
    ontoenv_kwargs: Optional[Dict[str, Any]] = None,
):
    if resolver_name == "ontoenv":
        return OntoEnvDependencyResolver(bm, ontoenv_kwargs=ontoenv_kwargs)
    raise ValueError(
        "BuildingMOTIF now requires the 'ontoenv' dependency resolver; "
        f"got '{resolver_name}'."
    )
