import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import storage
from attachments import MAX_FILE_BYTES, AttachmentError, Turn, ext_of, load_attachment, parse_upload
from auth import get_current_user
from db import db
from llm_provider import (
    MODELS, QUOTA_MESSAGE, TITLE_MODEL, active_provider, generate_text, is_quota_error, model_id_for, stream_chat,
)
from memory import after_reply, build_system_prompt, summarize_turns

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("gemini-perso.chat")
DEFAULT_TITLE = "Nouvelle discussion"
_background: set = set()


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _spawn(coro) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


# ---------- schemas ----------

class FileOut(BaseModel):
    id: str
    name: str
    mime: str
    kind: str
    size: int
    message_id: str
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    model: Optional[str] = None
    status: str = "complete"
    memory_updated: bool = False
    files: List[FileOut] = []
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    model: str
    imported: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: List[MessageOut]


class ConversationCreate(BaseModel):
    model: str = "flash"


class ConversationPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    model: Optional[str] = None


# ---------- helpers ----------

def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _check_model(key: str) -> str:
    if key not in MODELS:
        raise HTTPException(422, f"Modèle inconnu : « {key} ». Choisissez « pro » ou « flash ».")
    return key


async def own_conversation(cid: str, user: dict) -> dict:
    conv = await db.conversations.find_one({"id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Discussion introuvable.")
    return conv


async def _files_by_message(cid: str, user_id: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    async for f in db.files.find({"conversation_id": cid, "user_id": user_id}, {"_id": 0}).sort("created_at", 1):
        grouped.setdefault(f["message_id"], []).append(f)
    return grouped


def _message_out(m: dict, files: list[dict]) -> MessageOut:
    return MessageOut(**{**m, "files": [FileOut(**f) for f in files]})


async def _build_turns(conv: dict, user_id: str) -> list[Turn]:
    cid, upto = conv["id"], conv.get("rolling_upto")
    files = await _files_by_message(cid, user_id)
    turns: list[Turn] = []
    carry = []  # files of messages already folded into the rolling summary stay as context
    async for m in db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1):
        atts = [load_attachment(f, storage.read(f["path"]) if f["kind"] != "text" else None)
                for f in files.get(m["id"], [])]
        if upto and m["created_at"] <= upto:
            carry.extend(atts)
            continue
        if m["role"] == "model" and not m["content"].strip():
            continue
        if turns and turns[-1].role == m["role"]:
            turns[-1].text = f"{turns[-1].text}\n\n{m['content']}".strip()
            turns[-1].attachments.extend(atts)
            turns[-1].ts = m["created_at"]
        else:
            turns.append(Turn(m["role"], m["content"], atts, ts=m["created_at"]))
    first_user = next((t for t in turns if t.role == "user"), None)
    if carry and first_user:
        first_user.attachments[:0] = carry
    return turns


def history_budget() -> int:
    return int(os.environ.get("HISTORY_CHAR_BUDGET", "60000"))


async def _compact(conv: dict, turns: list[Turn]) -> tuple[list[Turn], str]:
    """Fold older turns into a rolling summary when the history exceeds the budget."""
    rolling = conv.get("rolling_summary") or ""
    budget = history_budget()
    if sum(len(t.text) for t in turns) <= budget or len(turns) < 3:
        return turns, rolling
    split, acc = len(turns) - 1, len(turns[-1].text)
    for i in range(len(turns) - 2, -1, -1):
        acc += len(turns[i].text)
        if acc > budget // 2:
            break
        split = i
    while turns[split].role != "user":
        split += 1
    if split == 0:
        return turns, rolling
    dropped, kept = turns[:split], turns[split:]
    try:
        rolling = await summarize_turns(rolling, dropped)
    except Exception:
        logger.exception("Rolling summary failed")
        return turns, conv.get("rolling_summary") or ""
    await db.conversations.update_one(
        {"id": conv["id"]}, {"$set": {"rolling_summary": rolling, "rolling_upto": dropped[-1].ts}})
    kept[0].attachments[:0] = [a for t in dropped for a in t.attachments]
    logger.info("Conversation %s compacted: %d turns folded into rolling summary", conv["id"], len(dropped))
    return kept, rolling


async def _finalize(mid: str, cid: str, content: str, status: str) -> None:
    await db.messages.update_one({"id": mid}, {"$set": {"content": content, "status": status}})
    await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now()}})


