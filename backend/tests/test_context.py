# pyrefly: ignore[missing-import]
import pytest

from app.services import context_builder as cb
from app.services.tokens import estimate_tokens


def msgs(n, size=40):
    return [{"id": i + 1, "role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i} " + "x" * size}
            for i in range(n)]


def test_basic_layout(settings):
    built = cb.build_context(settings, "What is 2+2?", msgs(4))
    assert built.messages[0]["role"] == "system"
    assert built.messages[-1] == {"role": "user", "content": "What is 2+2?"}
    assert built.info["history_messages_included"] == 4
    assert built.info["estimate"] is True


def test_history_is_bounded_and_keeps_newest(settings):
    settings.history_token_budget = 200
    history = msgs(50, size=200)
    built = cb.build_context(settings, "q", history)
    hist = built.messages[1:-1]
    assert 0 < len(hist) < 50
    assert hist[-1]["content"] == history[-1]["content"]  # newest kept
    assert hist[0]["role"] == "user"  # never starts with dangling assistant turn
    assert sum(estimate_tokens(m["content"]) for m in hist) <= 200


def test_total_within_input_budget(settings):
    settings.model_context_window = 2000
    settings.max_response_tokens = 500
    built = cb.build_context(settings, "q", msgs(100, 300), passages=[
        {"document_id": "d", "filename": "a.pdf", "page": i, "text": "y" * 2000, "score": 0.9} for i in range(10)
    ], doc_mode_active=True)
    assert built.info["estimated_prompt_tokens"] <= cb.input_budget(settings)


def test_current_question_never_truncated(settings):
    q = "z" * 5000
    settings.history_token_budget = 10
    built = cb.build_context(settings, q, msgs(10))
    assert built.messages[-1]["content"] == q


def test_question_too_large_raises(settings):
    settings.model_context_window = 500
    settings.max_response_tokens = 100
    with pytest.raises(cb.ContextTooLargeError):
        cb.build_context(settings, "z" * 10_000, [])


def test_summary_included_in_system_prompt(settings):
    built = cb.build_context(settings, "q", [], summary="User's name is Ana.")
    assert "User's name is Ana." in built.messages[0]["content"]
    assert built.info["has_summary"]


def test_passages_have_source_boundaries_and_budget(settings):
    settings.rag_token_budget = 400
    passages = [{"document_id": "d", "filename": "f.pdf", "page": p, "text": "w " * 300, "score": 0.8}
                for p in (1, 2, 3)]
    built = cb.build_context(settings, "q", [], passages=passages, doc_mode_active=True)
    rag = built.messages[-2]["content"]
    assert '<source id="1" filename="f.pdf" page="1">' in rag
    assert len(built.used_passages) < 3  # budget enforced


def test_doc_mode_without_passages_warns_not_to_cite(settings):
    built = cb.build_context(settings, "unrelated?", [], passages=[], doc_mode_active=True)
    assert cb.NO_PASSAGES_NOTE in built.messages[-2]["content"]
    assert built.used_passages == []


def test_needs_summary(settings):
    settings.history_token_budget = 100
    assert not cb.needs_summary(settings, msgs(3, 500))  # too few messages to summarize
    assert cb.needs_summary(settings, msgs(20, 200))
