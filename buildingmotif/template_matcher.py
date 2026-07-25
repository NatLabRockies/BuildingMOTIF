"""
Using the VF2 algorithm to compute subgraph isomorphisms between a template T and a graph G.
If the found isomorphism is a subgraph of T, then T is not fully matched and additional
input is required to fully populate the template.
"""
from collections import defaultdict
from itertools import combinations, permutations
from typing import TYPE_CHECKING, Callable, Dict, Generator, List, Optional, Set, Tuple

import networkx as nx  # type: ignore
from networkx.algorithms.isomorphism import DiGraphMatcher  # type: ignore
from rdflib import Graph, URIRef
from rdflib.extras.external_graph_libs import rdflib_to_networkx_digraph
from rdflib.term import Node

from buildingmotif.namespaces import OWL, PARAM, RDF, RDFS
from buildingmotif.utils import copy_graph

if TYPE_CHECKING:
    from buildingmotif.dataclasses.template import Template

Mapping = Dict[Node, Node]


# used to accelerate monomorphism search
# outer key is the address of the ontology graph
# inner map is from a class to its parent classes
class _ontology_lookup_cache:
    sc_cache: Dict[int, Dict[Node, Set[Node]]]
    t_cache: Dict[int, Dict[Node, Set[Node]]]
    in_cache: Dict[int, Dict[Node, bool]]

    def __init__(self):
        self.sc_cache = {}
        self.sp_cache = {}
        self.t_cache = {}
        self.in_cache = {}

    def parents(self, ntype: Node, ontology: Graph) -> Set[Node]:
        if id(ontology) not in self.sc_cache:
            self.sc_cache[id(ontology)] = {}
        cache = self.sc_cache[id(ontology)]
        # populate cache if necessary
        if ntype not in cache:
            cache[ntype] = set(ontology.transitive_objects(ntype, RDFS.subClassOf))  # type: ignore
        return cache[ntype]

    def superproperties(self, ntype: Node, ontology: Graph) -> Set[Node]:
        if id(ontology) not in self.sp_cache:
            self.sp_cache[id(ontology)] = {}
        cache = self.sp_cache[id(ontology)]
        # populate cache if necessary
        if ntype not in cache:
            cache[ntype] = set(ontology.transitive_objects(ntype, RDFS.subPropertyOf))
        return cache[ntype]

    def types(self, node: Node, graph: Graph) -> Set[URIRef]:
        if id(graph) not in self.t_cache:
            self.t_cache[id(graph)] = {}
        cache = self.t_cache[id(graph)]
        # populate cache if necessary
        if node not in cache:
            cache[node] = set(graph.objects(node, RDF.type))  # type: ignore
        if len(cache[node]) == 0:
            cache[node] = {OWL.NamedIndividual}
        return cache[node]  # type: ignore

    def defined_in(self, node: Node, graph: Graph) -> bool:
        if id(graph) not in self.in_cache:
            self.in_cache[id(graph)] = {}
        cache = self.in_cache[id(graph)]
        # populate cache if necessary
        if node not in cache:
            cache[node] = (node, RDF.type, OWL.Class) in graph
        return cache[node]


def _get_types(n: Node, g: Graph, _cache: _ontology_lookup_cache) -> Set[URIRef]:
    """
    Types for a node should only be URIRefs, so the
    type filtering here should be safe.
    Defaults to owl:NamedIndividual as a "root" type
    """
    return _cache.types(n, g)


def _compatible_types(
    n1: Node,
    g1: Graph,
    n2: Node,
    g2: Graph,
    ontology: Graph,
    _cache: _ontology_lookup_cache,
) -> bool:
    """
    Returns true if the two terms have covariant types.

    :param n1: First node
    :type n1: Node
    :param g1: The graph containing the first node's types
    :type g1: Graph
    :param n2: Second node
    :type n2: Node
    :param g2: The graph containing the second node's types
    :type g2: Graph
    :param ontology: The ontology graph that defines the class hierarchy
    :type ontology: Graph
    :return: True if the nodes are semantically compatible, false otherwise
    :rtype: bool
    """
    n1types = _get_types(n1, g1, _cache)
    n2types = _get_types(n2, g2, _cache)
    # check if these are properties; if so, use subPropertyOf, not subClassOf
    property_types = {OWL.ObjectProperty, OWL.DatatypeProperty}
    if property_types.intersection(n1types) and property_types.intersection(n2types):
        for n1type in _get_types(n1, g1, _cache):
            for n2type in _get_types(n2, g2, _cache):

                # check if types are covariant
                if n2type in _cache.superproperties(
                    n1type, ontology
                ) or n1type in _cache.superproperties(n2type, ontology):
                    return True
    else:
        for n1type in _get_types(n1, g1, _cache):
            for n2type in _get_types(n2, g2, _cache):

                # check if types are covariant
                if n2type in _cache.parents(
                    n1type, ontology
                ) or n1type in _cache.parents(n2type, ontology):
                    return True
    return False


