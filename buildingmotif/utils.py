import logging
import secrets
from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, Union

import pyshacl  # type: ignore
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import _TripleCanonicalizer
from rdflib.paths import ZeroOrOne
from rdflib.term import Node

from buildingmotif.database.errors import TemplateNotFound
from buildingmotif.namespaces import OWL, PARAM, RDF, SH, XSD, bind_prefixes

if TYPE_CHECKING:
    from buildingmotif.dataclasses import Library, Template

Triple = Tuple[Node, Node, Node]
_gensym_counter = 0


def _strip_param(param: Union[Node, str]) -> str:
    """
    Strips all PARAM namespaces from the input parameter
    """
    param = str(param)
    while param.startswith(PARAM):
        param = param[len(PARAM) :]
    return param


def _gensym(prefix: str = "p") -> URIRef:
    """
    Generate a unique identifier.
    """
    global _gensym_counter
    _gensym_counter += 1
    return PARAM[f"{prefix}{_gensym_counter}"]


def _param_name(param: URIRef) -> str:
    """
    Returns the name of the param without the prefix.
    """
    assert param.startswith(PARAM)
    return param[len(PARAM) :]


def _guarantee_unique_template_name(library: "Library", name: str) -> str:
    """
    Ensure that the template name is unique in the library by appending an increasing
    number. This is only called when we are generating templates from GraphDiffs and
    the names are local to the Library. The Library is intended to be ephemeral so these
    names will not be around for long.
    """
    idx = 1
    original_name = name
    try:
        while library.get_template_by_name(name):
            name = f"{original_name}_{idx}"
            idx += 1
    except TemplateNotFound:
        # this means that the template does not exist and we can use the original name
        pass
    return name


def copy_graph(g: Graph, preserve_blank_nodes: bool = True) -> Graph:
    """
    Copy a graph. Creates new blank nodes so that these remain unique to each Graph

    :param g: the graph to copy
    :type g: Graph
    :param preserve_blank_nodes: if true, keep blank nodes the same when copying the graph
    :type preserve_blank_nodes: boolean, defaults to True
    :return: a copy of the input graph
    :rtype: Graph
    """
    c = Graph()
    new_prefix = secrets.token_hex(4)
    for t in g.triples((None, None, None)):
        assert isinstance(t, tuple)
        (s, p, o) = t
        if not preserve_blank_nodes:
            if isinstance(s, BNode):
                s = BNode(value=new_prefix + s.toPython())
            if isinstance(p, BNode):
                p = BNode(value=new_prefix + p.toPython())
            if isinstance(o, BNode):
                o = BNode(value=new_prefix + o.toPython())
        c.add((s, p, o))
    return c


