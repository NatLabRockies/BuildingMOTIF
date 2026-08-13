from pathlib import Path

import pytest

from buildingmotif.knowledge import KnowledgeService, ProcessedChunk


class FakeProcessor:
    def process(self, source):
        assert source.content == b"evidence"
        return [ProcessedChunk(0, "evidence", "evidence", {"page": 1})]


class FakeIndex:
    def __init__(self):
        self.source = None
        self.chunks = None
        self.removed = []
        self.closed = False

    def replace_document(self, source, chunks):
        self.source = source
        self.chunks = chunks
        return len(chunks)

    def remove_document(self, document_id):
        self.removed.append(document_id)

    def retrieve(self, query, *, limit=10, document_ids=None):
        return []

    def close(self):
        self.closed = True


def test_service_indexes_sql_source(bm):
    document = bm.table_connection.create_db_knowledge_document(
        name="Evidence",
        file_name="evidence.txt",
        mime_type="text/plain",
        content=b"evidence",
    )
    index = FakeIndex()
    service = KnowledgeService(bm, FakeProcessor(), index)

    assert service.index_document(document.id) == 1
    assert index.source.id == document.id
    assert index.source.sha256 == document.sha256
    assert index.chunks[0].provenance == {"page": 1}

    service.remove_document(document.id)
    assert index.removed == [document.id]

    service.close()
    assert index.closed


def test_service_manages_document_lifecycle(bm, tmp_path: Path):
    source_path = tmp_path / "ahu-schedule.txt"
    source_path.write_bytes(b"AHU-1 has a supply fan")
    index = FakeIndex()
    service = KnowledgeService(bm, FakeProcessor(), index)

    document = service.add_document(
        source_path,
        name="AHU schedule",
        description="Controls submittal",
    )

    assert document.name == "AHU schedule"
    assert document.file_name == "ahu-schedule.txt"
    assert document.mime_type == "text/plain"
    assert service.list_documents() == [document]
    assert service.get_document(document.id).id == document.id
    assert service.get_document(document.id, include_content=True).content == (
        b"AHU-1 has a supply fan"
    )

    updated = service.update_document(document.id, description="Reviewed submittal")
    assert updated.description == "Reviewed submittal"
    assert index.removed == [document.id]

    service.delete_document(document.id)
    assert index.removed == [document.id, document.id]
    assert service.list_documents() == []


def test_service_creates_document_from_bytes(bm):
    service = KnowledgeService(bm, FakeProcessor(), FakeIndex())

    document = service.create_document(
        name="Sequence of operations",
        description="Generated text export",
        file_name="sequence.txt",
        mime_type="text/plain",
        content=b"Enable AHU-1 when occupied.",
    )

    assert document.size == len(b"Enable AHU-1 when occupied.")
    assert service.get_document(document.id, include_content=True).content == (
        b"Enable AHU-1 when occupied."
    )


def test_service_rejects_invalid_document(bm):
    service = KnowledgeService(bm, FakeProcessor(), FakeIndex())

    with pytest.raises(ValueError, match="name must be a non-empty string"):
        service.create_document(
            name=" ", file_name="sequence.txt", mime_type="text/plain", content=b"x"
        )
    with pytest.raises(ValueError, match="file_name must be a non-empty string"):
        service.create_document(
            name="Sequence", file_name="", mime_type="text/plain", content=b"x"
        )
    with pytest.raises(ValueError, match="mime_type must be a non-empty string"):
        service.create_document(
            name="Sequence", file_name="sequence.txt", mime_type="", content=b"x"
        )
    with pytest.raises(ValueError, match="content must not be empty"):
        service.create_document(
            name="Sequence",
            file_name="sequence.txt",
            mime_type="text/plain",
            content=b"",
        )
