import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from attachments import Turn
from auth import get_current_user
from db import db
from llm_provider import SYSTEM_PROMPT, TITLE_MODEL, generate_text

router = APIRouter(prefix="/api", tags=["memory"])
logger = logging.getLogger("gemini-perso.memory")

MEMORY_CHAR_BUDGET = 6000
PAST_SUMMARY_CHAR_BUDGET = 4000
MAX_PAST_SUMMARIES = 8
STOPWORDS = set(
    "les des une un le la de du et en est que qui quoi pour pas sur avec dans par plus mais ou ce cette ces son sa ses "
    "mon ma mes ton ta tes nous vous ils elles je tu il elle on au aux the and for you are was what est-ce quel quelle "
    "quels quelles comment pourquoi suis être avoir fait faire tout tous très bien".split()
)


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- schemas ----------

class MemoryOut(BaseModel):
    id: str
    content: str
    source: str
    conversation_id: Optional[str] = None
    conversation_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    conversation_id: Optional[str] = None


class MemoryPatch(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ImportIn(BaseModel):
    items: List[str]


class SettingsOut(BaseModel):
    memory_enabled: bool = True
    auto_memory: bool = True
    context_file: str = ""


class SettingsPatch(BaseModel):
    memory_enabled: Optional[bool] = None
    auto_memory: Optional[bool] = None
    context_file: Optional[str] = Field(default=None, max_length=50000)


# ---------- helpers ----------

async def get_settings(user_id: str) -> dict:
    doc = await db.user_settings.find_one({"user_id": user_id}, {"_id": 0}) or {}
    return SettingsOut(**doc).model_dump()


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"\w{3,}", text.lower()) if w not in STOPWORDS}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _pick(items: list[dict], key: str, query: str, budget: int, limit: int | None = None) -> list[dict]:
    if sum(len(i[key]) for i in items) <= budget and (limit is None or len(items) <= limit):
        return items
    q = _tokens(query)
    ranked = sorted(items, key=lambda i: (len(q & _tokens(i[key] + " " + i.get("title", ""))), i["updated_at"]),
                    reverse=True)
    chosen, used = [], 0
    for item in ranked:
        if used + len(item[key]) > budget or (limit and len(chosen) >= limit):
            continue
        chosen.append(item)
        used += len(item[key])
    return chosen


async def _insert_memory(user_id: str, content: str, source: str, conversation_id: str | None = None) -> dict:
    ts = now()
    doc = {"id": str(uuid.uuid4()), "user_id": user_id, "content": content.strip(), "source": source,
           "conversation_id": conversation_id, "created_at": ts, "updated_at": ts}
    await db.memories.insert_one(dict(doc))
    await _unmark_obsolete(user_id, content)
    return doc


GENERIC_TERMS = {"utilisateur", "nommé", "nommée", "appelé", "appelée", "travaille", "projet", "projets", "préfère",
                 "utiliser", "aime", "possède", "programmation", "langage", "actuellement", "souhaite"}


def _distinctive(text: str) -> set[str]:
    return _tokens(text) - GENERIC_TERMS


async def _mark_obsolete(user_id: str, old: str, new: str = "") -> None:
    terms = sorted(_distinctive(old) - _distinctive(new))
    if terms:
        await db.user_settings.update_one(
            {"user_id": user_id}, {"$addToSet": {"obsolete_terms": {"$each": terms}}}, upsert=True)


async def _unmark_obsolete(user_id: str, content: str) -> None:
    terms = list(_distinctive(content))
    if terms:
        await db.user_settings.update_one({"user_id": user_id}, {"$pull": {"obsolete_terms": {"$in": terms}}})


def _strip_obsolete(summary: str, obsolete: set[str]) -> str:
    """Drop summary sentences mentioning facts the user edited or deleted from memory."""
    if not obsolete:
        return summary
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    return " ".join(s for s in sentences if not (_tokens(s) & obsolete)).strip()


