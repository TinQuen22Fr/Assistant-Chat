# Rapport d'expertise — Assistant-Chat

**Branche** : `Make-With-Forge`
**Dépôt** : `TinQuen22Fr/Assistant-Chat`
**Date** : analyse en lecture seule (aucune modification appliquée)

---

## 1. Constat global

Le clone est un **squelette UI + mock**. La mémoire, le gestionnaire de contexte et le résumé roulant sont réels, mais le « cerveau » est factice : `backend/llm_provider.py` renvoie des réponses codées en dur et n'appelle **jamais** Google.

**Conséquence** : tout ce qui touche aux modèles et aux niveaux d'effort n'a aucun effet tant que la vraie connexion à l'API Gemini n'est pas rétablie.

---

## 2. État des lieux par composant

| Composant | État constaté | Impact |
|---|---|---|
| `backend/llm_provider.py` | **100 % mock** (`stream_chat` → « Reçu… », « Arthur », « ZEBRE-7731 ») | **Bloquant** : le LLM est factice |
| `backend/auth.py` | OAuth scope `openid email profile` uniquement, token jeté après `userinfo` | **Bloquant** : aucun token Google Gemini conservé |
| `backend/requirements.txt` | `google-genai` absent (présent dans le venv mais non déclaré) | Reproductibilité cassée |
| `backend/chat.py` | Aucun champ `effort` dans les schémas et routes | À ajouter |
| `backend/memory.py` | Mémoire + résumé + contexte permanent solides | Peu de refactor, à reconnecter au vrai LLM |
| `frontend/src/components/ModelSelect.jsx` | Liste codée en dur (2 modèles), ignore `GET /api/models` | À brancher sur l'API |
| Fallback | Existe (`code: quota` + `retryWithFlash`) mais cible `flash` au lieu de `3.1 Pro` | À corriger |

---

## 3. Plan d'exécution (10 étapes)

### Étape 1 — Réactiver le provider Google GenAI
- **Objectif** : remplacer le mock par un vrai appel SDK `google-genai`.
- **Fichiers** : `backend/llm_provider.py`, `backend/requirements.txt`
- **Actions** :
  - Ajouter `google-genai` à `requirements.txt`.
  - Réécrire `stream_chat()` pour itérer sur `generate_content_stream`.
  - Réécrire `generate_text()` (titres, résumés, mémoires) via le même chemin réel.
  - Supprimer toutes les branches mock.
  - Ajouter une détection `is_quota_error()` (HTTP 429).
- **Vérification** : un message reçoit une réponse **non mock**.

### Étape 2 — Conserver le token Google + élargir le scope
- **Objectif** : fournir un token utilisable par l'API Gemini.
- **Fichiers** : `backend/auth.py`
- **Actions** :
  - Ajouter le scope génératif Gemini à l'OAuth.
  - Demander `access_token` + `refresh_token` (`access_type=offline`, `prompt=consent`).
  - Stocker les tokens dans le document `users` (chiffrés).
  - Ajouter `get_google_credentials(user_id)` avec rafraîchissement.
- **Vérification** : les champs token apparaissent en base sans être exposés.

### Étape 3 — Config des modèles + fallback
- **Objectif** : aligner sur `gemini.google.com/app`.
- **Fichiers** : `backend/llm_provider.py`
- **Actions** :
  - `MODELS` : `pro` = `gemini-3-pro-preview`, `flash` = `gemini-3-flash-preview`, fallback = `gemini-3.1-pro-preview`.
  - `EFFORTS` : `rapide → LOW`, `equilibre → MEDIUM`, `approfondi → HIGH`.
  - Exposer via `GET /api/models`.
- **Vérification** : la route renvoie 3 modèles + efforts.

### Étape 4 — Niveaux d'effort côté backend
- **Objectif** : persister et transmettre l'effort.
- **Fichiers** : `backend/chat.py`
- **Actions** :
  - Ajouter `effort: str = "equilibre"` à `ConversationCreate`/`ConversationPatch`.
  - Lire `effort` dans `send_message` / `regenerate`.
  - Propager dans `_stream_reply()`.
  - Persister dans `conversations` et `messages`.
- **Vérification** : l'effort survit au rechargement.

### Étape 5 — Transmission au SDK (`ThinkingConfig`)
- **Objectif** : donner un effet réel à l'effort.
- **Fichiers** : `backend/llm_provider.py`
- **Actions** :
  - Construire `ThinkingConfig(thinking_level=<niveau>)` selon l'effort.
  - Passer la config à `generate_content`.
