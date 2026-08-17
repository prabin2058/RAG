"""Document endpoint tests: auth required, ownership isolation, file validation."""

from tests.conftest import auth_headers, make_pdf_bytes


def _upload(client, token, filename="doc.pdf", content=None):
    files = {"file": (filename, content or make_pdf_bytes(), "application/pdf")}
    return client.post("/api/v1/upload", files=files, headers=auth_headers(token))


def test_upload_without_token_401(client):
    files = {"file": ("doc.pdf", make_pdf_bytes(), "application/pdf")}
    res = client.post("/api/v1/upload", files=files)
    assert res.status_code == 401


def test_upload_non_pdf_400(client, user_a):
    files = {"file": ("notes.txt", b"not a pdf", "text/plain")}
    res = client.post("/api/v1/upload", files=files, headers=auth_headers(user_a["token"]))
    assert res.status_code == 400


def test_upload_starts_processing(client, user_a):
    res = _upload(client, user_a["token"])
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "processing"
    assert body["doc_id"]


def test_list_requires_auth(client):
    assert client.get("/api/v1/documents").status_code == 401


def test_status_of_own_document(client, user_a):
    doc_id = _upload(client, user_a["token"]).json()["doc_id"]
    res = client.get(f"/api/v1/documents/{doc_id}/status", headers=auth_headers(user_a["token"]))
    assert res.status_code == 200
    assert res.json()["status"] in {"processing", "ready", "failed"}


def test_foreign_document_invisible(client, user_a, user_b):
    doc_id = _upload(client, user_a["token"]).json()["doc_id"]

    # B cannot see, status, or delete A's document.
    assert client.get(
        f"/api/v1/documents/{doc_id}/status", headers=auth_headers(user_b["token"])
    ).status_code == 404
    assert client.delete(
        f"/api/v1/documents/{doc_id}", headers=auth_headers(user_b["token"])
    ).status_code == 404

    # B's list does not contain it.
    ids = [d["id"] for d in client.get(
        "/api/v1/documents", headers=auth_headers(user_b["token"])
    ).json()]
    assert doc_id not in ids


def test_delete_own_document(client, user_a):
    doc_id = _upload(client, user_a["token"]).json()["doc_id"]
    res = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers(user_a["token"]))
    assert res.status_code == 204
    assert client.get(
        f"/api/v1/documents/{doc_id}/status", headers=auth_headers(user_a["token"])
    ).status_code == 404


def test_query_without_token_401(client):
    res = client.post(
        "/api/v1/query", json={"doc_id": "x", "question": "hi"}
    )
    assert res.status_code == 401
