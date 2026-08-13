from hashlib import sha256
from io import BytesIO

from buildingmotif.knowledge import EvidenceChunk


def _upload(client, content=b"air handler schedule", **fields):
    data = {
        "file": (BytesIO(content), "schedule.txt", "text/plain"),
        "name": "AHU schedule",
        "description": "Controls evidence",
    }
    data.update(fields)
    return client.post("/knowledge/documents", data=data)


def test_document_crud_and_download(client):
    content = b"air handler schedule"
    created = _upload(client, content)

    assert created.status_code == 201
    document_id = created.json["id"]
    assert created.json == {
        "id": document_id,
        "name": "AHU schedule",
        "description": "Controls evidence",
        "file_name": "schedule.txt",
        "mime_type": "text/plain",
        "size": len(content),
        "sha256": sha256(content).hexdigest(),
        "created_at": created.json["created_at"],
        "updated_at": created.json["updated_at"],
    }

    listed = client.get("/knowledge/documents")
    assert listed.status_code == 200
    assert listed.json == [created.json]

    downloaded = client.get(f"/knowledge/documents/{document_id}/content")
    assert downloaded.status_code == 200
    assert downloaded.data == content
    assert downloaded.mimetype == "text/plain"
    assert "schedule.txt" in downloaded.headers["Content-Disposition"]

    updated = client.patch(
        f"/knowledge/documents/{document_id}",
        json={"name": "Updated AHU schedule", "description": "Verified evidence"},
    )
    assert updated.status_code == 200
    assert updated.json["name"] == "Updated AHU schedule"
    assert updated.json["description"] == "Verified evidence"
    assert updated.json["sha256"] == created.json["sha256"]

    deleted = client.delete(f"/knowledge/documents/{document_id}")
    assert deleted.status_code == 204
    assert client.get(f"/knowledge/documents/{document_id}").status_code == 404


def test_replace_document_content(client):
    document_id = _upload(client).json["id"]
    replacement = b"%PDF replacement"

    result = client.patch(
        f"/knowledge/documents/{document_id}",
        data={"file": (BytesIO(replacement), "submittal.pdf", "application/pdf")},
    )

    assert result.status_code == 200
    assert result.json["file_name"] == "submittal.pdf"
    assert result.json["mime_type"] == "application/pdf"
    assert result.json["size"] == len(replacement)
    assert result.json["sha256"] == sha256(replacement).hexdigest()
    assert client.get(f"/knowledge/documents/{document_id}/content").data == replacement


def test_upload_validation_and_missing_documents(client, app):
    assert client.post("/knowledge/documents", json={}).status_code == 400
    assert (
        client.post("/knowledge/documents", data={"name": "missing"}).status_code == 400
    )
    assert _upload(client, content=b"").status_code == 400

    app.config["KNOWLEDGE_MAX_DOCUMENT_BYTES"] = 3
    assert _upload(client, content=b"four").status_code == 413

    assert client.get("/knowledge/documents/999").status_code == 404
    assert client.get("/knowledge/documents/999/content").status_code == 404
    assert (
        client.patch("/knowledge/documents/999", json={"name": "x"}).status_code == 404
    )
    assert client.delete("/knowledge/documents/999").status_code == 404


def test_update_validation(client):
    document_id = _upload(client).json["id"]
    url = f"/knowledge/documents/{document_id}"

    assert client.patch(url, json={}).status_code == 400
    assert client.patch(url, json={"name": "  "}).status_code == 400
    assert client.patch(url, json={"description": 3}).status_code == 400
    assert client.patch(url, json={"unexpected": True}).status_code == 400


class FakeKnowledgeService:
    def __init__(self):
        self.indexed = []
        self.removed = []
        self.queries = []
        self.closed = False

    def index_document(self, document_id):
        self.indexed.append(document_id)
        return 3

    def remove_document(self, document_id):
        self.removed.append(document_id)

    def retrieve(self, query, *, limit=10, document_ids=None):
        self.queries.append((query, limit, document_ids))
        return [
            EvidenceChunk(
                score=0.75,
                knowledge_document_id=1,
                source_sha256="abc",
                source_name="Schedule",
                source_description="Controls evidence",
                file_name="schedule.pdf",
                mime_type="application/pdf",
                chunk_ordinal=2,
                text="AHU-1 has a supply fan",
                provenance={"page": 4},
            )
        ]

    def close(self):
        self.closed = True


def test_index_and_search_api(client, app):
    service = FakeKnowledgeService()
    app.building_motif.configure_knowledge(service)
    document_id = _upload(client).json["id"]

    indexed = client.post(f"/knowledge/documents/{document_id}/index")
    assert indexed.status_code == 200
    assert indexed.json == {"document_id": document_id, "chunk_count": 3}

    searched = client.post(
        "/knowledge/search",
        json={"query": "supply fan", "limit": 5, "document_ids": [document_id]},
    )
    assert searched.status_code == 200
    assert searched.json[0]["knowledge_document_id"] == 1
    assert searched.json[0]["provenance"] == {"page": 4}
    assert service.queries == [("supply fan", 5, [document_id])]

    client.patch(f"/knowledge/documents/{document_id}", json={"description": "changed"})
    client.delete(f"/knowledge/documents/{document_id}")
    assert service.removed == [document_id, document_id]


def test_index_api_requires_configuration(client):
    assert client.post("/knowledge/documents/1/index").status_code == 503
    assert client.post("/knowledge/search", json={"query": "fan"}).status_code == 503


def test_search_validation(client, app):
    app.building_motif.configure_knowledge(FakeKnowledgeService())

    assert client.post("/knowledge/search").status_code == 400
    assert client.post("/knowledge/search", json={}).status_code == 400
    assert client.post("/knowledge/search", json={"query": " "}).status_code == 400
    assert (
        client.post("/knowledge/search", json={"query": "fan", "limit": 0}).status_code
        == 400
    )
    assert (
        client.post(
            "/knowledge/search", json={"query": "fan", "document_ids": [True]}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/knowledge/search", json={"query": "fan", "unexpected": True}
        ).status_code
        == 400
    )
