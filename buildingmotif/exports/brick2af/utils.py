import json
import random
import string
import sys
from functools import reduce
from typing import Any, Dict

try:  # prefer lxml for pretty output
    from lxml import etree  # type: ignore
except Exception:  # fallback to stdlib
    from xml.etree import ElementTree as etree  # type: ignore

from rdflib import RDF, SH, BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from xmldiff import formatting, main

from buildingmotif.namespaces import BMOTIF, BRICK

# build relationship
RELATIONSHIPS = ["hasPoint", "hasPart", "isPointOf", "isPartOf", "feeds"]
RELATIONSHIPS += [f"{r}+" for r in RELATIONSHIPS]
RELATIONSHIPS += [f"{r}?" for r in RELATIONSHIPS]
RELATIONSHIPS += [f"{r}*" for r in RELATIONSHIPS]


def _describe_path_component(value) -> str:
    """Return a short descriptive label for a property path element."""
    if isinstance(value, URIRef):
        text = str(value)
        if "#" in text:
            return text.split("#")[-1]
        if "/" in text:
            return text.rstrip("/").split("/")[-1]
        return text
    return "specified path"


def pretty_print(element):
    """Simple printing of an xml element from the bsync library"""
    print(etree.tostring(element.toxml(), pretty_print=True).decode("utf-8"))


def xml_dump(root_element, file="example1.xml"):
    """Write the element to the specified file"""
    doctype = '<?xml version="1.0" encoding="UTF-8"?>'
    as_etree = root_element.toxml()
    # as_etree.set("xmlns", "http://buildingsync.net/schemas/bedes-auc/2019")
    output = etree.tostring(as_etree, doctype=doctype, pretty_print=True)
    with open(file, "wb+") as f:
        f.write(output)
        return True


def xml_compare(left, right):
    file_diff = main.diff_files(
        left,
        right,
        diff_options={"ratio_mode": "faster"},
        formatter=formatting.XMLFormatter(),
    )
    return file_diff


def _definition_to_sparql(classname, defn, variable):
    """
    defn is a JSON structure like this:
        "Chilled_Water_Valve_Command": {
            "choice": [
                {"hasPoint": "Chilled_Water_Valve_Command"},
                {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
            ]
        },
    This method turns this into a SPARQL query which retrieves values into a variable
    named whatever the top-level key is
    """
    query = f"""SELECT ?root ?{variable} WHERE {{ 
        ?root rdf:type {classname.n3()} .
        {_sparql_recurse(defn, variable, hook="root")} 
    }}"""
    return query


def _gensym():
    """generates random sparql variable name"""
    return "var" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))


def _sparql_recurse(defn, varname, hook=None):
    """
    Generate a SPARQL query recursively based on the definition provided.

    Args:
        self (object): The instance of the class containing the RDF graph and BRICK definitions.
        defn (dict or str): The definition to be converted into a SPARQL query. If it's a string, it represents a type. If it's a dictionary, it
            can contain relationships or other types.
        varname (str): The base variable name for the current level of recursion in the SPARQL query.
        hook (str or None, optional): A placeholder variable to be used as the subject of certain relationships. Defaults to None.

    Returns:
        str: The generated SPARQL query string.
    """
    relationships = ["hasPoint", "hasPart", "isPointOf", "isPartOf", "feeds"]
    # add '+' versions to relationships
    relationships += [f"{r}+" for r in relationships]
    # add '?' versions to relationships
    relationships += [f"{r}?" for r in relationships]
    # add '*' versions to relationships
    relationships += [f"{r}*" for r in relationships]
    query = ""
    if isinstance(defn, str):
        if hook is not None and hook != varname:
            # then varname is hasPoint from hook
            query += f"?{hook} brick:hasPoint ?{varname} .\n"
        query += f"?{varname} rdf:type {BRICK[defn].n3()} .\n"
        return query
    for key, value in defn.items():
        if key == "choice":
            # UNION of the list of descriptions in 'value'
            query += "{\n"
            query += " UNION ".join(
                [f"{{ {_sparql_recurse(v, varname, hook=hook)} }}\n" for v in value]
            )
            query += "}\n"
        elif key in relationships:
            # start with a random var
            subject_var = hook or _gensym()

            # get the relationship name
            suffix = key[-1] if key[-1] in ["+", "?", "*"] else ""
            relname = key.replace("+", "").replace("?", "").replace("*", "")
            # get the relationship type
            reltype = BRICK[relname]

            # the object of the relationship is one of two things:
            # - varname, if 'value' is a type
            # - a new variable, if 'value' is a dict
            if isinstance(value, str):
                object_var = varname
            else:
                object_var = _gensym()

            # add the relationship to the query
            query += f"?{subject_var} {reltype.n3()}{suffix} ?{object_var} .\n"
            # add the object to the query
            query += _sparql_recurse(value, varname, hook=object_var)
        else:  # key represents a type
            subject_var = hook or _gensym()
            query += f"?{subject_var} rdf:type {BRICK[key].n3()} .\n"
            # value should be a dictionary
            query += _sparql_recurse(value, varname, hook=subject_var)

    return query