def get_semantic_feasibility(
    G1: Graph, G2: Graph, ontology: Graph, _cache: _ontology_lookup_cache
) -> Callable[[Node, Node], bool]:
    """Returns a function that checks if two nodes are semantically feasible to
    be matched given the information in the provided ontology.

    The function returns true if the two nodes are semantically feasible to be
    matched. We use the following checks:
    1. If the two nodes are both classes, one must be a subclass of the other.
    2. If the two nodes are instances, they must be of the same class.

    :param G1: graph 1
    :type G1: Graph
    :param G2: graph 2
    :type G2: Graph
    :param ontology: ontology graph
    :type ontology: Graph
    :param _cache: ontology lookup cache
    :type _cache: _ontology_lookup_cache
    :return: function that checks if two nodes are semantically feasible
    :rtype: Callable[[Node, Node], bool]
    """
    # TODO: other checks?
    def semantic_feasibility(n1: Node, n2: Node) -> bool:
        """Checks if two nodes are semantically feasible to be matched.

        :param n1: node 1
        :type n1: Node
        :param n2: node 2
        :type n2: Node
        :return: true if nodes are feasible, false if not
        :rtype: bool
        """
        # case 0: same node
        if n1 == n2:
            return True
        # case 1: both are classes
        if _cache.defined_in(n1, ontology) and _cache.defined_in(n2, ontology):
            if n2 in _cache.parents(n1, ontology):
                return True
            elif n1 in _cache.parents(n2, ontology):
                return True
            else:
                return False
        # case 2: both are instances
        if _compatible_types(n1, G1, n2, G2, ontology, _cache):
            return True
        return False

    return semantic_feasibility


class _VF2SemanticMatcher(DiGraphMatcher):
    """
    A subclass of DiGraphMatcher that incorporates semantic feasibility into the matching
    process using the provided ontology.

    :param T: template graph
    :param G: building graph
    :param ontology: ontology that contains the information about node semantics
    """

    def __init__(self, T: Graph, G: Graph, ontology: Graph):
        super().__init__(rdflib_to_networkx_digraph(T), rdflib_to_networkx_digraph(G))
        self.ontology = ontology
        self._cache = _ontology_lookup_cache()
        self._semantic_feasibility = get_semantic_feasibility(
            T, G, ontology, self._cache
        )

    def semantic_feasibility(self, g1: Node, g2: Node) -> bool:
        """
        Returns true if the two nodes are semantically feasible to be matched.
        """
        val = self._semantic_feasibility(g1, g2)
        return val


def generate_all_subgraphs(T: Graph) -> Generator[Graph, None, None]:
    """Generates all node-induced subgraphs of T in order of decreasing size.

    We generate subgraphs in decreasing order of size because we want to find
    the largest subgraph as part of the monomorphism search process.

    :param T: template graph
    :type T: Graph
    :yield: subgraphs
    :rtype: Generator[Graph, None, None]
    """
    # no monomorphism will be larger than the number of distinct nodes in the graph
    largest_sg_size = len(T.all_nodes())
    for nodecount in range(largest_sg_size, 1, -1):
        for nodelist in combinations(T.all_nodes(), nodecount):
            yield digraph_to_rdflib(rdflib_to_networkx_digraph(T).subgraph(nodelist))


def digraph_to_rdflib(digraph: nx.DiGraph) -> Graph:
    """Turns a `nx.DiGraph` into an `rdflib.Graph`.

    Expects the nx.DiGraph to have been produced by
    :py:func:`rdflib_to_networkx_digraph`.

    :param digraph: directed graph
    :type digraph: nx.DiGraph
    :return: RDF graph
    :rtype: Graph
    """
    g = Graph()
    for s, o, pdict in digraph.edges(data=True):
        g.add((s, pdict["triples"][0][1], o))
    return g