async def build_system_prompt(user_id: str, cid: str, query: str, rolling_summary: str = "") -> str:
    settings = await get_settings(user_id)
    sections = [SYSTEM_PROMPT]
    if settings["context_file"].strip():
        sections.append("## Instructions permanentes de l'utilisateur (fichier de contexte)\n"
                        + settings["context_file"].strip())
    if settings["memory_enabled"]:
        past = await db.conversations.find(
            {"user_id": user_id, "id": {"$ne": cid}, "summary": {"$nin": [None, ""]}},
            {"_id": 0, "title": 1, "summary": 1, "updated_at": 1},
        ).sort("updated_at", -1).to_list(200)
        past = _pick(past, "summary", query, PAST_SUMMARY_CHAR_BUDGET, MAX_PAST_SUMMARIES)
        obsolete = set((await db.user_settings.find_one({"user_id": user_id}, {"obsolete_terms": 1}) or {})
                       .get("obsolete_terms") or [])
        past = [{**p, "summary": _strip_obsolete(p["summary"], obsolete)} for p in past]
        past = [p for p in past if p["summary"]]
        if past:
            sections.append(
                "## Résumés de discussions passées avec l'utilisateur\n"
                + "\n".join(f"- [{p['updated_at']:%d/%m/%Y}] {p['title']} : {p['summary']}" for p in past)
                + "\nAppuie-toi dessus si l'utilisateur évoque des échanges précédents. "
                "Ces résumés peuvent être obsolètes."
            )
        mems = await db.memories.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1).to_list(1000)
        mems = _pick(mems, "content", query, MEMORY_CHAR_BUDGET)
        if mems:
            sections.append(
                "## Ce que tu sais sur l'utilisateur (mémoire permanente)\n"
                + "\n".join(f"- {m['content']}" for m in mems)
                + "\nUtilise ces informations naturellement quand c'est pertinent, sans les réciter.\n"
                "PRIORITÉ : les souvenirs de la mémoire (modifiés par l'utilisateur) priment sur les résumés "
                "de discussions passées ; en cas de contradiction, utilise la mémoire et ignore l'information "
                "obsolète des résumés."
            )
    if rolling_summary:
        sections.append("## Résumé du début de cette discussion (messages plus anciens)\n" + rolling_summary)
    return "\n\n".join(sections)


def _parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


async def _update_conversation_summary(cid: str, user_text: str, reply: str) -> None:
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0, "summary": 1}) or {}
    prompt = (
        "Mets à jour le résumé de la discussion en 2 à 4 phrases (sujets, décisions, informations clés). "
        "Réponds uniquement par le résumé.\n\n"
        f"Résumé actuel :\n{conv.get('summary') or '(aucun)'}\n\n"
        f"Dernier message de l'utilisateur :\n{user_text[:4000]}\n\nRéponse de l'assistant :\n{reply[:4000]}"
    )
    try:
        summary = await generate_text(TITLE_MODEL, prompt, "Tu résumes des conversations de façon fidèle, en français.")
    except Exception:
        logger.exception("Conversation summary update failed")
        return
    if summary:
        await db.conversations.update_one({"id": cid}, {"$set": {"summary": summary[:1500]}})


def _editable(m: dict) -> bool:
    return m.get("source") == "auto" and not m.get("user_edited")


async def _extract_memories(user_id: str, cid: str, user_text: str, reply: str) -> int:
    existing = await db.memories.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    editable = [m for m in existing if _editable(m)]
    locked = [m for m in existing if not _editable(m)]
    prompt = f"""Analyse UNIQUEMENT le dernier message de l'utilisateur et renvoie UNIQUEMENT un objet JSON valide :
{{"memories": [{{"action": "add", "content": "..."}}, {{"action": "update", "id": "<id modifiable>", "content": "..."}}]}}

Règles :
- Extrais seulement des faits DURABLES que l'utilisateur affirme lui-même dans ce message : identité, projets, préférences, contexte pro/perso, instructions explicites (« souviens-toi que… »).
- N'extrais JAMAIS de faits depuis la réponse de l'assistant (elle sert seulement à comprendre le contexte). Une question de l'utilisateur n'est pas un fait.
- Formule chaque souvenir en une phrase courte en français, à la 3e personne (« L'utilisateur… »).
- Si le fait est déjà couvert par un souvenir (modifiable ou verrouillé), ne l'ajoute pas.
- "update" n'est permis que sur un souvenir MODIFIABLE portant sur le même sujet (fusion/correction). Les souvenirs VERROUILLÉS ont été définis par l'utilisateur : ne les contredis pas et ne les recrée pas autrement.
- Ignore les demandes ponctuelles, la culture générale et tout ce qui est trivial ou éphémère. S'il n'y a rien de durable, renvoie {{"memories": []}}.

Souvenirs MODIFIABLES :
{chr(10).join(f"[{m['id']}] {m['content']}" for m in editable) or "(aucun)"}

Souvenirs VERROUILLÉS (lecture seule) :
{chr(10).join(f"- {m['content']}" for m in locked) or "(aucun)"}

Dernier message de l'utilisateur :
{user_text[:4000]}

Réponse de l'assistant (contexte uniquement) :
{reply[:2000]}"""
    try:
        data = _parse_json(await generate_text(TITLE_MODEL, prompt, "Tu es un extracteur de mémoire précis. Tu réponds en JSON."))
    except Exception:
        logger.exception("Memory extraction failed")
        return 0

    editable_ids = {m["id"] for m in editable}
    seen = {_norm(m["content"]) for m in existing}
    changes = 0
    for op in data.get("memories") or []:
        content = (op.get("content") or "").strip() if isinstance(op, dict) else ""
        if not content or _norm(content) in seen:
            continue
        if op.get("action") == "update":
            if op.get("id") not in editable_ids:
                continue  # never touch manual / imported / user-edited memories
            await db.memories.update_one(
                {"id": op["id"], "user_id": user_id, "source": "auto", "user_edited": {"$ne": True}},
                {"$set": {"content": content, "updated_at": now(), "conversation_id": cid}},
            )
        else:
            await _insert_memory(user_id, content, "auto", cid)
        seen.add(_norm(content))
        changes += 1
    return changes


