import secrets
from typing import Dict, List, Optional, Union

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.store import Store
from rdflib.term import Node

from buildingmotif.dataclasses import Library, Template
from buildingmotif.namespaces import RDF, RDFS


class TemplateBuilderContext(Graph):
    """
    A context for building templates. This class allows the user to
    add templates to the context and then access them by name. The
    context also allows the user to compile all of the templates in
    the context into a single graph.
    """

    def __init__(self, ns: Namespace, store: Optional[Union[Store, str]] = None):
        """
        Creates a new TemplateBuilderContext. The context will create
        entities in the given namespace.

        :param ns:  The namespace to use for the context
        :param store: An optional backing store for the graph; ok to leave blank unless
                    you are experiencing performance issues using TemplateBuilderContext
        """
        self.templates: Dict[str, Template] = {}
        self.wrappers: List[TemplateWrapper] = []
        self.ns: Namespace = ns
        super(TemplateBuilderContext, self).__init__(
            store=store or "default", identifier=None
        )

    def add_template(self, template: Template):
        """
        Adds a template to the context with all of its dependencies
        inlined. Allows the user of the context to access the template
        by name.

        :param template: The template to add to the context
        """
        self.templates[template.name] = template.inline_dependencies()

    def add_templates_from_library(self, library: Library):
        """
        Adds all of the templates from a library to the context

        :param library: The library to add to the context
        """
        for template in library.get_templates():
            self.add_template(template)

    def __getitem__(self, template_name):
        if template_name in self.templates:
            w = TemplateWrapper(self.templates[template_name], self.ns)
            self.wrappers.append(w)
            return w
        else:
            raise KeyError(f"Invalid template name: {template_name}")

    def compile(self) -> Graph:
        """
        Compiles all of the template wrappers and concatenates them into a single Graph

        :return: A graph containing all of the compiled templates
        """
        graph = Graph()
        graph += self
        for wrapper in self.wrappers:
            graph += wrapper.compile()
        # add a label to every instance if it doesn't have one. Make
        # the label the same as the value part of the URI
        for s, o in graph.subject_objects(predicate=RDF.type):
            if (s, RDFS.label, None) not in graph:
                # get the 'value' part of the o URI using qname
                _, _, value = graph.namespace_manager.compute_qname(str(o))
                graph.add((s, RDFS.label, Literal(value)))
        return graph


class TemplateWrapper:
    def __init__(self, template: Template, ns: Namespace):
        """
        Creates a new TemplateWrapper. The wrapper is used to bind
        parameters to a template and then compile the template into
        a graph.

        :param template: The template to wrap
        :param ns: The namespace to use for the wrapper; all bindings will be added to this namespace
        """
        self.template = template
        self.bindings: Dict[str, Node] = {}
        self.ns = ns

    def __call__(self, **kwargs):
        for k, v in kwargs.items():
            self[k] = v
        return self

    def __getitem__(self, param):
        if param in self.bindings:
            return self.bindings[param]
        elif param not in self.template.parameters_with_dependencies(
            transitive=False, renamed=False
        ):
            raise KeyError(f"Invalid parameter: {param}")
        # if the param is not bound, then invent a name
        # by prepending the parameter name to a random string
        self.bindings[param] = self.ns[param + "_" + secrets.token_hex(4)]
        return self.bindings[param]

    def __setitem__(self, param, value):
        if param not in self.template.parameters_with_dependencies(
            transitive=False, renamed=False
        ):
            raise KeyError(f"Invalid parameter: {param}")
        # if value is not a URIRef, Literal or BNode, then put it in the namespace
        if not isinstance(value, (URIRef, Literal, BNode)):
            value = self.ns[value]
        # check datatype of value is URIRef, Literal or BNode
        if not isinstance(value, (URIRef, Literal, BNode)):
            raise TypeError(f"Invalid type for value: {type(value)}")
        self.bindings[param] = value

    @property
    def parameters(self):
        return self.template.parameters

    def compile(self) -> Graph:
        """
        Compiles the template into a graph. If there are still parameters
        to be bound, then the template will be returned. Otherwise, the
        template will be filled and the resulting graph will be returned.

        :return: A graph containing the compiled template
        :rtype: Graph
        """
        tmp = self.template.substitute(self.bindings)
        if tmp.is_complete:
            return tmp.to_graph()
        # there are still parameters to be bound; invent names for them
        bindings, graph = tmp.fill(self.ns, include_optional=False)
        self.bindings.update(bindings)
        return graph
