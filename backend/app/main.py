import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

import jwt
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from app.models import BalanceConfig, SaveRow, User, get_session, init_db

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_ALGORITHM = "HS256"
JWT_TTL_S = 60 * 60 * 24 * 30  # 30 days
ADMIN_TOKEN_TTL_S = 60 * 60 * 12  # 12h - an admin session, not a player one

# Stage I4: balance admin panel. This backend runs isolated from game/ (the
# deployed VM only ever gets backend/app copied to it, never the game/
# package - see project_oracle_cloud_deploy memory), so these defaults are a
# deliberate, curated DUPLICATE of the current values in game/items.py,
# game/difficulty.py, game/spells.py, game/stats.py - not a cross-import.
# They're just the reference shown in the admin page; the actual
# authoritative defaults remain the ones in game/ (this dict only matters
# for what the admin page displays before an override exists - the /balance
# endpoint itself only ever returns overrides, never these defaults).
BALANCE_DEFAULTS = {
    "item.health_potion.price": 30, "item.mana_potion.price": 24, "item.antidote.price": 40,
    "item.max_stock": 50,
    "difficulty.normal.ml_bonus": 0, "difficulty.normal.champion_chance": 0.0, "difficulty.normal.boss_enrage_frac": 0.5,
    "difficulty.hard.ml_bonus": 6, "difficulty.hard.champion_chance": 0.08, "difficulty.hard.boss_enrage_frac": 0.55,
    "difficulty.very_hard.ml_bonus": 14, "difficulty.very_hard.champion_chance": 0.14, "difficulty.very_hard.boss_enrage_frac": 0.6,
    "difficulty.nightmare.ml_bonus": 24, "difficulty.nightmare.champion_chance": 0.20, "difficulty.nightmare.boss_enrage_frac": 0.65,
    "difficulty.inferno.ml_bonus": 36, "difficulty.inferno.champion_chance": 0.28, "difficulty.inferno.boss_enrage_frac": 0.7,
    "stats.mitigation_k": 120, "stats.xp_curve_base": 20, "stats.xp_curve_exp": 1.4,
    "stats.ml_growth_rate": 0.35, "stats.anti_farm_level_gap": 5, "stats.anti_farm_xp_mult": 0.1,
    "spell.fireball.mana_cost": 8, "spell.fireball.cooldown": 2.0, "spell.fireball.spell_base": 12,
    "spell.frost_nova.mana_cost": 12, "spell.frost_nova.cooldown": 3.0, "spell.frost_nova.spell_base": 14,
    "spell.healing_light.mana_cost": 15, "spell.healing_light.cooldown": 7.0, "spell.healing_light.heal_frac": 0.25,
}


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
# Same pattern as GOOGLE_CLIENT_ID - unset means the admin routes are simply
# unusable (500 "not configured") rather than defaulting to some guessable
# password.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app = FastAPI(title="Dungeon Quest Backend")
init_db()

# The LAN entry lets the phone's local-dev pygbag tab (192.168.100.19:8001)
# call this API even though Google's own OAuth origin check won't accept
# that origin (plain http, non-localhost) - login is PC-only for the local
# dev setup, but non-auth endpoints work from the phone there too. The
# deployed sslip.io origin (Stage I9) is same-origin with the game there
# (Caddy serves both), so CORS doesn't gate that path at all - listed here
# anyway for robustness/testing from other origins.
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://192.168.100.19:8001",
    "https://129.80.222.127.sslip.io",
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
    google_sub = claims.get("sub")
    if google_sub is None:
        # An admin token (see _require_admin) is a valid JWT signed with
        # the same JWT_SECRET but has no "sub" claim at all (it isn't a
        # player identity) - reusing it here must fail clean, not KeyError
        # into a raw 500.
        raise HTTPException(status_code=401, detail="not a player token")
    with get_session() as session:
        user = session.query(User).filter_by(google_sub=google_sub).one_or_none()
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


@app.get("/balance")
def get_balance():
    """Public, no auth - the game (game/net.py's trigger_balance_fetch())
    fetches this at boot regardless of login state. Only ever returns
    overrides that actually exist in the DB - an absent key means the
    caller's own code default stands, this endpoint never needs to know
    what those defaults even are."""
    with get_session() as session:
        rows = session.query(BalanceConfig).all()
        return {row.key: row.value for row in rows}


class AdminLoginBody(BaseModel):
    password: str


