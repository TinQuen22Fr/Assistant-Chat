#!/usr/bin/env bash
#
# Assistant-Chat — installation de production (Dedibox multi-host)
#
# Installe le backend FastAPI (venv + service systemd), construit le frontend
# Vite, cree le vhost Nginx du domaine et obtient le certificat HTTPS.
#
# Rejouable sans danger : ne touche jamais un backend/.env existant, ne
# remplace jamais un service systemd deja present s'il differe du gabarit, et
# genere le vhost Nginx dans /etc/nginx/sites-available sans ecraser le site
# "default" (serveur multi-host).
#
# Usage (depuis la racine du depot clone) :
#   sudo bash install.sh
#   sudo bash install.sh --domain gemini-memory-assistant.quentin-astro.fr
#   sudo bash install.sh --branch Make-With-Forge
#   sudo bash install.sh --skip-nginx
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
DEPLOY_DIR="$APP_DIR/deploy"

# --- Parametres surchargeables -----------------------------------------------
DOMAIN="${DOMAIN:-gemini-memory-assistant.quentin-astro.fr}"
SERVICE_NAME="${SERVICE_NAME:-gemini-perso}"
SITE_NAME="${SITE_NAME:-gemini-perso}"
APP_USER="${APP_USER:-gemini}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
DATA_DIR="${DATA_DIR:-/var/lib/gemini-perso}"
# Branche de travail GitHub : les ajouts/corrections futurs y seront merges.
WORK_BRANCH="${WORK_BRANCH:-Make-With-Forge}"

BRANCH="${BRANCH:-}"
DO_NGINX=1
DO_CERTBOT=1

c_info()  { printf '\033[36m[i]\033[0m %s\n' "$1"; }
c_ok()    { printf '\033[32m[OK]\033[0m %s\n' "$1"; }
c_warn()  { printf '\033[33m[!]\033[0m %s\n' "$1"; }
c_error() { printf '\033[31m[X]\033[0m %s\n' "$1" >&2; }
die()     { c_error "$1"; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --domain)      DOMAIN="${2:-}"; shift ;;
    --branch)      BRANCH="${2:-}"; shift ;;
    --user)        APP_USER="${2:-}"; shift ;;
    --port)        BACKEND_PORT="${2:-}"; shift ;;
    --data-dir)    DATA_DIR="${2:-}"; shift ;;
    --service)     SERVICE_NAME="${2:-}"; shift ;;
    --site-name)   SITE_NAME="${2:-}"; shift ;;
    --skip-nginx)  DO_NGINX=0 ;;
    --skip-certbot) DO_CERTBOT=0 ;;
    -h|--help)     sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "a lancer en root : sudo bash install.sh"
[ -f "$BACKEND_DIR/server.py" ] || die "$APP_DIR ne ressemble pas a Assistant-Chat"

c_info "Domaine       : $DOMAIN"
c_info "Repertoire    : $APP_DIR"
c_info "Service       : $SERVICE_NAME (port $BACKEND_PORT)"
c_info "Branche Git   : ${BRANCH:-$WORK_BRANCH} (courante: $(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?'))"

# --- Branche de travail GitHub -----------------------------------------------
# Detection automatique : la branche de travail du depot (WORK_BRANCH) est
# utilisee si elle existe sur origin ; sinon on conserve la branche courante.
git -C "$APP_DIR" fetch origin --prune >/dev/null 2>&1 || true
CUR_BRANCH="$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

if [ -n "$BRANCH" ]; then
  TARGET_BRANCH="$BRANCH"
elif git -C "$APP_DIR" show-ref --verify --quiet "refs/remotes/origin/$WORK_BRANCH"; then
  TARGET_BRANCH="$WORK_BRANCH"
else
  TARGET_BRANCH="$CUR_BRANCH"
fi

if [ -z "$TARGET_BRANCH" ] || [ "$TARGET_BRANCH" = "HEAD" ]; then
  die "aucune branche de travail detectable (cherche origin/$WORK_BRANCH)."
fi

if [ "$CUR_BRANCH" != "$TARGET_BRANCH" ]; then
  c_info "Bascule de la branche $CUR_BRANCH vers $TARGET_BRANCH ..."
  git -C "$APP_DIR" checkout "$TARGET_BRANCH" 2>/dev/null ||     git -C "$APP_DIR" checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH" 2>/dev/null ||     die "impossible de basculer sur $TARGET_BRANCH"
else
  c_ok "Branche de travail $TARGET_BRANCH detectee."
fi
git -C "$APP_DIR" pull --ff-only origin "$TARGET_BRANCH" 2>/dev/null ||   c_warn "pull impossible (pas de branche distante ? code local conserve)."

