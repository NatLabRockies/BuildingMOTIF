from io import BytesIO
from typing import Dict, Optional, Tuple

import flask
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_api import status
from werkzeug.datastructures import FileStorage

from buildingmotif.api.serializers.knowledge import serialize
from buildingmotif.database.errors import KnowledgeDocumentNotFound

blueprint = Blueprint("knowledge", __name__)


def _error(message: str, status_code: int) -> Tuple[Dict[str, str], int]:
    return {"message": message}, status_code


def _read_upload(upload: FileStorage) -> Tuple[Optional[bytes], Optional[Tuple]]:
    limit = current_app.config["KNOWLEDGE_MAX_DOCUMENT_BYTES"]
    content = upload.stream.read(limit + 1)
    if len(content) > limit:
        return None, _error(
            f"file exceeds the {limit}-byte document limit",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    if not content:
        return None, _error("file must not be empty", status.HTTP_400_BAD_REQUEST)
    return content, None


def _required_text(value, field: str) -> Tuple[Optional[str], Optional[Tuple]]:
    if not isinstance(value, str) or not value.strip():
        return None, _error(
            f"{field} must be a non-empty string", status.HTTP_400_BAD_REQUEST
        )
    return value.strip(), None


@blueprint.route("/documents", methods=["GET"])
def list_documents() -> flask.Response:
    documents = (
        current_app.building_motif.table_connection.get_all_db_knowledge_documents()
    )
    return jsonify(serialize(documents)), status.HTTP_200_OK


@blueprint.route("/documents/<int:document_id>", methods=["GET"])
def get_document(document_id: int) -> flask.Response:
    try:
        document = (
            current_app.building_motif.table_connection.get_db_knowledge_document(
                document_id, include_content=False
            )
        )
    except KnowledgeDocumentNotFound:
        return _error(f"ID: {document_id}", status.HTTP_404_NOT_FOUND)
    return jsonify(serialize(document)), status.HTTP_200_OK


@blueprint.route("/documents/<int:document_id>/content", methods=["GET"])
def get_document_content(document_id: int) -> flask.Response:
    try:
        document = (
            current_app.building_motif.table_connection.get_db_knowledge_document(
                document_id
            )
        )
    except KnowledgeDocumentNotFound:
        return _error(f"ID: {document_id}", status.HTTP_404_NOT_FOUND)
    return send_file(
        BytesIO(document.content),
        mimetype=document.mime_type,
        download_name=document.file_name,
        as_attachment=True,
    )


@blueprint.route("/documents", methods=["POST"])
def create_document() -> flask.Response:
    if request.mimetype != "multipart/form-data":
        return _error(
            "request content type must be multipart/form-data",
            status.HTTP_400_BAD_REQUEST,
        )
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return _error("must provide a file", status.HTTP_400_BAD_REQUEST)
    name, error = _required_text(request.form.get("name", upload.filename), "name")
    if error:
        return error
    content, error = _read_upload(upload)
    if error:
        return error
    document = current_app.building_motif.table_connection.create_db_knowledge_document(
        name=name,
        description=request.form.get("description", ""),
        file_name=upload.filename,
        mime_type=upload.mimetype or "application/octet-stream",
        content=content,
    )
    return jsonify(serialize(document)), status.HTTP_201_CREATED


@blueprint.route("/documents/<int:document_id>", methods=["PATCH"])
def update_document(document_id: int) -> flask.Response:
    content = None
    file_name = None
    mime_type = None
    if request.mimetype == "application/json":
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("body must be a JSON object", status.HTTP_400_BAD_REQUEST)
    elif request.mimetype == "multipart/form-data":
        body = request.form.to_dict()
        upload = request.files.get("file")
        if upload is not None:
            if not upload.filename:
                return _error("file must have a filename", status.HTTP_400_BAD_REQUEST)
            content, error = _read_upload(upload)
            if error:
                return error
            file_name = upload.filename
            mime_type = upload.mimetype or "application/octet-stream"
    else:
        return _error(
            "request content type must be application/json or multipart/form-data",
            status.HTTP_400_BAD_REQUEST,
        )

    unknown = set(body) - {"name", "description"}
    if unknown:
        return _error(
            f"unknown fields: {', '.join(sorted(unknown))}",
            status.HTTP_400_BAD_REQUEST,
        )
    if "name" in body:
        name, error = _required_text(body["name"], "name")
        if error:
            return error
    else:
        name = None
    description = body.get("description")
    if description is not None and not isinstance(description, str):
        return _error("description must be a string", status.HTTP_400_BAD_REQUEST)
    if name is None and description is None and content is None:
        return _error("no changes supplied", status.HTTP_400_BAD_REQUEST)

    try:
        document = (
            current_app.building_motif.table_connection.update_db_knowledge_document(
                document_id,
                name=name,
                description=description,
                file_name=file_name,
                mime_type=mime_type,
                content=content,
            )
        )
    except KnowledgeDocumentNotFound:
        return _error(f"ID: {document_id}", status.HTTP_404_NOT_FOUND)
    return jsonify(serialize(document)), status.HTTP_200_OK


@blueprint.route("/documents/<int:document_id>", methods=["DELETE"])
def delete_document(document_id: int) -> flask.Response:
    try:
        current_app.building_motif.table_connection.delete_db_knowledge_document(
            document_id
        )
    except KnowledgeDocumentNotFound:
        return _error(f"ID: {document_id}", status.HTTP_404_NOT_FOUND)
    return flask.Response(status=status.HTTP_204_NO_CONTENT)
