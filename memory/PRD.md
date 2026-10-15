# Gemini Perso — PRD

## Original problem statement
Self-hostable clone of gemini.google.com ("Gemini Perso"). All UI in French, LIGHT theme, clean Gemini-like look.
Global: React + Vite (migrated from CRA), FastAPI + MongoDB (motor), Python 3.12→3.14 compatible. Target: Dedibox behind Nginx.
LLM provider abstraction: authentification par compte Google (OAuth) → google-genai SDK (streaming); aucune clé API Gemini, aucun fallback externe.
Models: gemini-3.1-pro-preview, gemini-3-flash-preview. Expose /api/openapi.json.
Phase 0 POC: SSE streaming endpoint POST /api/poc/chat, attachments (PDF/DOCX/TXT/MD/PNG/JPG/WEBP, 20 MB max, French errors), minimal French test page.
Future note from user: persistent file storage must be local disk (dir configurable via env) for self-hosting — no Emergent Object Storage.

## Architecture
- backend/server.py — FastAPI app, /api/poc/chat (SSE), /api/poc/config, /api/openapi.json, /api/docs
- backend/llm_provider.py — provider switch (google-genai vs disabled), MODELS map
- backend/attachments.py — validation (size/ext), Pillow image normalize (≤2048px), pypdf check, python-docx extraction, prompt building
- frontend (Vite 6, plugin-react 4, Tailwind, shadcn): App.jsx, hooks/useChatStream.js, lib/api.js (fetch+ReadableStream SSE), components/*
- Vite reads REACT_APP_* via envPrefix; HMR clientPort from WDS_SOCKET_PORT

## Implemented (2026-09)
- Phase 0 POC done: streaming with both models (own Google API key), PDF native, images multimodal, DOCX/TXT/MD extracted, 413/415/400/422 French errors, stop generation, model select, French UI
- Vite migration done (craco/react-scripts removed)
- Python 3.14 wheels verified for pypdf, python-docx, lxml, pillow, pydantic-core, google-genai, motor/pymongo, fastapi, uvicorn
- Testing: iteration_1 100% backend + frontend

## Phase 1 (2026-09) — done
- Auth: email/password JWT (httpOnly cookies access 15 min + refresh 7 d, bcrypt, lockout 5 tries/15 min) + Google (own OAuth2 code flow if GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI set; Google sign-in = Google account auth). Users linked by email. Seeded test user (ADMIN_EMAIL/ADMIN_PASSWORD).
- Backend modules: auth.py, chat.py (conversations/messages/files/regenerate, SSE), storage.py (FILES_DIR local disk), db.py (indexes, tz_aware)
- Multi-turn history rebuilt from Mongo each turn; files re-injected in their original message (PDF/images native, DOCX/TXT/MD cached text); auto-title via Flash
- UI: Gemini-like sidebar (new, search title+content, rename, delete confirm, collapse), model select per conversation, stop, regenerate, copy, files panel, profile menu/logout
- Testing: iteration_2 — 18/18 backend, frontend flows pass

## Phase 2 (2026-09) — done
- Copy buttons: clipboard API + execCommand fallback (lib/clipboard.js), French error toast
- memory.py: memories CRUD/search/delete-all, settings (memory_enabled, auto_memory, context_file), export/import .md with preview + dedupe
- after_reply background task (Flash, one JSON call): memory add/update ops + per-conversation summary; SSE "memory" event -> "Mémoire mise à jour" indicator (persisted memory_updated)
- System prompt = base + context file (always) + relevant memories (budget 6000 chars, keyword scoring) + past-conversation summaries (max 8) + rolling summary
- Rolling summary when history > HISTORY_CHAR_BUDGET (env, default 60000 chars); folded turns' files still attached
- Summaries: POST /api/conversations/{id}/summary, POST /api/files/{id}/summary; SummaryPanel (copy, export .md, save to memory)
- Testing: iteration_3 — 15/15 backend, frontend 100%
- Fixes after Phase 2 review: auto-extraction can only add/update source=auto & non user_edited memories (separate summary call); memory > summaries priority in system prompt; obsolete_terms (user_settings) strip stale facts from past summaries after edit/delete; memory badge sync fallback
- google-genai path bug fixed (client cached with lru_cache; previous per-call client was GC'd -> aiohttp AssertionError). Auth via compte Google uniquement : aucune clé API Gemini stockée (pas de quota payant).

## Phase 3 (2026-10) — done
- Quota 429 handling: French message + "Réessayer avec Gemini 3 Flash" (SSE error code "quota"); verified with real Google 429 locally
- Takeout import (takeout.py, imports.py): .zip / MyActivity.json (streamed array decoder) / MyActivity.html (streamed by activity cell, FR/EN dates); groups by 30-min gap (max 300 entries); dedupe by entry key (time+prompt) across formats; preview session stored on disk (FILES_DIR/imports); commit -> imported conversations (dates preserved, "Importé" badge); background job: summaries + memories with progress
- google_mode: oauth (own Google OAuth2 creds) / disabled (self-host without creds -> button hidden); COOKIE_DOMAIN; atomic admin seed
- Deploy: requirements.txt (tested install+run on Python 3.12.15 and 3.14.8 via uv), .env.example (backend/frontend), deploy/{nginx.conf, gemini-perso.service, docker-compose.yml, Dockerfile.backend, backup.sh}, DEPLOIEMENT.md; /api/deploy/guide + /api/deploy/bundle; relative /api when backend URL unset; prod build tested behind nginx 1.22 (local)
- Testing: iteration_4 — 11/11 backend, frontend 100%

## Backlog
- Later phases (user-defined): TBD
- P1: syntax highlighting in code blocks, password reset, long-conversation token budgeting (files re-sent every turn)
- P2: Dockerfile / Nginx config for Dedibox (client_max_body_size 25m, proxy_buffering off for SSE), requirements.txt as the single install source
