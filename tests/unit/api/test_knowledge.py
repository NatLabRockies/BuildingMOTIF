from hashlib import sha256
from io import BytesIO


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
