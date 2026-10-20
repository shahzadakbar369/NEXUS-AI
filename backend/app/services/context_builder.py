"""Builds the bounded prompt sent to the LLM for every request.

Layout of the final message list:
    1. system  - instructions (+ rolling summary of older turns, if any)
    2. ...     - most recent conversation turns that fit the history budget
    3. system  - retrieved document passages with explicit source boundaries
    4. user    - the current question (never truncated or summarized)

Budgets (estimated tokens, all configurable in Settings):
    input_budget = model_context_window - max_response_tokens - safety margin
    passages  <= rag_token_budget
    summary + history <= history_token_budget
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.services.tokens import estimate_message_tokens, estimate_tokens, truncate_to_tokens

SYSTEM_PROMPT = (
    "You are NEXUS AI, a helpful, accurate and concise assistant. "
    "Use Markdown for formatting and fenced code blocks with a language tag for code. "
    "If you don't know something, say so instead of guessing."
)

RAG_INSTRUCTIONS = (
    "The user has uploaded documents. Relevant passages are provided below between "
    "<source> tags. When your answer uses a passage, cite it inline as [filename, p. N] "
    "using exactly the filename and page given in the tag. Only cite passages that "
    "actually support the statement. Never invent sources or page numbers. If the "
    "passages do not contain enough information to answer, say clearly that the "
    "uploaded documents do not cover it (you may then answer from general knowledge, "
    "explicitly labelled as such and without citations)."
)

NO_PASSAGES_NOTE = (
    "Document mode is on, but no passage in the uploaded documents was relevant enough "
    "to this question. Tell the user the documents do not appear to cover it, and do "
    "not cite the documents."
)


class ContextTooLargeError(Exception):
    pass


@dataclass
class BuiltContext:
    messages: list[dict]
    used_passages: list[dict]
    info: dict = field(default_factory=dict)


def input_budget(settings: Settings) -> int:
    safety = int(settings.model_context_window * 0.05)
    return settings.model_context_window - settings.max_response_tokens - safety


def format_passage(p: dict) -> str:
    return f'<source id="{p["n"]}" filename="{p["filename"]}" page="{p["page"]}">\n{p["text"]}\n</source>'


def build_context(
    settings: Settings,
    question: str,
    history: list[dict],
    summary: str = "",
    passages: list[dict] | None = None,
    doc_mode_active: bool = False,
) -> BuiltContext:
    """history: prior ok messages (oldest first), excluding the current question."""
    budget = input_budget(settings)
    user_msg = {"role": "user", "content": question}
    user_tokens = estimate_message_tokens(user_msg)

    system_text = SYSTEM_PROMPT
    summary_text = ""
    if summary:
        summary_text = truncate_to_tokens(summary, settings.summary_max_tokens)
        system_text += f"\n\nSummary of earlier parts of this conversation:\n{summary_text}"
    system_tokens = estimate_tokens(system_text) + 4

    remaining = budget - system_tokens - user_tokens
    if remaining < 0:
        raise ContextTooLargeError(
            f"Your message is too long for the configured context window "
            f"(~{user_tokens} estimated tokens, limit ~{budget - system_tokens}). Please shorten it.")

    # --- document passages (in relevance order) ---
    used: list[dict] = []
    rag_msg: dict | None = None
    if doc_mode_active:
        header = RAG_INSTRUCTIONS if passages else NO_PASSAGES_NOTE
        rag_budget = min(settings.rag_token_budget, remaining)
        spent = estimate_tokens(header) + 4
        blocks: list[str] = []
        for p in passages or []:
            block = format_passage({**p, "n": len(used) + 1})
            cost = estimate_tokens(block)
            if spent + cost > rag_budget:
                continue
            blocks.append(block)
            used.append({**p, "n": len(used) + 1})
            spent += cost
        if spent <= remaining:
            header = RAG_INSTRUCTIONS if used else NO_PASSAGES_NOTE
            rag_msg = {"role": "system", "content": header + ("\n\n" + "\n\n".join(blocks) if blocks else "")}
            remaining -= estimate_message_tokens(rag_msg)
        else:
            used = []

    # --- recent history, newest first, within history budget ---
    hist_budget = min(settings.history_token_budget - estimate_tokens(summary_text), remaining)
    kept: list[dict] = []
    spent = 0
    for m in reversed(history):
        msg = {"role": m["role"], "content": m["content"]}
        cost = estimate_message_tokens(msg)
        if spent + cost > hist_budget:
            break
        kept.append(msg)
        spent += cost
    kept.reverse()
    # A conversation should not start with a dangling assistant reply.
    while kept and kept[0]["role"] == "assistant":
        spent -= estimate_message_tokens(kept.pop(0))

    messages = [{"role": "system", "content": system_text}, *kept]
    if rag_msg:
        messages.append(rag_msg)
    messages.append(user_msg)

    prompt_tokens = sum(estimate_message_tokens(m) for m in messages)
    info = {
        "estimated_prompt_tokens": prompt_tokens,
        "max_response_tokens": settings.max_response_tokens,
        "context_window": settings.model_context_window,
        "history_messages_included": len(kept),
        "history_messages_dropped": len(history) - len(kept),
        "has_summary": bool(summary_text),
        "document_passages": len(used),
        "estimate": True,
    }
    return BuiltContext(messages=messages, used_passages=used, info=info)


def needs_summary(settings: Settings, history: list[dict]) -> bool:
    if len(history) <= settings.recent_messages_to_keep:
        return False
    total = sum(estimate_message_tokens(m) for m in history)
    return total > settings.history_token_budget


def summary_prompt(previous_summary: str, older: list[dict], max_input_tokens: int) -> list[dict]:
    lines = []
    for m in older:
        lines.append(f"{m['role'].upper()}: {m['content']}")
    transcript = truncate_to_tokens("\n\n".join(lines), max_input_tokens)
    content = (
        (f"Existing summary:\n{previous_summary}\n\n" if previous_summary else "")
        + f"New conversation turns:\n{transcript}\n\n"
        "Write an updated, concise summary (max ~200 words) of the conversation so far. "
        "Keep key facts, user preferences, names, numbers, decisions and open questions."
    )
    return [
        {"role": "system", "content": "You summarize conversations faithfully and concisely."},
        {"role": "user", "content": content},
    ]
