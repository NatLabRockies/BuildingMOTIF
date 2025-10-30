import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from itertools import chain
from secrets import token_hex
from typing import TYPE_CHECKING, Dict, Generator, List, Optional, Set, Tuple, Union

import rdflib
from pyshacl.helper.path_helper import shacl_path_to_sparql_path
from pyshacl.shapes_graph import ShapesGraph
from rdflib import Graph, URIRef
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

    def reason(self) -> str:
        """Human-readable explanation of this GraphDiff."""
        return f"{self.focus} needs to match one of the following shapes: {', '.join(self.shapes)}"

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
            ShapesGraph(self.graph), self.path, prefixes=dict(self.graph.namespaces())
        )

        classname = self.graph.qname(self.classname)
        return self.format_count_error(self.maxc, self.minc, path, classname)

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
        for (focus, path, minc, maxc, shapename) in results:
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
            ShapesGraph(self.graph), self.path, prefixes=dict(self.graph.namespaces())
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

    def as_templates(self) -> List["Template"]:
        """Produces the set of templates that reconcile the GraphDiffs from the
        SHACL validation report.

        :return: reconciling templates
        :rtype: List[Template]
        """
        return diffset_to_templates(self.diffset)

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

        :return: a set of GraphDiffs that each abstract a SHACL shape violation
        :rtype: Set[GraphDiff]
        """
        classpath = SH["class"] | (SH.qualifiedValueShape / SH["class"])  # type: ignore
        shapepath = SH["node"] | (SH.qualifiedValueShape / SH["node"])  # type: ignore
        # TODO: for future use
        # proppath = SH["property"] | (SH.qualifiedValueShape / SH["property"])  # type: ignore

        g = self.report + self.shapes_graph
        diffs: Dict[Optional[URIRef], Set[GraphDiff]] = defaultdict(set)

        for result in g.objects(predicate=SH.result):
            # check if the failure is due to our count constraint component
            focus = g.value(result, SH.focusNode)
            # get the subgraph corresponding to this ValidationReport -- see
            # https://www.w3.org/TR/shacl/#results-validation-result for details
            # on the structure and expected properties
            validation_report = g.cbd(result)
            if (
                g.value(result, SH.sourceConstraintComponent)
                == CONSTRAINT.countConstraintComponent
            ):
                expected_count = g.value(
                    result, SH.sourceShape / CONSTRAINT.exactCount  # type: ignore
                )
                of_class = g.value(result, SH.sourceShape / CONSTRAINT["class"])  # type: ignore
                # here, our 'self.focus' is the graph itself, which we don't want to have bound
                # to the templates during evaluation (for this specific kind of diff).
                # For this reason we override focus to be None
                diffs[None].add(
                    GraphClassCardinality(
                        None, validation_report, g, of_class, int(expected_count)
                    )
                )
            elif (
                g.value(result, SH.sourceConstraintComponent)
                == SH.ClassConstraintComponent
            ):
                requiring_shape = g.value(result, SH.sourceShape)
                expected_class = g.value(requiring_shape, SH["class"])
                if expected_class is None or isinstance(expected_class, BNode):
                    continue
                diffs[focus].add(
                    RequiredClass(focus, validation_report, g, expected_class)
                )
            elif (
                g.value(result, SH.sourceConstraintComponent)
                == SH.NodeConstraintComponent
            ):
                # TODO: handle node constraint components
                pass
            # check if property shape
            elif g.value(result, SH.resultPath):
                path = g.value(result, SH.resultPath)
                min_count = g.value(
                    result, SH.sourceShape / (SH.minCount | SH.qualifiedMinCount)  # type: ignore
                )
                max_count = g.value(
                    result, SH.sourceShape / (SH.maxCount | SH.qualifiedMaxCount)  # type: ignore
                )
                classname = g.value(
                    result,
                    SH.sourceShape / classpath,
                )

                # TODO: finish this for some shapes
                # shapes_of_object = g.value(result, SH.sourceShape / SH.qualifiedValueShape)
                # for soo in shapes_of_object:
                #     soo_graph = g.cbd(soo)
                # handle properties (on qualifiedValueShapes?)
                # extra = g.value(result, SH.sourceShape / proppath)  # type: ignore

                if focus and (min_count or max_count) and classname:
                    diffs[focus].add(
                        PathClassCount(
                            focus,
                            validation_report,
                            g,
                            path,
                            int(min_count) if min_count else None,
                            int(max_count) if max_count else None,
                            classname,
                        )
                    )
                    continue
                shapename = g.value(result, SH.sourceShape / shapepath)  # type: ignore
                if focus and (min_count or max_count) and shapename:
                    extra_body, deps = get_template_parts_from_shape(shapename, g)
                    diffs[focus].add(
                        PathShapeCount(
                            focus,
                            validation_report,
                            g,
                            path,
                            int(min_count) if min_count else None,
                            int(max_count) if max_count else None,
                            shapename,
                            extra_body,
                            tuple(deps),
                        )
                    )
                    continue
                if focus and (min_count or max_count):
                    diffs[focus].add(
                        RequiredPath(
                            focus,
                            validation_report,
                            g,
                            path,
                            int(min_count) if min_count else None,
                            int(max_count) if max_count else None,
                        )
                    )

        # TODO: this is still kind of broken...ideally we would actually interpret the shapes
        # inside the or clause
        candidates = OrShape.from_validation_report(g)
        for c in candidates:
            diffs[c.focus].add(c)
        return diffs


def diffset_to_templates(
    grouped_diffset: Dict[Optional[URIRef], Set[GraphDiff]]
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
        templates.append(unified_evaluated)
    return templates
