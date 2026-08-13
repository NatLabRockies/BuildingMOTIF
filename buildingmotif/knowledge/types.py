from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class KnowledgeSource:
    """The immutable source metadata passed into an indexing run."""

    id: int
    name: str
    description: str
    file_name: str
    mime_type: str
    sha256: str
    content: bytes


@dataclass(frozen=True)
class ProcessedChunk:
    """A source-grounded text chunk produced by a document processor."""

    ordinal: int
    text: str
    embedding_text: str
    provenance: Dict[str, Any]


@dataclass(frozen=True)
class EvidenceChunk:
    """A retrieval result that remains traceable to an uploaded document."""

    score: float
    knowledge_document_id: int
    source_sha256: str
    source_name: str
    source_description: str
    file_name: str
    mime_type: str
    chunk_ordinal: int
    text: str
    provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DocumentProcessor(Protocol):
    def process(self, source: KnowledgeSource) -> List[ProcessedChunk]:
        ...


class KnowledgeIndex(Protocol):
    def replace_document(
        self, source: KnowledgeSource, chunks: List[ProcessedChunk]
    ) -> int:
        ...

    def remove_document(self, document_id: int) -> None:
        ...

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        document_ids: Optional[List[int]] = None,
    ) -> List[EvidenceChunk]:
        ...
