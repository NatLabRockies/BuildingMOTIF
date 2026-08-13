import mimetypes
from pathlib import Path
from typing import List, Optional, Union

from buildingmotif.database.tables import DBKnowledgeDocument
from buildingmotif.knowledge.docling_processor import DoclingDocumentProcessor
from buildingmotif.knowledge.qdrant_index import QdrantKnowledgeIndex
from buildingmotif.knowledge.types import (
    DocumentProcessor,
    EvidenceChunk,
    KnowledgeIndex,
    KnowledgeSource,
)


class KnowledgeService:
    """Coordinates SQL source documents, processing, and retrieval indexing."""

    def __init__(
        self,
        building_motif,
        processor: DocumentProcessor,
        index: KnowledgeIndex,
    ) -> None:
        self.building_motif = building_motif
        self.processor = processor
        self.index = index

    @classmethod
    def local(
        cls,
        building_motif,
        path: Union[str, Path],
        *,
        collection_name: str = "buildingmotif-knowledge",
        embedding_model: str = DoclingDocumentProcessor.DEFAULT_EMBEDDING_MODEL,
        sparse_model: Optional[str] = QdrantKnowledgeIndex.DEFAULT_SPARSE_MODEL,
        max_tokens: Optional[int] = None,
    ) -> "KnowledgeService":
        processor = DoclingDocumentProcessor(
            embedding_model=embedding_model, max_tokens=max_tokens
        )
        index = QdrantKnowledgeIndex(
            path,
            collection_name=collection_name,
            dense_model=embedding_model,
            sparse_model=sparse_model,
        )
        return cls(building_motif, processor, index)

    @staticmethod
    def _source(document: DBKnowledgeDocument) -> KnowledgeSource:
        return KnowledgeSource(
            id=document.id,
            name=document.name,
            description=document.description,
            file_name=document.file_name,
            mime_type=document.mime_type,
            sha256=document.sha256,
            content=document.content,
        )

    def add_document(
        self,
        path: Union[str, Path],
        *,
        name: Optional[str] = None,
        description: str = "",
        mime_type: Optional[str] = None,
    ) -> DBKnowledgeDocument:
        """Store a file as a knowledge document.

        The source bytes are retained in SQL. Call :meth:`index_document`
        separately to build or rebuild its retrieval chunks.
        """
        source_path = Path(path)
        guessed_type, _ = mimetypes.guess_type(source_path.name)
        return self.create_document(
            name=name or source_path.name,
            description=description,
            file_name=source_path.name,
            mime_type=mime_type or guessed_type or "application/octet-stream",
            content=source_path.read_bytes(),
        )

    def create_document(
        self,
        *,
        name: str,
        file_name: str,
        mime_type: str,
        content: bytes,
        description: str = "",
    ) -> DBKnowledgeDocument:
        """Store an in-memory document and its metadata in SQL."""
        if not name.strip():
            raise ValueError("name must be a non-empty string")
        if not file_name.strip():
            raise ValueError("file_name must be a non-empty string")
        if not mime_type.strip():
            raise ValueError("mime_type must be a non-empty string")
        if not content:
            raise ValueError("content must not be empty")
        return self.building_motif.table_connection.create_db_knowledge_document(
            name=name.strip(),
            description=description,
            file_name=file_name.strip(),
            mime_type=mime_type.strip(),
            content=content,
        )

    def list_documents(self) -> List[DBKnowledgeDocument]:
        """List document metadata without loading the stored blobs."""
        return self.building_motif.table_connection.get_all_db_knowledge_documents()

    def get_document(
        self, document_id: int, *, include_content: bool = False
    ) -> DBKnowledgeDocument:
        """Get one document, optionally including its stored bytes."""
        return self.building_motif.table_connection.get_db_knowledge_document(
            document_id, include_content=include_content
        )

    def update_document(
        self,
        document_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
        content: Optional[bytes] = None,
    ) -> DBKnowledgeDocument:
        """Update a source document and invalidate its retrieval chunks."""
        self.remove_document(document_id)
        return self.building_motif.table_connection.update_db_knowledge_document(
            document_id,
            name=name,
            description=description,
            file_name=file_name,
            mime_type=mime_type,
            content=content,
        )

    def delete_document(self, document_id: int) -> None:
        """Delete a source document and its retrieval chunks."""
        self.remove_document(document_id)
        self.building_motif.table_connection.delete_db_knowledge_document(document_id)

    def index_document(self, document_id: int) -> int:
        document = self.building_motif.table_connection.get_db_knowledge_document(
            document_id
        )
        source = self._source(document)
        chunks = self.processor.process(source)
        return self.index.replace_document(source, chunks)

    def remove_document(self, document_id: int) -> None:
        self.index.remove_document(document_id)

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        document_ids: Optional[List[int]] = None,
    ) -> List[EvidenceChunk]:
        return self.index.retrieve(query, limit=limit, document_ids=document_ids)

    def close(self) -> None:
        close = getattr(self.index, "close", None)
        if close is not None:
            close()

    def __enter__(self) -> "KnowledgeService":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
