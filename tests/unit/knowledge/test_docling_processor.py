from types import SimpleNamespace

import pytest

from buildingmotif.knowledge import DoclingDocumentProcessor, KnowledgeSource

pytest.importorskip("docling")


class FakeMeta:
    def model_dump(self, **kwargs):
        return {"headings": ["AHU-1"], "doc_items": [{"page_no": 3}]}


class FakeChunker:
    def chunk(self, dl_doc):
        assert dl_doc == "converted-document"
        yield SimpleNamespace(text="Supply fan schedule", meta=FakeMeta())

    def contextualize(self, chunk):
        return f"AHU-1\n{chunk.text}"


class FakeConverter:
    def convert(self, source):
        assert source.name == "schedule.txt"
        assert source.stream.read() == b"Supply fan schedule"
        return SimpleNamespace(document="converted-document")


def test_docling_processor_preserves_context_and_provenance():
    source = KnowledgeSource(
        id=7,
        name="Schedule",
        description="",
        file_name="schedule.txt",
        mime_type="text/plain",
        sha256="abc",
        content=b"Supply fan schedule",
    )
    processor = DoclingDocumentProcessor(
        converter=FakeConverter(), chunker=FakeChunker()
    )

    chunks = processor.process(source)

    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].text == "Supply fan schedule"
    assert chunks[0].embedding_text == "AHU-1\nSupply fan schedule"
    assert chunks[0].provenance == {
        "headings": ["AHU-1"],
        "doc_items": [{"page_no": 3}],
    }


def test_docling_processor_converts_a_real_text_stream():
    from docling.document_converter import DocumentConverter
    from docling_core.transforms.chunker.hierarchical_chunker import HierarchicalChunker

    source = KnowledgeSource(
        id=8,
        name="Sequence",
        description="",
        file_name="sequence.txt",
        mime_type="text/plain",
        sha256="def",
        content=b"AHU-1 has a supply fan.",
    )
    processor = DoclingDocumentProcessor(
        converter=DocumentConverter(), chunker=HierarchicalChunker()
    )

    chunks = processor.process(source)

    assert [chunk.text for chunk in chunks] == ["AHU-1 has a supply fan."]
    assert chunks[0].provenance["origin"]["filename"] == "sequence.txt"
