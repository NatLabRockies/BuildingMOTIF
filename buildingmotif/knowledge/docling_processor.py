from io import BytesIO
from typing import Any, List, Optional

from buildingmotif.knowledge.errors import KnowledgeDependencyError
from buildingmotif.knowledge.types import KnowledgeSource, ProcessedChunk


class DoclingDocumentProcessor:
    """Convert and structure-aware chunk uploaded documents with Docling."""

    DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        *,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        max_tokens: Optional[int] = None,
        converter: Optional[Any] = None,
        chunker: Optional[Any] = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.max_tokens = max_tokens
        self._converter = converter
        self._chunker = chunker

    def _load_pipeline(self) -> None:
        try:
            from docling.chunking import HybridChunker
            from docling.document_converter import DocumentConverter
            from docling_core.transforms.chunker.tokenizer.huggingface import (
                HuggingFaceTokenizer,
            )
        except ImportError as error:
            raise KnowledgeDependencyError(
                "Docling support requires BuildingMOTIF[knowledge]"
            ) from error

        if self._converter is None:
            self._converter = DocumentConverter()
        if self._chunker is None:
            tokenizer = HuggingFaceTokenizer.from_pretrained(
                self.embedding_model, max_tokens=self.max_tokens
            )
            self._chunker = HybridChunker(tokenizer=tokenizer)

    def process(self, source: KnowledgeSource) -> List[ProcessedChunk]:
        """Convert a source blob and return chunks with Docling provenance."""
        if self._converter is None or self._chunker is None:
            self._load_pipeline()

        try:
            from docling.datamodel.base_models import DocumentStream
        except ImportError as error:
            raise KnowledgeDependencyError(
                "Docling support requires BuildingMOTIF[knowledge]"
            ) from error

        document_stream = DocumentStream(
            name=source.file_name, stream=BytesIO(source.content)
        )
        assert self._converter is not None
        assert self._chunker is not None
        converted = self._converter.convert(document_stream)
        document = converted.document

        chunks = []
        for ordinal, chunk in enumerate(self._chunker.chunk(dl_doc=document)):
            provenance = chunk.meta.model_dump(mode="json", exclude_none=True)
            chunks.append(
                ProcessedChunk(
                    ordinal=ordinal,
                    text=chunk.text,
                    embedding_text=self._chunker.contextualize(chunk),
                    provenance=provenance,
                )
            )
        return chunks
