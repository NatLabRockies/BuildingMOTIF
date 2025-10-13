import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from itertools import chain
from secrets import token_hex
from typing import TYPE_CHECKING, Dict, Generator, List, Optional, Set, Tuple, Union

import rdflib
from pyshacl.helper.path_helper import shacl_path_to_sparql_path
from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.term import BNode, Node

from buildingmotif import get_building_motif
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.namespaces import CONSTRAINT, PARAM, RDF, SH, A, bind_prefixes
from buildingmotif.utils import (
    _gensym,
    _guarantee_unique_template_name,
    get_template_parts_from_shape,
    replace_nodes,
)

if TYPE_CHECKING:
    from buildingmotif.dataclasses import Library, Model, Template


def shacl_to_sparql_path(g, shacl_path):
    def parse_path(node):
        if isinstance(node, URIRef):
            return g.qname(node)
        elif isinstance(node, BNode):
            for p, o in g.predicate_objects(node):
                if p == SH.inversePath:
                    return "^" + parse_path(o)
                elif p == SH.alternativePath:
                    return "|".join(parse_path(e) for e in g.items(node))
                elif p == SH.zeroOrMorePath:
                    return parse_path(o) + "*"
                elif p == SH.oneOrMorePath:
                    return parse_path(o) + "+"
                elif p == SH.zeroOrOnePath:
                    return parse_path(o) + "?"
        elif isinstance(node, Literal):
            return str(node)
        else:
            raise ValueError(f"Unsupported SHACL path element: {node}")

    # if shacl_path is an RDF list, then we need to turn it into a Collection
    if (shacl_path, RDF.first, None) in g:
        c = Collection(g, shacl_path)
        return "/".join([parse_path(e) for e in c])

    return parse_path(shacl_path)


