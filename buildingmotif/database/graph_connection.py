import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from rdflib.graph import Graph, Store, URIRef, plugin
from rdflib.namespace import NamespaceManager

if TYPE_CHECKING:
    from buildingmotif.building_motif.building_motif import BuildingMotifEngine

PROJECT_DIR = Path(__file__).resolve().parent


class GraphConnection:
    """Manages graph connection."""

    def __init__(
        self,
        engine: "BuildingMotifEngine",
        db_identifier: Optional[str] = "buildingmotif_store",
    ) -> None:
        """Constructor for the database and datastore.

        :param engine: database engine
        :type engine: Engine
        :param db_identifier: defaults to "buildingmotif_store"
        :type db_identifier: Optional[str], optional
        """
        self.logger = logging.getLogger(__name__)

        self.store = plugin.get("SQLAlchemy", Store)(
            identifier=db_identifier, engine=engine
        )

        # avoids the warnings raised by the issue in https://github.com/RDFLib/rdflib/issues/1880
        # Eventually will require rdflib-sqlalchemy to support the 'override' keyword
        def fixed_bind(self, prefix: str, namespace: URIRef, override: bool):
            self.store.bind(prefix, namespace)

        setattr(NamespaceManager, "_store_bind", fixed_bind)

        self.logger.debug("Creating tables for graph storage")
        self.store.create_all()

    def create_graph(self, identifier: str, graph: Graph) -> Graph:
        """Create a graph in the database.

        :param identifier: identifier of graph
        :type identifier: str
        :param graph: graph to add, defaults to None
        :type graph: Graph
        :return: graph added
        :rtype: Graph
        """
        self.logger.debug(
            f"Creating graph: '{identifier}' in database with: {len(graph)} triples"
        )
        g = Graph(self.store, identifier=identifier)
        new_triples = [(s, o, p, g) for (s, o, p) in graph]
        g.addN(new_triples)

        return g

    def add_graph(
        self, identifier: str, graph: Graph, overwrite: bool = False
    ) -> Graph:
        """Add or replace the contents of a graph in the database."""
        g = Graph(self.store, identifier=identifier)
        if overwrite:
            self.logger.debug(f"Overwriting graph: '{identifier}'")
            self.store.remove((None, None, None), g)
        elif identifier in self.get_all_graph_identifiers() and len(g) > 0:
            self.logger.debug(
                f"Graph '{identifier}' already exists and overwrite=False; leaving as-is"
            )
            return g

        new_triples = [(s, o, p, g) for (s, o, p) in graph]
        g.addN(new_triples)
        return g

    def get_all_graph_identifiers(self) -> List[str]:
        """Get all graph identifiers.

        :return: all graph identifiers
        :rtype: List[str]
        """
        graph_identifiers = [str(c) for c in self.store.contexts()]
        return graph_identifiers

    def get_graph(self, identifier: str) -> Graph:
        """Get graph by identifier. Graph has triples, no context.

        :param identifier: graph identifier
        :type identifier: str
        :return: graph without context
        :rtype: Graph
        """
        result = Graph(self.store, identifier=identifier)
        # we used to bind prefixes here but this is unnecessary because
        # the graph has prefixes bound when it is saved

        return result

    def delete_graph(self, identifier: str) -> None:
        """Delete graph.

        :param identifier: graph identifier
        :type identifier: str
        """
        self.logger.debug(f"Deleting graph: '{identifier}'")
        g = Graph(self.store, identifier=identifier)
        self.store.remove((None, None, None), g)

    def remove_graph(self, identifier: str) -> None:
        """Alias for OntoEnv's graph-store interface."""
        self.delete_graph(identifier)

    def graph_ids(self) -> List[str]:
        """Alias for OntoEnv's graph-store interface."""
        return self.get_all_graph_identifiers()

    def size(self) -> dict[str, int]:
        """Return the number of stored graphs and triples."""
        graph_identifiers = self.get_all_graph_identifiers()
        return {
            "num_graphs": len(graph_identifiers),
            "num_triples": sum(
                len(self.get_graph(identifier)) for identifier in graph_identifiers
            ),
        }