# --- Prerequis ----------------------------------------------------------------
command -v python3  >/dev/null || die "python3 introuvable."
command -v npm      >/dev/null || die "npm introuvable (Node.js requis)."
command -v systemctl >/dev/null || die "systemctl introuvable."
command -v git      >/dev/null || die "git introuvable."
command -v nginx    >/dev/null || { [ "$DO_NGINX" = "1" ] && die "nginx introuvable."; }
command -v certbot  >/dev/null || { [ "$DO_CERTBOT" = "1" ] && [ "$DO_NGINX" = "1" ] && c_warn "certbot introuvable : HTTPS non active."; DO_CERTBOT=0; }

# --- Utilisateur systeme ------------------------------------------------------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  c_info "Creation de l'utilisateur systeme $APP_USER ..."
  adduser --system --group --home "$APP_DIR" "$APP_USER"
else
  c_ok "Utilisateur $APP_USER deja present."
fi
mkdir -p "$DATA_DIR/files"
chown -R "$APP_USER":"$APP_USER" "$DATA_DIR"

# --- Backend : venv + dependances ---------------------------------------------
c_info "Backend : environnement virtuel ..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
  sudo -u "$APP_USER" python3 -m venv "$VENV_DIR"
  c_ok "venv cree dans $VENV_DIR"
else
  c_ok "venv deja present."
fi
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip --quiet
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
c_ok "Dependances Python installees."

# --- Backend : .env (jamais d'ecrasement) --------------------------------------
set_env_key() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys, re, pathlib
f, k, v = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(f)
lines = p.read_text().splitlines() if p.exists() else []
out, found = [], False
for line in lines:
    if re.match(rf'^{re.escape(k)}=', line):
        out.append(f'{k}={v}'); found = True
    else:
        out.append(line)
if not found:
    out.append(f'{k}={v}')
p.write_text('\n'.join(out) + '\n')
PY
}

ENV_FILE="$BACKEND_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  c_warn ".env absent : creation depuis .env.example"
  cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  JWT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  set_env_key "$ENV_FILE" "JWT_SECRET" "$JWT"
  set_env_key "$ENV_FILE" "PUBLIC_URL" "https://$DOMAIN"
  set_env_key "$ENV_FILE" "COOKIE_SECURE" "true"
  set_env_key "$ENV_FILE" "CORS_ORIGINS" "https://$DOMAIN"
  set_env_key "$ENV_FILE" "FILES_DIR" "$DATA_DIR/files"

  # Compte administrateur + Google OAuth (interactif si un terminal est ouvert)
  read_val() { # name default
    if [ -t 0 ]; then
      local v=""
      read -r -p "$1 [$2] : " v
      printf '%s' "${v:-$2}"
    else
      printf '%s' "$2"
    fi
  }
  ADMIN_EMAIL="${ADMIN_EMAIL:-$(read_val 'Email administrateur' 'admin@example.fr')}"
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(read_val 'Mot de passe administrateur' 'change-me')}"
  set_env_key "$ENV_FILE" "ADMIN_EMAIL" "$ADMIN_EMAIL"
  set_env_key "$ENV_FILE" "ADMIN_PASSWORD" "$ADMIN_PASSWORD"

  if [ -t 0 ]; then
    read -r -p "GOOGLE_CLIENT_ID (laisser vide pour desactiver le bouton Google) : " GID
    read -r -p "GOOGLE_CLIENT_SECRET (laisser vide) : " GSEC
    set_env_key "$ENV_FILE" "GOOGLE_CLIENT_ID" "${GID:-}"
    set_env_key "$ENV_FILE" "GOOGLE_CLIENT_SECRET" "${GSEC:-}"
  fi

  # GOOGLE_REDIRECT_URI vide = detection auto <PUBLIC_URL>/api/auth/google/callback
  set_env_key "$ENV_FILE" "GOOGLE_REDIRECT_URI" ""
  c_warn "VERIFIEZ $ENV_FILE (MONGO_URL, secrets, Google OAuth) puis relancez si besoin."
else
  c_ok ".env deja present (non modifie)."
  chmod 600 "$ENV_FILE" 2>/dev/null || true
fi

# --- Frontend : build de production -------------------------------------------
c_info "Frontend : installation des dependances ..."
chown -R "$APP_USER":"$APP_USER" "$FRONTEND_DIR" 2>/dev/null || true
if [ -f "$FRONTEND_DIR/package-lock.json" ]; then
  (cd "$FRONTEND_DIR" && sudo -u "$APP_USER" npm ci --legacy-peer-deps)
else
  (cd "$FRONTEND_DIR" && sudo -u "$APP_USER" npm install --legacy-peer-deps)
fi
c_info "Frontend : build Vite ..."
(cd "$FRONTEND_DIR" && sudo -u "$APP_USER" npm run build)
c_ok "Build genere dans $FRONTEND_DIR/build/"

