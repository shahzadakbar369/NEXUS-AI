import json

from app.services.groq_client import LLMError
from tests.test_retrieval import make_pdf


def events(resp):
    out = []
    for block in resp.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["groq"]["model_available"] is True


def test_chat_crud(client):
    cid = client.post("/api/chats", json={}).json()["id"]
    assert any(c["id"] == cid for c in client.get("/api/chats").json())
    assert client.patch(f"/api/chats/{cid}", json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert client.patch(f"/api/chats/{cid}", json={"title": "  "}).status_code == 422
    other = client.post("/api/chats", json={}).json()["id"]
    assert client.delete(f"/api/chats/{cid}").status_code == 204
    assert client.get(f"/api/chats/{cid}").status_code == 404
    assert client.get(f"/api/chats/{other}").status_code == 200  # unrelated chat untouched


def test_send_message_streams_and_persists(client, fake_llm):
    cid = client.post("/api/chats", json={}).json()["id"]
    r = client.post(f"/api/chats/{cid}/messages", json={"content": "Hi there, my name is Sam"})
    ev = events(r)
    assert [e for e, _ in ev][0] == "user_message"
    assert "".join(d["t"] for e, d in ev if e == "token") == "Hello from fake"
    detail = client.get(f"/api/chats/{cid}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["title"] == "Hi there, my name is Sam"

    # follow-up includes history; a new chat does not
    client.post(f"/api/chats/{cid}/messages", json={"content": "What is my name?"})
    assert any("Sam" in m["content"] for m in fake_llm.calls[-1][:-1])
    cid2 = client.post("/api/chats", json={}).json()["id"]
    client.post(f"/api/chats/{cid2}/messages", json={"content": "What is my name?"})
    assert not any("Sam" in m["content"] for m in fake_llm.calls[-1])


def test_llm_failure_keeps_user_message_and_reports_error(client, fake_llm):
    fake_llm.fail = LLMError("Groq rejected the API key.", 401, "invalid_api_key")
    cid = client.post("/api/chats", json={}).json()["id"]
    ev = events(client.post(f"/api/chats/{cid}/messages", json={"content": "hello"}))
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "invalid_api_key"
    msgs = client.get(f"/api/chats/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user"]  # no fake assistant reply

    fake_llm.fail = None
    ev = events(client.post(f"/api/chats/{cid}/messages", json={"regenerate": True}))
    assert ev[-1][0] == "done"
    assert len(client.get(f"/api/chats/{cid}").json()["messages"]) == 2


def test_empty_message_rejected(client):
    cid = client.post("/api/chats", json={}).json()["id"]
    assert client.post(f"/api/chats/{cid}/messages", json={"content": "   "}).status_code == 422


def test_document_upload_rag_and_delete(client, tmp_path, fake_llm):
    cid = client.post("/api/chats", json={}).json()["id"]
    pdf = tmp_path / "france.pdf"
    make_pdf(pdf, ["Paris is the capital city of France.", "The Eiffel Tower was completed in 1889."])
    r = client.post(f"/api/chats/{cid}/documents", files={"file": ("france.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 202
    docs = client.get(f"/api/chats/{cid}/documents").json()  # background task ran during the request
    assert docs[0]["status"] == "ready" and docs[0]["pages"] == 2

    ev = events(client.post(f"/api/chats/{cid}/messages", json={"content": "When was the Eiffel Tower completed?"}))
    ctx = next(d for e, d in ev if e == "context")
    assert ctx["sources"][0]["filename"] == "france.pdf" and ctx["sources"][0]["page"] == 2
    assert '<source id="1" filename="france.pdf" page="2">' in fake_llm.calls[-1][-2]["content"]

    # another chat cannot see this document
    cid2 = client.post("/api/chats", json={}).json()["id"]
    ev = events(client.post(f"/api/chats/{cid2}/messages", json={"content": "When was the Eiffel Tower completed?"}))
    assert next(d for e, d in ev if e == "context")["sources"] == []

    # toggling back to general chat disables retrieval
    client.patch(f"/api/chats/{cid}", json={"use_documents": False})
    ev = events(client.post(f"/api/chats/{cid}/messages", json={"content": "Eiffel Tower completed?"}))
    assert next(d for e, d in ev if e == "context")["sources"] == []

    assert client.delete(f"/api/chats/{cid}/documents/{docs[0]['id']}").status_code == 204
    assert client.get(f"/api/chats/{cid}/documents").json() == []


def test_invalid_uploads(client, tmp_path):
    cid = client.post("/api/chats", json={}).json()["id"]
    url = f"/api/chats/{cid}/documents"
    assert client.post(url, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 415
    assert client.post(url, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post(url, files={"file": ("big.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024), "application/pdf")}).status_code == 413
    assert client.post(url, files={"file": ("e.pdf", b"", "application/pdf")}).status_code == 422

    empty = tmp_path / "empty.pdf"
    make_pdf(empty, [""])
    assert client.post(url, files={"file": ("empty.pdf", empty.read_bytes(), "application/pdf")}).status_code == 202
    doc = client.get(url).json()[-1]
    assert doc["status"] == "failed" and "scanned" in doc["error"]
