# Auth testing playbook (Gemini Perso)

## Email/password JWT
- Login: curl -c cookies.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"test@geminiperso.fr","password":"Test1234!"}'
- Then: curl -b cookies.txt $API/api/auth/me
- Cookies: access_token (15 min) + refresh_token (7 days), httpOnly, Secure, SameSite=Lax. Bearer access token also accepted.
- bcrypt hash in db.users.password_hash starts with $2b$. Indexes: users.email unique, users.user_id unique, login_attempts.identifier.
- Brute force: 5 failed attempts per ip:email -> 429 for 15 min.

## Google (Emergent-managed, preview)
- Button redirects to https://auth.emergentagent.com/?redirect=<origin>/ ; on return URL has #session_id=... ; frontend POSTs /api/auth/google/emergent {session_id} -> sets same JWT cookies.
- To simulate without Google: create a user in mongo with user_id, email, and login via email/password; Google flow itself cannot be fully automated.

## Data isolation
- All conversations/messages/files filtered by user_id. Another user's conversation id -> 404 "Discussion introuvable."; file id -> 404 "Fichier introuvable."
