import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from rdflib import Graph
from scipy.optimize import linear_sum_assignment

from buildingmotif.dataclasses import Template
from buildingmotif.graph_generation.classes import Cost, Param, Token, URIRef
from buildingmotif.namespaces import PARAM

logger = logging.getLogger()


def get_typed_params(template) -> List[Param]:
    """
    Get the parameters of the template that have a type
    """
    query = """
            SELECT ?s ?o
            WHERE {
                ?s a ?o
                FILTER (strstarts(str(?s), 'urn:___param___'))
            }
        """
    params = []
    for s, c in template.body.query(query):
        params.append(Param(name=s[len(PARAM) :], classname=c))
    return params


class BipartiteTokenMapper:
    @staticmethod
    def _get_parent_class(ontology: Graph, ontology_class: URIRef) -> Optional[URIRef]:
        """Get the immediate parent of ontology class"""
        query = """
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?parent
            WHERE {{
                ?child rdfs:subClassOf ?parent .
            }}
        """
        result = ontology.query(query, initBindings={"child": ontology_class})
        parents = (parent for (parent,) in result)

        return next(parents, None)

    @staticmethod
    def _get_edge_cost(
        ontology: Graph, token_class: URIRef, param_class: URIRef, cost_power: int = 0
    ) -> float:
        """
        Return the cost between ontology classes token_class and param_class where cost is:

        - inf if token_class is not covariant of param_class.
        - 2 to the power of the number of hops between the classes.
        """
        if str(token_class) == str(param_class):
            return 2**cost_power - 1

        parent_class = BipartiteTokenMapper._get_parent_class(ontology, token_class)
        if parent_class is None:
            return np.inf

        return BipartiteTokenMapper._get_edge_cost(
            ontology, parent_class, param_class, cost_power + 1
        )

    @staticmethod
    def _create_cost_matrix(
        ontology: Graph, tokens: List[Token], params: List[Param]
    ) -> pd.DataFrame:
        """Create cost matrix of the above classes."""

        # a cost matrix is a matrix where the rows are the tokens and the columns are the params
        cost_matrix = pd.DataFrame(
            index=params,
            columns=tokens,
        )

        # populate the cost matrix with the "distance" between each parameter class and
        # each token class. The distance is the number of hops between the classes
        # in the given ontology
        for i, token in enumerate(cost_matrix.columns):
            for j, param in enumerate(cost_matrix.index):
                cost_matrix.iloc[j, i] = BipartiteTokenMapper._get_edge_cost(
                    ontology, token.classname, param.classname
                )

        logger.debug("cost matrix:")
        logger.debug(
            cost_matrix.rename(
                columns=lambda x: x.class_,
                index=lambda x: x.class_,
            )
        )
        return cost_matrix

    @staticmethod
    def find_bindings_for_tokens_and_params(
        ontology: Graph,
        tokens: List[Token],
        params: List[Param],
    ) -> Tuple[Dict[URIRef, Token], Cost]:
        """Get the cost of mapping token_classes to param_classes."""
        # create cost matrix based on the distances between the classes of the tokens
        # and the classes of the parameters. The params come from a template.
        cost_matrix = BipartiteTokenMapper._create_cost_matrix(ontology, tokens, params)

        # This code replaces all occurrences of positive infinity (np.inf) in
        # the cost_matrix with NaN (Not a Number), drops any rows that are all
        # NaN values, and finally replaces the remaining NaN values with
        # positive infinity.
        # The result is that the cost_matrix will have no rows that are all
        # positive infinity, and no NaN values. This reduces the number of
        # possible assignments that the linear_sum_assignment algorithm has to
        # consider, and therefore reduces the runtime of the algorithm.

        # TODO: determine if this is the right preprocessing step to take
        cost_matrix = (
            cost_matrix.replace([np.inf, -np.inf], np.nan)
            .dropna(axis=0, how="all")
            .replace(np.nan, np.inf)
        )
        # computes the optimal assignment between the tokens and the params
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        kept_costs = list(zip(row_ind, col_ind))
        # turns the optimal assignment into a dictionary of bindings
        bindings = {
            cost_matrix.index[row].name: cost_matrix.columns[col]
            for row, col in kept_costs
        }

        logger.debug("\nkept edges:")
        for row, col in kept_costs:
            param = cost_matrix.index[row]
            token = cost_matrix.columns[col]
            logger.debug(
                f"{param.class_} <- {cost_matrix.iloc[row, col]} -> {token.class_}"
            )

        # if no edges, give the cost as infinity
        if len(kept_costs) <= 0:
            edge_cost = np.inf
        else:
            edge_cost = cost_matrix.to_numpy()[row_ind, col_ind].sum()

        return (
            bindings,
            Cost(
                edge_cost=edge_cost,
                params_dropped=len(params) - len(kept_costs),
                tokens_dropped=len(tokens) - len(kept_costs),
            ),
        )

    @staticmethod
    def find_bindings_for_tokens_and_template(
        ontology: Graph,
        tokens: List[Token],
        template: Template,
    ) -> Tuple[Dict[Param, Token], Cost]:
        """Finds the bindings for tokens and template"""
        # get the parameters of the template that have a type
        params = get_typed_params(template)
        try:
            mapping, cost = BipartiteTokenMapper.find_bindings_for_tokens_and_params(
                ontology, tokens, params
            )
        except ValueError:
            mapping, cost = {}, Cost(
                edge_cost=np.inf,
                params_dropped=len(params),
                tokens_dropped=len(tokens),
            )

        return mapping, cost
