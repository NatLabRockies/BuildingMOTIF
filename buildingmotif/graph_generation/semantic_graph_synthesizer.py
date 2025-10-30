import logging
from typing import List

import numpy as np
from rdflib import Graph

from buildingmotif.dataclasses import Library
from buildingmotif.graph_generation.bipartite_token_mapper import BipartiteTokenMapper
from buildingmotif.graph_generation.classes import (
    Bindings,
    Cost,
    LabelSet,
    Token,
    TokenizedLabel,
)

logger = logging.getLogger()


def default_cost_loss_function(cost: Cost) -> float:
    return cost.scalar


class SemanticGraphSynthesizer:
    def __init__(
        self,
        bindings_cost_threshold=np.inf,
        cost_loss_function=default_cost_loss_function,
        should_inline_dependencies=True,
    ):
        self.bindings_cost_threshold = bindings_cost_threshold
        self.cost_loss_function = cost_loss_function
        self.should_inline_dependencies = should_inline_dependencies
        self.templates = []

    def add_templates_from_library(self, library: Library):
        self.templates.extend(library.get_templates())

    def _group_labels_by_tokens(self, labels: List[TokenizedLabel]) -> List[LabelSet]:
        """ "Group labels into labelsets based on shared sets on token classes"""
        labelsets: List[LabelSet] = []

        for label in labels:
            token_classes = sorted(t.classname for t in label.tokens)

            # proper labelset for tokenized_label
            labelset = next(
                (
                    labelset
                    for labelset in labelsets
                    if labelset.token_classes == token_classes
                ),
                None,
            )

            if labelset is None:
                labelset = LabelSet(token_classes=token_classes, labels=[])
                labelsets.append(labelset)

            # append it to the label set
            labelset.labels.append(label)

        return labelsets

    def find_bindings_for_label(
        self, ontology: Graph, label: TokenizedLabel
    ) -> Bindings:
        """Gets the bindings for a specific label."""
        best_bindings = Bindings(
            label=label, template=None, bindings={}, cost=Cost.inf()
        )

        logger.debug("Template costs:")
        # find the best template for the label
        for template in self.templates:
            if self.should_inline_dependencies:
                template = template.inline_dependencies()

            # compute the best bindings for using the tokens of the label with the template
            # and the cost of the bindings
            bindings, cost = BipartiteTokenMapper.find_bindings_for_tokens_and_template(
                ontology, label.tokens, template
            )
            logger.debug(f"- {template.name} {cost.scalar}")

            # if the cost is better than the current best cost, and it is below the
            # threshold, then update the best bindings
            if (
                self.cost_loss_function(cost)
                < self.cost_loss_function(best_bindings.cost)
                and self.cost_loss_function(cost) < self.bindings_cost_threshold
            ):
                best_bindings = Bindings(
                    label=label,
                    template=template,
                    bindings=bindings,
                    cost=cost,
                )

        return best_bindings

    def find_bindings_for_labelset(
        self, ontology: Graph, labelset: LabelSet
    ) -> List[Bindings]:
        """Find the bindings a given LabelSet."""
        index_label = TokenizedLabel(
            label="Index Label",
            tokens=[
                Token(identifier=str(i), classname=tc)
                for i, tc in enumerate(sorted(labelset.token_classes))
            ],
        )
        index_bindings = self.find_bindings_for_label(ontology, index_label)
        logger.debug(
            f"Index bindings: {index_bindings.bindings}. Now going through labels"
        )

        bindings_list = []
        for label in labelset.labels:
            sorted_tokens = sorted(label.tokens, key=lambda t: t.classname)
            token_identifiers = [t.identifier for t in sorted_tokens]
            bindings = {
                param: Token(
                    identifier=token_identifiers[int(token.identifier)],
                    classname=token.classname,
                )
                for param, token in index_bindings.bindings.items()
            }
            logger.debug(f"Bindings for label {label.label}: {bindings}")

            bindings_list.append(
                Bindings(
                    label=label,
                    template=index_bindings.template,
                    bindings=bindings,
                    cost=index_bindings.cost,
                )
            )
            logger.debug(f"Added binding: {bindings_list[-1]}")

        return bindings_list

    def find_bindings_for_labels(
        self, ontology: Graph, labels: List[TokenizedLabel]
    ) -> List[Bindings]:
        """Find the bindings a given labels.

        Groups them in label sets for optimization purposes.
        """
        labelsets = self._group_labels_by_tokens(labels)

        bindings_list = []
        for labelset in labelsets:
            logger.debug(
                f"Generating bindings for labelset: {labelset.token_classes} {labelset.labels}"
            )
            bindings_list.extend(self.find_bindings_for_labelset(ontology, labelset))

        return bindings_list
