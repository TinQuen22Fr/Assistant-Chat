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
#   sudo bash install.sh --env-source /opt/gemini-perso/backend/.env
#   sudo bash install.sh --forge-workspace /var/www/forge/workspace/Assistant-Chat
#   sudo bash install.sh --email quentin.dumont.22@gmail.com   # email certbot/ACME
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
# Workspace Forge sur le serveur : contient le .env de production a copier.
FORGE_WORKSPACE="${FORGE_WORKSPACE:-/var/www/forge/workspace/Assistant-Chat}"
# Branche de travail GitHub : les ajouts/corrections futurs y seront merges.
WORK_BRANCH="${WORK_BRANCH:-Make-With-Forge}"

BRANCH="${BRANCH:-}"
ENV_SOURCE="${ENV_SOURCE:-}"
# Email transmis a certbot (ACME). Priorite : --email > $CERTBOT_EMAIL >
# ADMIN_EMAIL du .env > CERTBOT_EMAIL_FALLBACK. Sert seulement aux
# notifications d'expiration du certificat.
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_EMAIL_FALLBACK="${CERTBOT_EMAIL_FALLBACK:-quentin.dumont.22@gmail.com}"
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
    --env-source)  ENV_SOURCE="${2:-}"; shift ;;
    --forge-workspace) FORGE_WORKSPACE="${2:-}"; shift ;;
    --email)       CERTBOT_EMAIL="${2:-}"; shift ;;
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
c_info "Workspace Forge: $FORGE_WORKSPACE (source .env)"

# --- Branche de travail GitHub -----------------------------------------------
# Detection automatique : la branche de travail du depot (WORK_BRANCH) est
# utilisee si elle existe sur origin ; sinon on conserve la branche courante.
# Le depot peut avoir ete clone par un utilisateur non-root (ex. quentin) :
# on declare le dossier sur pour git afin d'eviter "dubious ownership".
git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" ||
  git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
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

# Nginx >= 1.25.1 : la directive "listen ... http2" est depreciee, il faut une
# directive "http2 on;" separee. On detecte la version pour generer un vhost
# sans warning sur les Nginx recents tout en restant compatible 1.18 -> 1.24.
NGINX_HTTP2_MODE="listen"
if command -v nginx >/dev/null 2>&1; then
  NGINX_VERSION="$(nginx -v 2>&1 | sed -n 's#.*nginx/\([0-9][0-9.]*\).*#\1#p')"
  NGINX_NEW_HTTP2="$(printf '%s\n%s\n' "1.25.1" "$NGINX_VERSION" | sort -V | head -1)"
  if [ -n "$NGINX_VERSION" ] && [ "$NGINX_NEW_HTTP2" = "1.25.1" ]; then
    NGINX_HTTP2_MODE="directive"
  fi
  c_ok "Nginx $NGINX_VERSION detecte (mode http2 : $NGINX_HTTP2_MODE)."
fi

# --- Utilisateur systeme ------------------------------------------------------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  c_info "Creation de l'utilisateur systeme $APP_USER ..."
  adduser --system --group --home "$APP_DIR" "$APP_USER"
else
  c_ok "Utilisateur $APP_USER deja present."
fi
mkdir -p "$DATA_DIR/files"
chown -R "$APP_USER":"$APP_USER" "$DATA_DIR"

# Le depot peut avoir ete clone par un autre utilisateur (ex. quentin) : les
# repertoires dans lesquels l'utilisateur applicatif ecrit doivent lui
# appartenir, sinon python3 -m venv echoue en "Permission denied".
chown -R "$APP_USER":"$APP_USER" "$BACKEND_DIR" 2>/dev/null || true
install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$VENV_DIR"
chown -R "$APP_USER":"$APP_USER" "$VENV_DIR" 2>/dev/null || true

# --- Backend : venv + dependances ---------------------------------------------
c_info "Backend : environnement virtuel ..."
if [ ! -x "$VENV_DIR/bin/python" ]; then
  sudo -u "$APP_USER" env PIP_NO_CACHE_DIR=1 python3 -m venv "$VENV_DIR"
  c_ok "venv cree dans $VENV_DIR"
else
  c_ok "venv deja present."
fi
# Le HOME de l'utilisateur systeme peut pointer sur un dossier appartenant a un
# autre utilisateur : pip tenterait d'y ecrire son cache et emettrait un
# WARNING. On rend le cache explicite et accessible, propriete de $APP_USER.
PIP_CACHE_DIR="${PIP_CACHE_DIR:-$APP_DIR/.cache/pip}"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$PIP_CACHE_DIR"
sudo -u "$APP_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" "$VENV_DIR/bin/pip" install --upgrade pip --quiet
sudo -u "$APP_USER" env PIP_CACHE_DIR="$PIP_CACHE_DIR" "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
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

