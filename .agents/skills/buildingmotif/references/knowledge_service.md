# BuildingMOTIF knowledge service

Use the knowledge service to retain source files and retrieve source-grounded chunks from
large or unstructured document collections. It is especially useful for specifications,
O&M manuals, submittals, sequences of operation, commissioning reports, scanned PDFs, and
images whose wording is not predictable enough for grep alone.

## Contents

- [Install and configure](#install-and-configure)
- [Add documents and manage their lifecycle](#add-documents-and-manage-their-lifecycle)
- [Retrieve evidence](#retrieve-evidence)
- [Use it in the repair loop](#use-it-in-the-repair-loop)
- [Custom index backends](#custom-index-backends)

The architecture is deliberately split:

- SQL owns the original blob and its metadata: name, description, filename, MIME type,
  size, SHA-256, and timestamps.
- Docling converts the blob and creates structure-aware chunks.
- FastEmbed creates dense and sparse embeddings.
- Qdrant stores the disposable retrieval index.
- `bm.knowledge` owns indexing, retrieval, and index lifecycle.

The SQL document is authoritative. A Qdrant chunk is derived data and may be deleted and
regenerated. Never treat an index hit as an asserted fact about the building.

SQL storage accepts any non-empty file. The default Docling processor handles common
formats including PDF, text/Markdown, HTML, office documents, and images. Do not assume
that every stored blob is convertible by every configured processor.

## Install and configure

The document CRUD API is part of the base package. Conversion and retrieval require the
optional `knowledge` dependencies. In a BuildingMOTIF checkout, install them with:

```bash
uv sync --extra knowledge
```

For a downstream project, add the extra to the package source/version specified in
`setup.md`, for example:

```bash
uv add "buildingmotif[knowledge] @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"
```

Configure knowledge on the `BuildingMOTIF` instance. Do not construct a separate nested
service for the ordinary local case:

```python
from buildingmotif import BuildingMOTIF

with BuildingMOTIF(
    "sqlite:///buildingmotif.db",
    knowledge_index_path=".buildingmotif-knowledge",
) as bm:
    document = bm.knowledge.add_document(
        "ahu-schedule.pdf",
        name="AHU schedule",
        description="Controls submittal",
    )
    count = bm.knowledge.index_document(document.id)
    hits = bm.knowledge.retrieve(
        "AHU-1 supply fan", document_ids=[document.id], limit=5
    )
```

The `BuildingMOTIF` context closes the Qdrant client along with its SQL, graph-store, and
ontology resources. Accessing `bm.knowledge` without configuring it raises
`KnowledgeIndexNotConfigured`; use `bm.has_knowledge` when configuration is optional.

The first indexing operation may download the Docling tokenizer and FastEmbed models. Use
`HF_HOME` and `FASTEMBED_CACHE_PATH` for persistent model caches. A local Qdrant path must
not be shared by multiple processes.

## Add documents and manage their lifecycle

For a file on disk, use `add_document`. It accepts a string or `Path`; relative paths
resolve from the Python process's current working directory, and absolute paths work
unchanged. It reads the bytes and infers the MIME type from the filename:

```python
from pathlib import Path

source_path = Path("documents") / "ahu-schedule.pdf"
document = bm.knowledge.add_document(
    source_path,
    name="AHU schedule",                 # defaults to the filename
    description="Controls submittal",
    mime_type="application/pdf",         # optional inference override
)
```

For content already in memory, provide the filename and MIME type explicitly:

```python
document = bm.knowledge.create_document(
    name="Sequence of operations",
    description="Text export",
    file_name="sequence.txt",
    mime_type="text/plain",
    content=b"Enable AHU-1 when occupied.",
)
```

Storage and indexing are deliberately separate. After adding a document, call
`bm.knowledge.index_document(document.id)`. The other Python lifecycle methods are:

```python
documents = bm.knowledge.list_documents()  # metadata; content remains deferred
metadata = bm.knowledge.get_document(document.id)
content = bm.knowledge.get_document(document.id, include_content=True).content

bm.knowledge.update_document(document.id, description="Reviewed submittal")
bm.knowledge.index_document(document.id)  # update removed the old chunks
bm.knowledge.delete_document(document.id)  # deletes source and indexed chunks
```

The same operations are available over HTTP. Upload a document with multipart form data:

```bash
curl -F 'name=AHU schedule' \
     -F 'description=Controls submittal' \
     -F 'file=@./documents/ahu-schedule.pdf;type=application/pdf' \
     http://localhost:5000/knowledge/documents
```

Or upload the same relative path with a Python HTTP client:

```python
from pathlib import Path

import requests

path = Path("documents/ahu-schedule.pdf")
with path.open("rb") as stream:
    response = requests.post(
        "http://localhost:5000/knowledge/documents",
        data={"name": "AHU schedule", "description": "Controls submittal"},
        files={"file": (path.name, stream, "application/pdf")},
        timeout=60,
    )
response.raise_for_status()
document_id = response.json()["id"]
```

The HTTP upload limit is 100 MiB by default and is configurable with
`KNOWLEDGE_MAX_DOCUMENT_BYTES`.

Available document operations:

| Operation | Endpoint |
|---|---|
| List metadata | `GET /knowledge/documents` |
| Upload | `POST /knowledge/documents` (multipart form) |
| Read metadata | `GET /knowledge/documents/{id}` |
| Download original | `GET /knowledge/documents/{id}/content` |
| Edit metadata or replace file | `PATCH /knowledge/documents/{id}` |
| Delete source and indexed chunks | `DELETE /knowledge/documents/{id}` |
| Build/rebuild index | `POST /knowledge/documents/{id}/index` |

Indexing is synchronous. Editing either metadata or content invalidates and removes the
old chunks; explicitly re-index afterward. Re-indexing replaces every old chunk for that
document. Deleting a document also deletes its indexed chunks.

## Retrieve evidence

Through Python:

```python
all_hits = bm.knowledge.retrieve(
    "Does AHU-1 have a supply fan?",
    limit=5,
)

source_limited_hits = bm.knowledge.retrieve(
    "Does AHU-1 have a supply fan?",
    limit=5,
    document_ids=[1, 4],
)

for hit in all_hits:
    print(hit.score, hit.text)
    print(hit.knowledge_document_id, hit.file_name, hit.chunk_ordinal)
    print(hit.source_sha256, hit.provenance)
```

Through HTTP:

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"query":"Does AHU-1 have a supply fan?","limit":5,"document_ids":[1,4]}' \
     http://localhost:5000/knowledge/search
```

When `document_ids` is omitted (or `None` in Python), retrieval searches all chunks in
the configured index and returns the highest-ranked `limit` chunks across that corpus. It
does **not** search documents that exist only in SQL and have not been successfully
indexed. Supply `document_ids` only when the query should be restricted to selected
sources; the source filter is applied before ranking.

Each `EvidenceChunk` contains:

- retrieval score;
- SQL `knowledge_document_id`;
- source SHA-256, name, description, filename, and MIME type;
- chunk ordinal and retrieved chunk text;
- Docling provenance such as headings, captions, document items, page/layout information,
  and source origin when available.

The SHA-256 identifies the exact source version. Cite the document and the most precise
available Docling location, not merely the retrieval score or chunk ordinal. The score is
ranking information, not confidence that a claim is true.

## Use it in the repair loop

Knowledge retrieval belongs at the evidence step, never at the apply step:

1. Validate the model and choose one failure/witness (`validation.md`, `repair.md`).
2. Form a narrow query from the real-world equipment label and missing concept. Search
   `"VAV-1 zone temperature sensor"`, not its model URI or only a Brick class name.
3. Retrieve several candidates. If you know which uploaded sources govern the equipment,
   restrict with `document_ids`.
4. Read the returned text, headings, adjacent context, units, I/O type, and page/layout
   provenance. If context is insufficient, download the original source and inspect it.
5. Classify the evidence as direct, ambiguous, contradictory, or absent according to
   `evidence.md`.
6. Present the proposed mapping and citation to the user. Apply only after the evidence
   supports the real building fact and the user confirms ambiguous judgment calls.
7. Re-validate immediately after applying one repair.

Never:

- automatically apply the highest-scored result;
- equate semantic similarity with physical truth;
- mint equipment or point identifiers that the source does not provide;
- hide contradictory chunks or an absence of evidence;
- cite Qdrant, an embedding score, or a generated summary as the source.

## Custom index backends

For a remote Qdrant server or another backend, configure a service on the
`BuildingMOTIF` owner:

```python
from qdrant_client import QdrantClient

from buildingmotif import BuildingMOTIF
from buildingmotif.knowledge import (
    DoclingDocumentProcessor,
    KnowledgeService,
    QdrantKnowledgeIndex,
)

with BuildingMOTIF("postgresql://...") as bm:
    index = QdrantKnowledgeIndex(
        client=QdrantClient(url="http://qdrant:6333")
    )
    bm.configure_knowledge(
        KnowledgeService(bm, DoclingDocumentProcessor(), index)
    )
    hits = bm.knowledge.retrieve("VAV-1 zone temperature sensor")
```

An alternative index implements the `KnowledgeIndex` protocol:
`replace_document`, `remove_document`, and `retrieve`. An alternative converter/chunker
implements `DocumentProcessor.process`. Keep these adapters behind `bm.knowledge` so the
validation and repair workflows do not depend directly on Qdrant or Docling.
