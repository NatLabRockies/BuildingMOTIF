from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional, Tuple, Union

import rdflib
from ontoenv import OntoEnv

from buildingmotif.database.graph_connection import _is_uuid

if TYPE_CHECKING:
    from buildingmotif.database.graph_connection import GraphConnection


class OntologyImportsNotFound(Exception):
    """Raised when one or more owl:imports cannot be resolved."""

    def __init__(self, imports: Iterable[str]):
        self.imports = sorted(set(imports))

    def __str__(self) -> str:
        return "Could not resolve ontology imports: " + ", ".join(self.imports)


class OntologyEnvironment:
    """BuildingMOTIF's OntoEnv integration point."""

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        search_directories: Optional[Iterable[Union[str, Path]]] = None,
        offline: bool = False,
        strict: bool = False,
        graph_connection: Optional["GraphConnection"] = None,
    ) -> None:
        kwargs = {
            "offline": offline,
            "strict": strict,
            "search_directories": [str(path) for path in search_directories or []],
        }
        if graph_connection is not None:
            kwargs["graph_store"] = BuildingMOTIFGraphStore(graph_connection)
            kwargs["init_from_store"] = True
        if path is None:
            kwargs["temporary"] = True
        else:
            kwargs["path"] = str(path)
            kwargs["create_or_use_cached"] = True

        self.env = OntoEnv(**kwargs)

    def close(self) -> None:
        self.env.close()

    def add(
        self,
        source: Union[str, Path, rdflib.Graph],
        fetch_imports: bool = True,
        overwrite: bool = True,
    ) -> str:
        return self.env.add(
            str(source) if isinstance(source, Path) else source,
            overwrite=overwrite,
            fetch_imports=fetch_imports,
        )

    def graph_copy(self, ontology: str) -> rdflib.Graph:
        if hasattr(self.env, "copy_graph"):
            return self.env.copy_graph(ontology)
        return self._copy_graph(self.env.get_graph(ontology))

    def closure_copy(
        self, ontology: str, recursion_depth: int = -1
    ) -> Tuple[rdflib.Graph, list[str]]:
        # Always use get_closure rather than copy_closure: in ontoenv 0.6.x,
        # copy_closure reads from the native Rust store and bypasses the custom
        # graph_store adapter, returning empty graphs when BuildingMOTIF's store
        # is in use. get_closure returns a ClosureGraphView that correctly routes
        # through the adapter.
        graph, names = self.env.get_closure(ontology, recursion_depth=recursion_depth)
        return self._copy_graph(graph), list(names)

    def iter_closure_triples(
        self, ontology: str, recursion_depth: int = -1
    ) -> Iterable[Tuple[rdflib.term.Node, rdflib.term.Node, rdflib.term.Node]]:
        # iter_closure_triples has the same graph_store bypass issue as copy_closure;
        # iterate over get_closure instead.
        graph, _ = self.env.get_closure(ontology, recursion_depth=recursion_depth)
        return iter(graph)

    def dependencies_copy(
        self,
        graph: rdflib.Graph,
        graph_name: Optional[str] = None,
        recursion_depth: int = -1,
        fetch_missing: bool = False,
    ) -> Tuple[rdflib.Graph, list[str]]:
        result, names = self.env.get_dependencies(
            graph,
            graph_name=graph_name,
            recursion_depth=recursion_depth,
            fetch_missing=fetch_missing,
        )
        return self._copy_graph(result), list(names)

    def missing_imports(
        self, ontology_or_graph: Optional[Union[str, rdflib.Graph]] = None
    ) -> list[str]:
        return list(self.env.missing_imports(ontology_or_graph))

    def ontology_names(self) -> list[str]:
        return list(self.env.get_ontology_names())

    def ensure_and_get_closure(
        self,
        graph: rdflib.Graph,
        graph_name: str,
        recursion_depth: int = -1,
        fetch_imports: bool = False,
    ) -> rdflib.Graph:
        """Ensure graph is registered in ontoenv, then return its import closure.

        :raises Exception: if the closure cannot be resolved.
        """
        if graph_name not in self.ontology_names():
            self.add(graph, fetch_imports=fetch_imports, overwrite=True)
        closure, _ = self.closure_copy(graph_name, recursion_depth=recursion_depth)
        return closure

    @staticmethod
    def graph_name(graph: rdflib.Graph) -> Optional[str]:
        name = graph.value(
            predicate=rdflib.RDF.type, object=rdflib.OWL.Ontology, any=False
        )
        return str(name) if isinstance(name, rdflib.URIRef) else None

    @staticmethod
    def _copy_graph(graph: rdflib.Graph) -> rdflib.Graph:
        copied = rdflib.Graph()
        copied += graph
        return copied


class BuildingMOTIFGraphStore:
    """OntoEnv graph_store adapter backed by BuildingMOTIF's graph connection."""

    def __init__(self, graph_connection: "GraphConnection") -> None:
        self.graph_connection = graph_connection

    def add_graph(self, iri: str, graph: rdflib.Graph, overwrite: bool = False) -> None:
        if iri in self.graph_ids():
            if not overwrite:
                return
            self.remove_graph(iri)
        self.graph_connection.create_graph(iri, graph)

    def get_graph(self, iri: str) -> rdflib.Graph:
        return self.graph_connection.get_graph(iri)

    def remove_graph(self, iri: str) -> None:
        self.graph_connection.delete_graph(iri)

    def graph_ids(self) -> list[str]:
        return [
            gid
            for gid in self.graph_connection.get_all_graph_identifiers()
            if not _is_uuid(gid)
        ]

    def size(self) -> dict[str, int]:
        graph_ids = self.graph_ids()
        return {
            "num_graphs": len(graph_ids),
            "num_triples": sum(
                len(self.graph_connection.get_graph(graph_id)) for graph_id in graph_ids
            ),
        }
