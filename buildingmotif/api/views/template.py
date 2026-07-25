from io import StringIO
from typing import Dict

import flask
from flask import Blueprint, current_app, jsonify, request
from flask_api import status
from rdflib import Literal, URIRef
from rdflib.term import Node

from buildingmotif.api.serializers.template import serialize
from buildingmotif.database.errors import ModelNotFound, TemplateNotFound
from buildingmotif.dataclasses import Model, Template
from buildingmotif.ingresses import CSVIngress, TemplateIngress

blueprint = Blueprint("templates", __name__)


@blueprint.route("", methods=(["GET"]))
def get_all_templates() -> flask.Response:
    """Get all templates.

    :return: all templates
    :rtype: flask.Response
    """
    db_templates = current_app.building_motif.table_connection.get_all_db_templates()

    return jsonify(serialize(db_templates)), status.HTTP_200_OK


@blueprint.route("/<templates_id>", methods=(["GET"]))
def get_template(templates_id: int) -> flask.Response:
    """Get template by id.

    :param templates_id: template id
    :type templates_id: int
    :return: requested template
    :rtype: flask.Response
    """
    include_parameters = request.args.get("parameters", False)

    try:
        template = current_app.building_motif.table_connection.get_db_template(
            templates_id
        )
    except TemplateNotFound:
        return {"message": f"ID: {templates_id}"}, status.HTTP_404_NOT_FOUND

    return jsonify(serialize(template, include_parameters)), status.HTTP_200_OK


@blueprint.route("/<template_id>/evaluate/ingress", methods=(["POST"]))
def evaluate_ingress(template_id: int) -> flask.Response:
    # get template
    try:
        template = Template.load(template_id)
    except TemplateNotFound:
        return {"message": f"ID: {template_id}"}, status.HTTP_404_NOT_FOUND

    # get model
    model_id = request.args.get("model_id")
    if model_id is None:
        return {
            "message": "must contain query param 'model_id'"
        }, status.HTTP_400_BAD_REQUEST
    try:
        model = Model.load(model_id)
    except ModelNotFound:
        return {"message": f"ID: {model_id}"}, status.HTTP_404_NOT_FOUND

    # get file
    raw_data = flask.request.get_data()
    if raw_data is None:
        return {"message": "no file recieved."}, status.HTTP_400_NOT_FOUND

    # evaluate template
    try:
        data = StringIO(raw_data.decode("utf-8"))
        csv_ingress = CSVIngress(data=data)
        template_ingress = TemplateIngress(
            template.inline_dependencies(), None, csv_ingress
        )
        graph_or_template = template_ingress.graph(model.name)
    except Exception:
        return {"message": "Invalid csv."}, status.HTTP_400_BAD_REQUEST

    # parse bindings from input JSON
    if isinstance(graph_or_template, Template):
        graph = graph_or_template.body
    else:
        graph = graph_or_template

    return graph.serialize(format="ttl"), status.HTTP_200_OK


@blueprint.route("/<template_id>/evaluate/bindings", methods=(["POST"]))
def evaluate_bindings(template_id: int) -> flask.Response:
    """evaluate template with giving binding

    :param template_id: id of template
    :type template_id: int
    :return: evaluated Group
    :rtype: flask.Response
    """
    try:
        template = Template.load(template_id)
    except TemplateNotFound:
        return {"message": f"ID: {template_id}"}, status.HTTP_404_NOT_FOUND

    if request.content_type != "application/json":
        return {
            "message": "request content type must be json"
        }, status.HTTP_400_BAD_REQUEST

    model_id = request.get_json().get("model_id")
    if model_id is None:
        return {"message": "body must contain 'model_id'"}, status.HTTP_400_BAD_REQUEST
    try:
        model = Model.load(model_id)
    except ModelNotFound:
        return {"message": f"ID: {model_id}"}, status.HTTP_404_NOT_FOUND

    bindings = request.get_json().get("bindings")
    if bindings is None:
        return {"message": "body must contain 'bindings'"}, status.HTTP_400_BAD_REQUEST
    bindings = get_bindings(bindings)
    bindings = {k: model.name.rstrip("/") + "/" + v for k, v in bindings.items()}

    # parse bindings from input JSON
    filled = template.substitute(bindings)
    # a partially-bound template serializes its body, param: URIs and all
    graph = filled.to_graph() if filled.is_complete else filled.body

    return graph.serialize(format="ttl"), status.HTTP_200_OK


@blueprint.route("/<template_id>/body", methods=(["GET"]))
def get_template_body(template_id: int) -> flask.Response:
    """Get template body.

    :param template_id: template id
    :type template_id: int
    :return: template body
    :rtype: flask.Response
    """
    try:
        template: Template = Template.load(template_id)
    except TemplateNotFound:
        return {"message": f"ID: {template_id}"}, status.HTTP_404_NOT_FOUND

    return template.body.serialize(format="ttl"), status.HTTP_200_OK


def get_bindings(binding_dict) -> Dict[str, Node]:
    """type binding_dict values to nodes

    given:
        {name: {@id or @literal: value}}

    return:
        {name: typed value}

    :param binding_dict: untyped bindings
    :type binding_dict: dict
    :return: typed dict
    :rtype: Dict[str, Node]
    """
    bindings = {}
    for param, definition in binding_dict.items():
        if "@id" in definition:
            bindings[param] = URIRef(definition["@id"])
        if "@literal" in definition:
            dtype = definition.get("@datatype")
            bindings[param] = Literal(
                definition["@literal"], datatype=URIRef(dtype) if dtype else None
            )
    return bindings