def inline_sh_nodes(g: Graph):
    """
    Recursively inlines all sh:node properties and objects on the graph.

    :param g: graph to be edited
    :type g: Graph
    """
    q = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>
    CONSTRUCT {
        ?parent ?p ?o .
    }
    WHERE {
        ?parent sh:node ?child .
        ?child ?p ?o
    }"""
    original_size = 0
    while original_size != len(g):  # type: ignore
        original_size = len(g)  # type: ignore
        for (s, p, o) in g.query(q):  # type: ignore
            if p == RDF.type and o == SH.NodeShape:
                continue
            g.add((s, p, o))
        break


def combine_graphs(*graphs: Graph) -> Graph:
    """Combine all of the graphs into a new graph.

    :return: combined graph
    :rtype: Graph
    """
    newg = Graph()
    for graph in graphs:
        newg += graph
    return newg


def graph_size(g: Graph) -> int:
    """Returns the number of triples in a graph.

    :param g: graph to be measured
    :type g: Graph
    :return: number of triples in the graph
    :rtype: int
    """
    return len(tuple(g.triples((None, None, None))))


def remove_triples_with_node(g: Graph, node: URIRef) -> None:
    """Remove all triples that include the given node. Edits the graph
    in-place.

    :param g: the graph to remove triples from
    :type g: Graph
    :param node: the node to remove
    :type node: URIRef
    """
    for triple in g.triples((node, None, None)):
        g.remove(triple)
    for triple in g.triples((None, node, None)):
        g.remove(triple)
    for triple in g.triples((None, None, node)):
        g.remove(triple)


def replace_nodes(g: Graph, replace: Dict[Node, Node]) -> None:
    """Replace nodes in a graph.

    :param g: graph to replace nodes in
    :type g: Graph
    :param replace: dict mapping old nodes to new nodes
    :type replace: Dict[Node, Node]
    """
    for s, p, o in g.triples((None, None, None)):
        g.remove((s, p, o))
        if s in replace:
            s = replace[s]
        if p in replace:
            p = replace[p]
        if o in replace:
            o = replace[o]
        g.add((s, p, o))


def get_ontology_files(directory: Path, recursive: bool = True) -> List[Path]:
    """Returns a list of all ontology files in the given directory.

    If recursive is true, traverses the directory structure to find ontology
    files not just in the given directory.

    :param directory: the directory to begin the search
    :type directory: Path
    :param recursive: if true, find ontology files in nested directories,
        defaults to true
    :type recursive: bool, optional
    :return: a list of filenames
    :rtype: List[Path]
    """
    patterns = [
        "*.ttl",
        "*.n3",
        "*.rdf",
        "*.xml",
    ]
    if recursive:
        searches = (directory.rglob(f"{pat}") for pat in patterns)
    else:
        searches = (directory.glob(f"{pat}") for pat in patterns)
    # filter out files in .ipynb_checkpoints
    filtered_searches = (
        filter(lambda x: ".ipynb_checkpoints" not in Path(x).parts, search)
        for search in searches
    )
    return list(chain.from_iterable(filtered_searches))


def get_template_parts_from_shape(
    shape_name: URIRef,
    shape_graph: Graph,
    depedency_graphs: Dict[str, Graph] = {},
) -> Tuple[Graph, List[Dict]]:
    """Turn a SHACL shape into a template. The following attributes of
    NodeShapes will be incorporated into the resulting template:
    - sh:property with sh:minCount
    - sh:property with sh:qualifiedMinCount
    - sh:class
    - sh:node

    :param shape_name: name of shape
    :type shape_name: URIRef
    :param shape_graph: shape graph
    :type shape_graph: Graph
    :param depedency_graphs: colleciton of graphs and which depdency library they came from
    :type depedency_graphs: dict[str, Graph]
    :raises Exception: if more than one object type detected on shape
    :raises Exception: if more than one min count detected on shape
    :return: template parts
    :rtype: Tuple[Graph, List[Dict]]
    """
    # TODO: sh:or?
    # the template body
    body = Graph()
    root_param = PARAM["name"]

    deps = []

    pshapes = shape_graph.objects(subject=shape_name, predicate=SH["property"])
    for pshape in pshapes:
        property_path = shape_graph.value(pshape, SH["path"])
        if property_path is None:
            raise Exception(
                f"no sh:path detected on {shape_name} property shape {pshape}"
            )
        # TODO: expand otypes to include sh:in, sh:or, or no datatype at all!
        otypes = list(
            shape_graph.objects(
                subject=pshape,
                predicate=SH["qualifiedValueShape"]
                * ZeroOrOne  # type:ignore
                / (SH["class"] | SH["node"] | SH["datatype"]),
            )
        )
        mincounts = list(
            shape_graph.objects(
                subject=pshape, predicate=SH["minCount"] | SH["qualifiedMinCount"]
            )
        )
        if len(otypes) > 1:
            raise Exception(f"more than one object type detected on {shape_name}")
        if len(mincounts) > 1:
            raise Exception(f"more than one min count detected on {shape_name}")
        if len(mincounts) == 0 or len(otypes) == 0:
            # print(f"No useful information on {shape_name} - {pshape}")
            # print(shape_graph.cbd(pshape).serialize())
            continue
        (path, otype, mincount) = property_path, otypes[0], mincounts[0]
        assert isinstance(mincount, Literal)

        param_name = shape_graph.value(pshape, SH["name"])

        for num in range(int(mincount)):
            if param_name is not None:
                param = PARAM[f"{param_name}{num}"]
            else:
                param = _gensym()
            body.add((root_param, path, param))

            otype_as_class = (None, SH["class"], otype) in shape_graph
            otype_as_node = (None, SH["node"], otype) in shape_graph
            otype_is_nodeshape = (otype, RDF.type, SH.NodeShape) in shape_graph

            if (otype_as_class and otype_is_nodeshape) or otype_as_node:
                if not isinstance(otype, URIRef):
                    continue
                library = None
                for library_name, graph in depedency_graphs.items():
                    if (otype, RDF.type, SH.NodeShape) in graph:
                        library = library_name
                        break
                if library is None:
                    deps.append({"template": str(otype), "args": {"name": param}})
                else:
                    deps.append(
                        {
                            "template": str(otype),
                            "library": library,
                            "args": {"name": param},
                        }
                    )
                body.add((param, RDF.type, otype))

        pvalue = shape_graph.value(pshape, SH["hasValue"])
        if pvalue:
            body.add((root_param, path, pvalue))

    if (shape_name, RDF.type, OWL.Class) in shape_graph:
        body.add((root_param, RDF.type, shape_name))

    classes = shape_graph.objects(shape_name, SH["class"])
    for cls in classes:
        body.add((root_param, RDF.type, cls))

    classes = shape_graph.objects(shape_name, SH["targetClass"])
    for cls in classes:
        body.add((root_param, RDF.type, cls))

    # for all objects of sh:node, add them to the deps if they haven't been added
    # already through the property shapes above
    nodes = shape_graph.cbd(shape_name).objects(predicate=SH["node"], unique=True)
    for node in nodes:
        # if node is already in deps, skip it
        if any(str(node) == dep["template"] for dep in deps):
            continue
        # skip non-URIRef nodes
        if not isinstance(node, URIRef):
            continue
        deps.append(
            {"template": str(node), "args": {"name": "name"}}
        )  # tie to root param

    return body, deps


@dataclass
class _TemplateIndex:
    template: "Template"
    param_types: Dict[Node, List[Node]]
    prop_types: Dict[Node, List[Node]]
    prop_values: Dict[Node, List[Node]]
    prop_shapes: Dict[Node, List[Node]]
    target: URIRef

    @property
    def target_type(self):
        return self.param_types[self.target][0]


def _prep_shape_graph() -> Graph:
    shape = Graph()
    bind_prefixes(shape)
    shape.bind("mark", PARAM)
    return shape


def _index_properties(
    templ: "Template", error_on_missing_dependency: bool = True
) -> _TemplateIndex:
    templ_graph = templ.evaluate(
        {p: PARAM[p] for p in templ.parameters}, {"mark": PARAM}
    )
    assert isinstance(templ_graph, Graph)

    # pick a random node to act as the 'target' of the shape
    target = next(iter(templ_graph.subjects(RDF.type)))
    print(f"Choosing {target} as the target of the shape")
    assert isinstance(target, URIRef)

    # store the classes for each parameter
    param_types: Dict[Node, List[Node]] = defaultdict(list)
    for (param, ptype) in templ_graph.subject_objects(RDF.type):
        param_types[param].append(ptype)

    # store the properties and their types for the target
    prop_types: Dict[Node, List[Node]] = defaultdict(list)
    prop_values: Dict[Node, List[Node]] = defaultdict(list)
    prop_shapes: Dict[Node, List[Node]] = defaultdict(list)
    # TODO: prop_shapes for all properties whose object corresponds to another shape
    for p, o in templ_graph.predicate_objects(target):
        if p == RDF.type:
            continue
        # maybe_param = str(o).removeprefix(PARAM) Python >=3.9
        maybe_param = str(o)[len(PARAM) :]
        if maybe_param in templ.dependency_parameters:
            dep = templ.dependency_for_parameter(
                maybe_param, error_on_missing_dependency
            )
            if dep is not None:
                prop_shapes[p].append(URIRef(dep._name))
        elif o in param_types:
            prop_types[p].append(param_types[o][0])
        elif str(o) not in PARAM:
            prop_values[p].append(o)
        elif str(o) in PARAM and o not in param_types:
            logging.warn(
                f"{o} is does not have a type and does not seem to be a literal"
            )
    return _TemplateIndex(
        templ,
        dict(param_types),
        dict(prop_types),
        dict(prop_values),
        dict(prop_shapes),
        target,
    )


def _add_property_shape(
    graph: Graph, name: Node, constraint: Node, path: Node, value: Node
):
    pshape = BNode()
    graph.add((name, SH.property, pshape))
    graph.add((pshape, SH.path, path))
    graph.add((pshape, constraint, value))
    graph.add((pshape, SH["minCount"], Literal(1)))
    graph.add((pshape, SH["maxCount"], Literal(1)))


def _add_qualified_property_shape(
    graph: Graph, name: Node, constraint: Node, path: Node, value: Node
):
    pshape = BNode()
    graph.add((name, SH.property, pshape))
    graph.add((pshape, SH.path, path))
    qvc = BNode()
    graph.add((pshape, SH["qualifiedValueShape"], qvc))
    graph.add((qvc, constraint, value))
    graph.add((pshape, SH["qualifiedMinCount"], Literal(1)))
    graph.add((pshape, SH["qualifiedMaxCount"], Literal(1)))


def template_to_shape(template: "Template") -> Graph:
    """Turn this template into a SHACL shape.

    :param template: template to convert
    :type template: template
    :return: graph of template
    :rtype: Graph
    """
    # TODO If 'use_all' is True, this will create a shape that incorporates all
    # Templates by the same name in the same Library.
    templ = copy(template)
    shape = _prep_shape_graph()

    idx = _index_properties(templ)

    shape.add((PARAM[templ.name], SH.targetClass, idx.target_type))
    # create the shape
    shape.add((PARAM[templ.name], RDF.type, SH.NodeShape))
    shape.add((PARAM[templ.name], SH["class"], idx.target_type))
    for prop, ptypes in idx.prop_types.items():
        if len(ptypes) == 1:
            _add_property_shape(shape, PARAM[templ.name], SH["class"], prop, ptypes[0])
        else:  # more than one ptype
            for ptype in ptypes:
                _add_qualified_property_shape(
                    shape, PARAM[templ.name], SH["class"], prop, ptype
                )
    for prop, values in idx.prop_values.items():
        if len(values) == 1:
            _add_property_shape(shape, PARAM[templ.name], SH.hasValue, prop, values[0])
        else:  # more than one ptype
            for value in values:
                _add_qualified_property_shape(
                    shape, PARAM[templ.name], SH.hasValue, prop, value
                )
    for prop, shapes in idx.prop_shapes.items():
        if len(shapes) == 1:
            _add_property_shape(shape, PARAM[templ.name], SH["node"], prop, shapes[0])
        else:  # more than one ptype
            for shp in shapes:
                _add_qualified_property_shape(
                    # TODO: fix this?
                    shape,
                    PARAM[templ.name],
                    SH.node,
                    prop,
                    PARAM[str(shp)],
                )

    return shape


def new_temporary_graph(more_namespaces: Optional[dict] = None) -> Graph:
    """Creates a new in-memory RDF graph with common and additional namespace
    bindings.

    :param more_namespaces: namespaces, defaults to None
    :type more_namespaces: Optional[dict], optional
    :return: graph with namespaces
    :rtype: Graph
    """
    g = Graph()
    bind_prefixes(g)
    if more_namespaces:
        for prefix, uri in more_namespaces.items():
            g.bind(prefix, uri)
    return g


def get_parameters(graph: Graph) -> Set[str]:
    """Returns the set of parameter names in the given graph.

    Parameters are identified by the PARAM namespace, `urn:___param___#`. This
    method returns the names of the parameters, not the full URIs. For example,
    the parameter `urn:___param___#abc` in a graph would be returned as `abc`.

    :param graph: a graph containing parameters
    :type graph: Graph
    :return: a set of the parameter names in the graph
    :rtype: Set[str]
    """
    # get an iterable of all nodes in the graph
    all_nodes = chain.from_iterable(graph.triples((None, None, None)))
    # get all nodes in the PARAM namespace
    params = {str(node) for node in all_nodes if str(node).startswith(PARAM)}
    # extract the 'value' part of the param, which is the name of the parameter
    return {node[len(PARAM) :] for node in params}


def _inline_sh_node(sg: Graph):
    """
    This detects the use of 'sh:node' on SHACL NodeShapes and inlines
    the shape they point to.
    """
    q = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>
    SELECT ?parent ?child WHERE {
        ?parent a sh:NodeShape ;
                sh:node ?child .
        }"""
    for row in sg.query(q):
        parent, child = row  # type: ignore
        sg.remove((parent, SH.node, child))
        pos = sg.predicate_objects(child)
        for (p, o) in pos:
            sg.add((parent, p, o))