@dataclass(frozen=True)
class GraphDiff:
    """An abstraction of a SHACL Validation Result that can produce a template
    that resolves the difference between the expected and actual graph.

    Each GraphDiff has a 'focus' that is the node in the model that the
    GraphDiff is about. If 'focus' is None, then the GraphDiff is about the
    model itself rather than a specific node
    """

    # the node that failed (shape target)
    focus: Optional[URIRef]
    # the SHACL validation result graph corresponding to this failure
    validation_result: Graph
    graph: Graph

    def __post_init__(self):
        bind_prefixes(self.graph)

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff.

        :param lib: the library to hold the templates
        :type lib: Library
        :return: templates that reconcile the GraphDiff
        :rtype: List[Template]
        """
        raise NotImplementedError

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        raise NotImplementedError

    @cached_property
    def _result_uri(self) -> Node:
        """Return the 'name' of the ValidationReport to make failed_shape/failed_component
        easier to express. We compute this by taking advantage of the fact that the validation
        result graph is actually a tree with a single root. We can find the root by finding
        all URIs which appear as subjects in the validation_result graph that do *not* appear
        as objects; this should  be exactly one URI which is the 'root' of the validation result
        graph
        """
        return next(self.validation_result.subjects(RDF.type, SH.ValidationResult))

    @cached_property
    def failed_shape(self) -> Optional[URIRef]:
        """The URI of the Shape that failed"""
        return self.validation_result.value(self._result_uri, SH.sourceShape)

    @cached_property
    def failed_component(self) -> Optional[URIRef]:
        """The Constraint Component of the Shape that failed"""
        return self.validation_result.value(
            self._result_uri, SH.sourceConstraintComponent
        )

    def __hash__(self):
        return hash(self.reason())

    @property
    def dedup_key(self) -> Optional[Tuple[Node, Tuple[str, Optional[Node]]]]:
        """Key used to deduplicate diffs that express the same requirement.
        Subclasses should override to opt into deduplication.
        Returns a tuple of (path, ("kind", class_or_node)) or None to skip deduplication.
        """
        return None

    def format_count_error(
        self, max_count, min_count, path, object_type: Optional[str] = None
    ) -> str:
        """Format a count error message for a given object type and path.

        :param max_count: the maximum number of objects expected
        :type max_count: int
        :param min_count: the minimum number of objects expected
        :type min_count: int
        :param object_type: the type of object expected
        :type object_type: str
        :param path: the path to the object
        :type path: str
        :return: the formatted error message
        :rtype: str
        """
        instances = f"instance(s) of {object_type} on" if object_type else "uses of"
        if min_count == max_count:
            return f"{self.focus} expected {min_count} {instances} path {path}"
        elif min_count is not None and max_count is not None:
            return f"{self.focus} expected between {min_count} and {max_count} {instances} path {path}"
        elif min_count is not None:
            return f"{self.focus} expected at least {min_count} {instances} path {path}"
        elif max_count is not None:
            return f"{self.focus} expected at most {max_count} {instances} path {path}"
        else:
            return f"{self.focus} expected {instances} path {path}"


@dataclass(frozen=True)
class OrShape(GraphDiff):
    """Represents an entity that is missing one of several possible shapes, via sh:or"""

    shapes: Tuple[URIRef]
    messages: Optional[Tuple[str, ...]] = None

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        if self.messages:
            return f"{self.focus} must satisfy one of: " + " | ".join(self.messages)
        return f"{self.focus} needs to match one of the following shapes: {', '.join(str(s) for s in self.shapes)}"

    def resolve(self, lib: "Library") -> List["Template"]:
        """OrShape represents an OR between alternatives and cannot produce a
        single unambiguous corrective template. Return an empty list so that
        template synthesis for other diffs can proceed without error."""
        return []

    @classmethod
    def from_validation_report(cls, report: Graph) -> List["OrShape"]:
        """Construct OrShape objects from a SHACL validation report.

        :param report: the SHACL validation report
        :type report: Graph
        :return: a list of OrShape objects
        :rtype: List[OrShape]
        """
        query = """
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?result ?focus ?shapes WHERE {
            ?result sh:sourceConstraintComponent sh:OrConstraintComponent .
            ?result sh:sourceShape/sh:or ?shapes .
            ?result sh:focusNode ?focus .
        }"""
        results = report.query(query)
        ret = []
        for result, focus, shapes in results:
            validation_report = report.cbd(result)
            ret.append(
                cls(
                    focus,
                    validation_report,
                    report,
                    tuple([s for s in Collection(report, shapes)]),
                )
            )
        return ret


@dataclass(frozen=True)
class PathClassCount(GraphDiff):
    """Represents an entity missing paths to objects of a given type:
    $this <path> <object> .
    <object> a <classname> .
    """

    path: URIRef
    minc: Optional[int]
    maxc: Optional[int]
    classname: URIRef

    @classmethod
    def from_validation_report(cls, report: Graph) -> List["PathClassCount"]:
        """Construct PathClassCount objects from a SHACL validation report.

        :param report: the SHACL validation report
        :type report: Graph
        :return: a list of PathClassCount objects
        :rtype: List[PathClassCount]
        """

        query = """
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?focus ?path ?minc ?maxc ?classname WHERE {
            ?result sh:sourceShape/sh:qualifiedValueShape? ?shape .
            { ?result sh:sourceConstraintComponent sh:CountConstraintComponent }
            UNION
            { ?result sh:sourceConstraintComponent sh:QualifiedMinCountConstraintComponent }
            ?result sh:focusNode ?focus .
            ?shape sh:resultPath ?path .
            {
                ?shape sh:class ?classname .
                ?shape sh:minCount ?minc .
                OPTIONAL { ?shape sh:maxCount ?maxc }
            }
            UNION
            {
                ?shape sh:qualifiedValueShape [ sh:class ?classname ] .
                ?shape sh:qualifiedMinCount ?minc .
                OPTIONAL { ?shape sh:qualifiedMaxCount ?maxc }
            }
        }"""
        results = report.query(query)
        return [
            cls(
                focus,
                report,
                report,
                path,
                minc,
                maxc,
                classname,
            )
            for focus, path, minc, maxc, classname in results
        ]

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        # interpret a SHACL property path as a sparql property path
        path = shacl_path_to_sparql_path(
            self.graph, self.path, prefixes=dict(self.graph.namespaces())
        )

        classname = self.graph.qname(self.classname)
        return self.format_count_error(self.maxc, self.minc, path, classname)

    @property
    def dedup_key(self) -> Optional[Tuple[Node, Tuple[str, Optional[Node]]]]:
        return (self.path, ("class", self.classname))

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff.

        :param lib: the library to hold the templates
        :type lib: Library
        :return: templates that reconcile the GraphDiff
        :rtype: List[Template]
        """
        assert self.focus is not None
        body = Graph()
        # extract everything after the last "delimiter" character from self.classname
        name = re.split(r"[#\/]", self.classname)[-1]
        focus = re.split(r"[#\/]", self.focus)[-1]
        for _ in range(self.minc or 0):
            inst = _gensym()
            body.add((self.focus, self.path, inst))
            body.add((inst, A, self.classname))
        template_name = _guarantee_unique_template_name(lib, f"resolve{focus}{name}")
        return [lib.create_template(template_name, body)]