def _definition_to_shape(defn: Dict[str, Any], ns: Namespace) -> Graph:
    """
    Here's an example JSON rule:
        "SimultaneousHeatingAndCooling" : {
            "name" : "Simultaneous Heating and Cooling",
            "aftype" : "analysis",
            "aftimerule" : "Periodic",
            "frequency" : 900,
            "applicability" : ["AHU", "RTU", "RVAV"],
            "definitions": {
                "Chilled_Water_Valve_Command": {
                    "choice": [
                        {"hasPoint": "Chilled_Water_Valve_Command"},
                        {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
                    ]
                },
                "Hot_Water_Valve_Command": {
                    "choice": [
                        {"hasPoint": "Hot_Water_Valve_Command"},
                        {"hasPart": {"Hot_Water_Valve": {"hasPoint": "Valve_Command"}}}
                    ]
                }
            },
            "output" : "IF Chilled_Water_Valve_Command AND Hot_Water_Valve_Command THEN True ELSE False"
        },

    need to produce a shape like this:

    :Chilled_Water_Valve a sh:NodeShape ;
        sh:class brick:Chilled_Water_Valve ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:qualifiedValueShape [ sh:class brick:Valve_Command ]
            sh:qualifiedMinCount 1 ;
        ] ;
    .
    :Hot_Water_Valve a sh:NodeShape ;
        sh:class brick:Hot_Water_Valve ;
        sh:property [
            sh:path brick:hasPoint ;
            sh:qualifiedValueShape [ sh:class brick:Valve_Command ]
            sh:qualifiedMinCount 1 ;
        ] ;
    .

    :SimultaneousHeatingAndCooling a sh:NodeShape ;
        sh:targetClass brick:AHU, brick:RTU, brick:RVAV ;
        sh:or (
            [ sh:name "Chilled_Water_Valve_Command" ; sh:path brick:hasPoint ; sh:qualifiedValueShape [ sh:class brick:Chilled_Water_Valve_Command ] ; sh:qualifiedMinCount 1 ],
            [ sh:name "Chilled_Water_Valve_Command" ; sh:path brick:hasPart ; sh:qualifiedValueShape [ sh:node :Chilled_Water_Valve ] ; sh:qualifiedMinCount 1 ],
        ) ;
        sh:or (
            [ sh:name "Hot_Water_Valve_Command" ; sh:path brick:hasPoint ; sh:qualifiedValueShape [ sh:class brick:Hot_Water_Valve_Command ] ; sh:qualifiedMinCount 1 ],
            [ sh:name "Hot_Water_Valve_Command" ; sh:path brick:hasPart ; sh:qualifiedValueShape [ sh:node :Hot_Water_Valve ] ; sh:qualifiedMinCount 1 ],
        ) ;
    .
    """
    shape = Graph()
    shapename = ns[defn["name"].replace(" ", "_")]
    shape.add((shapename, RDF["type"], SH["NodeShape"]))
    shape.add((shapename, RDF["type"], BMOTIF["Analytics_Application"]))
    shape.add((shapename, SH["name"], Literal(defn["name"])))
    applicability = ", ".join(defn.get("applicability", []))
    if applicability:
        message = f"Applies to {applicability}."
    else:
        message = "Applies the BuildingMOTIF diagnostic rule."
    shape.add((shapename, SH["message"], Literal(message)))
    for target in defn["applicability"]:
        shape.add((shapename, SH["targetClass"], BRICK[target]))

    for key, value in defn["definitions"].items():
        varname = ns[key]
        _defn_to_shape(shapename, varname, value, shape, ns, name_hint=key)

    return shape


def _defn_to_shape(
    shapename,
    varname,
    defn,
    shape_graph,
    ns,
    path=None,
    name_hint: str | None = None,
):
    varname = ns[_gensym()]
    if isinstance(defn, str):
        return _string_to_shape(
            shapename,
            shape_graph,
            varname,
            defn,
            path=path,
            name_hint=name_hint or defn,
        )
    elif isinstance(defn, dict):
        if "union" in defn:
            return _union_to_shape(
                shapename, shape_graph, varname, defn.pop("union"), ns
            )
        # handle choice if it is present
        if "choice" in defn:
            return _choice_to_shape(
                shapename,
                shape_graph,
                varname,
                defn.pop("choice"),
                ns,
                name_hint=name_hint,
            )
        # treat the keys as properties
        for key, value in defn.items():
            propname = BRICK[key]
            _prop_to_shape(
                shapename,
                shape_graph,
                varname,
                propname,
                value,
                ns,
                name_hint=key,
            )
    return varname


