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

## 3. Fournir le `.env` de production (directement sur le serveur)

Tout se fait **sur la Dedibox**. Le `.env` de production est recupere par un simple `cp` depuis le **workspace Forge du serveur** vers le repertoire cible.

Le workspace Forge du serveur contient deja le `.env` de production (depose par Forge). Il suffit de le copier a l'emplacement attendu :

```bash
# Copie directe depuis le workspace Forge du serveur :
cp /var/www/forge/workspace/Assistant-Chat/backend/.env /opt/gemini-perso/.env.production
```

`install.sh` cherche un `.env` dans cet ordre (le premier trouve est copie vers `backend/.env`, sans jamais ecraser un `.env` existant) :

1. `--env-source <fichier>` (chemin absolu sur la Dedibox)
2. `/opt/gemini-perso/.env.production`
3. `/var/www/forge/workspace/Assistant-Chat/backend/.env` (workspace Forge du serveur)
4. `backend/.env.example` (gabarit, a verifier ensuite)

> Le chemin du workspace Forge est surchargeable :
> `sudo bash install.sh --forge-workspace /var/www/forge/workspace/Assistant-Chat ...`
>
> Le dépôt étant cloné par `quentin` dans `/opt/gemini-perso`, `install.sh` et
> `upgrade.sh` remettent `backend/` et `venv/` au nom de l'utilisateur `gemini`
> avant toute écriture (sinon `python3 -m venv` échoue en « Permission denied »).

Clés à renseigner/vérifier avant lancement (valeurs cible prod) :

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
# avec un .env à un autre emplacement :
# sudo bash install.sh --env-source /chemin/vers/env.backend ...
```

Ce que fait `install.sh` :
1. Déclare `/opt/gemini-perso` comme dépôt sûr pour git (`safe.directory`) puis bascule sur la branche `Make-With-Forge` (ou `--branch` explicite).
2. Crée l'utilisateur système `gemini`, donne à `gemini` la propriété de `backend/` et de `venv/` (le dépôt peut avoir été cloné par `quentin` : `chown` récursif avant toute écriture), crée le venv Python, installe `backend/requirements.txt`.
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
| `Permission denied: '/opt/gemini-perso/venv'` | dépôt cloné par un autre utilisateur : relancer `sudo bash install.sh` (le script remet `backend/` et `venv/` à `gemini`) |
| `detected dubious ownership` | relancer `sudo bash install.sh` (ajout automatique de `safe.directory`) |
