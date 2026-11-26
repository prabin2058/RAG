"""Shared test fixtures: isolated temp SQLite DB, dependency override, auth helpers."""

import os
import tempfile

# Tests never call a real LLM: use the provider that needs no API key, so the
# suite runs without secrets (real env vars override backend/.env).
os.environ["LLM_PROVIDER"] = "ollama"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.user import User

TEST_DB_FD, TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(TEST_DB_FD)

test_engine = create_engine(
    f"sqlite:///{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    os.remove(TEST_DB_PATH)


@pytest.fixture()
def db():
    """Function-scoped session with a clean DB between tests."""
    session = TestSession()
    try:
        session.query(Message).delete()
        session.query(Conversation).delete()
        session.query(Document).delete()
        session.query(User).delete()
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def user_a(client):
    """Register + return (email, password, access_token, user)."""
    payload = {"email": "alice@example.com", "password": "supersecret123"}
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    return {
        "email": payload["email"],
        "password": payload["password"],
        "token": data["access_token"],
        "user": data["user"],
    }


@pytest.fixture()
def user_b(client):
    payload = {"email": "bob@example.com", "password": "supersecret456"}
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    return {
        "email": payload["email"],
        "password": payload["password"],
        "token": data["access_token"],
        "user": data["user"],
    }


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_pdf_bytes(text: str = "Hello RAG world. This is a test document.") -> bytes:
    """Minimal valid PDF built by hand (no external deps in tests)."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b""
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        entry = f"{i} 0 obj\n{obj}\nendobj\n".encode()
        offsets.append(offsets[-1] + len(entry))
        body += entry
    xref_pos = 9 + len(body)
    xref = "xref\n0 6\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n"
    trailer = f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    return b"%PDF-1.4\n" + body + xref.encode() + trailer.encode()