@dataclass(frozen=True, unsafe_hash=True)
class PathShapeCount(GraphDiff):
    """Represents an entity missing paths to objects that match a given shape.
    $this <path> <object> .
    <object> a <shapename> .
    """

    path: URIRef = field(hash=True)
    minc: Optional[int] = field(hash=True)
    maxc: Optional[int] = field(hash=True)
    shapename: URIRef = field(hash=True)
    extra_body: Optional[Graph] = field(hash=False)
    extra_deps: Optional[Tuple] = field(hash=False)

    @classmethod
    def from_validation_report(
        cls, report: Graph
    ) -> Generator["PathShapeCount", None, None]:
        """Construct PathShapeCount objects from a SHACL validation report.

        :param report: the SHACL validation report
        :type report: Graph
        :return: a list of PathShapeCount objects
        :rtype: List[PathShapeCount]
        """
        query = """
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?focus ?path ?minc ?maxc ?shapename WHERE {
            ?result sh:sourceShape ?shape .
            ?result sh:resultPath ?path .
            { ?result sh:sourceConstraintComponent sh:CountConstraintComponent }
            UNION
            { ?result sh:sourceConstraintComponent sh:QualifiedMinCountConstraintComponent }
            ?result sh:focusNode ?focus .
            {
                ?shape sh:node ?shapename .
                ?shape sh:minCount ?minc .
                OPTIONAL { ?shape sh:maxCount ?maxc }
            }
            UNION
            {
                ?shape sh:qualifiedValueShape [ sh:node ?shapename ] .
                ?shape sh:qualifiedMinCount ?minc .
                OPTIONAL { ?shape sh:qualifiedMaxCount ?maxc }
            }

        }"""
        results = report.query(query)
        for focus, path, minc, maxc, shapename in results:
            extra_body, deps = get_template_parts_from_shape(shapename, report)
            yield cls(
                focus,
                report,
                report,
                path,
                minc,
                maxc,
                shapename,
                extra_body,
                tuple(deps),
            )

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        shapename = self.graph.qname(self.shapename)
        return self.format_count_error(self.maxc, self.minc, self.path, shapename)

    @property
    def dedup_key(self) -> Optional[Tuple[Node, Tuple[str, Optional[Node]]]]:
        return (self.path, ("node", self.shapename))

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff."""
        assert self.focus is not None
        generated = []
        if self.extra_deps:
            for dep in self.extra_deps:
                dep["args"] = {k: str(v)[len(PARAM) :] for k, v in dep["args"].items()}
        # extract everything after the last "delimiter" character from self.shapename
        name = re.split(r"[#\/]", self.shapename)[-1]
        focus = re.split(r"[#\/]", self.focus)[-1]
        for _ in range(self.minc or 0):
            body = Graph()
            inst = PARAM["name"]
            body.add((self.focus, self.path, inst))
            body.add((inst, A, self.shapename))
            if self.extra_body:
                replace_nodes(self.extra_body, {PARAM.name: inst})
                body += self.extra_body
            template_name = _guarantee_unique_template_name(
                lib, f"resolve{focus}{name}"
            )
            templ = lib.create_template(template_name, body)
            if self.extra_deps:
                from buildingmotif.dataclasses.template import Template

                bm = get_building_motif()
                for dep in self.extra_deps:
                    dbt = bm.table_connection.get_db_template_by_name(dep["template"])
                    t = Template.load(dbt.id)
                    templ.add_dependency(t, dep["args"])
            generated.append(templ)
        return generated


@dataclass(frozen=True)
class RequiredPath(GraphDiff):
    """Represents an entity missing a required property."""

    path: URIRef
    minc: Optional[int]
    maxc: Optional[int]

    @classmethod
    def from_validation_report(cls, report: Graph) -> List["RequiredPath"]:
        """Construct RequiredPath objects from a SHACL validation report.

        :param report: the SHACL validation report
        :type report: Graph
        :return: a list of RequiredPath objects
        :rtype: List[RequiredPath]
        """
        query = """
        PREFIX sh: <http://www.w3.org/ns/shacl#>
        SELECT ?focus ?path ?minc ?maxc WHERE {
            ?result sh:sourceShape ?shape .
            ?result sh:resultPath ?path .
            { ?result sh:sourceConstraintComponent sh:CountConstraintComponent }
            UNION
            { ?result sh:sourceConstraintComponent sh:QualifiedMinCountConstraintComponent }
            ?result sh:focusNode ?focus .
            {
                ?shape sh:minCount ?minc .
                OPTIONAL { ?shape sh:maxCount ?maxc }
            } UNION {
                ?shape sh:qualifiedMinCount ?minc .
                OPTIONAL { ?shape sh:qualifiedMaxCount ?maxc }
            }
        }"""
        results = report.query(query)
        return [
            cls(
                focus,
                report,
                report,
                path,
                minc,
                maxc,
            )
            for focus, path, minc, maxc in results
        ]

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        path = shacl_path_to_sparql_path(
            self.graph, self.path, prefixes=dict(self.graph.namespaces())
        )
        return self.format_count_error(self.maxc, self.minc, path)

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff.

        :param lib: the library to hold the templates
        :type lib: Library
        :return: templates that reconcile the GraphDiff
        :rtype: List[Template]
        """
        assert self.focus is not None
        body = Graph()
        # extract everything after the last "delimiter" character from self.shapename
        name = re.split(r"[#\/]", self.path)[-1]
        focus = re.split(r"[#\/]", self.focus)[-1]
        for _ in range(self.minc or 0):
            inst = _gensym()
            body.add((self.focus, self.path, inst))
        template_name = _guarantee_unique_template_name(lib, f"resolve{focus}{name}")
        return [lib.create_template(template_name, body)]

    @property
    def dedup_key(self) -> Optional[Tuple[Node, Tuple[str, Optional[Node]]]]:
        return (self.path, ("none", None))


