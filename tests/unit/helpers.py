"""Shared helpers for the unit tests."""

import rdflib

from buildingmotif.dataclasses import Library


def shapes_as_library(shapes: rdflib.Graph, name: str = "urn:test/shapes") -> Library:
    """Wrap a graph of ad-hoc shapes in a Library, so a manifest can name it.

    A manifest imports libraries rather than absorbing loose shapes, so a test
    holding a shapes graph needs this one step before ``model.manifest.add()``.
    Inference and template inference are both off: these graphs are meant to be
    validated against exactly as written.
    """
    graph = rdflib.Graph()
    graph += shapes
    graph.add((rdflib.URIRef(name), rdflib.RDF.type, rdflib.OWL.Ontology))
    return Library.from_ontology(
        graph, infer_templates=False, run_shacl_inference=False
    )
