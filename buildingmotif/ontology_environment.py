from pathlib import Path
from typing import Iterable, Optional, Tuple, Union

import rdflib
from ontoenv import OntoEnv


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
    ) -> None:
        kwargs = {
            "offline": offline,
            "strict": strict,
            "search_directories": [str(path) for path in search_directories or []],
        }
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
        if hasattr(self.env, "copy_closure"):
            return self.env.copy_closure(ontology, recursion_depth=recursion_depth)
        graph, names = self.env.get_closure(ontology, recursion_depth=recursion_depth)
        return self._copy_graph(graph), list(names)

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