env_key() { # file key -> valeur (vide si absente), lecture seule
  python3 - "$1" "$2" <<'PY'
import sys, re, pathlib
f, k = sys.argv[1], sys.argv[2]
p = pathlib.Path(f)
if not p.exists():
    sys.exit(0)
for line in p.read_text().splitlines():
    m = re.match(rf'^(?:export\s+)?{re.escape(k)}=(.*)$', line.strip())
    if m:
        v = m.group(1).strip().strip('"').strip("'")
        print(v)
        break
PY
}

# --- Helpers de verification ---------------------------------------------------
# Le port par defaut (8001) est aussi utilise par d'autres services du serveur
# (API Forge). Sans ces controles, uvicorn echouait en "address already in use"
# ET le health-check interrogeait l'API du voisin, qui repondait 200 : succes
# affiche alors que notre service ne tournait pas.
port_in_use() { # port -> 0 si un processus ecoute deja
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

api_is_ours() { # url -> 0 si la reponse porte bien la signature de notre API
  curl -fsS -m 5 "$1" 2>/dev/null | grep -q '"Gemini Perso API"'
}

ENV_FILE="$BACKEND_DIR/.env"

# Le .env de production est fourni directement sur le serveur. Tout se fait
# sur place, sur la Dedibox. Sources possibles, dans l'ordre :
#   1. --env-source <fichier>            (chemin absolu sur la Dedibox)
#   2. $APP_DIR/.env.production          (depose dans /opt/gemini-perso)
#   3. $FORGE_WORKSPACE/backend/.env     (workspace Forge du serveur)
#   4. $BACKEND_DIR/.env.example         (gabarit, valeurs a verifier ensuite)
ENV_FROM_SOURCE=0
ENV_FROM_TEMPLATE=0
if [ ! -f "$ENV_FILE" ]; then
  if [ -n "$ENV_SOURCE" ]; then
    [ -f "$ENV_SOURCE" ] || die "ENV_SOURCE introuvable : $ENV_SOURCE"
    c_info "Copie du .env depuis $ENV_SOURCE ..."
    install -o "$APP_USER" -g "$APP_USER" -m 600 "$ENV_SOURCE" "$ENV_FILE"
    ENV_FROM_SOURCE=1
  elif [ -f "$APP_DIR/.env.production" ]; then
    c_info "Copie du .env depuis $APP_DIR/.env.production ..."
    install -o "$APP_USER" -g "$APP_USER" -m 600 "$APP_DIR/.env.production" "$ENV_FILE"
    ENV_FROM_SOURCE=1
  elif [ -f "$FORGE_WORKSPACE/backend/.env" ]; then
    c_info "Copie du .env depuis le workspace Forge : $FORGE_WORKSPACE/backend/.env ..."
    install -o "$APP_USER" -g "$APP_USER" -m 600 "$FORGE_WORKSPACE/backend/.env" "$ENV_FILE"
    ENV_FROM_SOURCE=1
  elif [ -f "$BACKEND_DIR/.env.example" ]; then
    c_warn ".env absent : creation depuis .env.example (VERIFIEZ ses valeurs)"
    cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ENV_FROM_TEMPLATE=1
  else
    die "Aucun .env fourni. Deposez $APP_DIR/.env.production, le workspace Forge ($FORGE_WORKSPACE/backend/.env) ou passez --env-source <fichier>, puis relancez."
  fi
fi

# Seul un .env cree depuis le gabarit est complete. Un .env copie depuis une
# source (workspace Forge, .env.production, --env-source) est preserve tel quel :
# ses secrets et valeurs ne sont jamais ecrases.
if [ "$ENV_FROM_TEMPLATE" = "1" ]; then
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
elif [ "$ENV_FROM_SOURCE" = "1" ]; then
  c_ok ".env copie depuis une source (preserve tel quel, non modifie)."
else
  c_ok ".env deja present (non modifie)."
fi
chmod 600 "$ENV_FILE" 2>/dev/null || true
# --- Frontend : build de production -------------------------------------------
c_info "Frontend : installation des dependances ..."
# npm tourne en tant que $APP_USER. Deux pieges apres une execution precedente
# en root : le cache npm (frontend/.npmrc -> ../.npm-cache) et node_modules
# appartiennent a root. npm echoue alors en
# "EACCES: mkdir /opt/gemini-perso/.npm-cache" et laisse un node_modules
# partiel (TAR_ENTRY_ERROR ENOENT / ENOTEMPTY cleanup). On force donc un cache
# explicite propriete de $APP_USER et on purge node_modules avant installation
# (root peut supprimer des fichiers appartenant a root, gemini non).
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
c_info "Frontend : build Vite ..."
(cd "$FRONTEND_DIR" && sudo -u "$APP_USER" env npm_config_cache="$NPM_CACHE_DIR" npm run build)
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

# --- Backend : controle MONGO_URL (hote resolvable) -----------------------------
MONGO_HOST="$(env_key "$ENV_FILE" MONGO_URL | sed -E 's#^[a-z+]+://##; s#^[^@]*@##; s#[/?:,].*$##')"
if [ -n "$MONGO_HOST" ]; then
  if python3 -c 'import socket,sys; socket.gethostbyname(sys.argv[1])' "$MONGO_HOST" >/dev/null 2>&1; then
    c_ok "MONGO_URL : hote '$MONGO_HOST' resolu."
  else
    c_warn "MONGO_URL : hote '$MONGO_HOST' NON resolvable. Corrigez $ENV_FILE (echec au demarrage : Name or service not known)."
  fi
fi

# --- Controle du port avant redemarrage -----------------------------------------
# Si le port est tenu par un service etranger, on echoue explicitement au lieu de
# tenter un demarrage condamne ("address already in use") et de valider a tort.
if port_in_use "$BACKEND_PORT" && ! api_is_ours "http://127.0.0.1:${BACKEND_PORT}/api/"; then
  die "Port $BACKEND_PORT deja occupe par un autre service (reponse etrangere). Liberez-le ou relancez avec --port <autre port>."
fi

# --- Redemarrage + verification -------------------------------------------------
c_info "Redemarrage de $SERVICE_NAME ..."
systemctl restart "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME" || {
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager
  die "$SERVICE_NAME ne demarre pas."
}
# Un service en boucle de redemarrage est "active" un court instant : on laisse
# passer quelques secondes puis on controle le compteur systemd, sinon un crash
# (Mongo injoignable) est rapporte comme un succes.
sleep 3
NRESTARTS="$(systemctl show "$SERVICE_NAME" -p NRestarts --value 2>/dev/null || echo 0)"
if ! systemctl is-active --quiet "$SERVICE_NAME" || [ "${NRESTARTS:-0}" -gt 0 ]; then
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager
  die "$SERVICE_NAME instable (NRestarts=${NRESTARTS:-0}) : corrigez $ENV_FILE (MONGO_URL, secrets) puis relancez."
fi
c_ok "service actif (stable)"

URL="http://127.0.0.1:${BACKEND_PORT}/api/"
OK=0
for _ in $(seq 1 15); do
  if api_is_ours "$URL"; then OK=1; break; fi
  sleep 1
done
if [ "$OK" = "1" ]; then
  c_ok "API /api/ repond et porte la signature 'Gemini Perso API'."
else
  c_warn "API /api/ injoignable ou reponse inattendue — journalctl -u $SERVICE_NAME -n 50"
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
    # ADMIN_EMAIL n'est defini que si le .env a ete cree depuis le gabarit : on
    # le relit depuis le .env pour les installations dont le .env vient d'une
    # source (sinon "unbound variable" sous set -u).
    EMAIL="${CERTBOT_EMAIL:-}"
    if [ -z "$EMAIL" ] && [ -f "$ENV_FILE" ]; then
      EMAIL="$(env_key "$ENV_FILE" ADMIN_EMAIL)"
      [ "$EMAIL" = "admin@example.fr" ] && EMAIL=""
      [ "$EMAIL" = "admin@local.dev" ] && EMAIL=""
    fi
    if [ -z "$EMAIL" ] && [ -t 0 ]; then
      read -r -p "Email pour certbot (Let's Encrypt) [$CERTBOT_EMAIL_FALLBACK] : " EMAIL
    fi
    EMAIL="${EMAIL:-$CERTBOT_EMAIL_FALLBACK}"
    if [ -n "$EMAIL" ]; then
      CERT_ARGS+=(-m "$EMAIL")
      c_info "Email ACME : $EMAIL"
    else
      c_warn "Aucun email ACME : enregistrement sans notification d'expiration."
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
    TMP_NGINX="$(mktemp)"
    sed \
      -e "s|gemini.example.fr|$DOMAIN|g" \
      -e "s|/opt/gemini-perso|$APP_DIR|g" \
      -e "s|127.0.0.1:8001|127.0.0.1:$BACKEND_PORT|g" \
      "$DEPLOY_DIR/nginx.conf" > "$TMP_NGINX"
    if [ "$NGINX_HTTP2_MODE" = "directive" ]; then
      # Nginx recent : "listen 443 ssl;" + "http2 on;" (pas de warning).
      sed -i \
        -e "s|^\( *\)listen 443 ssl http2;|\1listen 443 ssl;\n\1http2 on;|" \
        -e "s|^\( *\)listen \[::\]:443 ssl http2;|\1listen [::]:443 ssl;|" \
        "$TMP_NGINX"
    fi
    mv "$TMP_NGINX" "$NGINX_AVAIL"
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