async def _make_title(first_message: str) -> str:
    system = "Tu génères des titres de discussion très courts."
    prompt = (
        "Donne un titre court (6 mots maximum, sans guillemets ni ponctuation finale), "
        "dans la langue du message, pour une discussion commençant par :\n\n" + first_message[:2000]
    )
    try:
        title = (await generate_text(TITLE_MODEL, prompt, system)).splitlines()[0]
        title = title.strip().strip('"«»*#').strip()
    except Exception:
        logger.exception("Title generation failed")
        title = ""
    return (title or first_message.strip() or DEFAULT_TITLE)[:80]


def _stream_reply(conv: dict, user: dict, model_key: str, user_msg: Optional[MessageOut]):
    cid, uid = conv["id"], user["user_id"]
    model_id = model_id_for(model_key)

    async def events():
        turns, rolling = await _compact(conv, await _build_turns(conv, uid))
        query = turns[-1].text if turns else ""
        system = await build_system_prompt(uid, cid, query, rolling)
        mid = str(uuid.uuid4())
        await db.messages.insert_one({
            "id": mid, "conversation_id": cid, "user_id": uid, "role": "model", "content": "",
            "model": model_id, "status": "streaming", "created_at": now(),
        })
        yield sse({
            "type": "meta", "provider": active_provider(), "model": model_id, "assistant_message_id": mid,
            "user_message": user_msg.model_dump(mode="json") if user_msg else None,
        })
        parts: list[str] = []
        finalized = False
        try:
            async for chunk in stream_chat(model_id, turns, system):
                parts.append(chunk)
                yield sse({"type": "delta", "text": chunk})
            await _finalize(mid, cid, "".join(parts), "complete")
            finalized = True
        except Exception as e:
            logger.exception("LLM stream error")
            await _finalize(mid, cid, "".join(parts), "error")
            finalized = True
            if is_quota_error(e):
                yield sse({"type": "error", "code": "quota", "message": QUOTA_MESSAGE})
            else:
                yield sse({"type": "error", "code": "model_error",
                           "message": f"Erreur du modèle ({type(e).__name__}) : {str(e)[:300]}"})
            return
        finally:
            if not finalized:  # client disconnected (stop button)
                _spawn(_finalize(mid, cid, "".join(parts), "stopped"))

        saved = await db.messages.find_one({"id": mid}, {"_id": 0})
        yield sse({"type": "done", "message": _message_out(saved, []).model_dump(mode="json")})

        memory_task = _spawn(after_reply(uid, cid, mid, query, saved["content"]))

        if not conv.get("titled"):
            first = next((t.text for t in turns if t.role == "user" and t.text), "") or DEFAULT_TITLE
            title = await _make_title(first)
            await db.conversations.update_one({"id": cid}, {"$set": {"title": title, "titled": True}})
            yield sse({"type": "title", "title": title})

        try:
            changes = await asyncio.wait_for(asyncio.shield(memory_task), timeout=45)
        except Exception:
            changes = 0
        if changes:
            yield sse({"type": "memory", "message_id": mid, "count": changes})

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- conversations ----------

@router.get("/models")
async def list_models():
    return {"provider": active_provider(), "models": [{"key": k, **v} for k, v in MODELS.items()],
            "max_file_bytes": MAX_FILE_BYTES}


