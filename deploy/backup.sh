#!/usr/bin/env bash
# Gemini Perso — sauvegarde quotidienne MongoDB + fichiers joints
# Cron conseillé (root) : 30 3 * * * /opt/gemini-perso/deploy/backup.sh >> /var/log/gemini-perso-backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/gemini-perso}"
ENV_FILE="${ENV_FILE:-/opt/gemini-perso/backend/.env}"
KEEP_DAYS="${KEEP_DAYS:-14}"

set -a; source "$ENV_FILE"; set +a
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/$STAMP"
mkdir -p "$DEST"

mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --archive="$DEST/mongo.archive.gz"
tar -czf "$DEST/files.tar.gz" -C "$(dirname "$FILES_DIR")" "$(basename "$FILES_DIR")"

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +
echo "[$(date)] Sauvegarde OK : $DEST"
