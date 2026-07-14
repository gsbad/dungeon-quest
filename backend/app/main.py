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
    # Stage K12's ~22 new potions/elixirs (game/items.py) - price only, same
    # as the original 3 above (the other fields on those 3 - heal_hp_frac/
    # heal_mana_frac/cures - aren't numeric-override candidates, and neither
    # is a K12 potion's "buff" field, which names a STATUS_EFFECTS id rather
    # than holding a tunable number).
    "item.potion_black.price": 100, "item.potion_orange.price": 100, "item.potion_purple.price": 100,
    "item.potion_white.price": 100, "item.potion_green.price": 100, "item.potion_darkblue.price": 100,
    "item.potion_yellow.price": 100, "item.potion_gray.price": 120, "item.potion_silver.price": 120,
    "item.potion_brown.price": 120, "item.potion_darkred.price": 150, "item.potion_violet.price": 150,
    "item.potion_ruby.price": 150, "item.potion_cyan.price": 100, "item.potion_pink.price": 100,
    "item.potion_gold.price": 250, "item.potion_turquoise.price": 250, "item.elixir_crimson.price": 400,
    "item.elixir_arcane.price": 400, "item.elixir_guardian.price": 400, "item.elixir_hunter.price": 400,
    "item.elixir_champion.price": 600,
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
    # Stage K16: monster combat stats + xp/gold-per-kill, one line per etype
    # (same dotted-key shape as item/difficulty/spell above).
    "monster.goblin.strength": 3, "monster.goblin.dexterity": 0, "monster.goblin.vigor": 0, "monster.goblin.luck": 0, "monster.goblin.weapon_base": 5.5, "monster.goblin.base_speed": 110, "monster.goblin.base_xp": 8, "monster.goblin.gold_drop": 3,
    "monster.skeleton.strength": 10, "monster.skeleton.dexterity": 0, "monster.skeleton.vigor": 2, "monster.skeleton.luck": 0, "monster.skeleton.weapon_base": 3, "monster.skeleton.base_speed": 70, "monster.skeleton.base_xp": 10, "monster.skeleton.gold_drop": 4,
    "monster.dark_knight.strength": 12, "monster.dark_knight.dexterity": 0, "monster.dark_knight.vigor": 8, "monster.dark_knight.luck": 0, "monster.dark_knight.weapon_base": 10, "monster.dark_knight.base_speed": 55, "monster.dark_knight.base_xp": 25, "monster.dark_knight.gold_drop": 10,
    "monster.aranha.strength": 4, "monster.aranha.dexterity": 8, "monster.aranha.vigor": 2, "monster.aranha.luck": 0, "monster.aranha.weapon_base": 4, "monster.aranha.base_speed": 100, "monster.aranha.base_xp": 9, "monster.aranha.gold_drop": 4,
    "monster.serpente.strength": 5, "monster.serpente.dexterity": 6, "monster.serpente.vigor": 2, "monster.serpente.luck": 0, "monster.serpente.weapon_base": 5, "monster.serpente.base_speed": 90, "monster.serpente.base_xp": 9, "monster.serpente.gold_drop": 4,
    "monster.treant.strength": 10, "monster.treant.dexterity": 0, "monster.treant.vigor": 12, "monster.treant.luck": 0, "monster.treant.weapon_base": 5, "monster.treant.base_speed": 40, "monster.treant.base_xp": 20, "monster.treant.gold_drop": 8,
    "monster.troll.strength": 9, "monster.troll.dexterity": 0, "monster.troll.vigor": 10, "monster.troll.luck": 0, "monster.troll.weapon_base": 6, "monster.troll.base_speed": 55, "monster.troll.base_xp": 20, "monster.troll.gold_drop": 8,
    "monster.death_knight.strength": 14, "monster.death_knight.dexterity": 2, "monster.death_knight.vigor": 12, "monster.death_knight.luck": 0, "monster.death_knight.weapon_base": 11, "monster.death_knight.base_speed": 55, "monster.death_knight.base_xp": 28, "monster.death_knight.gold_drop": 11,
    "monster.zumbi.strength": 8, "monster.zumbi.dexterity": 0, "monster.zumbi.vigor": 8, "monster.zumbi.luck": 0, "monster.zumbi.weapon_base": 6, "monster.zumbi.base_speed": 40, "monster.zumbi.base_xp": 16, "monster.zumbi.gold_drop": 6,
    "monster.verme.strength": 5, "monster.verme.dexterity": 2, "monster.verme.vigor": 4, "monster.verme.luck": 0, "monster.verme.weapon_base": 4, "monster.verme.base_speed": 70, "monster.verme.base_xp": 14, "monster.verme.gold_drop": 6,
    "monster.imp.strength": 3, "monster.imp.dexterity": 6, "monster.imp.vigor": 2, "monster.imp.luck": 0, "monster.imp.weapon_base": 4, "monster.imp.base_speed": 100, "monster.imp.base_xp": 18, "monster.imp.gold_drop": 7,
    "monster.dark_horse.strength": 10, "monster.dark_horse.dexterity": 8, "monster.dark_horse.vigor": 6, "monster.dark_horse.luck": 0, "monster.dark_horse.weapon_base": 7, "monster.dark_horse.base_speed": 130, "monster.dark_horse.base_xp": 24, "monster.dark_horse.gold_drop": 9,
    "monster.acolito.strength": 3, "monster.acolito.dexterity": 0, "monster.acolito.vigor": 4, "monster.acolito.luck": 0, "monster.acolito.weapon_base": 6, "monster.acolito.base_speed": 65, "monster.acolito.base_xp": 20, "monster.acolito.gold_drop": 8,
    "monster.feiticeira.strength": 4, "monster.feiticeira.dexterity": 2, "monster.feiticeira.vigor": 5, "monster.feiticeira.luck": 0, "monster.feiticeira.weapon_base": 8, "monster.feiticeira.base_speed": 70, "monster.feiticeira.base_xp": 26, "monster.feiticeira.gold_drop": 10,
    "monster.fire_hound.strength": 7, "monster.fire_hound.dexterity": 6, "monster.fire_hound.vigor": 5, "monster.fire_hound.luck": 0, "monster.fire_hound.weapon_base": 6, "monster.fire_hound.base_speed": 120, "monster.fire_hound.base_xp": 22, "monster.fire_hound.gold_drop": 9,
    "monster.ogro.strength": 16, "monster.ogro.dexterity": 0, "monster.ogro.vigor": 14, "monster.ogro.luck": 0, "monster.ogro.weapon_base": 10, "monster.ogro.base_speed": 50, "monster.ogro.base_xp": 28, "monster.ogro.gold_drop": 11,
    "monster.elemental_pedra.strength": 12, "monster.elemental_pedra.dexterity": 0, "monster.elemental_pedra.vigor": 18, "monster.elemental_pedra.luck": 0, "monster.elemental_pedra.weapon_base": 8, "monster.elemental_pedra.base_speed": 35, "monster.elemental_pedra.base_xp": 30, "monster.elemental_pedra.gold_drop": 12,
    "monster.chimera.strength": 14, "monster.chimera.dexterity": 6, "monster.chimera.vigor": 14, "monster.chimera.luck": 0, "monster.chimera.weapon_base": 10, "monster.chimera.base_speed": 75, "monster.chimera.base_xp": 32, "monster.chimera.gold_drop": 13,
    "monster.lyzardman.strength": 10, "monster.lyzardman.dexterity": 8, "monster.lyzardman.vigor": 7, "monster.lyzardman.luck": 0, "monster.lyzardman.weapon_base": 8, "monster.lyzardman.base_speed": 100, "monster.lyzardman.base_xp": 24, "monster.lyzardman.gold_drop": 9,
    "monster.dark_skeleton.strength": 13, "monster.dark_skeleton.dexterity": 6, "monster.dark_skeleton.vigor": 9, "monster.dark_skeleton.luck": 15, "monster.dark_skeleton.weapon_base": 9, "monster.dark_skeleton.base_speed": 60, "monster.dark_skeleton.base_xp": 28, "monster.dark_skeleton.gold_drop": 11,
    # Stage K16: debuffs (the original 7) and buffs (Stage K12's ~22 potions/
    # elixirs) share game/status_effects.py's STATUS_EFFECTS dict and
    # StatusEffectDef shape - split into two dotted-key prefixes here purely
    # for the admin panel's Buffs/Debuffs tabs (K17), same underlying table.
    # Only non-default fields are listed (StatusEffectDef defaults to 1.0/0.0
    # for every percentage axis) - an absent field for an effect just means
    # "this effect never touches that axis", same as the code's own defaults.
    "debuff.poison.duration": 12.0, "debuff.poison.tick_damage": 3, "debuff.poison.tick_interval": 5.0,
    "debuff.slow.duration": 12.0, "debuff.slow.speed_mult": 0.55,
    "debuff.weakness.duration": 12.0, "debuff.weakness.damage_taken_mult": 1.3,
    "debuff.burn.duration": 6.0, "debuff.burn.tick_damage": 2, "debuff.burn.tick_interval": 2.0,
    "debuff.chill.duration": 6.0, "debuff.chill.speed_mult": 0.85,
    "debuff.heat.duration": 8.0, "debuff.heat.tick_damage": 1, "debuff.heat.tick_interval": 4.0, "debuff.heat.speed_mult": 0.9,
    "debuff.shock.duration": 5.0, "debuff.shock.damage_taken_mult": 1.15,
    "buff.buff_black.duration": 180.0, "buff.buff_black.magic_defense_mult": 1.15,
    "buff.buff_orange.duration": 180.0, "buff.buff_orange.physical_damage_mult": 1.15,
    "buff.buff_purple.duration": 180.0, "buff.buff_purple.magic_damage_mult": 1.15,
    "buff.buff_white.duration": 180.0, "buff.buff_white.speed_mult": 1.15,
    "buff.buff_green.duration": 180.0, "buff.buff_green.max_hp_mult": 1.15,
    "buff.buff_darkblue.duration": 180.0, "buff.buff_darkblue.max_mana_mult": 1.15,
    "buff.buff_yellow.duration": 180.0, "buff.buff_yellow.attack_speed_mult": 1.15,
    "buff.buff_gray.duration": 180.0, "buff.buff_gray.physical_defense_mult": 1.15,
    "buff.buff_silver.duration": 180.0, "buff.buff_silver.debuff_resist_add": 0.2,
    "buff.buff_brown.duration": 180.0, "buff.buff_brown.physical_defense_mult": 1.2,
    "buff.buff_darkred.duration": 180.0, "buff.buff_darkred.physical_damage_mult": 1.2,
    "buff.buff_violet.duration": 180.0, "buff.buff_violet.magic_damage_mult": 1.2,
    "buff.buff_ruby.duration": 180.0, "buff.buff_ruby.crit_chance_add": 0.1,
    "buff.buff_cyan.duration": 180.0, "buff.buff_cyan.mana_regen_mult": 1.2,
    "buff.buff_pink.duration": 180.0, "buff.buff_pink.hp_regen_mult": 1.2,
    "buff.buff_gold.duration": 300.0, "buff.buff_gold.xp_gain_mult": 1.2,
    "buff.buff_turquoise.duration": 300.0, "buff.buff_turquoise.gold_gain_mult": 1.2,
    "buff.elixir_crimson.duration": 300.0, "buff.elixir_crimson.physical_damage_mult": 1.1, "buff.elixir_crimson.max_hp_mult": 1.1,
    "buff.elixir_arcane.duration": 300.0, "buff.elixir_arcane.magic_damage_mult": 1.1, "buff.elixir_arcane.max_mana_mult": 1.1,
    "buff.elixir_guardian.duration": 300.0, "buff.elixir_guardian.physical_defense_mult": 1.1, "buff.elixir_guardian.max_hp_mult": 1.1,
    "buff.elixir_hunter.duration": 300.0, "buff.elixir_hunter.speed_mult": 1.1, "buff.elixir_hunter.attack_speed_mult": 1.1,
    "buff.elixir_champion.duration": 120.0, "buff.elixir_champion.speed_mult": 1.1, "buff.elixir_champion.physical_damage_mult": 1.1, "buff.elixir_champion.magic_damage_mult": 1.1, "buff.elixir_champion.physical_defense_mult": 1.1, "buff.elixir_champion.magic_defense_mult": 1.1, "buff.elixir_champion.crit_chance_add": 0.05, "buff.elixir_champion.attack_speed_mult": 1.1, "buff.elixir_champion.max_hp_mult": 1.1, "buff.elixir_champion.max_mana_mult": 1.1,
    # Stage K16: Posturas (Stage K11) - game/stances.py's STANCES, one line
    # per profession (name field excluded, display-only).
    "stance.Guerreiro.physical_damage_mult": 1.15, "stance.Guerreiro.physical_defense_mult": 1.1,
    "stance.Assassino.speed_mult": 1.2, "stance.Assassino.crit_chance_add": 0.15,
    "stance.Mago.max_mana_mult": 1.2, "stance.Mago.mana_regen_mult": 1.25,
    "stance.Feiticeiro.magic_damage_mult": 1.2, "stance.Feiticeiro.debuff_chance_add": 0.1,
    "stance.Cavaleiro.max_hp_mult": 1.25, "stance.Cavaleiro.damage_taken_mult": 0.9,
    "stance.Duelista.physical_damage_mult": 1.1, "stance.Duelista.attack_speed_mult": 1.1, "stance.Duelista.dodge_chance_add": 0.05,
    "stance.Cavaleiro Arcano.magic_damage_mult": 1.1, "stance.Cavaleiro Arcano.max_mana_mult": 1.1, "stance.Cavaleiro Arcano.mana_cost_mult": 0.9,
    "stance.Paladino.physical_damage_mult": 1.1, "stance.Paladino.debuff_resist_add": 0.15, "stance.Paladino.hp_regen_flat_pct": 0.02,
    "stance.Campeao.max_hp_mult": 1.2, "stance.Campeao.physical_damage_mult": 1.1, "stance.Campeao.physical_defense_mult": 1.1,
    "stance.Monge.mana_regen_mult": 1.2, "stance.Monge.attack_speed_mult": 1.1, "stance.Monge.mana_cost_mult": 0.85,
    "stance.Xama.debuff_chance_add": 0.15, "stance.Xama.speed_mult": 1.1, "stance.Xama.magic_damage_mult": 1.1,
    "stance.Ranger.speed_mult": 1.15, "stance.Ranger.crit_chance_add": 0.1, "stance.Ranger.hp_regen_flat_pct": 0.02,
    "stance.Arcanista.magic_damage_mult": 1.25, "stance.Arcanista.mana_regen_mult": 1.2,
    "stance.Druida.hp_regen_flat_pct": 0.02, "stance.Druida.mana_regen_flat_pct": 0.02, "stance.Druida.speed_mult": 1.1, "stance.Druida.max_hp_mult": 1.1,
    "stance.Templario.damage_taken_mult": 0.85, "stance.Templario.debuff_resist_add": 0.2, "stance.Templario.hp_regen_flat_pct": 0.03,
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


