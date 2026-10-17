#!/usr/bin/env bash
#
# Assistant-Chat — mise a jour d'une installation de production existante.
#
#   install.sh = premiere installation (venv, .env, service systemd, Nginx)
#   upgrade.sh = correctifs, nouveautes, nouvelles dependances, nouveau .env
#
# Usage (depuis la racine du depot, en root) :
#   sudo bash upgrade.sh                 # pull + deps + build + restart
#   sudo bash upgrade.sh --no-pull       # ne touche pas a git (code deja a jour)
#   sudo bash upgrade.sh --backend-only  # saute le build frontend
#   sudo bash upgrade.sh --frontend-only # saute pip + service
#   sudo bash upgrade.sh --branch Make-With-Forge
#
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
DEPLOY_DIR="$APP_DIR/deploy"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
SERVICE="${SERVICE:-gemini-perso}"
SERVICE_FILE="/etc/systemd/system/${SERVICE}.service"
APP_USER="${APP_USER:-gemini}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
WORK_BRANCH="${WORK_BRANCH:-Make-With-Forge}"

BRANCH="${BRANCH:-}"
DO_PULL=1
DO_BACKEND=1
DO_FRONTEND=1
DO_SERVICE=1

c_ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
c_step() { printf '\n\033[1;36m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
c_warn() { printf '\033[1;33m  /!\\\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m[i]\033[0m %s\n' "$1"; }
port_in_use() { # port -> 0 si un processus ecoute deja
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}
api_is_ours() { # url -> 0 si la reponse porte la signature de notre API
  curl -fsS -m 5 "$1" 2>/dev/null | grep -q '"Gemini Perso API"'
}
die()    { printf '\033[1;31mERREUR:\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)       DO_PULL=0 ;;
    --backend-only)  DO_FRONTEND=0 ;;
    --frontend-only) DO_BACKEND=0 ;;
    --no-restart)    DO_SERVICE=0 ;;
    --branch)        BRANCH="${2:-}"; shift ;;
    --service)       SERVICE="${2:-}"; shift ;;
    --port)          BACKEND_PORT="${2:-}"; shift ;;
    --user)          APP_USER="${2:-}"; shift ;;
    -h|--help)       sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "a lancer en root : sudo bash upgrade.sh"
[ -f "$BACKEND_DIR/server.py" ] || die "$APP_DIR ne ressemble pas a Assistant-Chat"
[ -x "$VENV_DIR/bin/pip" ] || die "venv introuvable dans $VENV_DIR — lancer d'abord install.sh"

# Les repertoires d'ecriture de l'utilisateur applicatif doivent lui appartenir
# (le depot peut avoir ete clone par un autre utilisateur).
chown -R "$APP_USER":"$APP_USER" "$BACKEND_DIR" 2>/dev/null || true
install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$VENV_DIR"
chown -R "$APP_USER":"$APP_USER" "$VENV_DIR" 2>/dev/null || true

cd "$APP_DIR"

# Le depot peut avoir ete clone par un utilisateur non-root (ex. quentin) :
# on declare le dossier sur pour git afin d'eviter "dubious ownership".
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" ||
  git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

STAMP="$(date +%Y%m%d-%H%M%S)"

# --- Detection de la branche de travail GitHub ----------------------------------
CUR_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
c_step "Branche Git"
c_info "Branche courante : ${CUR_BRANCH:-inconnue}"

if [ "$DO_PULL" = "1" ]; then
  TARGET="$BRANCH"
  if [ -z "$TARGET" ]; then
    # Detection automatique : branche de travail du depot, sinon branche courante.
    if git show-ref --verify --quiet "refs/remotes/origin/$WORK_BRANCH"; then
      TARGET="$WORK_BRANCH"
    elif [ -n "$CUR_BRANCH" ] && git show-ref --verify --quiet "refs/remotes/origin/$CUR_BRANCH"; then
      TARGET="$CUR_BRANCH"
    else
      die "aucune branche de travail detectable (cherche origin/$WORK_BRANCH)."
    fi
  fi
  c_info "Mise a jour depuis origin/$TARGET ..."
  git fetch origin --prune
  if git show-ref --verify --quiet "refs/remotes/origin/$TARGET"; then
    git checkout "$TARGET" 2>/dev/null || git checkout -b "$TARGET" "origin/$TARGET"
    git reset --hard "origin/$TARGET"
    c_ok "code a jour sur $TARGET"
  else
    c_warn "origin/$TARGET introuvable — code local conserve."
  fi
else
  c_warn "--no-pull : git non modifie (code suppose deja a jour)."
fi

# --- .env : synchronisation non destructive --------------------------------------
c_step "Configuration .env"
ENV_FILE="$BACKEND_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  c_warn ".env absent : cree depuis .env.example — VERIFIEZ ses valeurs puis relancez."
  die ".env a completer avant de continuer."
fi