- **Vérification** : `approfondi` produit une réponse plus réfléchie que `rapide`.

### Étape 6 — Fallback automatique « 3.1 Pro »
- **Objectif** : basculer en cas de coupure/quota.
- **Fichiers** : `backend/chat.py`, `frontend/src/hooks/useConversation.js`, `frontend/src/pages/ChatPage.jsx`
- **Actions** :
  - SSE : sur `429`, émettre `code: quota` avec cible `3.1 Pro` (au lieu de `flash`).
  - Front : `retryWithFlash` → `retryWithFallback` ciblant `3.1 Pro`.
- **Vérification** : le bouton propose et relance bien `3.1 Pro`.

### Étape 7 — Sélecteur de modèles dynamique
- **Objectif** : supprimer la liste codée en dur.
- **Fichiers** : `frontend/src/components/ModelSelect.jsx`
- **Actions** :
  - Charger `GET /api/models`.
  - Afficher les libellés officiels.
  - Conserver les `data-testid` existants.
- **Vérification** : plus aucune liste codée en dur.

### Étape 8 — Sélecteur de niveaux d'effort
- **Objectif** : ajouter l'UI Rapide / Équilibré / Approfondi.
- **Fichiers** : `ModelSelect.jsx` (+ éventuel `EffortSelect.jsx`), `TopBar.jsx`, `ChatPage.jsx`, `useConversation.js`
- **Actions** :
  - Ajouter l'état `effort` (défaut `equilibre`).
  - Propager dans `send()`, `regenerate()`, `setModel()`.
  - Calquer le rendu sur la capture officielle.
- **Vérification** : sélection persistée et visuel conforme.

### Étape 9 — Reconnexion mémoire/contexte au vrai LLM
- **Objectif** : valider la chaîne complète avec le vrai modèle.
- **Fichiers** : `backend/memory.py` (vérification, refactor léger)
- **Actions** :
  - Vérifier que titres, résumés et mémoires passent par le vrai chemin.
  - Confirmer le budget de contexte et le résumé roulant.
- **Vérification** : résumé et mémoire se créent après réponse réelle.

### Étape 10 — Tests + validation globale
- **Objectif** : consolider sans régression.
- **Fichiers** : `backend/tests/` (nouveaux cas)
- **Actions** :
  - Tests : validation `effort`, persistance, `/models`, fallback, `is_quota_error`.
  - Lancer toute la suite.
- **Vérification** :

```bash
cd backend && .venv/bin/pytest -n 0
cd frontend && npm run build
```

- **Critère** : tout vert, 0 warning.

---

## 4. Dépendances et ordre d'exécution

- `1 ⇄ 2` : provider réel et token Google sont **inséparables**.
- `3 → 4 → 5` : config → schéma → SDK.
- `6` requiert `3` + `4`.
- `7` requiert `3`.
- `8` requiert `4` + `7`.
- `9` requiert `1`.
- `10` requiert tout.

**Ordre conseillé** : `2 → 1 → 3 → 4 → 5 → 7 → 8 → 6 → 9 → 10`.

---

## 5. Points non vérifiables en lecture seule

1. **Nom exact du scope Gemini** et de `ThinkingLevel`/`ThinkingConfig` dans la version précise de `google-genai` installée.
2. **Libellés exacts des niveaux d'effort** (Rapide/Équilibré/Approfondi vs Low/Medium/High).
3. **Identifiants exacts des modèles** (`gemini-3-pro-preview` vs alias SDK).
4. **Quota réel** du compte Google : le fallback ne se valide qu'en conditions réelles (429).
5. **Chiffrement des tokens Google en base** (choix AES/champ JWT non tranché).

---

## 6. Risques majeurs

- **Étapes 1–2** : les plus risquées et les plus importantes. Sans elles, les Étapes 3–8 ne produisent qu'une apparence.
- **Consommation de quota Google** : à surveiller.
- **Refresh token** : gestion obligatoire (expiration, rotation).
- **Secrets en base** : à chiffrer avant de stocker les tokens.

---

## 7. Décision requise avant de commencer

Confirmer le périmètre :

- **Option A** — UI/config uniquement (le mock reste).
- **Option B** — Intégration réelle Google GenAI (recommandé, correspond à ton objectif de « vrai clone fonctionnel »).

**Recommandation** : **Option B**, en commençant par les Étapes 2 puis 1.