# --- Service systemd -----------------------------------------------------------
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
NEW_SERVICE="$(mktemp)"
sed \
  -e "s|/opt/gemini-perso|$APP_DIR|g" \
  -e "s|/var/lib/gemini-perso|$DATA_DIR|g" \
  -e "s|--port 8001|--port $BACKEND_PORT|g" \
  -e "s|^User=gemini|User=$APP_USER|" \
  -e "s|^Group=gemini|Group=$APP_USER|" \
  "$DEPLOY_DIR/gemini-perso.service" > "$NEW_SERVICE"

if [ ! -f "$SERVICE_FILE" ]; then
  c_info "Installation du service systemd $SERVICE_NAME ..."
  install -m 0644 "$NEW_SERVICE" "$SERVICE_FILE"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
  c_ok "Service installe."
elif diff -q "$NEW_SERVICE" "$SERVICE_FILE" >/dev/null 2>&1; then
  c_ok "Service systemd deja identique au gabarit."
else
  c_warn "Service $SERVICE_NAME existant different du gabarit : conserve intact."
  c_info "  diff -u $SERVICE_FILE $NEW_SERVICE"
fi
rm -f "$NEW_SERVICE"

# --- Redemarrage + verification -------------------------------------------------
c_info "Redemarrage de $SERVICE_NAME ..."
systemctl restart "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME" || {
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager
  die "$SERVICE_NAME ne demarre pas."
}
c_ok "service actif"

URL="http://127.0.0.1:${BACKEND_PORT}/api/"
CODE=000
for _ in $(seq 1 15); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -X GET "$URL" || echo 000)"
  [ "$CODE" = "200" ] && break
  sleep 1
done
if [ "$CODE" = "200" ]; then
  c_ok "API /api/ repond 200."
else
  c_warn "API /api/ repond $CODE — journalctl -u $SERVICE_NAME -n 50"
fi

# --- Nginx (multi-host) ----------------------------------------------------------
if [ "$DO_NGINX" = "1" ]; then
  NGINX_AVAIL="/etc/nginx/sites-available/$SITE_NAME"
  NGINX_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
  ACME_DIR="/var/www/certbot"
  mkdir -p "$ACME_DIR"

  c_info "Vhost Nginx (ACME, HTTP uniquement) ..."
  cat > "$NGINX_AVAIL" <<NGINX_ACME
# ${SERVICE_NAME} — ACME challenge (HTTP). Remplacé après obtention du certificat.
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ { root ${ACME_DIR}; }
    location / { return 200 'Assistant-Chat - installation en cours'; }
}
NGINX_ACME
  ln -sfn "$NGINX_AVAIL" "$NGINX_ENABLED"
  nginx -t && systemctl reload nginx

  CERT_OK=0
  if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    CERT_OK=1
    c_ok "Certificat deja present pour $DOMAIN."
  elif [ "$DO_CERTBOT" = "1" ]; then
    c_info "Obtention du certificat HTTPS (certbot) ..."
    CERT_ARGS=(--webroot -w "$ACME_DIR" -d "$DOMAIN" --non-interactive --agree-tos)
    if [ -n "${CERTBOT_EMAIL:-$ADMIN_EMAIL}" ]; then
      CERT_ARGS+=(-m "${CERTBOT_EMAIL:-$ADMIN_EMAIL}")
    else
      CERT_ARGS+=(--register-unsafely-without-email)
    fi
    if certbot certonly "${CERT_ARGS[@]}" --keep-until-expiring; then
      CERT_OK=1
      c_ok "Certificat obtenu."
    else
      c_warn "certbot a echoue (DNS pointe-t-il vers ce serveur ?)."
      c_warn "Le site reste en HTTP. Relancez apres propagation DNS : sudo bash install.sh"
    fi
  fi

  if [ "$CERT_OK" = "1" ]; then
    c_info "Installation du vhost HTTPS complet ..."
    sed \
      -e "s|gemini.example.fr|$DOMAIN|g" \
      -e "s|/opt/gemini-perso|$APP_DIR|g" \
      -e "s|127.0.0.1:8001|127.0.0.1:$BACKEND_PORT|g" \
      "$DEPLOY_DIR/nginx.conf" > "$NGINX_AVAIL"
    nginx -t && systemctl reload nginx
    c_ok "Nginx configure : https://$DOMAIN"
  fi
else
  c_warn "Nginx non configure (--skip-nginx)."
fi

# --- Rappels ----------------------------------------------------------------------
echo ""
c_ok "Installation terminee."
cat <<EOF
  .env a verifier   : $ENV_FILE
  Journaux          : journalctl -u $SERVICE_NAME -f
  URI Google OAuth  : https://$DOMAIN/api/auth/google/callback
  Upgrade futur     : sudo bash $APP_DIR/upgrade.sh
  Retour arriere    : git checkout <sha> && sudo bash upgrade.sh --no-pull
EOF