def _inline_sh_and(sg: Graph):
    """
    This detects the use of 'sh:and' on SHACL NodeShapes and inlines
    all of the included shapes
    """
    q = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>
    SELECT ?parent ?child ?andnode WHERE {
        ?parent a sh:NodeShape ;
                sh:and ?andnode .
        ?andnode rdf:rest*/rdf:first ?child .
        }"""
    for row in sg.query(q):
        parent, child, to_remove = row  # type: ignore
        sg.remove((parent, SH["and"], to_remove))
        pos = sg.predicate_objects(child)
        for (p, o) in pos:
            sg.add((parent, p, o))


def _inline_sh_qualified_value_shape(sg: Graph):
    """
    This detects the use of 'sh:qualifiedValueShape' on SHACL PropertyShapes and inlines
    all of the included shapes
    """
    q = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>
    SELECT ?parent ?child WHERE {
        ?parent a sh:PropertyShape ;
                sh:qualifiedValueShape ?child .
        }"""
    for row in sg.query(q):
        parent, child = row  # type: ignore
        sg.remove((parent, SH["qualifiedValueShape"], child))
        pos = sg.predicate_objects(child)
        for (p, o) in pos:
            sg.add((parent, p, o))


def rewrite_shape_graph(g: Graph) -> Graph:
    """
    Rewrites the input graph to make the resulting validation report more useful.

    :param g: the shape graph to rewrite
    :type g: Graph
    :return: a *copy* of the original shape graph w/ rewritten shapes
    :rtype: Graph
    """
    sg = copy_graph(g)

    previous_size = -1
    while len(sg) != previous_size:  # type: ignore
        previous_size = len(sg)  # type: ignore
        _inline_sh_and(sg)
        # make sure to handle sh:node *after* sh:and
        _inline_sh_node(sg)
        _inline_sh_qualified_value_shape(sg)
    return sg