async def after_reply(user_id: str, cid: str, mid: str, user_text: str, reply: str) -> int:
    """Background: update conversation summary + extract durable memories. Returns number of memory changes."""
    settings = await get_settings(user_id)
    tasks = [_update_conversation_summary(cid, user_text, reply)]
    if settings["memory_enabled"] and settings["auto_memory"] and user_text.strip():
        tasks.append(_extract_memories(user_id, cid, user_text, reply))
    results = await asyncio.gather(*tasks)
    changes = results[1] if len(results) > 1 else 0
    if changes:
        await db.messages.update_one({"id": mid}, {"$set": {"memory_updated": True}})
    return changes


async def summarize_turns(previous: str, turns: list[Turn]) -> str:
    transcript = "\n\n".join(
        f"{'Utilisateur' if t.role == 'user' else 'Assistant'} : {t.text[:8000]}" for t in turns
    )
    prompt = (
        "Condense les échanges suivants en un résumé factuel et dense (10 à 20 lignes max) qui conserve "
        "les informations, décisions, chiffres et demandes importantes, pour poursuivre la discussion.\n\n"
        f"Résumé précédent :\n{previous or '(aucun)'}\n\nNouveaux échanges à intégrer :\n{transcript}"
    )
    return await generate_text(TITLE_MODEL, prompt, "Tu résumes des conversations de façon fidèle, en français.")


def export_markdown(memories: list[dict]) -> str:
    lines = ["# Mémoire — Gemini Perso", "", f"_Exporté le {now():%d/%m/%Y à %H:%M} UTC_", "", "## Souvenirs", ""]
    for m in memories:
        first, *rest = m["content"].strip().splitlines() or [""]
        lines.append(f"- {first}")
        lines.extend(f"  {r}" for r in rest)
    return "\n".join(lines) + "\n"


GENERIC_HEADINGS = {"souvenirs", "mémoire", "memoire", "memories", "memory", "mémoire — gemini perso"}


def parse_markdown(text: str) -> list[str]:
    items: list[str] = []
    heading = ""
    para: list[str] = []
    current: list[str] | None = None

    def flush_para():
        if para:
            items.append(" ".join(para).strip())
            para.clear()

    def flush_item():
        nonlocal current
        if current:
            items.append("\n".join(current).strip())
        current = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        bullet = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if not stripped:
            flush_item()
            flush_para()
        elif stripped.startswith("#"):
            flush_item()
            flush_para()
            h = stripped.lstrip("#").strip()
            heading = "" if h.lower() in GENERIC_HEADINGS or stripped.startswith("# ") else h
        elif re.fullmatch(r"_.*_", stripped) and "export" in stripped.lower():
            continue
        elif bullet:
            flush_item()
            flush_para()
            body = bullet.group(1).strip()
            current = [f"{heading} : {body}" if heading else body]
        elif current is not None and raw.startswith((" ", "\t")):
            current.append(stripped)
        else:
            flush_item()
            para.append(stripped)
    flush_item()
    flush_para()
    return [i for i in items if i][:500]


async def _memory_out(user_id: str, docs: list[dict]) -> list[MemoryOut]:
    cids = list({d["conversation_id"] for d in docs if d.get("conversation_id")})
    titles = {c["id"]: c["title"] async for c in db.conversations.find(
        {"id": {"$in": cids}, "user_id": user_id}, {"_id": 0, "id": 1, "title": 1})}
    return [MemoryOut(**d, conversation_title=titles.get(d.get("conversation_id"))) for d in docs]


