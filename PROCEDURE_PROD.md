# Déploiement production avec `install.sh` et `upgrade.sh`

Procédure pour déployer **Gemini Perso** sur la Dedibox, domaine **`gemini-memory-assistant.quentin-astro.fr`**.

> Architecture : `Navigateur → Nginx (443) → /  : frontend/build (statique)` · `→ /api : uvicorn 127.0.0.1:8001 → MongoDB 127.0.0.1:27017`
>
> **Prérequis de compte** : un utilisateur non-root disposant des droits `sudo`. Les scripts `install.sh` et `upgrade.sh` exigent `root` (ils s'arrêtent si `id -u` != 0) ; ils doivent donc être lancés via `sudo bash ...`.

---

## 1. Prérequis serveur

À exécuter avec `sudo` sur la Dedibox :

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx python3 python3-venv git curl

# Node.js (version LTS, ex. 22)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt install -y nodejs

# MongoDB (ex. 7.0 sur Ubuntu 24.04)
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-7.gpg
echo "deb [signed-by=/usr/share/keyrings/mongodb-7.gpg] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/7.0 multiverse" \
  | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update && sudo apt install -y mongodb-org

# Démarrer MongoDB
sudo systemctl enable --now mongod
sudo systemctl status mongod --no-pager
```

**Indispensable avant la suite :**
- Le DNS **A** de `gemini-memory-assistant.quentin-astro.fr` doit pointer vers l'IP publique de la Dedibox (sinon certbot échoue).
- MongoDB doit être **démarré** (sinon `gemini-perso.service` plante).

---

## 2. Cloner le dépôt

```bash
sudo mkdir -p /opt/gemini-perso
sudo chown -R "$USER":"$USER" /opt/gemini-perso
cd /opt/gemini-perso
git clone --branch Make-With-Forge https://github.com/TinQuen22Fr/Assistant-Chat.git .
```

---

## 3. Fournir le `.env` de production (via SSH)

Les fichiers `.env.example` ne sont **pas** versionnés dans Git. Le `.env` réel doit donc être copié depuis votre poste **avant** de lancer `install.sh`.

```bash
# Depuis VOTRE poste (pas la Dedibox) :
scp backend/.env <USER>@<IP_DEDIBOX>:/tmp/gemini-perso.env
```

Puis **sur la Dedibox**, placer le fichier et adapter les clés suivantes au domaine de production :

```bash
sudo install -o "$USER" -g "$USER" -m 600 /tmp/gemini-perso.env /opt/gemini-perso/backend/.env
sudo rm -f /tmp/gemini-perso.env
cd /opt/gemini-perso
nano backend/.env
```

Clés à adapter (les valeurs indiquent la cible prod) :

```ini
PUBLIC_URL=https://gemini-memory-assistant.quentin-astro.fr
FRONTEND_URL=https://gemini-memory-assistant.quentin-astro.fr
GOOGLE_REDIRECT_URI=https://gemini-memory-assistant.quentin-astro.fr/api/auth/google/callback
CORS_ORIGINS=https://gemini-memory-assistant.quentin-astro.fr
COOKIE_SECURE=true
MONGO_URL=***REDACTED***
FILES_DIR=/var/lib/gemini-perso/files
```

> `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` restent identiques (même projet Google Cloud).
> Si `GOOGLE_REDIRECT_URI` est absent, le backend la déduit de `PUBLIC_URL`. Renseignez quand même `PUBLIC_URL` pour rester explicite derrière Nginx.

---

## 4. Installer

```bash
cd /opt/gemini-perso
sudo bash install.sh --domain gemini-memory-assistant.quentin-astro.fr --branch Make-With-Forge
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
sudo systemctl status gemini-perso --no-pager
sudo journalctl -u gemini-perso -f          # Ctrl+C pour sortir
curl -s http://127.0.0.1:8001/api/          # doit répondre (JSON)
sudo nginx -t
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
sudo bash upgrade.sh
```

Variantes :

```bash
sudo bash upgrade.sh --branch Make-With-Forge   # branche explicite
sudo bash upgrade.sh --no-pull                  # sans toucher à git (reconstruit seulement)
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
| 502 Bad Gateway | `sudo systemctl status gemini-perso`, `sudo journalctl -u gemini-perso -n 100` |
| Service en échec au démarrage | MongoDB non démarré : `sudo systemctl status mongod` |
| certbot échoue | DNS absent / port 80 non accessible : vérifier le A et Nginx |
| « redirect_uri_mismatch » | URI Google Console ≠ `GOOGLE_REDIRECT_URI` |
| Déconnexion immédiate | `COOKIE_SECURE=true` requis en HTTPS ; vérifier `CORS_ORIGINS`/`FRONTEND_URL` |
