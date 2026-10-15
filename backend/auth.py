import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from db import db

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=7)
MAX_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


# ---------- helpers ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _token(user_id: str, kind: str, ttl: timedelta) -> str:
    payload = {"sub": user_id, "type": kind, "exp": datetime.now(timezone.utc) + ttl}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def _cookie_opts() -> dict:
    opts = {
        "httponly": True,
        "secure": os.environ.get("COOKIE_SECURE", "true").lower() == "true",
        "samesite": os.environ.get("COOKIE_SAMESITE", "lax"),
        "path": "/",
    }
    if os.environ.get("COOKIE_DOMAIN"):
        opts["domain"] = os.environ["COOKIE_DOMAIN"]
    return opts


def set_auth_cookies(response: Response, user_id: str) -> None:
    opts = _cookie_opts()
    response.set_cookie("access_token", _token(user_id, "access", ACCESS_TTL),
                        max_age=int(ACCESS_TTL.total_seconds()), **opts)
    response.set_cookie("refresh_token", _token(user_id, "refresh", REFRESH_TTL),
                        max_age=int(REFRESH_TTL.total_seconds()), **opts)


def clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token"):
        response.delete_cookie(name, path="/", domain=os.environ.get("COOKIE_DOMAIN") or None)


def public_user(user: dict) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name") or user["email"].split("@")[0],
        "picture": user.get("picture"),
        "auth_providers": user.get("auth_providers", []),
    }


def _decode(token: str, kind: str) -> str:
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Jeton invalide.")
    if payload.get("type") != kind:
        raise HTTPException(401, "Type de jeton invalide.")
    return payload["sub"]


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization", "")
    if not token and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        raise HTTPException(401, "Non authentifié.")
    user = await db.users.find_one({"user_id": _decode(token, "access")}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "Utilisateur introuvable.")
    return user


async def upsert_google_user(email: str, name: str | None, picture: str | None) -> dict:
    email = email.lower().strip()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        update = {"$addToSet": {"auth_providers": "google"}}
        fields = {k: v for k, v in {"picture": picture, "name": existing.get("name") or name}.items() if v}
        if fields:
            update["$set"] = fields
        await db.users.update_one({"email": email}, update)
        return await db.users.find_one({"email": email}, {"_id": 0})
    user = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": email,
        "name": name or email.split("@")[0],
        "picture": picture,
        "auth_providers": ["google"],
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(dict(user))
    return user


def google_mode() -> str:
    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        return "oauth"
    return "disabled"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


# ---------- models ----------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ---------- email / password ----------

@router.get("/config")
async def auth_config():
    return {"google_mode": google_mode()}


@router.post("/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing and existing.get("password_hash"):
        raise HTTPException(409, "Un compte existe déjà avec cette adresse e-mail.")
    if existing:
        await db.users.update_one(
            {"email": email},
            {"$set": {"password_hash": hash_password(body.password)}, "$addToSet": {"auth_providers": "password"}},
        )
        user = await db.users.find_one({"email": email}, {"_id": 0})
    else:
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": email,
            "name": body.name.strip() or email.split("@")[0],
            "picture": None,
            "password_hash": hash_password(body.password),
            "auth_providers": ["password"],
            "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(dict(user))
    set_auth_cookies(response, user["user_id"])
    return public_user(user)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.lower()
    identifier = f"{_client_ip(request)}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    now = datetime.now(timezone.utc)
    if attempt and attempt.get("locked_until"):
        locked = attempt["locked_until"]
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if locked > now:
            raise HTTPException(429, "Trop de tentatives. Réessayez dans 15 minutes.")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        count = (attempt or {}).get("count", 0) + 1
        update = {"count": count, "locked_until": now + LOCKOUT if count >= MAX_ATTEMPTS else None}
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")

    await db.login_attempts.delete_one({"identifier": identifier})
    set_auth_cookies(response, user["user_id"])
    return public_user(user)


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "Non authentifié.")
    user = await db.users.find_one({"user_id": _decode(token, "refresh")}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Utilisateur introuvable.")
    set_auth_cookies(response, user["user_id"])
    return public_user(user)


# ---------- Google: own OAuth2 client (self-hosted) ----------

def _frontend_url(path: str = "/") -> str:
    return os.environ["FRONTEND_URL"].rstrip("/") + path


@router.get("/google/login")
async def google_login():
    if google_mode() != "oauth":
        raise HTTPException(404, "OAuth Google non configuré.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    resp.set_cookie("oauth_state", state, max_age=600, **_cookie_opts())
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, code: str = "", state: str = ""):
    fail = RedirectResponse(_frontend_url("/login?erreur=google"))
    if google_mode() != "oauth" or not code or state != request.cookies.get("oauth_state"):
        return fail
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
            "grant_type": "authorization_code",
        })
        if token_res.status_code != 200:
            return fail
        info_res = await client.get(
            GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token_res.json()['access_token']}"}
        )
    info = info_res.json() if info_res.status_code == 200 else {}
    if not info.get("email") or not info.get("email_verified"):
        return fail
    user = await upsert_google_user(info["email"], info.get("name"), info.get("picture"))
    resp = RedirectResponse(_frontend_url("/"))
    resp.delete_cookie("oauth_state", path="/")
    set_auth_cookies(resp, user["user_id"])
    return resp


async def seed_test_user():
    email = os.environ["ADMIN_EMAIL"].lower()
    password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing is None:
        await db.users.update_one({"email": email}, {"$setOnInsert": {
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": email,
            "name": "Utilisateur Test",
            "picture": None,
            "password_hash": hash_password(password),
            "auth_providers": ["password"],
            "created_at": datetime.now(timezone.utc),
        }}, upsert=True)
    elif not existing.get("password_hash") or not verify_password(password, existing["password_hash"]):
        await db.users.update_one(
            {"email": email},
            {"$set": {"password_hash": hash_password(password)}, "$addToSet": {"auth_providers": "password"}},
        )
