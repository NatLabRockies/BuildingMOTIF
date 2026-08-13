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