def _string_to_shape(
    shapename: URIRef,
    shape_graph: Graph,
    varname: URIRef,
    string_value: str,
    path=None,
    name_hint: str | None = None,
):
    """
    Given a string value, create a SHACL shape that requires the sh:class to be that BRICK[string_value]
    """
    if shapename is not None:
        shape_graph.add((shapename, SH["property"], varname))
    shape_graph.add((varname, RDF["type"], SH["PropertyShape"]))
    actual_path = path or BRICK["hasPoint"]
    shape_graph.add((varname, SH["path"], actual_path))
    display_name = name_hint or string_value
    shape_graph.add((varname, SH["name"], Literal(display_name)))
    message = (
        f"Ensure at least one {string_value} is related via "
        f"{_describe_path_component(actual_path)}."
    )
    shape_graph.add((varname, SH["message"], Literal(message)))
    class_shape = BNode()
    shape_graph.add((varname, SH["qualifiedValueShape"], class_shape))
    shape_graph.add((class_shape, RDF["type"], SH["NodeShape"]))
    shape_graph.add((class_shape, SH["class"], BRICK[string_value]))
    shape_graph.add((class_shape, SH["name"], Literal(f"{string_value} shape")))
    shape_graph.add(
        (class_shape, SH["message"], Literal(f"Value must be a {string_value}."))
    )
    shape_graph.add((varname, SH["qualifiedMinCount"], Literal(1)))
    return varname


def _union_to_shape(
    shapename: URIRef, shape_graph: Graph, varname: URIRef, union: Dict[str, Any], ns
):
    """
    "union": [
    "AFDD_rule_a",
    "AFDD_rule_b
    ]

    Given the options list, create a shape for each rule in the options list
    and add them to the shape graph. Then add to the shapename an sh:and that
    includes all the options.
    """
    and_list = []
    for option in union:
        print(f"shapename: {shapename}, varname: {varname}, option: {option}")
        oshape = _defn_to_shape(None, None, option, shape_graph, ns)
        and_list.append(oshape)
    print(and_list)

    and_list_name = BNode()
    Collection(shape_graph, and_list_name, and_list)
    shape_graph.add((shapename, SH["and"], and_list_name))

    return varname


def _choice_to_shape(
    shapename: URIRef,
    shape_graph: Graph,
    varname: URIRef,
    choice: Dict[str, Any],
    ns,
    name_hint: str | None = None,
):
    """
    "choice": [
    {"hasPoint": "Chilled_Water_Valve_Command"},
    {"hasPart": {"Chilled_Water_Valve": {"hasPoint": "Valve_Command"}}}
    ]

    Given the choice list, create a shape for each option in the choice list
    and add them to the shape graph. Then add to the shapename an sh:or that
    includes all the options.
    """
    or_list = []
    for idx, option in enumerate(choice, start=1):
        print(f"shapename: {shapename}, varname: {varname}, option: {option}")
        oshape = _defn_to_shape(
            None, None, option, shape_graph, ns, name_hint=name_hint
        )
        option_node = BNode()
        label_base = name_hint or "Choice"
        shape_graph.add((option_node, RDF["type"], SH["NodeShape"]))
        shape_graph.add((option_node, SH["property"], oshape))
        shape_graph.add(
            (option_node, SH["name"], Literal(f"{label_base} option {idx}"))
        )
        shape_graph.add(
            (
                option_node,
                SH["message"],
                Literal(f"Satisfy option {idx} for {label_base}."),
            )
        )
        or_list.append(option_node)
    print(or_list)

    or_list_name = BNode()
    Collection(shape_graph, or_list_name, or_list)
    target_shape = shapename if shapename is not None else varname
    shape_graph.add((target_shape, SH["or"], or_list_name))

    return varname