@dataclass(frozen=True)
class RequiredClass(GraphDiff):
    """Represents an entity that should be an instance of the class."""

    classname: URIRef

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        value_node = self.validation_result.value(self._result_uri, SH.value)
        return f"{value_node} on {self.focus} needs to be a {self.classname}"

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff.

        :param lib: the library to hold the templates
        :type lib: Library
        :return: templates that reconcile the GraphDiff
        :rtype: List[Template]
        """
        assert self.focus is not None
        body = Graph()
        name = re.split(r"[#\/]", self.classname)[-1]
        body.add((self.focus, A, self.classname))
        template_name = _guarantee_unique_template_name(lib, f"resolveSelf{name}")
        return [lib.create_template(template_name, body)]


@dataclass(frozen=True)
class GraphClassCardinality(GraphDiff):
    """Represents a graph that is missing an expected number of instances of
    the given class.
    """

    classname: URIRef
    expectedCount: int

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        return f"Graph did not have {self.expectedCount} instances of {self.classname}"

    def resolve(self, lib: "Library") -> List["Template"]:
        """Produces a list of templates to resolve this GraphDiff.

        :param lib: the library to hold the templates
        :type lib: Library
        :return: templates that reconcile the GraphDiff
        :rtype: List[Template]
        """
        templs = []
        name = re.split(r"[#\/]", self.classname)[-1]
        for _ in range(self.expectedCount):
            template_body = Graph()
            template_body.add((PARAM["name"], A, self.classname))
            template_name = _guarantee_unique_template_name(lib, f"resolveAdd{name}")
            templs.append(lib.create_template(template_name, template_body))
        return templs


def _to_int_maybe(val: Optional[Literal]) -> Optional[int]:
    """Safely cast a Literal integer to int if present."""
    if isinstance(val, Literal):
        try:
            return int(val)
        except Exception:
            return None
    return None


def _detect_qvs_class_min_pattern(
    g: Graph, result: Node
) -> Optional[Tuple[Node, Optional[int], Optional[int], URIRef]]:
    """Detect the 'qualifiedValueShape' + 'qualifiedMinCount' pattern that often
    manifests as a ClassConstraintComponent on a value node, but whose actionable
    fix is to add a missing value of a required class along the resultPath.

    Returns:
        (result_path, qualifiedMinCount, qualifiedMaxCount, expected_class) if pattern matches.
    """
    shape = g.value(result, SH.sourceShape)
    if shape is None:
        return None
    qvs = g.value(shape, SH.qualifiedValueShape)
    if qvs is None:
        return None
    result_path = g.value(result, SH.resultPath)
    expected_class = g.value(qvs, SH["class"])
    qmin = g.value(shape, SH.qualifiedMinCount)
    qmax = g.value(shape, SH.qualifiedMaxCount)
    if result_path and isinstance(expected_class, URIRef) and qmin is not None:
        return (result_path, _to_int_maybe(qmin), _to_int_maybe(qmax), expected_class)
    return None


# -------------------------------
# Helper detectors for GraphDiffs
# -------------------------------


def _detect_graph_class_cardinality(
    g: Graph, result: Node
) -> Optional["GraphClassCardinality"]:
    """Detect a graph-level class cardinality violation produced by custom CONSTRAINT component."""
    if (
        g.value(result, SH.sourceConstraintComponent)
        == CONSTRAINT.countConstraintComponent
    ):
        expected_count = g.value(result, SH.sourceShape / CONSTRAINT.exactCount)  # type: ignore
        of_class = g.value(result, SH.sourceShape / CONSTRAINT["class"])  # type: ignore
        if expected_count is not None and of_class is not None:
            validation_report = g.cbd(result)
            return GraphClassCardinality(
                None, validation_report, g, of_class, int(expected_count)  # type: ignore[arg-type]
            )
    return None


def _detect_required_class(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> Optional["RequiredClass"]:
    """Detect a RequiredClass violation (focus must be an instance of a class)."""
    if (
        g.value(result, SH.sourceConstraintComponent) == SH.ClassConstraintComponent
        and focus
    ):
        requiring_shape = g.value(result, SH.sourceShape)
        expected_class = (
            g.value(requiring_shape, SH["class"]) if requiring_shape else None
        )
        if isinstance(expected_class, URIRef):
            validation_report = g.cbd(result)
            return RequiredClass(focus, validation_report, g, expected_class)
    return None


def _detect_path_class_count(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> Optional["PathClassCount"]:
    """Detect missing related entities with a given class along a path (supports qualifiedValueShape)."""
    if not focus:
        return None

    # First, handle the qualifiedValueShape + qualifiedMinCount pattern even if the engine
    # surfaces a ClassConstraintComponent on a value node.
    qvs_match = _detect_qvs_class_min_pattern(g, result)
    if qvs_match:
        path, minc_i, maxc_i, classname = qvs_match
        validation_report = g.cbd(result)
        return PathClassCount(
            focus, validation_report, g, path, minc_i, maxc_i, classname
        )

    # Fall back to standard class/minCount detection on the source shape
    classpath = SH["class"] | (SH.qualifiedValueShape / SH["class"])  # type: ignore
    path = g.value(result, SH.resultPath)
    if not path:
        return None
    min_count_lit = g.value(result, SH.sourceShape / (SH.minCount | SH.qualifiedMinCount))  # type: ignore
    max_count_lit = g.value(result, SH.sourceShape / (SH.maxCount | SH.qualifiedMaxCount))  # type: ignore
    classname = g.value(result, SH.sourceShape / classpath)
    if classname is None:
        return None
    minc = _to_int_maybe(min_count_lit)
    maxc = _to_int_maybe(max_count_lit)
    if minc is None and maxc is None:
        return None
    validation_report = g.cbd(result)
    return PathClassCount(focus, validation_report, g, path, minc, maxc, classname)  # type: ignore[arg-type]


def _detect_path_shape_count(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> Optional["PathShapeCount"]:
    """Detect missing related entities that must conform to a node shape along a path."""
    if not focus:
        return None
    shapepath = SH["node"] | (SH.qualifiedValueShape / SH["node"])  # type: ignore
    path = g.value(result, SH.resultPath)
    shapename = g.value(result, SH.sourceShape / shapepath)  # type: ignore
    if not (path and shapename):
        return None
    min_count_lit = g.value(result, SH.sourceShape / (SH.minCount | SH.qualifiedMinCount))  # type: ignore
    max_count_lit = g.value(result, SH.sourceShape / (SH.maxCount | SH.qualifiedMaxCount))  # type: ignore
    minc = _to_int_maybe(min_count_lit)
    maxc = _to_int_maybe(max_count_lit)
    if minc is None and maxc is None:
        return None
    extra_body, deps = get_template_parts_from_shape(shapename, g)  # type: ignore[arg-type]
    validation_report = g.cbd(result)
    return PathShapeCount(
        focus,
        validation_report,
        g,
        path,  # type: ignore[arg-type]
        minc,
        maxc,
        shapename,  # type: ignore[arg-type]
        extra_body,
        tuple(deps) if deps else None,
    )


def _detect_required_path(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> Optional["RequiredPath"]:
    """Detect a missing path with min/max constraints and no specific class/shape requirement."""
    if not focus:
        return None
    path = g.value(result, SH.resultPath)
    if not path:
        return None
    min_count_lit = g.value(result, SH.sourceShape / (SH.minCount | SH.qualifiedMinCount))  # type: ignore
    max_count_lit = g.value(result, SH.sourceShape / (SH.maxCount | SH.qualifiedMaxCount))  # type: ignore
    minc = _to_int_maybe(min_count_lit)
    maxc = _to_int_maybe(max_count_lit)
    if minc is None and maxc is None:
        return None
    validation_report = g.cbd(result)
    return RequiredPath(
        focus,
        validation_report,
        g,
        path,  # type: ignore[arg-type]
        minc,
        maxc,
    )


def _expand_or_result_to_diffs(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> List["GraphDiff"]:
    """Expand an sh:OrConstraintComponent result into concrete GraphDiffs by
    recursing into its sh:detail children and running the standard detectors.

    If no sh:detail children are present, returns an empty list.
    """
    diffs: List["GraphDiff"] = []
    for child in g.objects(result, SH.detail):
        # Prefer the child's own focus node if present
        child_focus = g.value(child, SH.focusNode) or focus

        gc = _detect_graph_class_cardinality(g, child)
        if gc is not None:
            diffs.append(gc)
            continue

        pcc = _detect_path_class_count(g, child, child_focus)  # type: ignore[arg-type]
        if pcc is not None:
            diffs.append(pcc)
            continue

        psc = _detect_path_shape_count(g, child, child_focus)  # type: ignore[arg-type]
        if psc is not None:
            diffs.append(psc)
            continue

        rp = _detect_required_path(g, child, child_focus)  # type: ignore[arg-type]
        if rp is not None:
            diffs.append(rp)
            continue

        rc = _detect_required_class(g, child, child_focus)  # type: ignore[arg-type]
        if rc is not None:
            diffs.append(rc)
            continue
    return diffs


def _expand_and_result_to_diffs(
    g: Graph, result: Node, focus: Optional[URIRef]
) -> List["GraphDiff"]:
    """Expand an sh:AndConstraintComponent result into concrete GraphDiffs by
    examining referenced shapes and any sh:detail children.

    The SHACL engine may emit only the top-level And violation without per-option
    results, so we additionally analyze the shapes graph structure to synthesize
    actionable diffs for each required sub-shape."""

    diffs: List["GraphDiff"] = []

    and_list = g.value(result, SH.sourceShape / SH["and"])
    if and_list is not None:
        try:
            members = list(Collection(g, and_list))
        except Exception:
            members = []
        for member in members:
            # If the member itself offers alternatives, surface an OrShape to preserve context.
            or_list = g.value(member, SH["or"])
            if or_list is not None:
                try:
                    alt_shapes = tuple(Collection(g, or_list))
                except Exception:
                    alt_shapes = ()
                messages = _messages_from_or_shapes(g, or_list, focus)
                validation_report = g.cbd(result)
                diffs.append(
                    OrShape(
                        focus,
                        validation_report,
                        g,
                        alt_shapes,
                        tuple(messages) if messages else None,
                    )
                )
                for alt in alt_shapes:
                    diffs.extend(_diffs_from_shape_node(g, alt, focus))
                continue

            diffs.extend(_diffs_from_shape_node(g, member, focus))

    # Also examine any detail children emitted by the validation engine.
    for child in g.objects(result, SH.detail):
        child_focus = g.value(child, SH.focusNode) or focus

        gc = _detect_graph_class_cardinality(g, child)
        if gc is not None:
            diffs.append(gc)
            continue

        pcc = _detect_path_class_count(g, child, child_focus)  # type: ignore[arg-type]
        if pcc is not None:
            diffs.append(pcc)
            continue

        psc = _detect_path_shape_count(g, child, child_focus)  # type: ignore[arg-type]
        if psc is not None:
            diffs.append(psc)
            continue

        rp = _detect_required_path(g, child, child_focus)  # type: ignore[arg-type]
        if rp is not None:
            diffs.append(rp)
            continue

        rc = _detect_required_class(g, child, child_focus)  # type: ignore[arg-type]
        if rc is not None:
            diffs.append(rc)
            continue

    return diffs


def _diffs_from_shape_node(
    g: Graph, shape_node: Node, focus: Optional[URIRef]
) -> List[GraphDiff]:
    """Derive GraphDiffs from the structure of a shape node in the shapes graph (no reliance on report).

    Supports:
      - Property shapes with sh:path and:
          * sh:class or sh:qualifiedValueShape/sh:class  -> PathClassCount
          * sh:node or sh:qualifiedValueShape/sh:node    -> PathShapeCount
          * otherwise                                    -> RequiredPath
      - Node shapes with sh:property children            -> recursively derive diffs for each property shape
      - Node shapes with sh:class                        -> simple RequiredClass-like message (via RequiredClass)
    """
    diffs: List[GraphDiff] = []

    # Property shape
    path = g.value(shape_node, SH.path)
    if path is not None:
        # min/max from shape or qualified variants
        minc_lit = g.value(shape_node, SH.minCount) or g.value(
            shape_node, SH.qualifiedMinCount
        )
        maxc_lit = g.value(shape_node, SH.maxCount) or g.value(
            shape_node, SH.qualifiedMaxCount
        )
        minc = (
            _to_int_maybe(minc_lit)
            if isinstance(minc_lit, Literal)
            else _to_int_maybe(minc_lit)
        )
        maxc = (
            _to_int_maybe(maxc_lit)
            if isinstance(maxc_lit, Literal)
            else _to_int_maybe(maxc_lit)
        )

        qvs = g.value(shape_node, SH.qualifiedValueShape)
        cls_uri = g.value(shape_node, SH["class"]) or (
            g.value(qvs, SH["class"]) if qvs else None
        )
        node_shape = g.value(shape_node, SH.node) or (
            g.value(qvs, SH.node) if qvs else None
        )

        if isinstance(cls_uri, URIRef):
            diffs.append(PathClassCount(focus, Graph(), g, path, minc, maxc, cls_uri))  # type: ignore[arg-type]
            return diffs
        if isinstance(node_shape, URIRef):
            diffs.append(
                PathShapeCount(  # type: ignore[arg-type]
                    focus, Graph(), g, path, minc, maxc, node_shape, None, None
                )
            )
            return diffs

        diffs.append(RequiredPath(focus, Graph(), g, path, minc, maxc))  # type: ignore[arg-type]
        return diffs

    # Node shape: collect property shapes
    props = list(g.objects(shape_node, SH.property))
    if props:
        for ps in props:
            diffs.extend(_diffs_from_shape_node(g, ps, focus))
        return diffs

    # Node shape with a direct class requirement
    cls_req = g.value(shape_node, SH["class"])
    if isinstance(cls_req, URIRef) and focus:
        # Create a tiny faux validation_result graph so RequiredClass.reason can render
        valres = Graph()
        vr = BNode()
        valres.add((vr, RDF.type, SH.ValidationResult))
        valres.add((vr, SH.value, focus))
        diffs.append(RequiredClass(focus, valres, g, cls_req))
        return diffs

    return diffs


def _messages_from_or_shapes(
    g: Graph, shapes_list: Node, focus: Optional[URIRef]
) -> List[str]:
    """Produce messages for each shape alternative by analyzing the shape graph structure."""
    messages: List[str] = []
    try:
        alts = list(Collection(g, shapes_list))
    except Exception:
        alts = []
    for alt in alts:
        alt_diffs = _diffs_from_shape_node(g, alt, focus)
        if alt_diffs:
            combined = " and ".join(d.reason() for d in alt_diffs)
            messages.append(combined)
            continue
        # Fall back to authored messages on the shape
        authored = [
            str(m) for m in g.objects(alt, SH.message) if isinstance(m, Literal)
        ]
        if authored:
            messages.append(" ".join(authored))
        else:
            label = g.qname(alt) if isinstance(alt, URIRef) else str(alt)
            messages.append(f"{focus} must satisfy shape {label}")
    # De-duplicate while preserving order
    return list(dict.fromkeys(messages))


def _collect_or_messages(g: Graph, result: Node) -> List[str]:
    """Collect human-readable messages for the alternatives under an sh:OrConstraintComponent.

    Priority of sources:
    1) Analyze the referenced shapes list (sh:sourceShape/sh:or ...) and derive messages from shape structure
    2) sh:resultMessage values on each sh:detail child (if provided by the engine)
    3) sh:message values declared on each child's sh:sourceShape (shape-authored copy)
    4) Generated reasons from our nested GraphDiff detectors for each child in the report
    """
    focus = g.value(result, SH.focusNode)

    # 1) Prefer shape-graph analysis of the OR alternatives
    shapes_list = g.value(result, SH.sourceShape / SH["or"])
    if shapes_list is not None:
        msgs = _messages_from_or_shapes(g, shapes_list, focus)
        if msgs:
            return msgs

    messages: List[str] = []

    # 2) Collect engine-produced child result messages
    for child in g.objects(result, SH.detail):
        for m in g.objects(child, SH.resultMessage):
            if isinstance(m, Literal):
                messages.append(str(m))

    # 3) If none, fall back to sh:message on the child's source shape
    if not messages:
        for child in g.objects(result, SH.detail):
            shape = g.value(child, SH.sourceShape)
            if shape is not None:
                for m in g.objects(shape, SH.message):
                    if isinstance(m, Literal):
                        messages.append(str(m))

    # 4) If still none, generate reasons from nested diffs using the report structure
    if not messages:
        diffs = _expand_or_result_to_diffs(g, result, focus)
        messages.extend(d.reason() for d in diffs)

    # De-duplicate while preserving order
    return list(dict.fromkeys(messages))


def _deduplicate_diffs_by_focus_path_classnode(
    diffs: Dict[Optional[URIRef], Set[GraphDiff]],
) -> Dict[Optional[URIRef], Set[GraphDiff]]:
    """Deduplicate diffs using each diff's declared dedup_key."""
    new_diffs: Dict[Optional[URIRef], Set[GraphDiff]] = {}
    for focus, s in diffs.items():
        seen: Set[Tuple[Node, Tuple[str, Optional[Node]]]] = set()
        kept: List[GraphDiff] = []
        for d in s:
            key = d.dedup_key
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            kept.append(d)
        new_diffs[focus] = set(kept)
    return new_diffs


