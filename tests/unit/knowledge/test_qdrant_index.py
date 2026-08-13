from types import SimpleNamespace

import numpy as np
import pytest

from buildingmotif.knowledge import (
    KnowledgeSource,
    ProcessedChunk,
    QdrantKnowledgeIndex,
)

qdrant_client = pytest.importorskip("qdrant_client")


def _dense(text):
    lowered = text.lower()
    return np.array(
        [float("fan" in lowered or "ahu" in lowered), float("vav" in lowered)]
    )


class FakeDenseEmbedder:
    def embed(self, documents):
        return (_dense(document) for document in documents)

    def query_embed(self, query):
        return iter([_dense(query)])


class FakeSparseEmbedder:
    @staticmethod
    def _embed(text):
        lowered = text.lower()
        if "fan" in lowered or "ahu" in lowered:
            return SimpleNamespace(indices=np.array([1]), values=np.array([1.0]))
        return SimpleNamespace(indices=np.array([2]), values=np.array([1.0]))

    def embed(self, documents):
        return (self._embed(document) for document in documents)

    def query_embed(self, query):
        return iter([self._embed(query)])


def _source(document_id=7):
    return KnowledgeSource(
        id=document_id,
        name="Air handler schedule",
        description="Controls evidence",
        file_name="schedule.pdf",
        mime_type="application/pdf",
        sha256="source-hash",
        content=b"unused",
    )


def test_qdrant_index_replace_retrieve_filter_and_remove():
    client = qdrant_client.QdrantClient(":memory:")
    index = QdrantKnowledgeIndex(
        client=client,
        dense_embedder=FakeDenseEmbedder(),
        sparse_embedder=FakeSparseEmbedder(),
    )
    chunks = [
        ProcessedChunk(0, "AHU supply fan", "AHU supply fan", {"page": 2}),
        ProcessedChunk(1, "VAV schedule", "VAV schedule", {"page": 3}),
    ]

    assert index.replace_document(_source(), chunks) == 2
    results = index.retrieve("AHU fan", limit=2)

    assert results[0].knowledge_document_id == 7
    assert results[0].source_sha256 == "source-hash"
    assert results[0].source_description == "Controls evidence"
    assert results[0].file_name == "schedule.pdf"
    assert results[0].chunk_ordinal == 0
    assert results[0].provenance == {"page": 2}
    assert index.retrieve("AHU fan", document_ids=[999]) == []

    replacement = [ProcessedChunk(0, "Replacement", "Replacement", {"page": 4})]
    assert index.replace_document(_source(), replacement) == 1
    assert client.count(index.collection_name, exact=True).count == 1

    index.remove_document(7)
    assert index.retrieve("Replacement") == []
    index.close()