# Nouvelle cle du .env.example absente de l'existant ? On l'ajoute (vide ou valeur
# par defaut), sans jamais ecraser une valeur deja renseignee.
if [ -f "$BACKEND_DIR/.env.example" ]; then
  BACKUP="$ENV_FILE.bak-$STAMP"
  cp "$ENV_FILE" "$BACKUP"
  c_info "sauvegarde .env -> $BACKUP"
  python3 - "$ENV_FILE" "$BACKEND_DIR/.env.example" <<'PY'
import sys, re, pathlib
env_path, example_path = sys.argv[1], sys.argv[2]
env = pathlib.Path(env_path)
example = pathlib.Path(example_path)

def parse(p):
    out = {}
    for line in p.read_text().splitlines():
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out

cur = parse(env)
ref = parse(example)
added = []
for k in ref:
    if k not in cur:
        # On reprend la valeur par defaut de l'exemple pour les cles puresment
        # techniques ; pour les secrets/URL, laisser vide est plus sur.
        if k in {"JWT_SECRET", "ADMIN_PASSWORD", "GOOGLE_CLIENT_SECRET", "MONGO_URL"}:
            cur[k] = ""
        else:
            cur[k] = ref[k]
        added.append(k)
# Reecrit en preservant l'ordre des cles existantes puis les ajouts.
lines = env.read_text().splitlines()
existing = set()
for i, line in enumerate(lines):
    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
    if m:
        existing.add(m.group(1))
        lines[i] = f"{m.group(1)}={cur[m.group(1)]}"
for k in cur:
    if k not in existing:
        lines.append(f"{k}={cur[k]}")
env.write_text('\n'.join(lines) + '\n')
print("  nouvelles cles ajoutees : " + (", ".join(added) if added else "aucune"))
PY
fi

# --- Backend : dependances ---------------------------------------------------------
if [ "$DO_BACKEND" = "1" ]; then
  c_step "Backend : dependances"
  # HOME de l'utilisateur systeme possiblement non inscriptible : cache pip
  # explicite et propriete de $APP_USER pour eviter les WARNING.
  PIP_CACHE_DIR="${PIP_CACHE_DIR:-$APP_DIR/.cache/pip}"
  install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$PIP_CACHE_DIR"
  sudo -u "$APP_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" "$VENV_DIR/bin/pip" install --upgrade pip --quiet
  sudo -u "$APP_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
  c_ok "dependances Python installees"
fi

# --- Frontend : build --------------------------------------------------------------
if [ "$DO_FRONTEND" = "1" ]; then
  c_step "Frontend : build"
  # Cache npm (frontend/.npmrc -> ../.npm-cache) et node_modules peuvent
  # appartenir a root : npm en tant que $APP_USER echoue en EACCES sur le cache
  # et laisse un node_modules partiel. Cache explicite + purge prealable.
  NPM_CACHE_DIR="${NPM_CACHE_DIR:-$APP_DIR/.npm-cache}"
  install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$NPM_CACHE_DIR"
  chown -R "$APP_USER":"$APP_USER" "$NPM_CACHE_DIR" 2>/dev/null || true
  rm -rf "$FRONTEND_DIR/node_modules"
  chown -R "$APP_USER":"$APP_USER" "$FRONTEND_DIR" 2>/dev/null || true
  if [ -f "$FRONTEND_DIR/package-lock.json" ]; then
    (cd "$FRONTEND_DIR" && sudo -u "$APP_USER" env npm_config_cache="$NPM_CACHE_DIR" npm ci --legacy-peer-deps)
  else
    (cd "$FRONTEND_DIR" && sudo -u "$APP_USER" env npm_config_cache="$NPM_CACHE_DIR" npm install --legacy-peer-deps)
  fi
  (cd "$FRONTEND_DIR" && sudo -u "$APP_USER" env npm_config_cache="$NPM_CACHE_DIR" npm run build)
  c_ok "build genere dans $FRONTEND_DIR/build/"
fi

