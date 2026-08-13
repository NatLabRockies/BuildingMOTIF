#!/usr/bin/env python3
"""Inspect ontology terms without losing their namespaces.

Load an ontology through BuildingMOTIF, find terms by complete IRI or local name, and
print the facts needed to make a safe source-to-ontology mapping decision.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library


def local_name(node: URIRef) -> str:
    """Return a display-only local name; never use it to reconstruct an IRI."""
    value = str(node).rstrip("/#")
    return value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def uri_nodes(graph: Graph) -> set[URIRef]:
    return {node for node in graph.all_nodes() if isinstance(node, URIRef)}


def find_terms(graph: Graph, query: str) -> list[URIRef]:
    if query.startswith(("http://", "https://", "urn:")):
        candidate = URIRef(query)
        return [candidate] if candidate in uri_nodes(graph) else []
    return sorted(
        (node for node in uri_nodes(graph) if local_name(node) == query),
        key=str,
    )


def search_terms(graph: Graph, query: str, limit: int) -> list[URIRef]:
    needle = query.casefold()
    matches: list[URIRef] = []
    for node in sorted(uri_nodes(graph), key=str):
        labels = " ".join(str(value) for value in graph.objects(node, RDFS.label))
        if needle in local_name(node).casefold() or needle in labels.casefold():
            matches.append(node)
            if len(matches) == limit:
                break
    return matches


def values(graph: Graph, subject: URIRef, predicate: URIRef) -> list[str]:
    return sorted({str(value) for value in graph.objects(subject, predicate)})


def deprecated_values(graph: Graph, subject: URIRef) -> list[str]:
    results: set[str] = set()
    for predicate, value in graph.predicate_objects(subject):
        if predicate == OWL.deprecated or (
            isinstance(predicate, URIRef) and local_name(predicate) == "deprecated"
        ):
            results.add(str(value))
    return sorted(results)


def property_shape_summary(graph: Graph, shape: URIRef) -> Iterable[str]:
    fields = (
        SH.path,
        SH.minCount,
        SH.maxCount,
        SH["class"],
        SH.node,
        SH.qualifiedMinCount,
        SH.qualifiedMaxCount,
        SH.hasValue,
    )
    for prop in graph.objects(shape, SH.property):
        details = []
        for predicate in fields:
            for value in graph.objects(prop, predicate):
                details.append(f"{local_name(predicate)}={value}")
        yield f"{prop}: " + (", ".join(details) if details else "no summarized fields")


def describe(graph: Graph, term: URIRef) -> None:
    print(f"\nIRI: {term}")
    print(f"local name (display only): {local_name(term)}")
    for label, entries in (
        ("types", values(graph, term, RDF.type)),
        ("direct superclasses", values(graph, term, RDFS.subClassOf)),
        ("deprecated", deprecated_values(graph, term)),
        ("labels", values(graph, term, RDFS.label)),
        ("comments", values(graph, term, RDFS.comment)),
    ):
        print(f"{label}:")
        if entries:
            for entry in entries:
                print(f"  - {entry}")
        else:
            print("  - (none in the loaded graph)")

    shapes = {term} if (term, RDF.type, SH.NodeShape) in graph else set()
    shapes.update(graph.subjects(SH.targetClass, term))
    print("direct SHACL property constraints:")
    summaries = [
        summary
        for shape in sorted(shapes, key=str)
        for summary in property_shape_summary(graph, shape)
    ]
    if summaries:
        for summary in summaries:
            print(f"  - {summary}")
    else:
        print("  - (none in the loaded graph; inherited shapes may still apply)")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "source",
        help="Ontology path/URL or builtin resource such as brick/Brick.ttl",
    )
    result.add_argument(
        "--term",
        action="append",
        default=[],
        help="Exact full IRI or local name; repeat for multiple terms",
    )
    result.add_argument(
        "--search",
        help="Case-insensitive substring search over local names and rdfs:labels",
    )
    result.add_argument("--limit", type=int, default=25)
    result.add_argument(
        "--fetch-imports",
        action="store_true",
        help="Resolve/fetch owl:imports; disabled by default for a fast direct-graph probe",
    )
    result.add_argument(
        "--database",
        default="sqlite://",
        help="BuildingMOTIF SQL URL; defaults to an in-memory database",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.term and not args.search:
        parser().error("provide at least one --term or --search")
    if args.limit < 1:
        parser().error("--limit must be positive")

    with BuildingMOTIF(
        args.database,
        ontology_fetch_imports=args.fetch_imports,
    ):
        library = Library.from_ontology(
            args.source,
            run_shacl_inference=False,
            fetch_imports=args.fetch_imports,
        )
        graph = library.get_shape_collection().graph
        print(f"loaded triples: {len(graph)}")

        selected: list[URIRef] = []
        for query in args.term:
            matches = find_terms(graph, query)
            if not matches:
                print(f"\nno exact match: {query}")
            selected.extend(matches)
        if args.search:
            selected.extend(search_terms(graph, args.search, args.limit))

        seen: set[URIRef] = set()
        for term in selected:
            if term not in seen:
                describe(graph, term)
                seen.add(term)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
