# Document indexing and retrieval

BuildingMOTIF can retain source documents in SQL and build a derived retrieval index with
[Docling](https://docling-project.github.io/docling/) and
[Qdrant](https://qdrant.tech/). The SQL blob remains the authoritative source. Indexed
chunks are disposable and can always be regenerated from it.

Install the optional dependencies:

```bash
uv sync --extra knowledge
```

## Local API setup

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

Upload and index a document:

```bash
curl -F 'name=AHU schedule' \
     -F 'description=Controls submittal' \
     -F 'file=@ahu-schedule.pdf' \
     http://localhost:5000/knowledge/documents

curl -X POST http://localhost:5000/knowledge/documents/1/index
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

Use `document_ids` in the JSON body to restrict a query to selected sources. Every result
contains the SQL document ID, source SHA-256, filename, chunk ordinal, and Docling
provenance. A retrieval result is evidence for a user to review; it is not permission to
assert metadata or automatically apply a model repair.

## Python API and custom indexes

The service depends only on BuildingMOTIF's `DocumentProcessor` and `KnowledgeIndex`
protocols. The default local setup is:

```python
from buildingmotif import BuildingMOTIF
with BuildingMOTIF(
    "sqlite:///buildingmotif.db",
    knowledge_index_path=".buildingmotif-knowledge",
) as bm:
    chunk_count = bm.knowledge.index_document(1)
    evidence = bm.knowledge.retrieve("AHU-1 supply fan", limit=5)
```

For a remote Qdrant deployment, construct the adapter explicitly:

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