def skip_uri(uri: URIRef) -> bool:
    """
    Returns True if the URI should be skipped during processing
    because it is axiomatic or not expected to be imported.

    Skips URIs in the XSD and SHACL namespaces.

    :return: True if the URI should be skipped; False otherwise
    :rtype: bool
    """
    # Now that we have all the templates, we can populate the dependencies.
    # IGNORES missing XSD imports --- there is really no reason to import the XSD
    # ontology because the handling is baked into the software processing the RDF
    # graph. Thus, XSD URIs will always yield import warnings. This is noisy, so we
    # suppress them.
    skip_ns = [XSD, SH]
    for ns in skip_ns:
        if uri.startswith(ns):
            return True
    return False


def shacl_validate(
    data_graph: Graph,
    shape_graph: Optional[Graph] = None,
    engine: Optional[str] = "topquadrant",
) -> Tuple[bool, Graph, str]:
    """
    Validate the data graph against the shape graph.
    Uses the fastest validation method available. Use the 'topquadrant' feature
    to use TopQuadrant's SHACL engine. Defaults to using PySHACL.

    :param data_graph: the graph to validate
    :type data_graph: Graph
    :param shape_graph: the shape graph to validate against
    :type shape_graph: Graph, optional
    :param engine: the SHACL engine to use, defaults to "topquadrant"
    :type engine: str, optional
    :return: a tuple containing the validation result, the validation report, and the validation report string
    :rtype: Tuple[bool, Graph, str]
    """

    if engine == "topquadrant":
        try:
            from brick_tq_shacl.topquadrant_shacl import (
                validate as tq_validate,  # type: ignore
            )

            return tq_validate(data_graph, shape_graph or Graph())  # type: ignore
        except ImportError:
            logging.info(
                "TopQuadrant SHACL engine not available. Using PySHACL instead."
            )
            pass

    data_graph = data_graph + (shape_graph or Graph())
    return pyshacl.validate(
        data_graph,
        shacl_graph=shape_graph,
        ont_graph=shape_graph,
        advanced=True,
        js=True,
        allow_warnings=True,
    )  # type: ignore


