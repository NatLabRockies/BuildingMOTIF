from datetime import timezone
from typing import List, Union

from typing_extensions import TypedDict

from buildingmotif.database.tables import DBKnowledgeDocument

KnowledgeDocumentDict = TypedDict(
    "KnowledgeDocumentDict",
    {
        "id": int,
        "name": str,
        "description": str,
        "file_name": str,
        "mime_type": str,
        "size": int,
        "sha256": str,
        "created_at": str,
        "updated_at": str,
    },
)


def _timestamp(value) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat()}Z"


def serialize(
    value: Union[DBKnowledgeDocument, List[DBKnowledgeDocument]]
) -> Union[KnowledgeDocumentDict, List[KnowledgeDocumentDict]]:
    """Serialize document metadata, deliberately excluding blob contents."""
    if isinstance(value, DBKnowledgeDocument):
        return _serialize(value)
    if isinstance(value, list):
        return [_serialize(document) for document in value]
    raise ValueError("invalid input. Must be a DBKnowledgeDocument or list")


def _serialize(document: DBKnowledgeDocument) -> KnowledgeDocumentDict:
    return {
        "id": document.id,
        "name": document.name,
        "description": document.description,
        "file_name": document.file_name,
        "mime_type": document.mime_type,
        "size": document.size,
        "sha256": document.sha256,
        "created_at": _timestamp(document.created_at),
        "updated_at": _timestamp(document.updated_at),
    }
