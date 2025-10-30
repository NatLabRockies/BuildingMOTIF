import logging
from typing import List

from rdflib import Graph, Namespace

from buildingmotif.dataclasses import Library, Template
from buildingmotif.graph_generation.bindings_utils import (
    evaluate_bindings,
    unify_bindings,
)
from buildingmotif.graph_generation.classes import TokenizedLabel
from buildingmotif.graph_generation.semantic_graph_synthesizer import (
    SemanticGraphSynthesizer,
)
from buildingmotif.ingresses.base import GraphIngressHandler
from buildingmotif.ingresses.naming_convention import NamingConventionIngress

logger = logging.getLogger(__name__)


class SemanticGraphSynthesizerIngress(GraphIngressHandler):
    def __init__(
        self,
        upstream: NamingConventionIngress,
        libraries: List[Library],
        ontology: Graph,
    ):
        self.upstream = upstream
        self.libraries = libraries

        self.sgs = SemanticGraphSynthesizer()
        self.ontology = ontology
        # Add templates from libraries; the synthesizer will look at these to determine the "best fit"
        # for each group of input tokens
        logger.info(f"Adding templates from {len(libraries)} libraries")
        for library in libraries:
            self.sgs.add_templates_from_library(library)
        logger.info(f"Added templates from {len(libraries)} libraries")

    def graph(self, ns: Namespace) -> Graph:
        g = Graph()
        # converts the input records to TokenizedLabels
        labels = [TokenizedLabel.from_dict(x.fields) for x in self.upstream.records]
        logger.info(f"Got {len(labels)} labels from upstream")
        # this groups labels into LabelSets based on shared sets of token classes.
        # This is used to speed up the matching process as we can figure out which labels are compatible
        bindings_list = self.sgs.find_bindings_for_labels(self.ontology, labels)
        logger.info(f"Got {len(bindings_list)} bindings from the synthesizer")
        unified_bindings_list = unify_bindings(bindings_list)
        logger.info(f"Unified bindings into {len(unified_bindings_list)} groups")
        # at this point, the unified_bindings_list contains the best fit for each group of input tokens

        # for each group of labels, evaluate the bindings and add the resulting graph to the output
        for ub in unified_bindings_list:
            ev = evaluate_bindings(ns, ub)
            logger.info(f"Evaluated bindings to {ev}")
            # if the evaluation returns a Template, we need to mint new URIs in the given namespace
            # for any unbound parameters. If it returns a Graph, we can just add it to the output.
            if isinstance(ev, Template):
                graph = ev.body
            else:
                graph = ev
            logger.info(f"Adding graph with {len(graph)} triples to output")
            g += graph
        return g
