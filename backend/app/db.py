"""SQLite persistence for chats, messages and document metadata.

A new connection is opened per operation (cheap for SQLite) so this module is
safe to use from FastAPI's threadpool and from background tasks.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    summary_upto INTEGER NOT NULL DEFAULT 0,
    use_documents INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    sources TEXT NOT NULL DEFAULT '[]',
    context_info TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    pages INTEGER NOT NULL DEFAULT 0,
    chunks INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_chat ON documents(chat_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- chats ----------
    def create_chat(self, title: str = "New chat") -> dict[str, Any]:
        cid, ts = uuid.uuid4().hex, now_iso()
        with self.connect() as c:
            c.execute("INSERT INTO chats (id,title,created_at,updated_at) VALUES (?,?,?,?)", (cid, title, ts, ts))
        return self.get_chat(cid)  # type: ignore[return-value]

    def list_chats(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM chats ORDER BY updated_at DESC").fetchall()
        return [_chat(r) for r in rows]

    def get_chat(self, chat_id: str) -> dict[str, Any] | None:
        with self.connect() as c:
            r = c.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return _chat(r) if r else None

    def update_chat(self, chat_id: str, **fields: Any) -> None:
        allowed = {"title", "summary", "summary_upto", "use_documents"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.connect() as c:
            c.execute(f"UPDATE chats SET {cols} WHERE id=?", (*fields.values(), chat_id))

    def delete_chat(self, chat_id: str) -> bool:
        with self.connect() as c:
            cur = c.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return cur.rowcount > 0

    # ---------- messages ----------
    def add_message(self, chat_id: str, role: str, content: str, status: str = "ok",
                    sources: list | None = None, context_info: dict | None = None) -> dict[str, Any]:
        with self.connect() as c:
            cur = c.execute(
                "INSERT INTO messages (chat_id,role,content,status,sources,context_info,created_at) VALUES (?,?,?,?,?,?,?)",
                (chat_id, role, content, status, json.dumps(sources or []), json.dumps(context_info or {}), now_iso()),
            )
            c.execute("UPDATE chats SET updated_at=? WHERE id=?", (now_iso(), chat_id))
            r = c.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()
        return _message(r)

    def list_messages(self, chat_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
        return [_message(r) for r in rows]

    def delete_messages_after(self, chat_id: str, message_id: int) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM messages WHERE chat_id=? AND id>?", (chat_id, message_id))

    # ---------- documents ----------
    def add_document(self, chat_id: str, filename: str, kind: str, size_bytes: int) -> dict[str, Any]:
        did = uuid.uuid4().hex
        with self.connect() as c:
            c.execute(
                "INSERT INTO documents (id,chat_id,filename,kind,size_bytes,status,created_at) VALUES (?,?,?,?,?,?,?)",
                (did, chat_id, filename, kind, size_bytes, "processing", now_iso()),
            )
        return self.get_document(chat_id, did)  # type: ignore[return-value]

    def get_document(self, chat_id: str, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as c:
            r = c.execute("SELECT * FROM documents WHERE id=? AND chat_id=?", (doc_id, chat_id)).fetchone()
        return dict(r) if r else None

    def list_documents(self, chat_id: str) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM documents WHERE chat_id=? ORDER BY created_at", (chat_id,)).fetchall()
        return [dict(r) for r in rows]

    def update_document(self, doc_id: str, **fields: Any) -> None:
        allowed = {"status", "error", "pages", "chunks"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.connect() as c:
            c.execute(f"UPDATE documents SET {cols} WHERE id=?", (*fields.values(), doc_id))

    def delete_document(self, chat_id: str, doc_id: str) -> bool:
        with self.connect() as c:
            cur = c.execute("DELETE FROM documents WHERE id=? AND chat_id=?", (doc_id, chat_id))
        return cur.rowcount > 0


def _chat(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["use_documents"] = bool(d["use_documents"])
    return d


def _message(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["sources"] = json.loads(d["sources"])
    d["context_info"] = json.loads(d["context_info"])
    return d
