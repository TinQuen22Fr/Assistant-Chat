"""Backend tests for Gemini Perso POC endpoints."""
import json
import os
import re
import pathlib
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if BASE_URL is None:
    # fallback to frontend .env
    env = pathlib.Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

FIX = pathlib.Path("/app/tests/fixtures")
TIMEOUT = 120


def _collect_sse(resp):
    """Collect SSE stream, return list of event dicts and full concatenated text."""
    events = []
    text = ""
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        events.append(ev)
        if ev.get("type") == "delta":
            text += ev.get("text", "")
    return events, text


# ---------- Config / OpenAPI ----------
def test_openapi():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "/api/poc/chat" in data["paths"]


def test_poc_config():
    r = requests.get(f"{BASE_URL}/api/poc/config", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "provider" in data
    keys = {m["key"] for m in data["models"]}
    assert {"pro", "flash"}.issubset(keys)


# ---------- Validation errors ----------
def test_invalid_model_422():
    r = requests.post(f"{BASE_URL}/api/poc/chat", data={"prompt": "hi", "model": "banana"}, timeout=30)
    assert r.status_code == 422
    assert "Modèle" in r.text or "inconnu" in r.text


def test_empty_prompt_no_file_400():
    r = requests.post(f"{BASE_URL}/api/poc/chat", data={"prompt": "", "model": "flash"}, timeout=30)
    assert r.status_code == 400
    assert "Veuillez" in r.text or "fichier" in r.text


def test_unsupported_ext_415(tmp_path):
    p = tmp_path / "x.json"
    p.write_bytes(b'{"a":1}')
    with open(p, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "ok", "model": "flash"},
            files={"files": ("x.json", f, "application/json")},
            timeout=30,
        )
    assert r.status_code == 415
    assert "Format" in r.text


def test_too_large_413():
    with open(FIX / "big.png", "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "ok", "model": "flash"},
            files={"files": ("big.png", f, "image/png")},
            timeout=60,
        )
    assert r.status_code == 413
    assert "dépasse la limite autorisée de 20 Mo" in r.text


# ---------- Streaming/model resolution ----------
def test_stream_flash_pdf_zebre():
    with open(FIX / "test.pdf", "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "Quel est le code secret présent dans ce PDF ? Réponds en citant exactement le code.", "model": "flash"},
            files={"files": ("test.pdf", f, "application/pdf")},
            stream=True,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        events, text = _collect_sse(r)
    assert events[0]["type"] == "meta"
    assert events[0]["model"] == "gemini-3-flash-preview"
    assert any(e["type"] == "done" for e in events)
    assert "ZEBRE-7731" in text, f"Got text: {text[:500]}"


def test_stream_pro_image_banane():
    with open(FIX / "test.png", "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "Décris cette image : couleurs, formes, et tout texte visible.", "model": "pro"},
            files={"files": ("test.png", f, "image/png")},
            stream=True,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        events, text = _collect_sse(r)
    assert events[0]["model"] == "gemini-3.1-pro-preview"
    assert any(e["type"] == "done" for e in events)
    lower = text.lower()
    # Expect at least one of the key markers
    assert ("banane" in lower and "42" in text) or "banane 42" in lower, f"Text: {text[:600]}"


def test_stream_docx_hibou():
    with open(FIX / "test.docx", "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "Qui est le personnage mentionné dans ce document ? Donne son nom exact.", "model": "flash"},
            files={"files": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            stream=True,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        events, text = _collect_sse(r)
    assert any(e["type"] == "done" for e in events)
    assert "Hibou" in text, f"Text: {text[:500]}"


def test_stream_txt_file(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("Le mot-clé secret est TOURNESOL-1234.", encoding="utf-8")
    with open(p, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/poc/chat",
            data={"prompt": "Quel est le mot-clé secret dans la note ?", "model": "flash"},
            files={"files": ("note.txt", f, "text/plain")},
            stream=True,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        events, text = _collect_sse(r)
    assert "TOURNESOL-1234" in text, f"Text: {text[:500]}"