class TemplateMatcher:
    """Computes the set of subgraphs of G that are monomorphic to T; these are
    organized by how "complete" the monomorphism is.
    """

    mappings: Dict[int, List[Mapping]]
    template: "Template"
    building: Graph
    template_bindings: Dict[str, Node]
    template_graph: Graph

    def __init__(
        self,
        building: Graph,
        template: "Template",
        ontology: Graph,
        graph_target: Optional[Node] = None,
    ):
        self.mappings = defaultdict(list)
        self.template_bindings = {}
        self.template = template
        self.building = building
        self.ontology = ontology
        self.graph_target = graph_target

        self.template_graph = copy_graph(template.body)
        self.template_parameters: Set[Node] = {
            PARAM[p] for p in self.template.parameters
        }

        self._generate_mappings()

    def _generate_mappings(self):
        for template_subgraph in generate_all_subgraphs(self.template_graph):
            matching = _VF2SemanticMatcher(
                self.building, template_subgraph, self.ontology
            )
            if matching.subgraph_is_monomorphic():
                for sg in matching.subgraph_monomorphisms_iter():
                    # skip if the subgraph does not contain the graph node we care about
                    if self.graph_target and self.graph_target not in sg.keys():
                        continue
                    # sg is a mapping from building graph nodes to template nodes
                    # that constitutes a monomorphism.
                    if len(sg) == 0:
                        continue
                    # TODO: Limit mappings to those that include all of the params?
                    # TODO: ignore optional parameters?
                    # TODO: require that 'name' is in the parameters?

                    # if there is an overlap, yield the subgraph
                    if set(sg.values()).intersection(self.template_parameters):
                        self.add_mapping(sg)

    def add_mapping(self, mapping: Mapping):
        """Adds a mapping to the set of mappings.

        :param mapping: mapping
        :type mapping: Mapping
        """
        if mapping not in self.mappings[len(mapping)]:
            self.mappings[len(mapping)].append(mapping)

    @property
    def largest_mapping_size(self) -> int:
        """Returns the size of the largest mapping.

        :return: size of largest mapping
        :rtype: int
        """
        return max(self.mappings.keys())

    def building_subgraph_from_mapping(self, mapping: Mapping) -> Graph:
        """Returns the subgraph of the building graph that corresponds to the
        given mapping.

        :param mapping: mapping
        :type mapping: Mapping
        :return: subgraph
        :rtype: Graph
        """
        g = rdflib_to_networkx_digraph(self.building)
        edges = permutations(mapping.keys(), 2)
        sg = g.edge_subgraph(edges)
        return digraph_to_rdflib(sg)

    def template_subgraph_from_mapping(self, mapping: Mapping) -> Graph:
        """Returns the subgraph of the template graph that corresponds to the
        given mapping.

        :param mapping: mapping
        :type mapping: Mapping
        :return: subgraph
        :rtype: Graph
        """
        # TODO: need to keep the edges that are more generic than what we have inside the graph.
        # For example, if the building has (x a brick:AHU) then we don't need to remind them to
        # add an edge (x a brick:Equipment) because that is redundant
        g = rdflib_to_networkx_digraph(self.template_graph)
        return digraph_to_rdflib(g.subgraph(mapping.values()))

    def remaining_template_graph(self, mapping: Mapping) -> Graph:
        """Returns the remaining template graph to be filled out given a
        mapping.

        :param mapping: mapping
        :type mapping: Mapping
        :return: remaining template graph to be filled out
        :rtype: Graph
        """
        sg = self.template_subgraph_from_mapping(mapping)
        return self.template_graph - sg

    def remaining_template(self, mapping: Mapping) -> Optional["Template"]:
        """Returns the remaining template to be filled out given a mapping.

        :param mapping: mapping
        :type mapping: Mapping
        :return: remaining template to be filled out
        :rtype: Optional[Template]
        """
        # if all parameters are fulfilled by the mapping, then return None
        mapping = {k: v for k, v in mapping.items() if str(v) in PARAM}
        mapped_params: Set[Node] = {v for v in mapping.values()}
        if not self.template_parameters - mapped_params:
            # return self.building_subgraph_from_mapping(mapping)
            return None
        bindings = {}
        for building_node, param in mapping.items():
            if param is not None:
                bindings[str(param)[len(PARAM) :]] = building_node
        return self.template.substitute(bindings)

    def mappings_iter(self, size=None) -> Generator[Mapping, None, None]:
        """Returns an iterator over all of the mappings of the given size.

        If size is None, then all mappings are returned in descending order
        of the size of the mapping. This means the most complete mappings
        will be returned first.

        :param size: size, defaults to None
        :type size: int, optional
        :yield: mapping iterator
        :rtype: Generator[Mapping, None, None]
        """
        if size is None:
            for size in sorted(self.mappings.keys(), reverse=True):
                for mapping in self.mappings[size]:
                    if not mapping:
                        continue
                    yield mapping
        else:
            for mapping in self.mappings[size]:
                if not mapping:
                    continue
                yield mapping

    def building_mapping_subgraphs_iter(
        self,
        size=None,
    ) -> Generator[Tuple[Mapping, Graph], None, None]:
        """Returns an iterator over all of the subgraphs with a mapping of the
        given size.

        If size is None, then all mappings are returned in descending order of
        the size of the mapping. This means the most complete subgraphs will be
        returned first.

        :param size: size, defaults to None
        :type size: int, optional
        :yield: mapping and subgraph iterator
        :rtype: Generator[Tuple[Mapping, Graph], None, None]
        """
        cache = set()
        for mapping in self.mappings_iter(size):
            subgraph = self.building_subgraph_from_mapping(mapping)
            if not subgraph.connected():
                continue
            key = tuple(sorted(subgraph.all_nodes()))  # type: ignore
            if key in cache:
                continue
            cache.add(key)
            yield mapping, subgraph
