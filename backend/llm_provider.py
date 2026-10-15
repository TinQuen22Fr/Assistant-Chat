import base64
import os
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path
from typing import AsyncIterator

from attachments import Attachment, Turn, turn_text

MODELS = {
    "pro": {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro"},
    "flash": {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash"},
}
TITLE_MODEL = MODELS["flash"]["id"]

SYSTEM_PROMPT = (
    "Tu es Gemini Perso, un assistant IA serviable et précis. "
    "Réponds en français par défaut (sauf si l'utilisateur écrit dans une autre langue), "
    "en utilisant le Markdown lorsque c'est utile. "
    "Les fichiers joints plus tôt dans la conversation restent disponibles comme contexte."
)


def active_provider() -> str:
    return "google-genai" if os.environ.get("GEMINI_API_KEY") else "emergent"


QUOTA_MESSAGE = ("Quota Google dépassé pour ce modèle — essayez Gemini 3 Flash ou activez la facturation "
                 "sur votre projet Google Cloud.")


def is_quota_error(e: Exception) -> bool:
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    text = f"{type(e).__name__} {e}".lower()
    return code == 429 or any(k in text for k in ("429", "resource_exhausted", "quota", "ratelimit", "rate limit"))


def model_id_for(key: str) -> str | None:
    return MODELS[key]["id"] if key in MODELS else None


# ---------- google-genai (self-hosted) ----------

def _google_contents(turns: list[Turn]):
    from google.genai import types

    contents = []
    for t in turns:
        parts = [
            types.Part.from_bytes(data=a.data, mime_type=a.mime)
            for a in t.attachments
            if a.kind in ("image", "pdf")
        ]
        parts.append(types.Part.from_text(text=turn_text(t)))
        contents.append(types.Content(role=t.role, parts=parts))
    return contents


@lru_cache(maxsize=1)
def _google_client():
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


async def _stream_google(model_id: str, turns: list[Turn], system: str) -> AsyncIterator[str]:
    from google.genai import types

    stream = await _google_client().aio.models.generate_content_stream(
        model=model_id,
        contents=_google_contents(turns),
        config=types.GenerateContentConfig(system_instruction=system),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


# ---------- Emergent universal key (preview) ----------

def _data_url(a: Attachment) -> str:
    return f"data:{a.mime};base64,{base64.b64encode(a.data).decode()}"


def _emergent_history(system: str, turns: list[Turn]) -> list[dict]:
    messages = [{"role": "system", "content": system}]
    for t in turns:
        if t.role == "model":
            messages.append({"role": "assistant", "content": t.text})
            continue
        content = [{"type": "text", "text": turn_text(t)}]
        for a in t.attachments:
            if a.kind == "image":
                content.append({"type": "image_url", "image_url": {"url": _data_url(a)}})
            elif a.kind == "pdf":
                content.append({"type": "file", "file": {"file_data": _data_url(a)}})
        messages.append({"role": "user", "content": content})
    return messages


async def _stream_emergent(model_id: str, turns: list[Turn], system: str) -> AsyncIterator[str]:
    from emergentintegrations.llm.chat import (
        FileContentWithMimeType, ImageContent, LlmChat, StreamDone, TextDelta, UserMessage,
    )

    *history, last = turns
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=str(uuid.uuid4()),
        system_message=system,
        initial_messages=_emergent_history(system, history),
    ).with_model("gemini", model_id)

    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, a in enumerate(last.attachments):
            if a.kind == "image":
                files.append(ImageContent(image_base64=base64.b64encode(a.data).decode()))
            elif a.kind == "pdf":
                path = Path(tmp) / f"{i}.pdf"
                path.write_bytes(a.data)
                files.append(FileContentWithMimeType(mime_type=a.mime, file_path=str(path)))
        async for ev in chat.stream_message(UserMessage(text=turn_text(last), file_contents=files)):
            if isinstance(ev, TextDelta) and ev.content:
                yield ev.content
            elif isinstance(ev, StreamDone):
                break


def stream_chat(model_id: str, turns: list[Turn], system: str = SYSTEM_PROMPT) -> AsyncIterator[str]:
    if active_provider() == "google-genai":
        return _stream_google(model_id, turns, system)
    return _stream_emergent(model_id, turns, system)


async def generate_text(model_id: str, prompt: str, system: str) -> str:
    parts = [chunk async for chunk in stream_chat(model_id, [Turn("user", prompt)], system)]
    return "".join(parts).strip()
