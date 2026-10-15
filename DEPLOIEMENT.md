# Déployer Gemini Perso sur une Dedibox (Ubuntu 24.04 / Debian 12)

Ce guide installe Gemini Perso sur un serveur Dedibox (Scaleway) derrière **Nginx** en **HTTPS**, avec **MongoDB**, un backend **FastAPI** géré par **systemd** et le frontend **Vite** servi en fichiers statiques.

> Architecture : `Navigateur → Nginx (443) → /  : frontend/build (statique)`
> `                                      → /api : uvicorn 127.0.0.1:8001 → MongoDB 127.0.0.1:27017`

Remplacez partout `gemini.example.fr` par votre domaine et `vous@example.fr` par votre e-mail.

---

## 1. Préparer le serveur

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl unzip nginx certbot python3-certbot-nginx ufw
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
sudo adduser --system --group --home /opt/gemini-perso gemini
```

Faites pointer un enregistrement DNS **A** (et **AAAA** si IPv6) de `gemini.example.fr` vers l'IP de la Dedibox.

## 2. Installer Python (3.12 à 3.14)

Ubuntu 24.04 fournit Python 3.12 (`sudo apt install -y python3-venv`). Pour une autre version, le plus simple est **uv** :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
sudo uv python install 3.12        # ou 3.13 / 3.14
```

## 3. Installer MongoDB 7

```bash
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-7.gpg
echo "deb [signed-by=/usr/share/keyrings/mongodb-7.gpg] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/7.0 multiverse" \
  | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update && sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
```

(Debian 12 : remplacez la ligne `deb` par `https://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main`.)
MongoDB écoute par défaut uniquement sur `127.0.0.1` : ne l'exposez pas sur Internet.

## 4. Installer Node.js 20 et Yarn (pour construire le frontend)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs && sudo corepack enable
```

## 5. Récupérer le code

```bash
sudo -u gemini git clone <URL-de-votre-dépôt> /opt/gemini-perso/app
# ou copiez le dossier du projet (backend/, frontend/, deploy/, DEPLOIEMENT.md) dans /opt/gemini-perso/app
sudo ln -s /opt/gemini-perso/app/backend  /opt/gemini-perso/backend
sudo ln -s /opt/gemini-perso/app/frontend /opt/gemini-perso/frontend
```

## 6. Backend : environnement Python et configuration

```bash
cd /opt/gemini-perso
sudo -u gemini uv venv -p 3.12 /opt/gemini-perso/venv          # ou : python3 -m venv venv
sudo -u gemini VIRTUAL_ENV=/opt/gemini-perso/venv uv pip install -r backend/requirements-selfhost.txt
# (sans uv : sudo -u gemini venv/bin/pip install -r backend/requirements-selfhost.txt)

sudo -u gemini cp backend/.env.example backend/.env
sudo -u gemini nano backend/.env
sudo mkdir -p /var/lib/gemini-perso/files && sudo chown -R gemini:gemini /var/lib/gemini-perso
```

Variables essentielles dans `backend/.env` :

| Variable | Rôle |
|---|---|
| `MONGO_URL`, `DB_NAME` | Connexion MongoDB (`mongodb://127.0.0.1:27017`, `gemini_perso`) |
| `JWT_SECRET` | Secret de signature des sessions — `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `CORS_ORIGINS`, `FRONTEND_URL` | `https://gemini.example.fr` |
| `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax`, `COOKIE_DOMAIN=` | Cookies de session (HTTPS obligatoire) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Votre compte, créé/mis à jour à chaque démarrage |
| `GEMINI_API_KEY` | Clé Google AI Studio (voir section 12) — **obligatoire** |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Connexion Google (section 11), optionnel |
| `FILES_DIR` | `/var/lib/gemini-perso/files` (pièces jointes) |
| `HISTORY_CHAR_BUDGET` | Taille d'historique avant résumé automatique (60000) |

Test rapide :

```bash
cd /opt/gemini-perso/backend && sudo -u gemini ../venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
curl -s http://127.0.0.1:8001/api/   # → {"message":"Gemini Perso API","provider":"google-genai"}
```

## 7. Frontend : build de production

```bash
cd /opt/gemini-perso/frontend
sudo -u gemini yarn install --frozen-lockfile
sudo -u gemini yarn build        # génère frontend/build/
```

Ne définissez **pas** `VITE_BACKEND_URL` / `REACT_APP_BACKEND_URL` : le frontend appellera alors `/api` sur le même domaine.

## 8. Service systemd

```bash
sudo cp /opt/gemini-perso/app/deploy/gemini-perso.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now gemini-perso
sudo systemctl status gemini-perso
journalctl -u gemini-perso -f     # journaux
```

## 9. Nginx + HTTPS (certbot)