async def _own_memory(mid: str, user: dict) -> dict:
    doc = await db.memories.find_one({"id": mid, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Souvenir introuvable.")
    return doc


# ---------- routes ----------

@router.get("/memory/settings", response_model=SettingsOut)
async def read_settings(user: dict = Depends(get_current_user)):
    return SettingsOut(**await get_settings(user["user_id"]))


@router.patch("/memory/settings", response_model=SettingsOut)
async def update_settings(body: SettingsPatch, user: dict = Depends(get_current_user)):
    update = body.model_dump(exclude_none=True)
    if update:
        await db.user_settings.update_one({"user_id": user["user_id"]}, {"$set": update}, upsert=True)
    return SettingsOut(**await get_settings(user["user_id"]))


@router.get("/memories", response_model=List[MemoryOut])
async def list_memories(q: str = "", user: dict = Depends(get_current_user)):
    query: dict = {"user_id": user["user_id"]}
    if q.strip():
        query["content"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    docs = await db.memories.find(query, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    return await _memory_out(user["user_id"], docs)


@router.post("/memories", response_model=MemoryOut)
async def add_memory(body: MemoryIn, user: dict = Depends(get_current_user)):
    cid = body.conversation_id
    if cid and not await db.conversations.find_one({"id": cid, "user_id": user["user_id"]}):
        cid = None
    doc = await _insert_memory(user["user_id"], body.content, "manuel", cid)
    return (await _memory_out(user["user_id"], [doc]))[0]


@router.patch("/memories/{mid}", response_model=MemoryOut)
async def edit_memory(mid: str, body: MemoryPatch, user: dict = Depends(get_current_user)):
    old = await _own_memory(mid, user)
    await _mark_obsolete(user["user_id"], old["content"], body.content)
    await _unmark_obsolete(user["user_id"], body.content)
    await db.memories.update_one(
        {"id": mid}, {"$set": {"content": body.content.strip(), "updated_at": now(), "user_edited": True}})
    return (await _memory_out(user["user_id"], [await _own_memory(mid, user)]))[0]


@router.delete("/memories/{mid}")
async def delete_memory(mid: str, user: dict = Depends(get_current_user)):
    old = await _own_memory(mid, user)
    await _mark_obsolete(user["user_id"], old["content"])
    await db.memories.delete_one({"id": mid})
    return {"ok": True}


@router.delete("/memories")
async def delete_all_memories(user: dict = Depends(get_current_user)):
    async for m in db.memories.find({"user_id": user["user_id"]}, {"content": 1}):
        await _mark_obsolete(user["user_id"], m["content"])
    res = await db.memories.delete_many({"user_id": user["user_id"]})
    return {"ok": True, "deleted": res.deleted_count}


@router.get("/memories/export")
async def export_memories(user: dict = Depends(get_current_user)):
    docs = await db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    return Response(
        export_markdown(docs), media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="memoire-gemini-perso.md"'},
    )


@router.post("/memories/import/preview")
async def import_preview(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not (file.filename or "").lower().endswith((".md", ".markdown", ".txt")):
        raise HTTPException(415, "Veuillez choisir un fichier Markdown (.md).")
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Le fichier dépasse la limite de 2 Mo.")
    items = parse_markdown(data.decode("utf-8-sig", errors="replace"))
    if not items:
        raise HTTPException(400, "Aucun élément de mémoire trouvé dans ce fichier.")
    existing = {_norm(m["content"]) async for m in db.memories.find({"user_id": user["user_id"]}, {"content": 1})}
    return {"items": [{"content": i, "duplicate": _norm(i) in existing} for i in items]}


@router.post("/memories/import")
async def import_memories(body: ImportIn, user: dict = Depends(get_current_user)):
    existing = {_norm(m["content"]) async for m in db.memories.find({"user_id": user["user_id"]}, {"content": 1})}
    added = 0
    for content in body.items[:500]:
        content = content.strip()[:10000]
        if content and _norm(content) not in existing:
            await _insert_memory(user["user_id"], content, "import")
            existing.add(_norm(content))
            added += 1
    return {"ok": True, "added": added, "skipped": len(body.items) - added}


async def process_imported_conversation(user_id: str, cid: str) -> None:
    """Background after Takeout import: conversation summary + memory extraction from the user's prompts."""
    msgs = await db.messages.find({"conversation_id": cid, "user_id": user_id}, {"_id": 0, "role": 1, "content": 1}).sort(
        "created_at", 1).to_list(2000)
    transcript = "\n\n".join(
        f"{'Utilisateur' if m['role'] == 'user' else 'Assistant'} : {m['content'][:3000]}" for m in msgs)[:30000]
    summary = await generate_text(
        TITLE_MODEL,
        "Résume cette discussion en 2 à 4 phrases (sujets, décisions, informations clés). "
        "Réponds uniquement par le résumé.\n\n" + transcript,
        "Tu résumes des conversations de façon fidèle, en français.",
    )
    if summary:
        await db.conversations.update_one({"id": cid}, {"$set": {"summary": summary[:1500]}})
    settings = await get_settings(user_id)
    if settings["memory_enabled"] and settings["auto_memory"]:
        prompts = "\n".join(m["content"][:1500] for m in msgs if m["role"] == "user")[:6000]
        await _extract_memories(user_id, cid, prompts, "")