# Stage J8: same duplication reasoning as BALANCE_DEFAULTS above (this
# backend never gets game/ copied to it, even on the deployed VM - see
# project_oracle_cloud_deploy memory) - a minimal, read-only reimplementation
# of game/achievements.py's ACHIEVEMENTS/check_unlocks() just to COUNT how
# many are unlocked for the leaderboard. Values must mirror the real
# definitions (5 difficulty tiers + these 9) or the count will drift.
_LEADERBOARD_DIFFICULTY_ORDER = ["normal", "hard", "very_hard", "nightmare", "inferno"]
_LEADERBOARD_STORY_BOSSES = ("orc_warlord", "necromancer", "shadow_king")
_LEADERBOARD_SECRET_BOSS = "cacodemon"
_LEADERBOARD_MAX_LEVEL = 30


def _count_achievements(state: dict) -> int:
    try:
        prog = state.get("progression", {})
        counters = state.get("counters", {})
        cleared = set(prog.get("cleared_difficulties", []))
        boss_kills = counters.get("boss_kills", {})
        total_kills = sum(counters.get("kills", {}).values())
        count = sum(1 for d in _LEADERBOARD_DIFFICULTY_ORDER if d in cleared)
        if counters.get("deaths", 0) > 0:
            count += 1
        if total_kills >= 100:
            count += 1
        if total_kills >= 500:
            count += 1
        if state.get("gold", 0) >= 1000:
            count += 1
        if any(c >= 50 for c in state.get("inventory", {}).values()):
            count += 1
        if counters.get("playtime_s", 0) >= 3600:
            count += 1
        if state.get("character", {}).get("level", 1) >= _LEADERBOARD_MAX_LEVEL:
            count += 1
        if all(boss_kills.get(b, 0) > 0 for b in _LEADERBOARD_STORY_BOSSES):
            count += 1
        if boss_kills.get(_LEADERBOARD_SECRET_BOSS, 0) > 0:
            count += 1
        return count
    except (TypeError, AttributeError):
        # A malformed/partial blob must never break the whole leaderboard -
        # this row just sorts as 0 for the achievements column.
        return 0


