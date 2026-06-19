from pathlib import Path

import pytest
from rdflib import RDF, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import FOAF

from buildingmotif.database.graph_connection import GraphConnection

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SMALL_OFFICE_BRICK_TTL = FIXTURES_DIR / "smallOffice_brick.ttl"
DB_FILE = FIXTURES_DIR / "smallOffice.db"


@pytest.fixture
def graph_connection():
    graph_connection = GraphConnection()
    yield graph_connection
    graph_connection.close()


def test_create_graph(graph_connection):
    g = Graph()
    hannahs_personhood = (URIRef("http://example.org/hannah"), RDF.type, FOAF.Person)
    g.add(hannahs_personhood)

    res = graph_connection.create_graph("my_graph", g)

    assert isomorphic(res, g)
    assert graph_connection.get_all_graph_identifiers() == ["my_graph"]


def test_create_empty_graph(graph_connection):
    g = Graph()

    graph_connection.create_graph("my_graph", g)

    assert graph_connection.get_all_graph_identifiers() == ["my_graph"]


def test_get_graph(graph_connection):
    g = Graph()
    hannahs_personhood = (URIRef("http://example.org/hannah"), RDF.type, FOAF.Person)
    g.add(hannahs_personhood)
    graph_connection.create_graph("my_graph", g)

    res = graph_connection.get_graph("my_graph")

    assert isomorphic(res, g)


@pytest.mark.skip(reason="a non-existant graph will just come back empty")
def test_get_graph_does_not_exist(graph_connection):
    with pytest.raises(ValueError):
        graph_connection.get_graph("I don't exist")


def test_delete_graph(graph_connection):
    g = Graph()
    hannahs_personhood = (URIRef("http://example.org/hannah"), RDF.type, FOAF.Person)
    g.add(hannahs_personhood)
    graph_connection.create_graph("my_graph", g)

    assert graph_connection.get_all_graph_identifiers() == ["my_graph"]
    graph_connection.delete_graph("my_graph")
    assert graph_connection.get_all_graph_identifiers() == []


@pytest.mark.parametrize(
    "identifier",
    [
        "2b4c6511-2ad9-4df7-b038-d0887d63dc78",
        "https://example.com/ontology/my-ontology#v1",
    ],
)
def test_graph_identifier_round_trips(graph_connection, identifier):
    graph_connection.create_graph(identifier, Graph())

    assert graph_connection.get_all_graph_identifiers() == [identifier]


def test_persistent_graph_store_survives_reopen(tmp_path):
    store_path = tmp_path / "oxigraph"
    g = Graph()
    hannahs_personhood = (URIRef("http://example.org/hannah"), RDF.type, FOAF.Person)
    g.add(hannahs_personhood)

    graph_connection = GraphConnection(store_path)
    graph_connection.create_graph("my_graph", g)
    graph_connection.close()

    reopened = GraphConnection(store_path)
    try:
        assert reopened.get_all_graph_identifiers() == ["my_graph"]
        assert isomorphic(reopened.get_graph("my_graph"), g)
    finally:
        reopened.close()