@dataclass
class ValidationContext:
    """Holds the necessary information for processing the results of SHACL
    validation.
    """

    shape_collections: List[ShapeCollection]
    # the shapes graph that was used to validate the model
    # This will be skolemized!
    shapes_graph: Graph
    valid: bool
    report: rdflib.Graph
    report_string: str
    model: "Model"

    @cached_property
    def diffset(self) -> Dict[Optional[URIRef], Set[GraphDiff]]:
        """The unordered set of GraphDiffs produced from interpreting the input
        SHACL validation report.
        """
        return self._report_to_diffset()

    def as_templates_with_focus(self) -> List[Tuple[Optional[URIRef], "Template"]]:
        """
        Produces the set of templates along with the focus node they are for.
        Returns a list of (focus, Template) pairs. focus may be None for graph-level diffs.
        """
        from buildingmotif.dataclasses import Library, Template

        lib = Library.create(f"resolve_{token_hex(4)}")
        # Persist final unified templates in a timestamped library so they have real IDs
        save_lib = Library.create(
            datetime.utcnow().strftime("resolved_%Y%m%dT%H%M%S%fZ")
        )
        results: List[Tuple[Optional[URIRef], Template]] = []
        for focus, diffset in self.diffset.items():
            if focus is None:
                for diff in diffset:
                    for t in diff.resolve(lib):
                        results.append((None, t))
                continue
            templ_lists = (diff.resolve(lib) for diff in diffset)
            templs: List[Template] = list(
                filter(None, chain.from_iterable(templ_lists))
            )
            if len(templs) <= 1:
                for t in templs:
                    results.append((focus, t))
                continue
            base = templs[0]
            for templ in templs[1:]:
                if "name" in templ.parameters:
                    base.add_dependency(templ, {"name": "name"})
                else:
                    base.body += templ.body
            unified = base.inline_dependencies()
            if len(unified.parameters) > 0:
                unified_evaluated = unified.evaluate({"name": focus})
            else:
                unified_evaluated = unified
            assert isinstance(unified_evaluated, Template)
            saved_name = f"{base.name}_unified"
            saved = save_lib.create_template(saved_name, unified_evaluated.body)
            results.append((focus, saved))
        return results

    def as_templates(self) -> List["Template"]:
        """Produces the set of templates that reconcile the GraphDiffs from the SHACL validation report."""
        return [templ for _, templ in self.as_templates_with_focus()]

    def get_broken_entities(self) -> Set[URIRef]:
        """Get the set of entities that are broken in the model.

        :return: set of entities that are broken
        :rtype: Set[URIRef]
        """
        return {diff or "Model" for diff in self.diffset}

    def get_diffs_for_entity(self, entity: URIRef) -> Set[GraphDiff]:
        """Get the set of diffs for a specific entity.

        :param entity: the entity to get diffs for
        :type entity: URIRef
        :return: set of diffs for the entity
        :rtype: Set[GraphDiff]
        """
        return self.diffset.get(entity, set())

    def get_reasons_with_severity(
        self, severity: Union[URIRef, str]
    ) -> Dict[Optional[URIRef], Set[GraphDiff]]:
        """
        Like diffset, but only includes ValidationResults with the given severity.
        Permitted values are:
        - SH.Violation or "Violation" for violations
        - SH.Warning or "Warning" for warnings
        - SH.Info or "Info" for info

        :param severity: the severity to filter by
        :type severity: Union[URIRef|str]
        :return: a dictionary of focus nodes to the reasons with the given severity
        :rtype: Dict[Optional[URIRef], Set[GraphDiff]]
        """

        if not isinstance(severity, URIRef):
            severity = SH[severity]

        # check if the severity is a valid SHACL severity
        if severity not in {SH.Violation, SH.Warning, SH.Info}:
            raise ValueError(
                f"Invalid severity: {severity}. Must be one of SH.Violation, SH.Warning, or SH.Info"
            )

        # for each value in the diffset, filter out the diffs that don't have the given severity
        # in the diffset.graph
        return {
            focus: {
                diff
                for diff in diffs
                if diff.validation_result.value(diff._result_uri, SH.resultSeverity)
                == severity
            }
            for focus, diffs in self.diffset.items()
        }

    def _report_to_diffset(self) -> Dict[Optional[URIRef], Set[GraphDiff]]:
        """Interpret a SHACL validation report and say what is missing.

        This implementation is organized as a sequence of small, focused detectors
        that each attempt to interpret a single ValidationResult node as a specific
        GraphDiff. The first matching detector wins for a given result.
        """
        g = self.report + self.shapes_graph
        diffs: Dict[Optional[URIRef], Set[GraphDiff]] = defaultdict(set)

        for result in g.objects(predicate=SH.result):
            focus = g.value(result, SH.focusNode)
            comp = g.value(result, SH.sourceConstraintComponent)
            # Handle OR constraint by recursing into sh:detail and converting children to GraphDiffs
            if comp == SH.OrConstraintComponent:
                # Preserve the "or" context by adding an OrShape that lists the messages
                # produced by each alternative, instead of raw shape references.
                validation_report = g.cbd(result)
                msgs = _collect_or_messages(g, result)
                print(f"OR constraint detected for focus {focus}, messages: {msgs}")
                diffs[focus].add(
                    OrShape(
                        focus,
                        validation_report,
                        g,
                        tuple(),
                        tuple(msgs) if msgs else None,
                    )
                )
                for d in _expand_or_result_to_diffs(g, result, focus):
                    print(f"From expanding OR: Adding diff {d} for focus {focus}")
                    diffs[focus].add(d)
                continue

            if comp == SH.AndConstraintComponent:
                for d in _expand_and_result_to_diffs(g, result, focus):
                    diffs[focus].add(d)
                continue

            # 1) Graph-level class cardinality (custom CONSTRAINT component)
            graph_card = _detect_graph_class_cardinality(g, result)
            if graph_card is not None:
                diffs[None].add(graph_card)
                continue

            # 2) Path to class (handles qualifiedValueShape + qualifiedMinCount pattern)
            pcc = _detect_path_class_count(g, result, focus)
            if pcc is not None:
                diffs[focus].add(pcc)
                continue

            # 3) Path to node shape
            psc = _detect_path_shape_count(g, result, focus)
            if psc is not None:
                diffs[focus].add(psc)
                continue

            # 4) Required path only (min/max count without class/shape requirement)
            rp = _detect_required_path(g, result, focus)
            if rp is not None:
                diffs[focus].add(rp)
                continue

            # 5) Required class on the (focus or value) node
            rc = _detect_required_class(g, result, focus)
            if rc is not None:
                diffs[focus].add(rc)
                continue

            # 6) NodeConstraintComponent handling (TODO)
            if (
                g.value(result, SH.sourceConstraintComponent)
                == SH.NodeConstraintComponent
            ):
                # Currently unhandled; reserved for future expansion
                continue

        return _deduplicate_diffs_by_focus_path_classnode(diffs)


