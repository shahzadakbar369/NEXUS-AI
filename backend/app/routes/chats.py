# pyrefly: ignore[missing-import]
from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore[missing-import]
from fastapi.responses import StreamingResponse

from app.deps import Container, get_container
from app.schemas import Chat, ChatCreate, ChatDetail, ChatUpdate, MessageCreate

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _require_chat(c: Container, chat_id: str) -> dict:
    chat = c.db.get_chat(chat_id)
    if not chat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return chat


def _out(chat: dict) -> dict:
    return {**chat, "has_summary": bool(chat.get("summary"))}


@router.post("", response_model=Chat, status_code=status.HTTP_201_CREATED)
def create_chat(body: ChatCreate | None = None, c: Container = Depends(get_container)) -> dict:
    title = (body.title.strip() if body and body.title else "") or "New chat"
    return _out(c.db.create_chat(title))


@router.get("", response_model=list[Chat])
def list_chats(c: Container = Depends(get_container)) -> list[dict]:
    return [_out(ch) for ch in c.db.list_chats()]


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str, c: Container = Depends(get_container)) -> dict:
    chat = _require_chat(c, chat_id)
    return {**_out(chat), "messages": c.db.list_messages(chat_id), "documents": c.db.list_documents(chat_id)}


@router.patch("/{chat_id}", response_model=Chat)
def update_chat(chat_id: str, body: ChatUpdate, c: Container = Depends(get_container)) -> dict:
    _require_chat(c, chat_id)
    fields = body.model_dump(exclude_none=True)
    if "use_documents" in fields:
        fields["use_documents"] = int(fields["use_documents"])
    if fields:
        c.db.update_chat(chat_id, **fields)
    return _out(c.db.get_chat(chat_id))  # type: ignore[arg-type]


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, c: Container = Depends(get_container)) -> None:
    _require_chat(c, chat_id)
    docs = c.db.list_documents(chat_id)
    c.db.delete_chat(chat_id)  # cascades to this chat's messages and document rows only
    for d in docs:
        c.store.delete_document(d["id"])
        for f in c.settings.uploads_dir.glob(f"{d['id']}.*"):
            f.unlink(missing_ok=True)


@router.post("/{chat_id}/messages")
async def send_message(chat_id: str, body: MessageCreate, c: Container = Depends(get_container)) -> StreamingResponse:
    """Streams the reply as Server-Sent Events.

    Events: user_message, context (sources + estimated token usage), token, done, error.
    """
    _require_chat(c, chat_id)
    if not body.regenerate and not body.content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message must not be empty")
    return StreamingResponse(
        c.chat.stream_reply(chat_id, body.content, body.regenerate),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