def shacl_inference(
    data_graph: Graph,
    shape_graph: Optional[Graph] = None,
    engine: Optional[str] = "topquadrant",
) -> Graph:
    """
    Infer new triples in the data graph using the shape graph.
    Edits the data graph in place. Uses the fastest inference method available.
    Use the 'topquadrant' feature to use TopQuadrant's SHACL engine. Defaults to
    using PySHACL.

    :param data_graph: the graph to infer new triples in
    :type data_graph: Graph
    :param shape_graph: the shape graph to use for inference
    :type shape_graph: Optional[Graph]
    :param engine: the SHACL engine to use, defaults to "topquadrant"
    :type engine: str, optional
    :return: the data graph with inferred triples
    :rtype: Graph
    """
    if engine == "topquadrant":
        try:
            from brick_tq_shacl.topquadrant_shacl import infer as tq_infer

            return tq_infer(data_graph, shape_graph or Graph())  # type: ignore
        except ImportError:
            logging.info(
                "TopQuadrant SHACL engine not available. Using PySHACL instead."
            )
            pass

    # We use a fixed-point computation approach to 'compiling' RDF models.
    # We accomlish this by keeping track of the size of the graph before and after
    # the inference step. If the size of the graph changes, then we know that the
    # inference has had some effect. We do this at most 3 times to avoid looping
    # forever.
    pre_compile_length = len(data_graph)  # type: ignore
    pyshacl.validate(
        data_graph=data_graph,
        shacl_graph=shape_graph,
        ont_graph=shape_graph,
        advanced=True,
        inplace=True,
        js=True,
        allow_warnings=True,
    )
    post_compile_length = len(data_graph)  # type: ignore

    attempts = 3
    while attempts > 0 and post_compile_length != pre_compile_length:
        pre_compile_length = len(data_graph)  # type: ignore
        pyshacl.validate(
            data_graph=data_graph,
            shacl_graph=shape_graph,
            ont_graph=shape_graph,
            advanced=True,
            inplace=True,
            js=True,
            allow_warnings=True,
        )
        post_compile_length = len(data_graph)  # type: ignore
        attempts -= 1
    return data_graph - (shape_graph or Graph())


