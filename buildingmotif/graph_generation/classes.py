from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
from rdflib import URIRef

from buildingmotif.dataclasses import Template


@dataclass
class Cost:
    """
    Represents the parameters that may be incorporated into the cost of a binding
    """

    # edge_cost is the cost of the edge between the template and the label in the
    # bipartite graph used for matching
    edge_cost: float
    # params_dropped counts the number of parameters in the template that are not
    # in the binding
    params_dropped: int
    # tokens_dropped counts the number of tokens in the label that are not in the
    # binding
    tokens_dropped: int

    @property
    def scalar(self):
        """
        Returns a scalar value for the cost. This could change in the future
        """
        return (
            self.edge_cost + self.tokens_dropped
        )  # self.params_dropped + self.tokens_dropped

    @classmethod
    def inf(self):
        """
        Returns a cost with all values set to infinity
        """
        return Cost(edge_cost=np.inf, params_dropped=np.inf, tokens_dropped=np.inf)


@dataclass
class Param:
    name: URIRef
    classname: URIRef

    @property
    def class_(self):
        return self.classname[self.classname.find("#") + 1 :]

    def __repr__(self):
        return f"{self.name} a {self.class_}"


@dataclass
class Token:
    identifier: str
    classname: URIRef

    @property
    def class_(self):
        return self.classname[self.classname.find("#") + 1 :]

    def __repr__(self):
        return f"{self.identifier} (type {self.classname})"


@dataclass
class TokenizedLabel:
    """
    Represents a label and the tokens that have been extracted from it.
    """

    label: str
    tokens: list[Token]

    @staticmethod
    def from_dict(d):
        return TokenizedLabel(
            label=d["label"],
            tokens=[
                Token(identifier=t["identifier"], classname=URIRef(t["type"]))
                for t in d["tokens"]
            ],
        )

    def __repr__(self):
        r = ""
        for token in self.tokens:
            r += f"    - {token}\n"

        return f"{self.label}:\n{r}"


@dataclass
class LabelSet:
    """
    Represents a collection of TokenizedLabels that have the same set of classes among
    their tokens. This is used to speed up the matching process as we can figure out
    which labels are compatible with a template by looking at the classes, and then batch
    process all the labels with the same set of classes.
    """

    token_classes: List[URIRef]
    labels: List[TokenizedLabel]


@dataclass
class Bindings:
    """
    Represents a binding between a template and a set of tokens. The binding is
    represented as a dictionary mapping the parameters of the template to the tokens
    that they are bound to.
    """

    label: TokenizedLabel
    template: Optional[Template]
    bindings: Dict[URIRef, Token]
    cost: Cost


@dataclass
class UnifiedBindings:
    labels: List[TokenizedLabel]
    template: Template
    bindings: Dict[str, Token]
    cost: Cost