# --- Service systemd : aligner puis redemarrer ---------------------------------------
if [ "$DO_SERVICE" = "1" ] && [ -f "$SERVICE_FILE" ]; then
  c_step "Service systemd $SERVICE"
  NEW_SERVICE="$(mktemp)"
  sed \
    -e "s|/opt/gemini-perso|$APP_DIR|g" \
    -e "s|/var/lib/gemini-perso|${DATA_DIR:-/var/lib/gemini-perso}|g" \
    -e "s|--port 8001|--port $BACKEND_PORT|g" \
    -e "s|^User=gemini|User=$APP_USER|" \
    -e "s|^Group=gemini|Group=$APP_USER|" \
    "$DEPLOY_DIR/gemini-perso.service" > "$NEW_SERVICE"

  if diff -q "$NEW_SERVICE" "$SERVICE_FILE" >/dev/null 2>&1; then
    c_ok "service deja identique au gabarit"
  else
    c_warn "le service en place differe du gabarit (durcissement local preserve)."
    c_info "  diff -u $SERVICE_FILE $NEW_SERVICE"
  fi
  rm -f "$NEW_SERVICE"

  # Meme controle que dans install.sh : un port tenu par un service etranger
  # (API Forge) fait repondre 200 leur API, pas la notre.
  if port_in_use "$BACKEND_PORT" && ! api_is_ours "http://127.0.0.1:${BACKEND_PORT}/api/"; then
    die "Port $BACKEND_PORT occupe par un autre service (reponse etrangere). Liberez-le ou relancez avec --port <autre port>."
  fi

  systemctl daemon-reload
  systemctl restart "$SERVICE"
  systemctl is-active --quiet "$SERVICE" || {
    journalctl -u "$SERVICE" -n 40 --no-pager
    die "$SERVICE ne demarre pas (journal ci-dessus)"
  }
  sleep 3
  NRESTARTS="$(systemctl show "$SERVICE" -p NRestarts --value 2>/dev/null || echo 0)"
  if ! systemctl is-active --quiet "$SERVICE" || [ "${NRESTARTS:-0}" -gt 0 ]; then
    journalctl -u "$SERVICE" -n 40 --no-pager
    die "$SERVICE instable (NRestarts=${NRESTARTS:-0}) : verifiez $ENV_FILE (MONGO_URL, secrets)."
  fi
  c_ok "service actif (stable)"

  URL="http://127.0.0.1:${BACKEND_PORT}/api/"
  OK=0
  for _ in $(seq 1 15); do
    if api_is_ours "$URL"; then OK=1; break; fi
    sleep 1
  done
  if [ "$OK" = "1" ]; then
    c_ok "API /api/ repond et porte la signature 'Gemini Perso API'"
  else
    c_warn "API /api/ injoignable ou reponse inattendue — inspecte : journalctl -u $SERVICE -n 50"
  fi
elif [ "$DO_SERVICE" = "1" ]; then
  c_warn "service $SERVICE absent — lancez install.sh d'abord."
fi

# --- Nginx : recharger si la config du depot a change ----------------------------------
c_step "Nginx"
SITE="${SITE_NAME:-gemini-perso}"
NGINX_AVAIL="/etc/nginx/sites-available/$SITE"
DOMAIN="${DOMAIN:-gemini-memory-assistant.quentin-astro.fr}"
# Nginx >= 1.25.1 : "listen ... http2" est deprecie -> "http2 on;". On applique
# la meme regle qu'install.sh pour que la comparaison au gabarit reste exacte.
NGINX_HTTP2_MODE="listen"
if command -v nginx >/dev/null 2>&1; then
  NGINX_VERSION="$(nginx -v 2>&1 | sed -n 's#.*nginx/\([0-9][0-9.]*\).*#\1#p')"
  NGINX_NEW_HTTP2="$(printf '%s\n%s\n' "1.25.1" "$NGINX_VERSION" | sort -V | head -1)"
  if [ -n "$NGINX_VERSION" ] && [ "$NGINX_NEW_HTTP2" = "1.25.1" ]; then
    NGINX_HTTP2_MODE="directive"
  fi
fi
if [ -f "$NGINX_AVAIL" ] && grep -q "$DOMAIN" "$NGINX_AVAIL"; then
  # On ne reecrit jamais un vhost en place : on signale simplement les changements.
  if [ -f "$DEPLOY_DIR/nginx.conf" ]; then
    TMP_NGINX="$(mktemp)"
    sed \
      -e "s|gemini.example.fr|$DOMAIN|g" \
      -e "s|/opt/gemini-perso|$APP_DIR|g" \
      -e "s|127.0.0.1:8001|127.0.0.1:$BACKEND_PORT|g" \
      "$DEPLOY_DIR/nginx.conf" > "$TMP_NGINX"
    if [ "$NGINX_HTTP2_MODE" = "directive" ]; then
      sed -i \
        -e "s|^\( *\)listen 443 ssl http2;|\1listen 443 ssl;\n\1http2 on;|" \
        -e "s|^\( *\)listen \[::\]:443 ssl http2;|\1listen [::]:443 ssl;|" \
        "$TMP_NGINX"
    fi
    if diff -q "$TMP_NGINX" "$NGINX_AVAIL" >/dev/null 2>&1; then
      c_ok "vhost Nginx a jour"
    else
      c_warn "vhost Nginx different du gabarit — comparez avant d'appliquer :"
      c_info "  diff -u $NGINX_AVAIL $TMP_NGINX"
      c_info "  sudo nginx -t && sudo systemctl reload nginx"
    fi
    rm -f "$TMP_NGINX"
  fi
  nginx -t && systemctl reload nginx && c_ok "Nginx recharge"
else
  c_warn "vhost Nginx absent ou domaine non detecte — rien a recharger."
fi

c_step "Mise a jour terminee"
cat <<EOF
  Journal en direct   : journalctl -u $SERVICE -f
  Nouvelles variables : nano $ENV_FILE
  Retour arriere      : git checkout <sha> && sudo bash upgrade.sh --no-pull
  Sauvegarde .env     : $ENV_FILE.bak-$STAMP
EOF
