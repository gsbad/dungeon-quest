import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from app.models import SaveRow, User, get_session, init_db

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_ALGORITHM = "HS256"
JWT_TTL_S = 60 * 60 * 24 * 30  # 30 days


def _load_jwt_secret() -> str:
    """JWT_SECRET env var wins (that's how Stage I9's systemd EnvironmentFile
    sets it in production). For local dev, persist a generated secret next to
    this file so `uvicorn` restarts don't invalidate every JWT already handed
    out to a running pygbag tab (backend/.jwt_secret_dev, gitignored)."""
    env_secret = os.environ.get("JWT_SECRET")
    if env_secret:
        return env_secret
    secret_path = Path(__file__).resolve().parent.parent / ".jwt_secret_dev"
    if secret_path.exists():
        return secret_path.read_text().strip()
    secret = secrets.token_hex(32)
    secret_path.write_text(secret)
    return secret


JWT_SECRET = _load_jwt_secret()

app = FastAPI(title="Dungeon Quest Backend")
init_db()

# Stage I9 will add the deployed HTTPS origin here once it exists; the LAN
# entry lets the phone's pygbag tab (192.168.100.19:8001) call this API even
# though Google's own OAuth origin check won't accept that origin (plain
# http, non-localhost) - login stays PC-only until Stage I9, but non-auth
# endpoints work from the phone from day one.
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://192.168.100.19:8001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    # "*" alone does NOT cover Authorization - the Fetch/CORS spec
    # special-cases it and always requires it listed explicitly, wildcard
    # or not. This was the real cause of "missing bearer token" surviving
    # 5 structurally different header-construction attempts in
    # game/net.py's emscripten fetch() call: the browser was silently
    # dropping the header before preflight ever approved the real request,
    # so no amount of Python/JS interop rework could have fixed it.
    allow_headers=["*", "Authorization", "Content-Type"],
)


class GoogleAuthRequest(BaseModel):
    id_token: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/google")
def auth_google(body: GoogleAuthRequest):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured on server")
    try:
        claims = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid Google id_token")

    google_sub = claims["sub"]
    email = claims.get("email", "")
    name = claims.get("name", "")

    # Upsert rather than insert-only: a returning user's email/name can have
    # changed since their first login (Google account rename, etc.), and
    # google_sub is the stable identity to key on, not email.
    with get_session() as session:
        user = session.query(User).filter_by(google_sub=google_sub).one_or_none()
        if user is None:
            user = User(google_sub=google_sub, email=email, name=name)
            session.add(user)
        else:
            user.email = email
            user.name = name
        session.commit()

    now = int(time.time())
    payload = {
        "sub": google_sub,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + JWT_TTL_S,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"jwt": token, "email": email, "name": name}


def _extract_token(authorization: str | None, token: str | None) -> str:
    """Header wins when both are present (native/urllib branch in game/net.py
    still sends Authorization and works fine headless). The `token` query
    param is the emscripten branch's transport: 6 structurally different
    ways of attaching an Authorization header from inside pygbag's fetch()/
    XMLHttpRequest all had the browser silently drop the header before it
    ever left the page (confirmed via DevTools Network tab - no CORS block,
    no service worker, no extension), so the browser build stops depending
    on headers being deliverable at all and puts the JWT in the URL
    instead."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    if token:
        return token
    raise HTTPException(status_code=401, detail="missing bearer token")


def _decode_bearer(authorization: str | None, token: str | None = None) -> dict:
    raw = _extract_token(authorization, token)
    try:
        return jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")


def _current_user(authorization: str | None, token: str | None = None) -> User:
    claims = _decode_bearer(authorization, token)
    with get_session() as session:
        user = session.query(User).filter_by(google_sub=claims["sub"]).one_or_none()
        if user is None:
            # Can only happen if a JWT outlives its user row (never deleted
            # today) or was forged against the right secret but a sub that
            # never actually logged in - treat both as unauthenticated.
            raise HTTPException(status_code=401, detail="unknown user")
        session.expunge(user)
        return user


@app.get("/me")
def me(authorization: str | None = Header(default=None), token: str | None = None):
    user = _current_user(authorization, token)
    return {"email": user.email, "name": user.name}


class SaveBody(BaseModel):
    state: dict[str, Any]


@app.get("/save")
def get_save(authorization: str | None = Header(default=None), token: str | None = None):
    user = _current_user(authorization, token)
    with get_session() as session:
        row = session.query(SaveRow).filter_by(user_id=user.id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="no save on server yet")
        return {"state": json.loads(row.blob), "updated_at": row.updated_at}


@app.put("/save")
def put_save(body: SaveBody, authorization: str | None = Header(default=None), token: str | None = None):
    user = _current_user(authorization, token)
    now = time.time()
    with get_session() as session:
        row = session.query(SaveRow).filter_by(user_id=user.id).one_or_none()
        if row is None:
            row = SaveRow(user_id=user.id, blob=json.dumps(body.state), updated_at=now)
            session.add(row)
        else:
            row.blob = json.dumps(body.state)
            row.updated_at = now
        session.commit()
    return {"updated_at": now}
