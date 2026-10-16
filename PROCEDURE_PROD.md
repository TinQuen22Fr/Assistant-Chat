# Déploiement production avec `install.sh` et `upgrade.sh`

Procédure pour déployer **Gemini Perso** sur la Dedibox, domaine **`gemini-memory-assistant.quentin-astro.fr`**.

> Architecture : `Navigateur → Nginx (443) → /  : frontend/build (statique)` · `→ /api : uvicorn 127.0.0.1:8001 → MongoDB 127.0.0.1:27017`

---

## 1. Prérequis serveur

À exécuter en **root** sur la Dedibox :

```bash
apt update
apt install -y nginx certbot python3-certbot-nginx python3 python3-venv git curl

# Node.js (version LTS, ex. 22)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs

# MongoDB (ex. 7.0 sur Ubuntu 24.04)
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-7.gpg
echo "deb [signed-by=/usr/share/keyrings/mongodb-7.gpg] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/7.0 multiverse" \
  | tee /etc/apt/sources.list.d/mongodb-org-7.0.list
apt update && apt install -y mongodb-org

# Démarrer MongoDB
systemctl enable --now mongod
systemctl status mongod --no-pager
```

**Indispensable avant la suite :**
- Le DNS **A** de `gemini-memory-assistant.quentin-astro.fr` doit pointer vers l'IP publique de la Dedibox (sinon certbot échoue).
- MongoDB doit être **démarré** (sinon `gemini-perso.service` plante).

---

## 2. Cloner le dépôt

```bash
mkdir -p /opt/gemini-perso
cd /opt/gemini-perso
git clone https://github.com/TinQuen22Fr/Assistant-Chat.git .
```

---

## 3. Fournir le `.env` de production (via SSH)

Les fichiers `.env.example` ne sont **pas** versionnés dans Git. Le `.env` réel doit donc être copié depuis votre poste **avant** de lancer `install.sh`.

```bash
# Depuis VOTRE poste (pas la Dedibox) :
scp backend/.env root@<IP_DEDIBOX>:/opt/gemini-perso/backend/.env
```

Puis **sur la Dedibox**, adapter les clés suivantes au domaine de production :

```bash
cd /opt/gemini-perso
nano backend/.env
chmod 600 backend/.env
```

Clés à adapter (les valeurs indiquent la cible prod) :

```ini
PUBLIC_URL=https://gemini-memory-assistant.quentin-astro.fr
FRONTEND_URL=https://gemini-memory-assistant.quentin-astro.fr
GOOGLE_REDIRECT_URI=https://gemini-memory-assistant.quentin-astro.fr/api/auth/google/callback
CORS_ORIGINS=https://gemini-memory-assistant.quentin-astro.fr
COOKIE_SECURE=true
MONGO_URL=mongodb://127.0.0.1:27017
FILES_DIR=/var/lib/gemini-perso/files
```

> `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` restent identiques (même projet Google Cloud).
> Si `GOOGLE_REDIRECT_URI` est absent, le backend la déduit de `PUBLIC_URL`. Renseignez quand même `PUBLIC_URL` pour rester explicite derrière Nginx.

---

## 4. Installer

```bash
cd /opt/gemini-perso
bash install.sh --domain gemini-memory-assistant.quentin-astro.fr --branch Make-With-Forge
```

Ce que fait `install.sh` :
1. Bascule sur la branche `Make-With-Forge` (ou `--branch` explicite).
2. Crée l'utilisateur système `gemini`, le venv Python, installe `backend/requirements.txt`.
3. **Ne touche pas** au `.env` déjà présent (ne l'écrase jamais).
4. Construit le frontend (`npm ci` + `npm run build`).
5. Installe le service systemd `gemini-perso`, le redémarre, vérifie `/api/`.
6. Configure Nginx : vhost HTTP temporaire pour l'ACME challenge → certbot (`--webroot`) → vhost HTTPS complet multi-host (sans écraser le site `default`).

---

## 5. Vérifier l'installation

```bash
systemctl status gemini-perso --no-pager
journalctl -u gemini-perso -f          # Ctrl+C pour sortir
curl -s http://127.0.0.1:8001/api/     # doit répondre (JSON)
nginx -t
curl -sI https://gemini-memory-assistant.quentin-astro.fr/api/
```

---

## 6. Google OAuth (à faire une fois dans la console Google)

Ajouter exactement cette URI dans **Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs** (client `185430846163-g4btb243vpkk7vimjo5k3lq0hob33426`) :

```
https://gemini-memory-assistant.quentin-astro.fr/api/auth/google/callback
```

Protocole, domaine et trailing slash doivent correspondre exactement, sinon `redirect_uri_mismatch`.

---

## 7. Mises à jour futures (upgrade)

```bash
cd /opt/gemini-perso
bash upgrade.sh
```

Variantes :

```bash
bash upgrade.sh --branch Make-With-Forge   # branche explicite
bash upgrade.sh --no-pull                  # sans toucher à git (reconstruit seulement)
```

Ce que fait `upgrade.sh` :
1. `git fetch` + bascule sur la branche + mise à jour `--hard` (sauf `--no-pull`).
2. Synchronise `backend/.env` de façon **non destructive** : ajoute uniquement les clés manquantes, sans écraser les valeurs existantes, avec sauvegarde horodatée.
3. Met à jour les dépendances Python, reconstruit le frontend.
4. Compare le service systemd **sans l'écraser**, redémarre le service, vérifie `/api/`.
5. Recharge Nginx et signale (sans appliquer) les éventuelles différences du vhost.

---

## 8. Dépannage rapide

| Symptôme | Piste |
|---|---|
| 502 Bad Gateway | `systemctl status gemini-perso`, `journalctl -u gemini-perso -n 100` |
| Service en échec au démarrage | MongoDB non démarré : `systemctl status mongod` |
| certbot échoue | DNS absent / port 80 non accessible : vérifier le A et Nginx |
| « redirect_uri_mismatch » | URI Google Console ≠ `GOOGLE_REDIRECT_URI` |
| Déconnexion immédiate | `COOKIE_SECURE=true` requis en HTTPS ; vérifier `CORS_ORIGINS`/`FRONTEND_URL` |
