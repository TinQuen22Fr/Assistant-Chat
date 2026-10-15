# Auth testing playbook (Gemini Perso)

## Email/password JWT
- Login: curl -c cookies.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}'
- Then: curl -b cookies.txt $API/api/auth/me
- Cookies: access_token (15 min) + refresh_token (7 days), httpOnly, Secure, SameSite=Lax. Bearer access token also accepted.
- bcrypt hash in db.users.password_hash starts with $2b$. Indexes: users.email unique, users.user_id unique, login_attempts.identifier.
- Brute force: 5 failed attempts per ip:email -> 429 for 15 min.

## Google (OAuth2 propre, auto-hébergé)
- Actif uniquement si GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET sont définis ; sinon /api/auth/config renvoie google_mode="disabled".
- Flux : GET /api/auth/google/login -> Google -> GET /api/auth/google/callback -> cookies JWT puis redirection vers FRONTEND_URL.
- Le flux Google ne peut pas être automatisé de bout en bout ; le tester manuellement.

## Data isolation
- All conversations/messages/files filtered by user_id. Another user's conversation id -> 404 "Discussion introuvable."; file id -> 404 "Fichier introuvable."