def _prop_to_shape(
    shapename: URIRef,
    shape_graph: Graph,
    varname: URIRef,
    propname: URIRef,
    value: Any,
    ns,
    name_hint: str | None = None,
):
    """
    Given a property name and value, create a shape that requires the sh:path to be that propname
    and the sh:qualifiedValueShape to be the shape of the value
    """
    print("=" * 80)
    if isinstance(value, str):
        # treat like a property shape
        print(f"string value: {value}")
        return _string_to_shape(
            shapename,
            shape_graph,
            varname,
            value,
            path=propname,
            name_hint=name_hint or value,
        )

    possible_edges = [
        "hasPoint",
        "hasPart",
        "feeds",
        "hasLocation",
        "isPartOf",
        "isLocationOf",
        "isPointOf",
        "isFedBy",
    ]

    def _consume_edges(vdict, edge_stack):
        key, value = list(vdict.items())[0]
        edge_stack.append(BRICK[key])
        print(f"adding {key} to edge stack: {edge_stack}")
        if isinstance(value, dict):
            # are there any edges?
            print(f"recursing on {value}")
            if any([key.startswith(edge) for edge in possible_edges]):
                return _consume_edges(value, edge_stack)
            # if no edges, then treat 'value' like a shape
            print(f"returning {value} as leftover")
            property_path = edge_list_to_property_path(edge_stack, shape_graph)
            return _defn_to_shape(
                shapename,
                varname,
                value,
                shape_graph,
                ns,
                path=property_path,
                name_hint=name_hint,
            )
        print(f"returning {value} as leftover (string)")
        # if value is a string, treat it like a property
        property_path = edge_list_to_property_path(edge_stack, shape_graph)
        return _string_to_shape(
            shapename,
            shape_graph,
            varname,
            value,
            path=property_path,
            name_hint=name_hint or value,
        )

    # args are
    for key, vdict in value.items():
        # if the key is an edge, then we need to consume the edges
        if any([key.startswith(edge) for edge in possible_edges]):
            print(f"edge? {key=}, {vdict=}")
            edge_stack = [propname]
            leftover = _consume_edges({key: vdict}, edge_stack)
        else:
            # if key is not an edge, then it is a class name
            print(f"not an edge? {key=}, {vdict=} {propname=}")
            property_path = propname

            if shapename is not None:
                shape_graph.add((shapename, SH["property"], varname))
            shape_graph.add((varname, RDF["type"], SH["PropertyShape"]))
            shape_graph.add((varname, SH["path"], property_path))
            display_name = name_hint or key
            shape_graph.add((varname, SH["name"], Literal(display_name)))
            message = (
                f"Ensure at least one {key} is related via "
                f"{_describe_path_component(property_path)}."
            )
            shape_graph.add((varname, SH["message"], Literal(message)))

            # key is a 'class'
            qvs = BNode()
            shape_graph.add((varname, SH["qualifiedValueShape"], qvs))
            shape_graph.add((varname, SH["qualifiedMinCount"], Literal(1)))
            shape_graph.add((qvs, SH["class"], BRICK[key]))
            shape_graph.add((qvs, RDF["type"], SH["NodeShape"]))
            shape_graph.add((qvs, SH["name"], Literal(f"{key} shape")))
            shape_graph.add((qvs, SH["message"], Literal(f"Value must be a {key}.")))
            # the 'leftover' is a property shape on qvs
            leftover = _defn_to_shape(
                shapename,
                varname,
                vdict,
                shape_graph,
                ns,
                name_hint=name_hint,
            )
            shape_graph.add((qvs, SH["property"], leftover))


def edge_list_to_property_path(edge_list, shape_graph):
    """
    Given a list of edges, return a string that represents the path.
    The edges might end with '?' or '*' or '+'; in which case that needs to be stripped
    and turned into a ZeroOrOne, ZeroOrMore, or OneOrMore
    """
    property_path = BNode()
    edges = []
    for edge in edge_list:
        if edge.endswith("?"):
            edge = URIRef(edge[:-1])
            # make a [ sh:zeroOrOnePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["zeroOrOnePath"], edge))
            edges.append(edge_name)
        elif edge.endswith("*"):
            edge = URIRef(edge[:-1])
            # make a [ sh:zeroOrMorePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["zeroOrMorePath"], edge))
            edges.append(edge_name)
        elif edge.endswith("+"):
            edge = URIRef(edge[:-1])
            # make a [ sh:oneOrMorePath edge ]
            edge_name = BNode()
            shape_graph.add((edge_name, SH["oneOrMorePath"], edge))
            edges.append(edge_name)
        else:
            edges.append(edge)
    if len(edges) == 1:
        return edges[0]
    Collection(shape_graph, property_path, edges)
    return property_path


def generate_manifest(
    rules_json: dict, ns: Namespace = Namespace("http://example.org/building#")
) -> Graph:
    shapes = Graph()
    for _, definition in rules_json.items():
        sg = _definition_to_shape(definition, ns)
        shapes += sg
    return shapes


def generate_manifest_json(rules_json: dict, ns: Namespace):
    shapes = Graph()
    for _, definition in rules_json.items():
        sg = _definition_to_shape(definition, ns)
        shapes += sg
    return shapes
