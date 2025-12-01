import logging
import random
import string
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Union

import rdflib
from pyshacl.helper.path_helper import shacl_path_to_sparql_path
from pyshacl.shapes_graph import ShapesGraph
from rdflib import RDF, RDFS, Graph, URIRef
from rdflib.paths import ZeroOrMore, ZeroOrOne
from rdflib.term import Node

from buildingmotif import get_building_motif
from buildingmotif.namespaces import BMOTIF, OWL, SH
from buildingmotif.utils import Triple, copy_graph, get_template_parts_from_shape

if TYPE_CHECKING:
    from buildingmotif import BuildingMOTIF
    from buildingmotif.dataclasses import Library

ONTOLOGY_FILE = (
    Path(__file__).resolve().parents[1] / "resources" / "building_motif_ontology.ttl"
)
ontology = rdflib.Graph().parse(ONTOLOGY_FILE)


@dataclass
class ShapeCollection:
    """This class mirrors :py:class:`database.tables.DBShapeCollection`."""

    _id: int
    graph: rdflib.Graph
    _bm: "BuildingMOTIF"

    @classmethod
    def create(cls) -> "ShapeCollection":
        """Create a new ShapeCollection.

        :return: new ShapeCollection
        :rtype: ShapeCollection
        """
        bm = get_building_motif()
        db_shape_collection = bm.table_connection.create_db_shape_collection()
        graph = bm.graph_connection.create_graph(
            db_shape_collection.graph_id, rdflib.Graph()
        )

        return cls(_id=db_shape_collection.id, graph=graph, _bm=bm)

    @classmethod
    def load(cls, id: int) -> "ShapeCollection":
        """Get ShapeCollection from database by id.

        :param id: ShapeCollection id
        :type id: int
        :return: ShapeCollection
        :rtype: ShapeCollection
        """
        bm = get_building_motif()
        db_shape_collection = bm.table_connection.get_db_shape_collection(id)
        graph = bm.graph_connection.get_graph(db_shape_collection.graph_id)

        return cls(_id=db_shape_collection.id, graph=graph, _bm=bm)

    @property
    def id(self) -> Optional[int]:
        return self._id

    @id.setter
    def id(self, new_id):
        raise AttributeError("Cannot modify db id")

    @property
    def graph_name(self) -> Optional[URIRef]:
        """
        Returns the name of the graph (subject of "a owl:Ontology")
        if one exists
        """
        # will be None if this is not found
        return self.graph.value(predicate=RDF.type, object=OWL.Ontology)  # type: ignore

    def add_triples(self, *triples: Triple) -> None:
        """Add the given triples to the graph.

        :param triples: a sequence of triples to add to the graph
        :type triples: Triple
        """
        for triple in triples:
            self.graph.add(triple)

    def add_graph(self, graph: rdflib.Graph) -> None:
        """Add the given graph to the ShapeCollection.

        :param graph: the graph to add to the ShapeCollection
        :type graph: rdflib.Graph
        """
        self.graph += graph

    def _cbd(self, shape_name, self_contained=True):
        """Retrieves the Concise Bounded Description (CBD) of the shape."""
        cbd = self.graph.cbd(shape_name)
        # if computing self-contained, do the fixed-point computation produced by unioning
        # the CBDs of all nodes in the current CBD until the graph does not change
        changed = True
        while self_contained and changed:
            new_g = rdflib.Graph()
            for node in cbd.all_nodes():
                new_g += self.graph.cbd(node)
            new_cbd = new_g + cbd
            changed = len(new_cbd) > cbd
            cbd = new_cbd
        return cbd

    def resolve_imports(
        self, recursive_limit: int = -1, error_on_missing_imports: bool = True
    ) -> "ShapeCollection":
        """Resolves `owl:imports` to as many levels as requested.

        By default, all `owl:imports` are recursively resolved. This limit can
        be changed to 0 to suppress resolving imports, or to 1..n to handle
        recursion up to that limit.

        :param recursive_limit: how many levels of `owl:imports` to resolve,
            defaults to -1 (all)
        :type recursive_limit: int, optional
        :param error_on_missing_imports: if True, raises an error if any of the dependency
            ontologies are missing (i.e. they need to be loaded into BuildingMOTIF), defaults
            to True
        :type error_on_missing_imports: bool, optional
        :return: a new ShapeCollection with the types resolved
        :rtype: ShapeCollection
        """
        resolved_namespaces: Set[rdflib.URIRef] = set()
        resolved = _resolve_imports(
            self.graph,
            recursive_limit,
            resolved_namespaces,
            error_on_missing_imports=error_on_missing_imports,
        )
        new_sc = ShapeCollection.create()
        new_sc.add_graph(resolved)
        return new_sc

    @classmethod
    def _get_subclasses_of_definition_type(
        cls, definition_type: URIRef
    ) -> List[URIRef]:
        """Get all the definition types in the ontology that are subclasses in
        the given definition types.

        :param definition_type: the given definition type
        :type definition_type: URIRef
        :return: list of included definition types
        :rtype: List[URIRef]
        """
        children = ontology.subjects(RDFS.subClassOf, definition_type)

        results = [definition_type]
        for child in children:
            results += cls._get_subclasses_of_definition_type(child)

        return results

    @classmethod
    def _get_included_domains(cls, domain: URIRef) -> List[URIRef]:
        """Get all the domains in the ontology that are included in the given
        domains.

        :param domain: the given domain
        :type domain: URIRef
        :return: list of included domains
        :rtype: List[URIRef]
        """
        children = ontology.subjects(BMOTIF.includes, domain)

        results = [domain]
        for child in children:
            results += cls._get_included_domains(child)

        return results

    def infer_templates(self, library: "Library") -> None:
        """Infer templates from the graph in this ShapeCollection and add them to the given library.

        :param library: The library to add inferred templates to
        :type library: Library
        """
        # we need to do the Library import here to avoid circular imports
        from buildingmotif.dataclasses.library import Library

        imports_closure = copy_graph(self.graph)
        dependency_graphs: dict[str, Graph] = {}

        for dependency in self.graph.objects(predicate=rdflib.OWL.imports):
            try:
                lib = Library.load(name=str(dependency))
                imports_closure += lib.get_shape_collection().graph
                dependency_graphs[str(dependency)] = copy_graph(
                    lib.get_shape_collection().graph
                )
            except Exception as e:
                logging.warning(
                    f"An ontology could not resolve a dependency on {dependency} ({e}). Check this is loaded into BuildingMOTIF"
                )
                continue

        class_candidates = set(self.graph.subjects(rdflib.RDF.type, rdflib.OWL.Class))
        shape_candidates = set(
            self.graph.subjects(rdflib.RDF.type, rdflib.SH.NodeShape)
        )
        candidates = class_candidates.intersection(shape_candidates)

        for candidate in candidates:
            assert isinstance(candidate, rdflib.URIRef)
            partial_body, deps = get_template_parts_from_shape(
                candidate, imports_closure, dependency_graphs
            )
            library.create_template(str(candidate), partial_body, dependencies=deps)

    def get_shapes_of_definition_type(
        self, definition_type: URIRef, include_labels=False
    ) -> Union[List[URIRef], List[Tuple[URIRef, str]]]:
        """Get subjects present in shape of the definition type.

        :param definition_type: desired definition type
        :type definition_type: URIRef
        :return: subjects
        :rtype: List[URIRef]
        """
        definition_types = self._get_subclasses_of_definition_type(definition_type)

        results = []
        for definition_type in definition_types:
            instances = self.graph.subjects(RDF.type, definition_type)
            if include_labels:
                results += [
                    (shape, self.graph.value(shape, RDFS.label)) for shape in instances
                ]
            else:
                results += instances

        return results

    def get_shapes_of_domain(self, domain: URIRef) -> List[URIRef]:
        """Get subjects present in shape of domain type.

        :param domain: desired domain
        :type domain: URIRef
        :return: subjects
        :rtype: List[URIRef]
        """
        included_domains = self._get_included_domains(domain)

        results = []
        for domain in included_domains:
            results += self.graph.subjects(RDF.type, domain)

        return results

    def get_shapes_about_class(
        self, rdf_type: URIRef, contexts: Optional[List["ShapeCollection"]] = None
    ) -> List[URIRef]:
        """Returns a list of shapes that either target the given class (or
        superclasses of it), or otherwise only apply to URIs of the given type.

        :param rdf_type: an OWL class
        :type rdf_type: URIRef
        :param contexts: list of ShapeCollections that help determine the class
            structure
        :type contexts: List["ShapeCollection"], optional
        :return: a list of shapes in this ShapeCollection that concern that
            class
        :rtype: List[URIRef]
        """
        # merge the contexts together w/ our graph if they are provided, else
        # just use the existing shape collection graph
        if contexts is not None:
            context = sum(map(lambda x: x.graph, contexts), rdflib.Graph())
            graph = self.graph + context
        else:
            graph = self.graph
        rows = graph.query(
            f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?shape WHERE {{
            ?shape a sh:NodeShape .
            {rdf_type.n3()} rdfs:subClassOf* ?class .
            {{ ?shape sh:targetClass ?class }}
            UNION
            {{ ?shape sh:class ?class }}
        }}"""
        )
        return [row[0] for row in rows]  # type: ignore

    def shape_to_query(self, shape: URIRef) -> str:
        """
        This method takes a URI representing a SHACL shape as an argument and returns
        a SPARQL query selecting the information which would be used to satisfy that
        SHACL shape. This uses the following rules:
        - `<shape> sh:targetClass <class>` -> `?target rdf:type/rdfs:subClassOf* <class>`
        - `<shape> sh:property [ sh:path <path>; sh:class <class>; sh:name <name> ]` ->
            ?target <path> ?name . ?name rdf:type/rdfs:subClassOf* <class>
        - `<shape> sh:property [ sh:path <path>; sh:hasValue <value>]` ->
            ?target <path> <value>
        """
        clauses, project = _shape_to_where(self.graph, shape, "?target")
        preamble = """PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        """
        return f"{preamble} SELECT DISTINCT {' '.join(project)} WHERE {{\n{clauses}\n}}"


def _is_list(graph: Graph, node: Node):
    return (node, RDF.first, None) in graph


def _target_to_sparql(graph: Graph, nodeshape: Node, root_var: str = "?target") -> str:
    """
    Takes the nodeshape and returns the SPARQL query that would be used to
    find the target nodes of that nodeshape. This is a helper function for
    _shape_to_where
    Handles:
    - targetClass
    - targetSubjectsOf
    - targetObjectsOf
    - targetNode

    If there is more than one of these clauses on the nodeshape, they are
    combined with a UNION.

    Returns the string of the query.
    """

    # get all the clauses for the targetClass
    targetClasses = graph.objects(nodeshape, SH.targetClass)
    tc_clauses = [
        f"{root_var} rdf:type/rdfs:subClassOf* {tc.n3()} .\n" for tc in targetClasses  # type: ignore
    ]
    # get all the clauses for the targetSubjectsOf
    targetSubjectsOf = graph.objects(nodeshape, SH.targetSubjectsOf)
    tso_clauses = [
        f"{root_var} {tso.n3()} ?ignore .\n" for tso in targetSubjectsOf  # type: ignore
    ]
    # get all the clauses for the targetObjectsOf
    targetObjectsOf = graph.objects(nodeshape, SH.targetObjectsOf)
    too_clauses = [
        f"?ignore {too.n3()} {root_var} .\n" for too in targetObjectsOf  # type: ignore
    ]

    # get all the clauses for the targetNode
    targetNode = list(graph.objects(nodeshape, SH.targetNode))
    tn_clauses = [
        f"BIND({tn.n3()} AS {root_var}) .\n" for tn in targetNode  # type: ignore
    ]

    # combine all the clauses with a UNION
    all_clauses = tc_clauses + tso_clauses + too_clauses + tn_clauses
    return " UNION ".join(f"{{ {clause} }}" for clause in all_clauses)


def _clauses_on_nodeshape(
    graph: Graph, nodeshape: Node, root_variable: str = "?target"
) -> str:
    """handles the constraint components on a node shape (other than targetClass, targetSubjectsOf, targetObjectsOf, targetNode).
    Builds up the SPARQL query for the given node shape, starting with the given root variable.
    """
    clauses = []
    # handle sh:class
    for class_constraint in graph.objects(nodeshape, SH["class"]):
        clauses.append(
            f"{root_variable} rdf:type/rdfs:subClassOf* {class_constraint.n3()} .\n"
        )

    return " ".join(clauses)


def _shape_to_where(
    graph: Graph, shape: URIRef, root_var: str = "?target"
) -> Tuple[str, List[str]]:
    # we will build the query as a string
    clauses: str = ""
    # build up the SELECT clause as a set of vars
    project: Set[str] = {root_var}

    # local state for generating unique variable names
    prefix = "".join(random.choice(string.ascii_lowercase) for _ in range(2))
    variable_counter = 0

    def get_varname(shape):
        """
        Uses graph.value(shape, SH.name | RDFS.label) to get a name if it exists,
        converting to a string if it is a Literal. Otherwise, generates a new unique
        variable name.
        """
        name = graph.value(shape, SH.name | RDFS.label)
        if isinstance(name, rdflib.Literal):
            name = str(name)
        if name:
            return name.replace(" ", "_")

        # generate symbol
        nonlocal variable_counter
        varname = f"{prefix}{variable_counter}"
        variable_counter += 1
        return varname

    shape_graph = ShapesGraph(graph)

    # get all the target clauses
    clauses += _target_to_sparql(graph, shape, root_var)

    clauses += _clauses_on_nodeshape(graph, shape, root_var)

    # find all of the non-qualified property shapes. All of these will use the same variable
    # for all uses of the same sh:path value
    pshapes_by_path: Dict[Node, List[Node]] = defaultdict(list)
    qualified_pshapes: Set[Node] = set()
    for pshape in graph.objects(shape, SH.property):
        path = shacl_path_to_sparql_path(shape_graph, graph.value(pshape, SH.path))
        if not graph.value(pshape, SH.qualifiedValueShape):
            pshapes_by_path[path].append(pshape)  # type: ignore
        else:
            qualified_pshapes.add(pshape)

    # look at pshapes implicitly defined by sh:path
    for pshape in graph.subjects(predicate=SH.path):
        if (
            pshape == shape
        ):  # skip the input 'shape', otherwise this will infinitely recurse
            continue
        path = shacl_path_to_sparql_path(shape_graph, graph.value(pshape, SH.path))
        if not graph.value(pshape, SH.qualifiedValueShape):
            pshapes_by_path[path].append(pshape)  # type: ignore
        else:
            qualified_pshapes.add(pshape)

    for dep_shape in graph.objects(shape, SH.node):
        dep_clause, dep_project = _shape_to_where(graph, dep_shape, root_var)
        clauses += dep_clause
        project.update(dep_project)

    for or_clause in graph.objects(shape, SH["or"]):
        items = list(graph.objects(or_clause, (RDF.rest * ZeroOrMore) / RDF.first))  # type: ignore
        or_parts = []
        for item in items:
            or_body, or_project = _shape_to_where(graph, item, root_var)
            or_parts.append(or_body)
            project.update(or_project)
        clauses += " UNION ".join(f"{{ {or_body} }}" for or_body in or_parts)

    # 'pshapes_by_path' maps a path to all of the property shapes that use that path on the target
    # assign a unique variable for each sh:path w/o a qualified shape
    pshape_vars: Dict[Node, str] = {}
    for pshape_list in pshapes_by_path.values():
        # get name if it exists, otherwise generate a new one
        pshape_name = get_varname(pshape_list[0])
        varname = f"?{pshape_name}"
        for pshape in pshape_list:
            pshape_vars[pshape] = varname

    for pshape in graph.objects(shape, SH.property):
        # get the varname if we've already assigned one for this pshape above,
        # or generate a new one. When generating a name, use the SH.name|RDFS.label field
        # in the PropertyShape or generate a unique one
        name = pshape_vars.get(
            pshape,
            f"?{get_varname(pshape)}".replace(" ", "_"),
        )
        path = shacl_path_to_sparql_path(graph, graph.value(pshape, SH.path))
        qMinCount = graph.value(pshape, SH.qualifiedMinCount) or 0

        pclass = graph.value(
            pshape, (SH["qualifiedValueShape"] * ZeroOrOne / SH["class"])  # type: ignore
        )
        if pclass:
            clause = f"{root_var} {path} {name} .\n {name} rdf:type/rdfs:subClassOf* {pclass.n3()} .\n"
            if qMinCount == 0:
                clause = f"OPTIONAL {{ {clause} }} .\n"
            clauses += clause
            project.add(name)

        pnode = graph.value(
            pshape, (SH["qualifiedValueShape"] * ZeroOrOne / SH["node"])  # type: ignore
        )
        if pnode:
            node_clauses, node_project = _shape_to_where(graph, pnode, root_var)
            clause = f"{root_var} {path} {name} .\n"
            clause += node_clauses.replace(root_var, name)
            if qMinCount == 0:
                clause = f"OPTIONAL {{ {clause} }}"
            clauses += clause
            project.update({p.replace(root_var, name) for p in node_project})

        or_values = graph.value(
            pshape, (SH["qualifiedValueShape"] * ZeroOrOne / SH["or"])
        )
        if or_values:
            # or clauses share the variable name. Get the variablen name from the SH.name
            # or RDFS.label for the current pshape, or generate a new one
            or_var = get_varname(pshape)
            or_var = f"?{or_var}".replace(" ", "_")
            # connect ?target to the variable that will be used in the OR clauses
            clauses += f"{root_var} {path} {or_var} .\n"
            items = list(graph.objects(or_values, (RDF.rest * ZeroOrMore) / RDF.first))
            or_parts = []
            for item in items:
                or_body, or_project = _shape_to_where(graph, item, or_var)
                or_parts.append(or_body)
                project.update(or_project)
            clauses += " UNION ".join(f"{{ {or_body} }}" for or_body in or_parts)

        pvalue = graph.value(pshape, SH.hasValue)
        if pvalue:
            clauses += f"{root_var} {path} {pvalue.n3()} .\n"

        if not pclass and not pnode and not or_values and not pvalue:
            clauses += f"{root_var} {path} {name} .\n"

    return clauses, list(project)


def find_ontology(
    import_ref: URIRef, containing_graph: Graph = None
) -> Tuple[Union[Graph, None], str]:
    """Resolve a single ontology import by URIRef."""
    if containing_graph is not None:
        if import_ref in containing_graph.subjects(
            predicate=RDF.type, object=OWL.Ontology
        ):
            return containing_graph, "contained"

    from buildingmotif.dataclasses.library import Library

    bm = get_building_motif()
    # try to load the library by name
    try:
        lib = Library.load(name=import_ref)
        return lib.get_shape_collection().graph, "library"
    except Exception:
        pass

    # search through our shape collections for a graph with the provided name
    for shape_collection in bm.table_connection.get_all_db_shape_collections():
        sc = ShapeCollection.load(shape_collection.id)
        if sc.graph_name == import_ref:
            return sc.graph, "shape_collection"

    # Try loading from ontology URI
    try:
        g = Graph()
        g.parse(import_ref)
        return g, "internet"
    except Exception:
        pass

    return None, "not found"


def find_imports(
    graph: rdflib.Graph, depth: int = 1, visited: set = set()
) -> dict[URIRef, Tuple[Tuple[Union[Graph, None], str], dict]]:

    imports = {}
    for ontology in graph.objects(predicate=OWL.imports):
        if ontology not in visited:
            visited.add(ontology)
            resolved_ontology, source = find_ontology(ontology, graph)
            if resolved_ontology is not None and source != "contained" and depth > 0:
                imports[ontology] = (
                    (resolved_ontology, source),
                    find_imports(resolved_ontology, depth - 1),
                )
            else:
                imports[ontology] = ((resolved_ontology, source), {})
    return imports


def _resolve_imports(
    graph: rdflib.Graph,
    recursive_limit: int,
    seen: Set[rdflib.URIRef],
    error_on_missing_imports: bool = True,
) -> rdflib.Graph:
    from buildingmotif.dataclasses.library import Library

    bm = get_building_motif()

    logger = logging.getLogger(__name__)

    if recursive_limit == 0:
        return graph
    new_g = copy_graph(graph)
    for ontology in graph.objects(predicate=OWL.imports):
        if ontology in seen:
            continue
        seen.add(ontology)

        # go find the graph definition from our libraries
        try:
            lib = Library.load(name=ontology)
            sc_to_add = lib.get_shape_collection()
        except Exception as e:
            logger.warning(
                "Could not resolve import of %s from Libraries (%s). Trying shape collections",
                ontology,
                e,
            )
            sc_to_add = None

        # search through our shape collections for a graph with the provided name
        if sc_to_add is None:
            for shape_collection in bm.table_connection.get_all_db_shape_collections():
                sc = ShapeCollection.load(shape_collection.id)
                if sc.graph_name == ontology:
                    sc_to_add = sc
                    break
            logger.warning(
                "Could not resolve import of %s from Libraries. Trying shape collections",
                ontology,
            )

        if sc_to_add is None:
            if error_on_missing_imports:
                raise Exception("Could not resolve import of %s", ontology)
            continue

        dependency = _resolve_imports(
            sc_to_add.graph,
            recursive_limit - 1,
            seen,
            error_on_missing_imports=error_on_missing_imports,
        )
        new_g += dependency
    return new_g
