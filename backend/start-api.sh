#!/usr/bin/env bash
# Lance l'API FastAPI sur le port 8010 si elle ne tourne pas deja.
# Idempotent : utilisable en tache de fond de preview comme en local.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${API_PORT:-8010}"
HOST="${API_HOST:-0.0.0.0}"

# Deja en ecoute ? On ne relance pas.
if command -v ss >/dev/null 2>&1 && ss -ltn "( sport = :${PORT} )" 2>/dev/null | grep -q ":${PORT}"; then
  echo "[start-api] port ${PORT} deja en ecoute, rien a faire."
  exit 0
fi

UVICORN=""
for c in "$ROOT/.venv/bin/uvicorn" "$ROOT/backend/.venv/bin/uvicorn"; do
  [ -x "$c" ] && UVICORN="$c" && break
done
if [ -z "$UVICORN" ]; then
  UVICORN="$(command -v uvicorn || true)"
fi
if [ -z "$UVICORN" ]; then
  echo "[start-api] uvicorn introuvable. Installez backend/requirements.txt dans .venv." >&2
  exit 1
fi

cd "$ROOT/backend"
echo "[start-api] demarrage uvicorn sur ${HOST}:${PORT} ($UVICORN)"
exec "$UVICORN" server:app --host "$HOST" --port "$PORT"
