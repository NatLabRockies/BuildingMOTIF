from collections import Counter
from secrets import token_hex
from typing import Callable, Dict, List

from rdflib import Graph
from rdflib.term import Node

from buildingmotif.dataclasses import Library, Template
from buildingmotif.namespaces import PARAM
from buildingmotif.template_matcher import (
    _ontology_lookup_cache,
    get_semantic_feasibility,
)
from buildingmotif.utils import Triple

# from rdflib.compare import graph_diff


def _is_parameterized_triple(triple: Triple) -> bool:
    """
    Returns true if a parameter appears in the triple
    """
    st = (str(triple[0]), str(triple[1]), str(triple[2]))
    return st[0].startswith(PARAM) or st[1].startswith(PARAM) or st[2].startswith(PARAM)


def _template_from_triples(lib: Library, triples: List[Triple]) -> Template:
    g = Graph()
    for t in triples:
        g.add(t)
    return lib.create_template(token_hex(4), g)


def compatible_triples(
    a: Triple, b: Triple, sf_func: Callable[[Node, Node], bool]
) -> bool:
    """
    Two triples are compatible if:
    - they are the same
    - they are pairwise semantically feasible
    """
    if a == b:
        return True
    for (a_term, b_term) in zip(a, b):
        if not sf_func(a_term, b_term):
            return False
    return True


def progressive_plan(templates: List[Template], context: Graph) -> List[Template]:
    """
    We are given a list of templates; this is either a set of templates that
    the model author supplies directly or are derived from sets of shapes that
    need to be fulfilled.

    We want to optimize the population of these templates: there may be
    redundant information between them, or there may be some unique/rare parts
    of templates whose populations can be postponed.
    """
    # present result as a sequence of (parameterized) triples?

    # greedy algorithm:
    # start with the most common (substitutable) triple amongst all templates
    # then choose the next most common triple, and so on.
    # Yield triples that have parameters; automatically include
    # non-parameterized triples
    templates = [template.inline_dependencies() for template in templates]
    histogram: Counter = Counter()

    inv: Dict[Triple, Template] = {}

    for templ in templates:
        cache = _ontology_lookup_cache()
        for body_triple in templ.body.triples((None, None, None)):
            found = False
            for hist_triple in histogram.keys():
                sf_func = get_semantic_feasibility(
                    templ.body, inv[hist_triple].body, context, cache
                )
                if compatible_triples(body_triple, hist_triple, sf_func):
                    print(body_triple)
                    print(hist_triple)
                    print("-" * 50)
                    found = True
                    histogram[hist_triple] += 1
                    break
            if not found:
                histogram[body_triple] = 1
                inv[body_triple] = templ

    # Start with the most common triple. We want to generate a sequence of triples
    # that maximizes the number of templates that are included in the resulting graph.
    # This is analogous to creating a left-biased CDF of (original) templates included

    # idea 1: just iterate through most common histogram
    # This has no guarantee that the sequence is optimal *or* connected.
    # We probably want to prioritize creating a connected sequence..
    most_common = histogram.most_common()
    triples = [triple[0] for triple in most_common]

    template_sequence: List[Template] = []

    lib = Library.create("temporary")
    buffer: List[Triple] = []
    for triple in triples:
        buffer.append(triple)
        if _is_parameterized_triple(triple):
            template_sequence.append(_template_from_triples(lib, buffer))
            buffer.clear()
    if len(buffer) > 0:
        template_sequence.append(_template_from_triples(lib, buffer))

    # TODO: need to mark when a new template is satisfied

    # can look at the CDF for a site specification as part of paper evaluation

    # stub of an alternative approach...
    # for pair in combinations(templates, 2):
    # for pair in permutations(templates, 2):
    #    t1, t2 = pair[0].in_memory_copy(), pair[1].in_memory_copy()
    #    print(t1.body.serialize())
    #    print("-" * 100)
    #    print(t2.body.serialize())
    #    print("-" * 100)
    #    tm = TemplateMatcher(t1.body, t2, context)
    #    for mapping, subgraph in tm.building_mapping_subgraphs_iter(
    #        size=tm.largest_mapping_size
    #    ):
    #        pprint(mapping)
    #        print(subgraph.serialize())

    #    # both, first, second = graph_diff(pair[0].body, pair[1].body)
    #    # print(both.serialize())
    #    print("*" * 100)
    #    print("*" * 100)

    return template_sequence