def _make_admin_token() -> str:
    now = int(time.time())
    return jwt.encode({"admin": True, "iat": now, "exp": now + ADMIN_TOKEN_TTL_S}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _require_admin(authorization: str | None) -> None:
    """Separate from _decode_bearer/_current_user on purpose - an admin
    token has no "sub"/email (it isn't a player identity) and a player JWT
    has no "admin" claim, so the two can never be confused or reused for
    each other even though they're signed with the same JWT_SECRET."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing admin token")
    try:
        claims = jwt.decode(authorization.removeprefix("Bearer "), JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired admin token")
    if not claims.get("admin"):
        raise HTTPException(status_code=403, detail="not an admin token")


@app.post("/admin/login")
def admin_login(body: AdminLoginBody):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD not configured on server")
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="invalid password")
    return {"token": _make_admin_token()}


@app.get("/admin/balance")
def get_balance_admin(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    with get_session() as session:
        rows = session.query(BalanceConfig).all()
        overrides = {row.key: row.value for row in rows}
    return {"defaults": BALANCE_DEFAULTS, "overrides": overrides}


class BalanceUpdateBody(BaseModel):
    values: dict[str, str]


@app.put("/admin/balance")
def put_balance_admin(body: BalanceUpdateBody, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    now = time.time()
    with get_session() as session:
        for key, value in body.values.items():
            row = session.query(BalanceConfig).filter_by(key=key).one_or_none()
            if row is None:
                row = BalanceConfig(key=key, value=value, updated_at=now)
                session.add(row)
            else:
                row.value = value
                row.updated_at = now
        session.commit()
    return {"ok": True}


_ADMIN_PAGE = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Dungeon Quest - Balanceamento</title>
<style>
body { font-family: monospace; background: #14141c; color: #ddd; padding: 24px; }
h1 { color: #e0b84c; }
table { border-collapse: collapse; width: 100%; max-width: 900px; }
td, th { border: 1px solid #444; padding: 6px 10px; text-align: left; }
th { background: #232330; }
input { width: 120px; background: #1e1e28; color: #ddd; border: 1px solid #555; padding: 4px; }
input.changed { border-color: #e0b84c; }
button { background: #e0b84c; color: #14141c; border: none; padding: 8px 18px; font-weight: bold; cursor: pointer; }
#login input { width: 220px; }
#status { margin-left: 12px; }
</style></head>
<body>
<h1>Dungeon Quest - Painel de Balanceamento</h1>
<div id="login">
  <input id="pw" type="password" placeholder="Senha de admin">
  <button onclick="doLogin()">Entrar</button>
  <span id="status"></span>
</div>
<div id="panel" style="display:none">
  <table id="tbl"><thead><tr><th>Chave</th><th>Default</th><th>Valor atual</th></tr></thead><tbody></tbody></table>
  <br><button onclick="doSave()">Salvar Tudo</button>
  <span id="save-status"></span>
</div>
<script>
const API = location.origin;
function token() { return sessionStorage.getItem("dq_admin_token"); }

async function doLogin() {
  const pw = document.getElementById("pw").value;
  const res = await fetch(API + "/admin/login", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({password: pw}),
  });
  if (!res.ok) {
    document.getElementById("status").textContent = "Senha invalida.";
    return;
  }
  const data = await res.json();
  sessionStorage.setItem("dq_admin_token", data.token);
  await loadBalance();
}

async function loadBalance() {
  const res = await fetch(API + "/admin/balance", {headers: {"Authorization": "Bearer " + token()}});
  if (!res.ok) {
    sessionStorage.removeItem("dq_admin_token");
    document.getElementById("status").textContent = "Sessao expirada, logue de novo.";
    return;
  }
  const data = await res.json();
  const tbody = document.querySelector("#tbl tbody");
  tbody.innerHTML = "";
  const keys = Object.keys(data.defaults).sort();
  for (const key of keys) {
    const def = data.defaults[key];
    const cur = data.overrides.hasOwnProperty(key) ? data.overrides[key] : String(def);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${key}</td><td>${def}</td><td><input data-key="${key}" value="${cur}"></td>`;
    tbody.appendChild(tr);
  }
  document.getElementById("login").style.display = "none";
  document.getElementById("panel").style.display = "block";
}

async function doSave() {
  const inputs = document.querySelectorAll("#tbl input");
  const values = {};
  inputs.forEach(inp => { values[inp.dataset.key] = inp.value; });
  const res = await fetch(API + "/admin/balance", {
    method: "PUT",
    headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token()},
    body: JSON.stringify({values}),
  });
  document.getElementById("save-status").textContent = res.ok ? "Salvo!" : "Erro ao salvar.";
}

if (token()) { loadBalance(); }
</script>
</body></html>"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return _ADMIN_PAGE
