import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import storage
from auth import get_current_user
from db import db
from memory import process_imported_conversation
from takeout import MAX_UPLOAD_BYTES, TakeoutError, group_entries, parse_takeout

router = APIRouter(prefix="/api/imports", tags=["import"])
logger = logging.getLogger("gemini-perso.import")
_jobs: set = set()
IMPORT_MODEL_LABEL = "gemini (import Takeout)"


def _session_path(user_id: str, sid: str) -> Path:
    return storage.files_dir() / "imports" / user_id / f"{sid}.json"


class CommitIn(BaseModel):
    group_keys: List[str]
    summarize: bool = True


async def _existing_keys(user_id: str, keys: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(keys), 5000):
        found |= set(await db.messages.distinct(
            "import_key", {"user_id": user_id, "import_key": {"$in": keys[i:i + 5000]}}))
    return found


@router.post("/takeout/preview")
async def takeout_preview(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    sid = str(uuid.uuid4())
    target = _session_path(uid, sid)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = target.with_suffix(".upload")
    size = 0
    with open(raw, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                raw.unlink(missing_ok=True)
                raise HTTPException(413, "Le fichier dépasse la limite de 250 Mo.")
            out.write(chunk)
    try:
        entries = await asyncio.to_thread(parse_takeout, raw)
    except TakeoutError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logger.exception("Takeout parse failed")
        raise HTTPException(400, "Impossible de lire ce fichier Takeout. Vérifiez qu'il s'agit bien de l'export « Applications Gemini ».")
    finally:
        raw.unlink(missing_ok=True)

    groups = group_entries(entries)
    target.write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
    existing = await _existing_keys(uid, [e["key"] for g in groups for e in g["entries"]])
    summary = []
    for g in groups:
        new = sum(1 for e in g["entries"] if e["key"] not in existing)
        total = len(g["entries"])
        status = "new" if new == total else ("existing" if new == 0 else "partial")
        summary.append({"key": g["key"], "title": g["title"], "start": g["start"], "end": g["end"],
                        "count": total, "new_count": new, "status": status,
                        "preview": (g["entries"][0]["prompt"] or "")[:160]})
    return {"session_id": sid, "entries": len(entries), "conversations": summary}


def _messages_for(entries: list[dict], cid: str, uid: str) -> list[dict]:
    docs = []
    for e in entries:
        t = datetime.fromisoformat(e["time"]).astimezone(timezone.utc).replace(microsecond=0)
        prompt = e["prompt"] or "(Requête non disponible dans l'export)"
        if e.get("files"):
            prompt += "\n\n[Fichiers joints dans Gemini : " + ", ".join(e["files"]) + "]"
        docs.append({"id": str(uuid.uuid4()), "conversation_id": cid, "user_id": uid, "role": "user",
                     "content": prompt, "status": "complete", "created_at": t, "import_key": e["key"]})
        if e["response"]:
            docs.append({"id": str(uuid.uuid4()), "conversation_id": cid, "user_id": uid, "role": "model",
                         "content": e["response"], "model": IMPORT_MODEL_LABEL, "status": "complete",
                         "created_at": t + timedelta(milliseconds=1)})
    return docs


@router.post("/takeout/{sid}/commit")
async def takeout_commit(sid: str, body: CommitIn, user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    path = _session_path(uid, sid)
    if not path.exists():
        raise HTTPException(404, "Session d'import introuvable ou expirée. Rechargez le fichier.")
    groups = {g["key"]: g for g in json.loads(path.read_text(encoding="utf-8"))}
    selected = [groups[k] for k in body.group_keys if k in groups]
    if not selected:
        raise HTTPException(400, "Sélectionnez au moins une conversation à importer.")

    created, appended, skipped, new_ids = 0, 0, 0, []
    for g in selected:
        keys = [e["key"] for e in g["entries"]]
        existing = await _existing_keys(uid, keys)
        fresh = [e for e in g["entries"] if e["key"] not in existing]
        if not fresh:
            skipped += 1
            continue
        end = datetime.fromisoformat(g["end"]).astimezone(timezone.utc).replace(microsecond=0)
        if existing:
            ref = await db.messages.find_one({"user_id": uid, "import_key": {"$in": list(existing)}}, {"conversation_id": 1})
            cid = ref["conversation_id"]
            await db.conversations.update_one({"id": cid, "user_id": uid}, {"$max": {"updated_at": end}})
            appended += 1
        else:
            cid = str(uuid.uuid4())
            await db.conversations.insert_one({
                "id": cid, "user_id": uid, "title": g["title"], "titled": True, "model": "flash",
                "imported": True, "import_source": "takeout",
                "created_at": datetime.fromisoformat(g["start"]).astimezone(timezone.utc).replace(microsecond=0), "updated_at": end,
            })
            created += 1
            new_ids.append(cid)
        await db.messages.insert_many(_messages_for(fresh, cid, uid))
    path.unlink(missing_ok=True)

    job_id = None
    if body.summarize and new_ids:
        job_id = str(uuid.uuid4())
        await db.import_jobs.insert_one({"id": job_id, "user_id": uid, "total": len(new_ids), "done": 0,
                                         "status": "running", "created_at": datetime.now(timezone.utc)})
        task = asyncio.get_running_loop().create_task(_run_job(job_id, uid, new_ids))
        _jobs.add(task)
        task.add_done_callback(_jobs.discard)
    return {"created": created, "appended": appended, "skipped": skipped, "job_id": job_id}


async def _run_job(job_id: str, uid: str, cids: list[str]) -> None:
    sem = asyncio.Semaphore(3)

    async def one(cid: str):
        async with sem:
            try:
                await process_imported_conversation(uid, cid)
            except Exception:
                logger.exception("Import post-processing failed for %s", cid)
            await db.import_jobs.update_one({"id": job_id}, {"$inc": {"done": 1}})

    await asyncio.gather(*(one(c) for c in cids))
    await db.import_jobs.update_one({"id": job_id}, {"$set": {"status": "done"}})


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.import_jobs.find_one({"id": job_id, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    if not job:
        raise HTTPException(404, "Tâche introuvable.")
    return job


def cleanup_sessions(max_age_hours: int = 24) -> None:
    root = storage.files_dir() / "imports"
    if not root.exists():
        return
    limit = datetime.now().timestamp() - max_age_hours * 3600
    for f in root.glob("*/*"):
        if f.stat().st_mtime < limit:
            f.unlink(missing_ok=True)
    for d in root.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            shutil.rmtree(d, ignore_errors=True)
