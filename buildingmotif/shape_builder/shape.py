from typing import List, Optional, Tuple, Union

from rdflib import RDF, BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.term import Node

from buildingmotif.namespaces import CONSTRAINT, SH, A, bind_prefixes


class Shape(Graph):
    """Base class for constructing shapes programatically"""

    def __init__(
        self,
        identifier: Optional[Union[Node, str]] = None,
        message: Optional[str] = None,
    ) -> None:
        """

        :param identifier: id for shape
        :type identifier: Optional[Union[Node, str]]
        :param message: sh:message annotation
        :type message: str
        """
        super().__init__(identifier=identifier)
        bind_prefixes(self)

        if message:
            self.add((self.identifier, SH["message"], Literal(message)))

    def add_property(self, property: URIRef, object: Node):
        """Add property to shape

        :param property: ref of property
        :type property: URIRef
        :param object: ref of object
        :type object: Node"""
        # This same functionality could be added with just use of add.
        # This design is useful to allow adding properties in the
        # builder paradigm.
        self.add((self, property, object))

        return self

    def add_list_property(
        self, property: URIRef, nodes: Union[List[Node], Tuple[Node, ...]]
    ):
        """Add property which references list to shape

        :param property: ref of property
        :type property: URIRef
        :param nodes: nodes to include in list
        :type nodes: Union[List[Node], Tuple[Node, ...]]"""
        identifier = BNode()
        Collection(self, identifier, nodes)

        self.add((self, property, identifier))

        return self

    def OR(self, *nodes: Node):
        """add OR property

        :param nodes: list of nodes to OR
        :type nodes: Union[List[Node], Tuple[Node, ...]]
        """
        self.add_list_property(SH["or"], nodes)
        return self

    def AND(self, *nodes: Node):
        """add AND property

        :param nodes: list of nodes to AND
        :type nodes: Union[List[Node], Tuple[Node, ...]]
        """
        self.add_list_property(SH["and"], nodes)
        return self

    def NOT(self, node: Node):
        """add NOT property

        :param nodes: list of nodes to NOT
        :type nodes: Union[List[Node], Tuple[Node, ...]]
        """
        self.add((self, SH["not"], node))

        return self

    def XONE(self, *nodes: Node):
        """add XONE property

        :param nodes: list of nodes to XONE
        :type nodes: Union[List[Node], Tuple[Node, ...]]
        """
        self.add_list_property(SH["xone"], nodes)
        return self

    def add(self, triple: Tuple[Node, Node, Node]):
        (s, p, o) = triple
        if isinstance(o, Shape):
            # if the object being added is of type Shape
            # add the whole graph to this graph
            self += o
            o = o.identifier
        if s == self:
            s = s.identifier
        triple = (s, p, o)
        return super().add(triple)


class NodeShape(Shape):
    """Class for constructing Node Shapes programatically"""

    def __init__(
        self,
        identifier: Optional[Union[Node, str]] = None,
        message: Optional[str] = None,
    ) -> None:
        """

        :param identifier: id for shape
        :type identifier: Optional[Union[Node, str]]
        :param message: sh:message annotation
        :type message: str
        """
        super().__init__(identifier=identifier, message=message)

        self.add((self, A, SH["NodeShape"]))

    def of_class(self, class_: Node, active=False):
        """Add constraint that target much be of a certain class

        :param class_: class of target
        :type class_: Node
        :param active: should shape actively target the class or not
        :type active: bool"""
        predicate = SH["targetClass"] if active else SH["class"]

        self.add((self, predicate, class_))
        self.add((self, CONSTRAINT["class"], class_))

        return self

    def always_run(self):
        """Add blank node target
        This target insures that the shape will always be evaluated.
        If the shape has properties this can cause it to fail."""
        self.add((self, SH["targetNode"], BNode()))
        return self

    def count(self, exactly: Optional[int] = None):
        """Add an exact count constraint.

        :param exactly: exact number of instances of class to match
        :type exactly: int"""
        if exactly:
            self.add((self, CONSTRAINT["exactCount"], Literal(exactly)))
        return self

    def has_property(self, property: Union[Node, URIRef]):
        """Add property constraint.

        :param property: property shape or property to add constraint for
        :type property: Union[Node, URIRef]"""
        if isinstance(property, URIRef):
            property = PropertyShape().has_path(property)

        self.add((self, SH["property"], property))

        return self


