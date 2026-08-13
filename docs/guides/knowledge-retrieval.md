# Document indexing and retrieval

BuildingMOTIF can retain source documents in SQL and build a derived retrieval index with
[Docling](https://docling-project.github.io/docling/) and
[Qdrant](https://qdrant.tech/). The SQL blob remains the authoritative source. Indexed
chunks are disposable and can always be regenerated from it.

SQL storage accepts any non-empty file. The default Docling processor can index common
document formats including PDF, plain text/Markdown, HTML, office documents, and images.
A successfully stored blob is not necessarily indexable by every configured processor.

Install the optional dependencies:

```bash
uv sync --extra knowledge
```

## HTTP API setup

Set a persistent Qdrant path before starting the API:

```bash
export KNOWLEDGE_INDEX_PATH=.buildingmotif-knowledge
buildingmotif serve --db sqlite:///buildingmotif.db
```

The first indexing request downloads the configured Docling tokenizer and FastEmbed
models. `HF_HOME` and `FASTEMBED_CACHE_PATH` can be set to persistent model-cache
directories. Do not share a local Qdrant path between multiple server processes; use a
Qdrant server and construct `QdrantKnowledgeIndex` with a remote client for that
deployment shape.

Upload a PDF from a path relative to the shell's current directory, then index it:

```bash
curl -F 'name=AHU schedule' \
     -F 'description=Controls submittal' \
     -F 'file=@./documents/ahu-schedule.pdf;type=application/pdf' \
     http://localhost:5000/knowledge/documents

curl -X POST http://localhost:5000/knowledge/documents/1/index
```

Absolute paths work with curl as well. The API accepts multipart uploads up to 100 MiB by
default; set `KNOWLEDGE_MAX_DOCUMENT_BYTES` to change that limit. A Python HTTP client can
upload the same local file:

```python
from pathlib import Path

import requests  # pip install requests

path = Path("documents/ahu-schedule.pdf")
with path.open("rb") as stream:
    response = requests.post(
        "http://localhost:5000/knowledge/documents",
        data={"name": "AHU schedule", "description": "Controls submittal"},
        files={"file": (path.name, stream, "application/pdf")},
        timeout=60,
    )
response.raise_for_status()
document = response.json()
```

Indexing is synchronous in this first implementation. Updating a document or its
metadata removes its existing chunks, so call the index endpoint again afterward.
Deleting a document also removes its indexed chunks.

Retrieve evidence:

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"query":"Does AHU-1 have a supply fan?","limit":5}' \
     http://localhost:5000/knowledge/search
```

Because the request above omits `document_ids`, it searches all chunks in the configured
index and returns the highest-ranked five. This means all documents that have been
successfully indexed—not every document merely stored in SQL. Add `document_ids` to
restrict a query to selected sources. Every result contains the SQL document ID, source
SHA-256, filename, chunk ordinal, and Docling provenance. A retrieval result is evidence
for a user to review; it is not permission to assert metadata or automatically apply a
model repair.

## Python API

Add a file, index it, and retrieve evidence through the service owned by the
`BuildingMOTIF` instance:

```python
from pathlib import Path

from buildingmotif import BuildingMOTIF

source_path = Path("documents") / "ahu-schedule.pdf"  # relative to this process

with BuildingMOTIF(
    "sqlite:///buildingmotif.db",
    knowledge_index_path=".buildingmotif-knowledge",
) as bm:
    document = bm.knowledge.add_document(
        source_path,
        name="AHU schedule",
        description="Controls submittal",
    )
    chunk_count = bm.knowledge.index_document(document.id)
    evidence = bm.knowledge.retrieve(
        "AHU-1 supply fan",
        limit=5,
        document_ids=[document.id],
    )
```

Omit `document_ids` to search the whole configured index:

```python
evidence = bm.knowledge.retrieve("AHU-1 supply fan", limit=5)
```

That searches every successfully indexed document and returns the five highest-ranked
chunks across the corpus. Documents that have only been added to SQL do not participate
until `index_document(...)` succeeds. Supplying `document_ids=[...]` applies a source
filter before ranking.

`add_document` accepts a string or `Path`; relative paths resolve from the Python
process's current working directory, and absolute paths work unchanged. It reads the file
(PDF, text, image, or another supported type) and infers its MIME type from the filename.
Pass `mime_type=` to override the inference. For bytes already in memory, use
`create_document`:

```python
document = bm.knowledge.create_document(
    name="Sequence of operations",
    description="Text export",
    file_name="sequence.txt",
    mime_type="text/plain",
    content=b"Enable AHU-1 when occupied.",
)
```

Document storage and indexing are separate operations: call `index_document(document.id)`
after creating a document and again after updating it. The Python lifecycle methods are:

```python
documents = bm.knowledge.list_documents()  # metadata only; blobs remain deferred
document = bm.knowledge.get_document(document.id)
source = bm.knowledge.get_document(document.id, include_content=True).content

bm.knowledge.update_document(
    document.id,
    name="Reviewed AHU schedule",
    description="Approved controls submittal",
)
bm.knowledge.index_document(document.id)  # update invalidated the old chunks
bm.knowledge.delete_document(document.id)  # removes SQL source and indexed chunks
```

All SQL writes commit when the `BuildingMOTIF` context exits normally and roll back when
an exception escapes it.

## Custom indexes

The service depends only on BuildingMOTIF's `DocumentProcessor` and `KnowledgeIndex`
protocols. For a remote Qdrant deployment, construct the adapter explicitly:

```python
from qdrant_client import QdrantClient

from buildingmotif.knowledge import (
    DoclingDocumentProcessor,
    KnowledgeService,
    QdrantKnowledgeIndex,
)

with BuildingMOTIF("postgresql://...") as bm:
    client = QdrantClient(url="http://qdrant:6333")
    processor = DoclingDocumentProcessor()
    index = QdrantKnowledgeIndex(client=client)
    bm.configure_knowledge(KnowledgeService(bm, processor, index))

    # The API stays the same regardless of the index backend.
    evidence = bm.knowledge.retrieve("AHU-1 supply fan", limit=5)
```

An alternative pgvector or domain-specific retriever can implement `KnowledgeIndex`
without changing the SQL document API or downstream repair workflow.
