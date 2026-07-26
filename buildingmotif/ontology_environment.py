from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, Optional, Tuple, Union

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
        options: Dict[str, Any] = {
            "offline": offline,
            "strict": strict,
            "search_directories": [str(path) for path in search_directories or []],
        }
        store = (
            BuildingMOTIFGraphStore(graph_connection)
            if graph_connection is not None
            else None
        )

        # ontoenv >=0.6.0a8 deprecated the `init_from_store` flag in favour of
        # explicit lifecycle entry points. The two cases are not the same call:
        #
        # - persistent: `connect` *is* "create it or reuse the saved index",
        #   which is what `create_or_use_cached` meant, and it also handles a
        #   pre-populated store itself (sync="auto" reads graph contents only
        #   on first encounter, or when the store reports a change).
        # - temporary: there is no saved index to reuse, so the scan of an
        #   already-populated store has to be asked for outright.
        if path is None:
            self.env = OntoEnv(graph_store=store, temporary=True, **options)
            if store is not None:
                # what init_from_store did at construction time
                self.env.refresh_from_store(full=True)
        else:
            self.env = OntoEnv.connect(str(path), graph_store=store, **options)

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
        return self.env.copy_graph(ontology)

    def closure_copy(
        self, ontology: str, recursion_depth: int = -1
    ) -> Tuple[rdflib.Graph, list[str]]:
        """Materialize the imports closure into a mutable ``rdflib.Graph``.

        Use this only when the caller will *mutate* the result. When the graph
        is read but never written -- or, as in the two library-loading call
        sites, discarded entirely in favour of the names -- prefer
        :py:meth:`closure_view`, which copies nothing.
        """
        graph, names = self.env.copy_closure(
            ontology,
            rewrite_sh_prefixes=False,
            recursion_depth=recursion_depth,
        )
        return graph, list(names)

    def closure_names(self, ontology: str, recursion_depth: int = -1) -> list[str]:
        """The names in an ontology's imports closure, without building a graph.

        Callers that only need to know *what is in* the closure should use this
        rather than discarding :py:meth:`closure_copy`'s first return value.
        Measured on the Brick 1.4 closure (15 graphs, ~155k triples), three
        reps, on ontoenv 0.6.0a9:

        - ``list_closure``  -- 0.000s, 0.000s, 0.000s
        - ``copy_closure``  -- 3.972s, 3.530s, 3.623s  (materializes every time)
        - ``get_closure``   -- 2.053s, 2.077s, 2.059s  (read-only view)

        All three report the same 15 names, so for a name lookup this is free
        where the alternatives cost seconds.

        The ``get_closure`` shape changed between releases and the numbers are
        worth keeping for that reason: on a8 it read 8.846s, 0.000s, 0.000s --
        one expensive eager index build, then cached. On a9 it is a flat ~2.05s
        per call. Cheaper on first use, but no longer free on repeat, so
        "bind once and query many times" is not the win it was on a8.
        """
        return list(self.env.list_closure(ontology, recursion_depth=recursion_depth))

    def iter_closure_triples(
        self, ontology: str, recursion_depth: int = -1
    ) -> Iterable[Tuple[rdflib.term.Node, rdflib.term.Node, rdflib.term.Node]]:
        return self.env.iter_closure_triples(ontology, recursion_depth=recursion_depth)

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

    def import_dependencies(
        self,
        graph: rdflib.Graph,
        recursion_depth: int = -1,
        fetch_missing: bool = False,
    ) -> list[str]:
        return list(
            self.env.import_dependencies(
                graph,
                recursion_depth=recursion_depth,
                fetch_missing=fetch_missing,
            )
        )

    def missing_imports(
        self, ontology_or_graph: Optional[Union[str, rdflib.Graph]] = None
    ) -> list[str]:
        return list(self.env.missing_imports(ontology_or_graph))

    def ontology_names(self) -> list[str]:
        return list(self.env.get_ontology_names())

    def knows(self, ontology: str) -> bool:
        """Whether ontoenv can resolve ``ontology``.

        ontoenv >=0.6.0a8 implements the container protocol, so this is a
        direct lookup rather than building the full name list to test one
        membership. It is also *broader* than ``ontology in ontology_names()``:
        ``in`` resolves aliases and source URLs as well as canonical names, so
        an ontology known under a different spelling is correctly reported as
        present instead of being needlessly re-added.
        """
        return ontology in self.env

    def ensure_and_get_closure(
        self,
        graph: rdflib.Graph,
        graph_name: str,
        recursion_depth: int = -1,
        fetch_imports: bool = False,
    ) -> rdflib.Graph:
        """Ensure graph is registered in ontoenv, then return its import closure.

        The returned graph is materialized and mutable. ontoenv's read-only
        ``get_closure`` view would avoid the copy, but as of 0.6.0a9 a
        ``ViewGraph`` deliberately **does not subclass rdflib.Graph**, so it
        cannot be handed back through this signature.

        :raises Exception: if the closure cannot be resolved.
        """
        if not self.knows(graph_name):
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
