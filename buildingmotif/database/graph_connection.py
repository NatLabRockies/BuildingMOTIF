import logging
import uuid
from pathlib import Path
from typing import List, Optional, Set, Tuple, Union
from urllib.parse import quote, unquote

from pyoxigraph import NamedNode
from rdflib.graph import Graph, Store, URIRef, plugin
from rdflib.term import Node

PROJECT_DIR = Path(__file__).resolve().parent
GRAPH_IDENTIFIER_PREFIX = "urn:buildingmotif:graph:"
INVALID_URIREF_PREFIX = "urn:buildingmotif:invalid-uri:"


class BuildingMOTIFOxigraphGraph(Graph):
    """RDFLib Graph wrapper that keeps invalid URIRefs round-trippable.

    RDFLib can carry URIRefs with spaces or other invalid IRI code points, but
    Oxigraph correctly rejects them. BuildingMOTIF has historically allowed
    those terms for generated template parameters, so encode them only at the
    storage boundary and decode them when reading triples back through RDFLib.
    """

    def add(self, triple):  # type: ignore[no-untyped-def]
        return super().add(tuple(_encode_term(term) for term in triple))

    def addN(self, quads):  # type: ignore[no-untyped-def]
        encoded_quads = (
            (
                _encode_term(subject),
                _encode_term(predicate),
                _encode_term(object_),
                context,
            )
            for subject, predicate, object_, context in quads
        )
        return super().addN(encoded_quads)

    def remove(self, triple):  # type: ignore[no-untyped-def]
        return super().remove(tuple(_encode_term(term) for term in triple))

    def triples(self, triple):  # type: ignore[no-untyped-def]
        encoded_triple = tuple(_encode_term(term) for term in triple)
        for subject, predicate, object_ in super().triples(encoded_triple):
            yield (
                _decode_term(subject),
                _decode_term(predicate),
                _decode_term(object_),
            )


class GraphConnection:
    """Manages graph connection."""

    def __init__(
        self,
        graph_store_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Constructor for the database and datastore.

        :param graph_store_path: directory for a persistent Oxigraph store. If
            omitted, an in-memory Oxigraph store is used.
        """
        self.logger = logging.getLogger(__name__)
        self.graph_store_path = Path(graph_store_path) if graph_store_path else None

        self.store = plugin.get("Oxigraph", Store)()

        if self.graph_store_path is not None:
            self.logger.debug("Opening Oxigraph store at %s", self.graph_store_path)
            self.graph_store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store.open(str(self.graph_store_path), create=False)
        else:
            self.logger.debug("Opening in-memory Oxigraph store")

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
        g = BuildingMOTIFOxigraphGraph(
            self.store, identifier=self._to_store_identifier(identifier)
        )
        self.store.add_graph(g)
        for prefix, namespace in graph.namespaces():
            g.bind(prefix, namespace, override=False)
        new_triples = [(s, p, o, g) for (s, p, o) in graph]
        g.addN(new_triples)

        return g

    def get_all_graph_identifiers(self) -> List[str]:
        """Get all graph identifiers.

        :return: all graph identifiers
        :rtype: List[str]
        """
        graph_identifiers = [
            self._from_store_identifier(c.identifier) for c in self.store.contexts()
        ]
        return graph_identifiers

    def get_graph(self, identifier: str) -> Graph:
        """Get graph by identifier. Graph has triples, no context.

        :param identifier: graph identifier
        :type identifier: str
        :return: graph without context
        :rtype: Graph
        """
        result = BuildingMOTIFOxigraphGraph(
            self.store, identifier=self._to_store_identifier(identifier)
        )
        # we used to bind prefixes here but this is unnecessary because
        # the graph has prefixes bound when it is saved

        return result

    def replace_graph_contents(self, graph: Graph) -> Tuple[str, Graph]:
        """Write ``graph`` into a brand-new named graph (copy-on-write).

        This never mutates an existing named graph. The caller atomically
        adopts the new contents by flipping its stored ``graph_id`` pointer to
        the returned identifier (a single SQL update that commits with the
        session); on failure or rollback the previous graph is still intact.
        The previously referenced graph becomes an orphan that
        :py:meth:`collect_garbage` reclaims.

        :param graph: the new contents to write
        :type graph: Graph
        :return: the new graph identifier and its store-backed view
        :rtype: Tuple[str, Graph]
        """
        new_identifier = str(uuid.uuid4())
        view = self.create_graph(new_identifier, graph)
        return new_identifier, view

    def collect_garbage(self, live_graph_ids: Set[str]) -> List[str]:
        """Delete UUID-identified named graphs not present in ``live_graph_ids``.

        Only graphs whose identifier is a UUID are considered for deletion:
        those are the graphs BuildingMOTIF creates for models, shape
        collections, and template bodies. OntoEnv-managed ontology graphs are
        keyed by their ontology IRI, so they are excluded by construction and
        never reclaimed here.

        :param live_graph_ids: identifiers that are still referenced and must
            be kept
        :type live_graph_ids: Set[str]
        :return: identifiers of the graphs that were reclaimed
        :rtype: List[str]
        """
        reclaimed: List[str] = []
        for identifier in self.get_all_graph_identifiers():
            if not _is_uuid(identifier):
                continue
            if identifier in live_graph_ids:
                continue
            self.delete_graph(identifier)
            reclaimed.append(identifier)
        return reclaimed

    def delete_graph(self, identifier: str) -> None:
        """Delete graph.

        :param identifier: graph identifier
        :type identifier: str
        """
        self.logger.debug(f"Deleting graph: '{identifier}'")
        g = BuildingMOTIFOxigraphGraph(
            self.store, identifier=self._to_store_identifier(identifier)
        )
        self.store.remove((None, None, None), g)
        self.store.remove_graph(g)

    def close(self) -> None:
        """Close the graph store."""
        self.store.close()

    @staticmethod
    def _to_store_identifier(identifier: str) -> URIRef:
        return URIRef(f"{GRAPH_IDENTIFIER_PREFIX}{quote(identifier, safe='')}")

    @staticmethod
    def _from_store_identifier(identifier: URIRef) -> str:
        identifier_str = str(identifier)
        if identifier_str.startswith(GRAPH_IDENTIFIER_PREFIX):
            return unquote(identifier_str[len(GRAPH_IDENTIFIER_PREFIX) :])
        return identifier_str


def _encode_term(term: Optional[Node]) -> Optional[Node]:
    if isinstance(term, URIRef) and not _is_valid_iri(term):
        return URIRef(f"{INVALID_URIREF_PREFIX}{quote(str(term), safe='')}")
    return term


def _decode_term(term: Node) -> Node:
    if isinstance(term, URIRef) and str(term).startswith(INVALID_URIREF_PREFIX):
        return URIRef(unquote(str(term)[len(INVALID_URIREF_PREFIX) :]))
    return term


def _is_valid_iri(term: URIRef) -> bool:
    try:
        NamedNode(str(term))
    except ValueError:
        return False
    return True


def _is_uuid(value: str) -> bool:
    """Return True if ``value`` is a UUID string, as generated for the graph
    identifiers of models, shape collections, and template bodies."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True
