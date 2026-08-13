import uuid
from pathlib import Path
from typing import Any, Iterable, List, Optional, Union

from buildingmotif.knowledge.errors import KnowledgeDependencyError
from buildingmotif.knowledge.types import EvidenceChunk, KnowledgeSource, ProcessedChunk


class QdrantKnowledgeIndex:
    """Persistent dense+sparse retrieval over source-grounded chunks."""

    DEFAULT_DENSE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    DEFAULT_SPARSE_MODEL = "Qdrant/bm25"
    DENSE_VECTOR = "dense"
    SPARSE_VECTOR = "sparse"

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        *,
        collection_name: str = "buildingmotif-knowledge",
        dense_model: str = DEFAULT_DENSE_MODEL,
        sparse_model: Optional[str] = DEFAULT_SPARSE_MODEL,
        client: Optional[Any] = None,
        dense_embedder: Optional[Any] = None,
        sparse_embedder: Optional[Any] = None,
    ) -> None:
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as error:
            raise KnowledgeDependencyError(
                "Qdrant support requires BuildingMOTIF[knowledge]"
            ) from error

        if client is None and path is None:
            raise ValueError("path is required when no Qdrant client is supplied")

        self.collection_name = collection_name
        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self._models = models
        self._client = client or QdrantClient(path=str(path))
        self._dense_embedder = dense_embedder
        self._sparse_embedder = sparse_embedder

    def _dense(self):
        if self._dense_embedder is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:
                raise KnowledgeDependencyError(
                    "FastEmbed support requires BuildingMOTIF[knowledge]"
                ) from error
            self._dense_embedder = TextEmbedding(model_name=self.dense_model)
        return self._dense_embedder

    def _sparse(self):
        if self.sparse_model is None:
            return None
        if self._sparse_embedder is None:
            try:
                from fastembed import SparseTextEmbedding
            except ImportError as error:
                raise KnowledgeDependencyError(
                    "FastEmbed support requires BuildingMOTIF[knowledge]"
                ) from error
            self._sparse_embedder = SparseTextEmbedding(model_name=self.sparse_model)
        return self._sparse_embedder

    @staticmethod
    def _dense_vector(value: Any) -> List[float]:
        if hasattr(value, "tolist"):
            value = value.tolist()
        return [float(item) for item in value]

    def _sparse_vector(self, value: Any):
        indices = (
            value.indices.tolist()
            if hasattr(value.indices, "tolist")
            else value.indices
        )
        values = (
            value.values.tolist() if hasattr(value.values, "tolist") else value.values
        )
        return self._models.SparseVector(
            indices=[int(item) for item in indices],
            values=[float(item) for item in values],
        )

    def _ensure_collection(self, dense_size: int) -> None:
        if self._client.collection_exists(self.collection_name):
            return
        sparse_config = None
        if self.sparse_model is not None:
            modifier = (
                self._models.Modifier.IDF
                if self.sparse_model == "Qdrant/bm25"
                else None
            )
            sparse_config = {
                self.SPARSE_VECTOR: self._models.SparseVectorParams(modifier=modifier)
            }
        self._client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                self.DENSE_VECTOR: self._models.VectorParams(
                    size=dense_size, distance=self._models.Distance.COSINE
                )
            },
            sparse_vectors_config=sparse_config,
        )

    def _document_filter(self, document_ids: Iterable[int]):
        return self._models.Filter(
            must=[
                self._models.FieldCondition(
                    key="knowledge_document_id",
                    match=self._models.MatchAny(any=list(document_ids)),
                )
            ]
        )

    def replace_document(
        self, source: KnowledgeSource, chunks: List[ProcessedChunk]
    ) -> int:
        """Atomically replace the indexed chunks for one source where possible."""
        if not chunks:
            self.remove_document(source.id)
            return 0

        texts = [chunk.embedding_text for chunk in chunks]
        dense_vectors = [
            self._dense_vector(value) for value in self._dense().embed(texts)
        ]
        if len(dense_vectors) != len(chunks):
            raise ValueError("dense embedder returned the wrong number of vectors")

        sparse_embedder = self._sparse()
        sparse_vectors = None
        if sparse_embedder is not None:
            sparse_vectors = [
                self._sparse_vector(value) for value in sparse_embedder.embed(texts)
            ]
            if len(sparse_vectors) != len(chunks):
                raise ValueError("sparse embedder returned the wrong number of vectors")

        self._ensure_collection(len(dense_vectors[0]))
        self.remove_document(source.id)

        points = []
        for position, (chunk, dense_vector) in enumerate(zip(chunks, dense_vectors)):
            vectors = {self.DENSE_VECTOR: dense_vector}
            if sparse_vectors is not None:
                vectors[self.SPARSE_VECTOR] = sparse_vectors[position]
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{self.collection_name}:{source.id}:{source.sha256}:{chunk.ordinal}",
                )
            )
            points.append(
                self._models.PointStruct(
                    id=point_id,
                    vector=vectors,
                    payload={
                        "knowledge_document_id": source.id,
                        "source_sha256": source.sha256,
                        "source_name": source.name,
                        "source_description": source.description,
                        "file_name": source.file_name,
                        "mime_type": source.mime_type,
                        "chunk_ordinal": chunk.ordinal,
                        "text": chunk.embedding_text,
                        "raw_text": chunk.text,
                        "provenance": chunk.provenance,
                    },
                )
            )
        self._client.upsert(
            collection_name=self.collection_name, points=points, wait=True
        )
        return len(points)

    def remove_document(self, document_id: int) -> None:
        if not self._client.collection_exists(self.collection_name):
            return
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=self._models.FilterSelector(
                filter=self._document_filter([document_id])
            ),
            wait=True,
        )

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        document_ids: Optional[List[int]] = None,
    ) -> List[EvidenceChunk]:
        if not query.strip():
            raise ValueError("query must be non-empty")
        if limit < 1:
            raise ValueError("limit must be positive")
        if document_ids == []:
            return []
        if not self._client.collection_exists(self.collection_name):
            return []

        dense_query = self._dense_vector(next(iter(self._dense().query_embed(query))))
        query_filter = (
            self._document_filter(document_ids) if document_ids is not None else None
        )
        prefetch = [
            self._models.Prefetch(
                query=dense_query,
                using=self.DENSE_VECTOR,
                filter=query_filter,
                limit=max(limit * 2, 20),
            )
        ]
        sparse_embedder = self._sparse()
        if sparse_embedder is not None:
            sparse_query = self._sparse_vector(
                next(iter(sparse_embedder.query_embed(query)))
            )
            prefetch.append(
                self._models.Prefetch(
                    query=sparse_query,
                    using=self.SPARSE_VECTOR,
                    filter=query_filter,
                    limit=max(limit * 2, 20),
                )
            )
        if len(prefetch) == 1:
            response = self._client.query_points(
                collection_name=self.collection_name,
                query=dense_query,
                using=self.DENSE_VECTOR,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        else:
            response = self._client.query_points(
                collection_name=self.collection_name,
                prefetch=prefetch,
                query=self._models.FusionQuery(fusion=self._models.Fusion.RRF),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                EvidenceChunk(
                    score=float(point.score),
                    knowledge_document_id=int(payload["knowledge_document_id"]),
                    source_sha256=str(payload["source_sha256"]),
                    source_name=str(payload["source_name"]),
                    source_description=str(payload.get("source_description", "")),
                    file_name=str(payload["file_name"]),
                    mime_type=str(payload["mime_type"]),
                    chunk_ordinal=int(payload["chunk_ordinal"]),
                    text=str(payload["text"]),
                    provenance=dict(payload.get("provenance", {})),
                )
            )
        return results

    def close(self) -> None:
        """Close the underlying local or remote Qdrant client."""
        self._client.close()