def diffset_to_templates(
    grouped_diffset: Dict[Optional[URIRef], Set[GraphDiff]],
) -> List["Template"]:
    """Combine GraphDiff by focus node to generate a list of templates that
    reconcile what is "wrong" with the Graph with respect to the GraphDiffs.

    :param diffset: a set of diffs produced by `_report_to_diffset`
    :type diffset: Set[GraphDiff]
    :return: list of templates that should resolve the SHACL violations when
        populated
    :rtype: List[Template]
    """
    from buildingmotif.dataclasses import Library, Template

    lib = Library.create(f"resolve_{token_hex(4)}")
    # Persist final unified templates in a timestamped library so they have real IDs
    save_lib = Library.create(datetime.utcnow().strftime("resolved_%Y%m%dT%H%M%S%fZ"))

    templates = []
    # now merge all tempaltes together for each focus node
    for focus, diffset in grouped_diffset.items():
        if focus is None:
            for diff in diffset:
                templates.extend(diff.resolve(lib))
            continue

        templ_lists = (diff.resolve(lib) for diff in diffset)
        templs: List[Template] = list(filter(None, chain.from_iterable(templ_lists)))
        if len(templs) <= 1:
            templates.extend(templs)
            continue
        base = templs[0]
        # treat all the other templates as dependencies of the first one.
        # This allows us to do a "join" with inline_dependencies() which
        # will ensure that there are no unintended overlaps in the choice
        # of parameter name
        for templ in templs[1:]:
            # if there is a 'name' in the parameter list, join on that name.
            # otherwise, just append the body
            # (we don't need to use use to_inline() to ensure uniqueness of parameters
            # because all params are created with _gensym() which ensures uniqueness)
            if "name" in templ.parameters:
                base.add_dependency(templ, {"name": "name"})
            else:
                base.body += templ.body
        unified = base.inline_dependencies()
        # only try to evaluate if there are parameters, else this will fail.
        # We may not have parameters if the GraphDiffs have all the information
        # they need to patch the graph and don't need user input
        if len(unified.parameters) > 0:
            unified_evaluated = unified.evaluate({"name": focus})
        else:
            unified_evaluated = unified
        assert isinstance(unified_evaluated, Template)
        saved_name = f"{base.name}_unified"
        saved = save_lib.create_template(saved_name, unified_evaluated.body)
        templates.append(saved)
    return templates