class PropertyShape(Shape):
    def __init__(
        self,
        identifier: Optional[Union[Node, str]] = None,
        message: Optional[str] = None,
    ) -> None:
        """

        :param identifier: id for shape
        :type identifier: Optional[Union[Node, str]]
        :param message: sh:message annotation
        :type message: str
        """
        super().__init__(identifier=identifier, message=message)

        self.add((self, RDF.type, SH["PropertyShape"]))

    def has_path(
        self,
        path: Node,
        zero_or_one: bool = False,
        zero_or_more: bool = False,
        one_or_more: bool = False,
    ) -> "PropertyShape":
        """Add path constraint to shape.
        zero_or_one, zero_or_more, and one_or_more flags are mutually exclusive

        :param path: path to add constraint for
        :type path: Node
        :param zero_or_one: match zero or one instances of path
        :type zero_or_one: bool
        :param zero_or_more: match zero or more instances of path
        :type zero_or_more: bool
        :param one_or_more: match one or more instances of path
        :type one_or_more: bool"""

        if zero_or_one or zero_or_more or one_or_more:
            path_constraint = None
            if zero_or_one:
                path_constraint = SH["path-zero-or-one"]
            elif zero_or_more:
                path_constraint = SH["path-zero-or-more"]
            elif one_or_more:
                path_constraint = SH["path-one-or-more"]
            self.add((self, SH["path"], Shape().add_property(path_constraint, path)))
        else:
            self.add((self, SH["path"], path))

        return self

    def matches(
        self,
        target: Node,
        type: URIRef,
        min: Optional[int] = None,
        max: Optional[int] = None,
        exactly: Optional[int] = None,
        qualified: bool = False,
    ):
        """Add target matches constraint to property shape

        :param target: target node to specify what should be matched, usually shape or class
        :type target: Node
        :param type: sh:class or sh:node
        :type type: URIRef
        :param min: min count of matched entities
        :type min: int
        :param max: max count of matched entities
        :type max: int
        :param exactly: exact count of matched entities (takes precidence over min/max)
        :type exactly: int
        :param qualified: Is this property qualified or universal
        :type qualified: bool

        """
        if min is None and max is None and exactly is None:
            if qualified:
                raise ValueError("min, max or exactly must have a value")
            else:
                self.add((self, type, target))
            return self

        if exactly is not None:
            min = max = exactly

        if qualified:
            blank_node = BNode()
            self.add((blank_node, type, target))
            self.add((self, SH["qualifiedValueShape"], blank_node))
            if min is not None:
                self.add((self, SH["qualifiedMinCount"], Literal(min)))
            if max is not None:
                self.add((self, SH["qualifiedMaxCount"], Literal(max)))
        else:
            self.add((self, type, target))
            if min is not None:
                self.add((self, SH["minCount"], Literal(min)))
            if max is not None:
                self.add((self, SH["maxCount"], Literal(max)))
        return self

    def matches_class(
        self,
        class_: URIRef,
        min: Optional[int] = None,
        max: Optional[int] = None,
        exactly: Optional[int] = None,
        qualified=False,
    ):
        """Add target matches class constraint to property shape

        :param class_: target class what should be matched
        :type class_: Node
        :param min: min count of matched entities
        :type min: int
        :param max: max count of matched entities
        :type max: int
        :param exactly: exact count of matched entities (takes precidence over min/max)
        :type exactly: int
        :param qualified: Is this property qualified or universal
        :type qualified: bool
        """
        return self.matches(class_, SH["class"], min, max, exactly, qualified)

    def matches_shape(
        self,
        shape: Node,
        min: Optional[int] = None,
        max: Optional[int] = None,
        exactly: Optional[int] = None,
        qualified=False,
    ):
        """Add target matches shape constraint to property shape

        :param shape: target shape what should be matched
        :type shape: Node
        :param min: min count of matched entities
        :type min: int
        :param max: max count of matched entities
        :type max: int
        :param exactly: exact count of matched entities (takes precidence over min/max)
        :type exactly: int
        :param qualified: Is this property qualified or universal
        :type qualified: bool
        """
        return self.matches(shape, SH["node"], min, max, exactly, qualified)


def OR(*nodes: Node) -> Shape:
    """add OR property

    :param nodes: list of nodes to OR
    :type nodes: Union[List[Node], Tuple[Node, ...]]
    """
    return Shape().OR(*nodes)


def AND(*nodes: Node) -> Shape:
    """add AND property

    :param nodes: list of nodes to AND
    :type nodes: Union[List[Node], Tuple[Node, ...]]
    """
    return Shape().AND(*nodes)


def NOT(node: Node) -> Shape:
    """add NOT property

    :param nodes: list of nodes to NOT
    :type nodes: Union[List[Node], Tuple[Node, ...]]
    """
    return Shape().NOT(node)


def XONE(*nodes: Node) -> Shape:
    """add XONE property

    :param nodes: list of nodes to XONE
    :type nodes: Union[List[Node], Tuple[Node, ...]]
    """
    return Shape().XONE(*nodes)
