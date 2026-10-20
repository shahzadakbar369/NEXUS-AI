"""Token estimation.

Groq hosts several model families (Llama, Qwen, GPT-OSS, ...) with different
tokenizers, so we use a documented, deliberately conservative approximation:
~3.5 characters per token plus a small per-message overhead. Real usage is
usually a bit lower, so staying under our estimate keeps us under the limit.
All numbers shown in the UI are labelled as estimates.
"""
import math

CHARS_PER_TOKEN = 3.5
MESSAGE_OVERHEAD_TOKENS = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict) -> int:
    return estimate_tokens(message.get("content", "")) + MESSAGE_OVERHEAD_TOKENS


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + " …"