_LEADERBOARD_SORT_KEYS = {
    "level": lambda state: state.get("character", {}).get("level", 1),
    "playtime": lambda state: state.get("counters", {}).get("playtime_s", 0.0),
    "achievements": _count_achievements,
    "gold": lambda state: state.get("gold", 0),
}


@app.get("/leaderboard")
def get_leaderboard(sort: str = "level"):
    """Public, no auth - read-only ranking, same reasoning as /balance. Only
    users with a SaveRow (synced to the cloud at least once) ever appear -
    a fully offline/never-logged-in save has no row in this table at all,
    so "offline play doesn't update the rank" falls out for free instead
    of needing an explicit check."""
    if sort not in _LEADERBOARD_SORT_KEYS:
        raise HTTPException(status_code=400, detail=f"unknown sort '{sort}', use one of {list(_LEADERBOARD_SORT_KEYS)}")
    key_fn = _LEADERBOARD_SORT_KEYS[sort]
    with get_session() as session:
        rows = (
            session.query(User, SaveRow)
            .join(SaveRow, SaveRow.user_id == User.id)
            .all()
        )
    entries = []
    for user, save_row in rows:
        try:
            state = json.loads(save_row.blob)
        except (json.JSONDecodeError, TypeError):
            continue
        entries.append({
            "name": state.get("character", {}).get("name") or user.name or user.email,
            "value": key_fn(state),
        })
    entries.sort(key=lambda e: e["value"], reverse=True)
    return {"sort": sort, "entries": entries[:50]}


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