def skolemize_shapes(g: Graph) -> Graph:
    """
    Skolemize the shapes in the graph.

    :param g: the graph to skolemize
    :type g: Graph
    :return: the skolemized graph
    :rtype: Graph
    """
    # write a query to update agraph by changing all PropertyShape blank nodes
    # to URIRefs
    g = copy_graph(g)
    property_shapes = list(g.subjects(predicate=RDF.type, object=SH.PropertyShape))
    property_shapes.extend(list(g.objects(predicate=SH.property)))
    replacements = {}
    for ps in property_shapes:
        # if not bnode, skip
        if not isinstance(ps, BNode):
            continue
        # create a new URIRef
        new_ps = URIRef(f"urn:well-known/{secrets.token_hex(4)}")
        # replace the old BNode with the new URIRef
        replacements[ps] = new_ps
    # apply the replacements
    replace_nodes(g, replacements)

    # name all objects of qualifiedValueShape
    qvs = list(g.objects(predicate=SH.qualifiedValueShape))
    replacements = {}
    for qv in qvs:
        # if not bnode, skip
        if not isinstance(qv, BNode):
            continue
        # create a new URIRef
        new_qv = URIRef(f"urn:well-known/{secrets.token_hex(4)}")
        # replace the old BNode with the new URIRef
        replacements[qv] = new_qv
    # apply the replacements
    replace_nodes(g, replacements)
    return g


def graph_hash(graph: Graph) -> int:
    """
    Returns a cryptographic hash of the graph contents.
    This uses the same method as rdflib's isomorphic function to generate a cryptographic hash of a given graph.
    This method calculates a consistent hash of the canonicalized form of the graph.
    If the hashes of two graphs are equal, this means that the graphs are isomorphic.
    Generating the hashes (using this method) and caching them allows graph isomorphism to be determined
    without having to recalculate the canonical form of the graph, which can be expensive.

    :param graph: graph to hash
    :type graph: graph

    :return: integer hash
    :rtype: int
    """
    # Copy graph to memory (improved performance if graph is backed by a DB store)
    graph_prime = copy_graph(graph)
    triple_canonicalizer = _TripleCanonicalizer(graph_prime)

    return triple_canonicalizer.to_hash()
