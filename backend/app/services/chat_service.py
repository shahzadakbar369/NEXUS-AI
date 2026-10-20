"""Orchestrates one chat turn: persist -> summarize -> retrieve -> build context -> stream -> persist."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from app.config import Settings
from app.db import Database
from app.services import context_builder as cb
from app.services.groq_client import GroqClient, LLMError
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)


class ChatBusyError(Exception):
    pass


def make_title(text: str, limit: int = 48) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text or "New chat"
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ChatService:
    def __init__(self, settings: Settings, db: Database, llm: GroqClient, store: VectorStore) -> None:
        self.settings, self.db, self.llm, self.store = settings, db, llm, store
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, chat_id: str) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    async def _maybe_summarize(self, chat: dict, history: list[dict]) -> tuple[str, list[dict]]:
        """If unsummarized history exceeds the budget, fold older turns into the chat's summary."""
        summary = chat["summary"]
        if not cb.needs_summary(self.settings, history):
            return summary, history
        keep = self.settings.recent_messages_to_keep
        older, recent = history[:-keep], history[-keep:]
        prompt = cb.summary_prompt(summary, older, max_input_tokens=cb.input_budget(self.settings) - 600)
        try:
            summary = (await self.llm.complete(prompt, self.settings.summary_max_tokens)).strip()
        except LLMError as exc:
            # Not fatal: the context builder will simply drop the oldest turns instead.
            log.warning("Summarization failed (%s); falling back to truncation", exc.message)
            return chat["summary"], history
        self.db.update_chat(chat["id"], summary=summary, summary_upto=older[-1]["id"])
        log.info("Chat %s: summarized %d older messages", chat["id"], len(older))
        return summary, recent

    async def _retrieve(self, chat: dict, question: str) -> tuple[bool, list[dict]]:
        docs = [d for d in self.db.list_documents(chat["id"]) if d["status"] == "ready"]
        if not chat["use_documents"] or not docs:
            return False, []
        passages = await asyncio.to_thread(
            self.store.search, question, [d["id"] for d in docs],
            self.settings.retrieval_top_k, self.settings.retrieval_min_score)
        return True, passages

    async def stream_reply(self, chat_id: str, content: str | None, regenerate: bool) -> AsyncIterator[str]:
        lock = self._lock(chat_id)
        if lock.locked():
            yield sse("error", {"message": "A reply is already being generated in this chat.", "code": "busy"})
            return
        await lock.acquire()
        try:
            async for event in self._stream_locked(chat_id, content, regenerate):
                yield event
        finally:
            lock.release()

    async def _stream_locked(self, chat_id: str, content: str | None, regenerate: bool) -> AsyncIterator[str]:
        chat = self.db.get_chat(chat_id)
        assert chat is not None
        messages = self.db.list_messages(chat_id)

        if regenerate:
            last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
            if not last_user:
                yield sse("error", {"message": "Nothing to regenerate.", "code": "bad_request"})
                return
            self.db.delete_messages_after(chat_id, last_user["id"])
            user_msg = last_user
        else:
            # Persist the user's message first so it is never lost if the LLM call fails.
            user_msg = self.db.add_message(chat_id, "user", content or "")
            if chat["title"] == "New chat" and not any(m["role"] == "user" for m in messages):
                self.db.update_chat(chat_id, title=make_title(user_msg["content"]))
        yield sse("user_message", user_msg)

        history = [m for m in self.db.list_messages(chat_id)
                   if m["id"] < user_msg["id"] and m["id"] > chat["summary_upto"] and m["status"] == "ok"]
        assistant_text = ""
        try:
            summary, history = await self._maybe_summarize(chat, history)
            try:
                doc_mode, passages = await self._retrieve(chat, user_msg["content"])
            except Exception:  # noqa: BLE001
                log.exception("Retrieval failed")
                yield sse("error", {"message": "Document retrieval failed, so no answer was generated. "
                                               "Try again, or turn off document mode.", "code": "retrieval_error"})
                return
            built = cb.build_context(self.settings, user_msg["content"], history, summary, passages, doc_mode)
            sources = [{k: p[k] for k in ("n", "document_id", "filename", "page", "score", "text")}
                       for p in built.used_passages]
            yield sse("context", {"context_info": built.info, "sources": sources})

            async for token in self.llm.stream(built.messages, self.settings.max_response_tokens):
                assistant_text += token
                yield sse("token", {"t": token})

            saved = self.db.add_message(chat_id, "assistant", assistant_text, "ok", sources, built.info)
            yield sse("done", saved)
        except cb.ContextTooLargeError as exc:
            yield sse("error", {"message": str(exc), "code": "context_too_large"})
        except LLMError as exc:
            if assistant_text:
                self.db.add_message(chat_id, "assistant", assistant_text, "incomplete")
            yield sse("error", {"message": exc.message, "code": exc.code})
        except (asyncio.CancelledError, GeneratorExit):
            # Client pressed Stop / disconnected: keep the partial answer, marked incomplete
            # (incomplete messages are excluded from future LLM context).
            if assistant_text:
                self.db.add_message(chat_id, "assistant", assistant_text, "incomplete")
            raise