@router.get("/conversations", response_model=List[ConversationOut])
async def list_conversations(q: str = "", user: dict = Depends(get_current_user)):
    query: dict = {"user_id": user["user_id"]}
    if q.strip():
        pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
        hits = await db.messages.distinct("conversation_id", {"user_id": user["user_id"], "content": pattern})
        query["$or"] = [{"title": pattern}, {"id": {"$in": hits}}]
    docs = await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return [ConversationOut(**d) for d in docs]


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(body: ConversationCreate, user: dict = Depends(get_current_user)):
    ts = now()
    doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "title": DEFAULT_TITLE, "titled": False,
           "model": _check_model(body.model), "created_at": ts, "updated_at": ts}
    await db.conversations.insert_one(dict(doc))
    return ConversationOut(**doc)


@router.get("/conversations/{cid}", response_model=ConversationDetail)
async def get_conversation(cid: str, user: dict = Depends(get_current_user)):
    conv = await own_conversation(cid, user)
    files = await _files_by_message(cid, user["user_id"])
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    return ConversationDetail(**conv, messages=[_message_out(m, files.get(m["id"], [])) for m in msgs])


@router.patch("/conversations/{cid}", response_model=ConversationOut)
async def patch_conversation(cid: str, body: ConversationPatch, user: dict = Depends(get_current_user)):
    await own_conversation(cid, user)
    update: dict = {}
    if body.title is not None:
        update.update(title=body.title.strip(), titled=True)
    if body.model is not None:
        update["model"] = _check_model(body.model)
    if update:
        await db.conversations.update_one({"id": cid}, {"$set": update})
    return ConversationOut(**await own_conversation(cid, user))


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, user: dict = Depends(get_current_user)):
    await own_conversation(cid, user)
    async for f in db.files.find({"conversation_id": cid, "user_id": user["user_id"]}, {"_id": 0, "path": 1}):
        storage.delete(f["path"])
    await db.files.delete_many({"conversation_id": cid})
    await db.messages.delete_many({"conversation_id": cid})
    await db.conversations.delete_one({"id": cid})
    return {"ok": True}


# ---------- messages ----------

@router.post("/conversations/{cid}/messages")
async def send_message(
    cid: str,
    content: str = Form(""),
    model: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    user: dict = Depends(get_current_user),
):
    conv = await own_conversation(cid, user)
    model_key = _check_model(model or conv["model"])
    if not content.strip() and not files:
        raise HTTPException(400, "Veuillez saisir un message ou joindre un fichier.")

    parsed = []
    for f in files:
        name = f.filename or "fichier"
        data = await f.read(MAX_FILE_BYTES + 1)
        try:
            parsed.append((parse_upload(name, data), data))
        except AttachmentError as e:
            raise HTTPException(e.status, e.message)

    mid, ts = str(uuid.uuid4()), now()
    file_docs = []
    for att, data in parsed:
        fid = str(uuid.uuid4())
        ext = "." + ext_of(att.name)
        doc = {"id": fid, "user_id": user["user_id"], "conversation_id": cid, "message_id": mid,
               "name": att.name, "mime": att.mime, "kind": att.kind, "size": len(data),
               "path": storage.save(user["user_id"], fid, ext, data), "text": att.text, "created_at": ts}
        await db.files.insert_one(dict(doc))
        file_docs.append(doc)

    msg = {"id": mid, "conversation_id": cid, "user_id": user["user_id"], "role": "user",
           "content": content.strip(), "status": "complete", "created_at": ts}
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": cid}, {"$set": {"model": model_key, "updated_at": ts}})
    return _stream_reply(conv, user, model_key, _message_out(msg, file_docs))


@router.post("/conversations/{cid}/regenerate")
async def regenerate(cid: str, model: Optional[str] = Form(None), user: dict = Depends(get_current_user)):
    conv = await own_conversation(cid, user)
    model_key = _check_model(model or conv["model"])
    last = await db.messages.find_one({"conversation_id": cid}, {"_id": 0}, sort=[("created_at", -1)])
    if not last:
        raise HTTPException(400, "Aucun message à régénérer.")
    if last["role"] == "model":
        await db.messages.delete_one({"id": last["id"]})
    await db.conversations.update_one({"id": cid}, {"$set": {"model": model_key}})
    return _stream_reply(conv, user, model_key, None)


