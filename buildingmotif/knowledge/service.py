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