```bash
sudo mkdir -p /var/www/certbot
# 1) obtenir le certificat (Nginx par défaut doit répondre sur le port 80)
sudo certbot certonly --nginx -d gemini.example.fr -m vous@example.fr --agree-tos -n
# 2) installer la configuration fournie
sudo cp /opt/gemini-perso/app/deploy/nginx.conf /etc/nginx/sites-available/gemini-perso
sudo sed -i 's/gemini.example.fr/VOTRE_DOMAINE/g' /etc/nginx/sites-available/gemini-perso
sudo ln -s /etc/nginx/sites-available/gemini-perso /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Points importants de `deploy/nginx.conf` :
- `client_max_body_size 250M` : imports Google Takeout volumineux ;
- `proxy_buffering off` + `proxy_read_timeout 600s` sur `/api/` : affichage progressif (SSE) des réponses ;
- `try_files … /index.html` : routes de l'application (`/c/…`, `/memoire`, `/importer`).

Le renouvellement du certificat est automatique (`systemctl list-timers | grep certbot`).

## 10. Sauvegardes et mises à jour

**Sauvegardes** (MongoDB + fichiers joints) avec `deploy/backup.sh` :

```bash
sudo apt install -y mongodb-database-tools
sudo chmod +x /opt/gemini-perso/app/deploy/backup.sh
sudo crontab -e
# 30 3 * * * /opt/gemini-perso/app/deploy/backup.sh >> /var/log/gemini-perso-backup.log 2>&1
```

Restauration :

```bash
mongorestore --uri="mongodb://127.0.0.1:27017" --gzip --archive=/var/backups/gemini-perso/<date>/mongo.archive.gz --drop
sudo tar -xzf /var/backups/gemini-perso/<date>/files.tar.gz -C /var/lib/gemini-perso
```

Copiez régulièrement `/var/backups/gemini-perso` hors du serveur (Dedibox Backup/FTP, rsync, S3…). Pensez aussi à sauvegarder `backend/.env`.

**Mise à jour** :

```bash
cd /opt/gemini-perso/app && sudo -u gemini git pull
sudo -u gemini VIRTUAL_ENV=/opt/gemini-perso/venv uv pip install -r backend/requirements-selfhost.txt
cd frontend && sudo -u gemini yarn install --frozen-lockfile && sudo -u gemini yarn build
sudo systemctl restart gemini-perso
```

**Alternative Docker** : `deploy/docker-compose.yml` lance MongoDB + backend (port 127.0.0.1:8001) ; Nginx de l'hôte reste configuré comme ci-dessus.

## 11. Créer votre identifiant Google OAuth (« Se connecter avec Google »)

1. Ouvrez la [Google Cloud Console](https://console.cloud.google.com/) et créez (ou sélectionnez) un projet.
2. **API et services → Écran de consentement OAuth** (« Google Auth Platform ») :
   - Type d'utilisateur : **Externe** ; nom de l'application « Gemini Perso » ; e-mail d'assistance ;
   - Domaine autorisé : `example.fr` (votre domaine racine) ;
   - Champs d'application : `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` ;
   - En mode **Test**, ajoutez votre adresse dans « Utilisateurs test » (ou publiez l'application).
3. **API et services → Identifiants → Créer des identifiants → ID client OAuth** :
   - Type : **Application Web** ;
   - Origines JavaScript autorisées : `https://gemini.example.fr` ;
   - **URI de redirection autorisés** : `https://gemini.example.fr/api/auth/google/callback`.
4. Copiez l'**ID client** et le **Code secret** dans `backend/.env` :

```env
GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
GOOGLE_REDIRECT_URI=https://gemini.example.fr/api/auth/google/callback
```

5. `sudo systemctl restart gemini-perso`. Le bouton « Se connecter avec Google » utilise alors votre propre client OAuth. Sans ces variables (et sans `EMERGENT_LLM_KEY`), le bouton Google est simplement masqué et seule la connexion e-mail/mot de passe est proposée. Un compte Google et un compte e-mail/mot de passe ayant la même adresse sont automatiquement liés.

## 12. Clé Gemini et facturation

1. Créez une clé sur [Google AI Studio → API keys](https://aistudio.google.com/apikey) (rattachée à un projet Google Cloud).
2. Renseignez-la dans `GEMINI_API_KEY` puis redémarrez le service. Au démarrage, `GET /api/` doit indiquer `"provider":"google-genai"`.
3. **Quotas** : l'offre gratuite est limitée et **Gemini 3.1 Pro n'y est généralement pas disponible** (erreur 429 « Quota exceeded … FreeTier »). Dans ce cas l'application affiche « Quota Google dépassé pour ce modèle » et propose de réessayer avec Gemini 3 Flash.
4. Pour lever ces limites : AI Studio → **Billing** (ou Cloud Console → Facturation) → associez un compte de facturation au projet de la clé. Suivez votre consommation dans AI Studio (« Usage ») et définissez une alerte budgétaire dans la Cloud Console.
5. Coût indicatif : chaque réponse déclenche aussi 1 à 2 petits appels Gemini 3 Flash (titre, résumé de discussion, extraction de mémoire). Les fichiers joints sont renvoyés au modèle à chaque tour de la discussion.

## 13. Dépannage

| Symptôme | Piste |
|---|---|
| 502 Bad Gateway | `systemctl status gemini-perso`, `journalctl -u gemini-perso -n 100` |
| Réponses affichées d'un bloc | vérifier `proxy_buffering off` sur `location /api/` |
| « 413 Request Entity Too Large » | `client_max_body_size 250M` dans le bloc `server` HTTPS |
| Déconnexion immédiate après login | HTTPS obligatoire avec `COOKIE_SECURE=true` ; vérifier `CORS_ORIGINS`/`FRONTEND_URL` |
| Erreur Google « redirect_uri_mismatch » | l'URI de la console doit être identique à `GOOGLE_REDIRECT_URI` |