# ---------- files ----------

@router.get("/conversations/{cid}/files", response_model=List[FileOut])
async def conversation_files(cid: str, user: dict = Depends(get_current_user)):
    await own_conversation(cid, user)
    docs = await db.files.find({"conversation_id": cid, "user_id": user["user_id"]}, {"_id": 0}).sort(
        "created_at", 1).to_list(1000)
    return [FileOut(**d) for d in docs]


@router.get("/files/{fid}")
async def download_file(fid: str, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({"id": fid, "user_id": user["user_id"]}, {"_id": 0})
    if not doc or not storage.path_of(doc["path"]).exists():
        raise HTTPException(404, "Fichier introuvable.")
    return FileResponse(storage.path_of(doc["path"]), media_type=doc["mime"], filename=doc["name"],
                        content_disposition_type="inline")


# ---------- summaries ----------

SUMMARY_SYSTEM = "Tu rédiges des synthèses claires et fidèles en français, en Markdown."


@router.post("/conversations/{cid}/summary")
async def summarize_conversation(cid: str, user: dict = Depends(get_current_user)):
    conv = await own_conversation(cid, user)
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    msgs = [m for m in msgs if m["content"].strip()]
    if not msgs:
        raise HTTPException(400, "La discussion est vide : rien à résumer.")
    transcript = "\n\n".join(
        f"{'Utilisateur' if m['role'] == 'user' else 'Assistant'} : {m['content']}" for m in msgs)[-200_000:]
    names = [f["name"] async for f in db.files.find({"conversation_id": cid, "user_id": user["user_id"]}, {"name": 1})]
    prompt = (
        "Résume la discussion suivante en Markdown : un paragraphe de synthèse, puis les points clés, "
        "les décisions prises et les éventuelles actions à faire (sections avec titres ###).\n\n"
        + (f"Fichiers joints : {', '.join(names)}\n\n" if names else "")
        + (f"Résumé des échanges plus anciens :\n{conv['rolling_summary']}\n\n" if conv.get("rolling_summary") else "")
        + f"Discussion « {conv['title']} » :\n{transcript}"
    )
    try:
        summary = await generate_text(TITLE_MODEL, prompt, SUMMARY_SYSTEM)
    except Exception as e:
        logger.exception("Conversation summary failed")
        raise HTTPException(502, f"Le résumé a échoué : {str(e)[:200]}")
    return {"summary": summary, "title": conv["title"]}


@router.post("/files/{fid}/summary")
async def summarize_file(fid: str, user: dict = Depends(get_current_user)):
    doc = await db.files.find_one({"id": fid, "user_id": user["user_id"]}, {"_id": 0})
    if not doc or not storage.path_of(doc["path"]).exists():
        raise HTTPException(404, "Fichier introuvable.")
    att = load_attachment(doc, storage.read(doc["path"]) if doc["kind"] != "text" else None)
    ask = ("Décris et résume cette image en Markdown." if doc["kind"] == "image" else
           "Résume ce document en Markdown : une synthèse courte, puis les points clés (### Points clés) "
           "et les informations importantes (chiffres, dates, noms).")
    try:
        summary = await generate_text_with(TITLE_MODEL, [Turn("user", ask, [att])])
    except Exception as e:
        logger.exception("File summary failed")
        raise HTTPException(502, f"Le résumé a échoué : {str(e)[:200]}")
    return {"summary": summary, "title": doc["name"]}


async def generate_text_with(model_id: str, turns: list[Turn]) -> str:
    return "".join([c async for c in stream_chat(model_id, turns, SUMMARY_SYSTEM)]).strip()
