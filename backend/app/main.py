import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

import jwt
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel

from app.models import AppearanceOverride, BalanceConfig, SaveRow, User, get_session, init_db

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
    # Stage K23: Dash (game/player.py's DASH_* constants) - not a mana-cost
    # SPELLS entry (no mana cost, gated on Destreza instead), but tunable
    # from the admin panel's Magias tab alongside the 3 above. "player" (not
    # "spell") prefix since it doesn't live in game/spells.py's SPELLS dict,
    # but the same 3-part player.dash.<field> shape as spell.<id>.<field> so
    # the admin page's groupEntities() renders it as its own "dash"
    # collapsible block instead of one unlabeled flat list.
    "player.dash.dex_req": 18, "player.dash.duration": 0.18, "player.dash.speed": 780, "player.dash.cooldown": 3.5,
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


# Stage K23: pre-rendered PNG snapshots of every monster/item's current
# PROCEDURAL sprite (game/assets.py's create_enemy_sprite()/
# create_potion_icon(), generated with no override active), so the admin
# panel's pixel editor (openPixelEditor() below) has something real to
# start from instead of a blank canvas for every entity that's never been
# manually overridden yet - which is every entity, on a fresh DB. This
# backend can't import pygame/game/ to render these live (runs isolated
# from game/ - see BALANCE_DEFAULTS above), so they're a static snapshot
# generated once with a local pygame and pasted in; a monster's 48x48
# sprite is downscaled to the editor's native 16x16 grid (lossy, but a
# starting point to paint over, not meant to be pixel-identical - items
# are already native 16x16, no downscale needed). Stale if create_*_sprite
# art changes later; regenerate by re-running the same snippet against a
# current checkout if that ever matters enough to bother.
SPRITE_DEFAULTS = {
    "monster.acolito": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAWElEQVQ4jWNgGGjAiEsiJ8LqLzJ/yopjzNjUMVHqApwGRKWkYGWjAxZ8puPTSNCAZXPmENTMwECFMMAaC+gxAAPYYoL6LsBlOy5XUNcFhGzH5gqKXTDwAADGgBVde0aGkQAAAABJRU5ErkJggg==",
    "monster.aranha": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA9klEQVQ4jWNgGAUUA2YGBgYGZTGtFb/+/Hzy++/PJ8RoYmVmk5YWVKj/++/PR7igOJ9MgayQcg8rM5s0TMxU0f6vqaL9X2TN6OoY0U2W4Jct/PXn55NnEly9Fr8lGRgYGBhOsD5n4Hv4wlqCX6bgxccnE77+/HQCpgfFAGSbsYmfvn+QGV2MRVlMayW64LVn56y0pIyOoWvGphYDyAop93Cz85rDXILsGmUxrRXIYYQCWJnZpGEKBLlFQwS5RUPQDWZlZpOWFVLuQZdjEOQWDZEVUu6BsTEUoBmCrB5uACHN6IawMrNJw7wKB9zsfBb4NJOqjigAACzXRqwqaGuyAAAAAElFTkSuQmCC",
    "monster.chimera": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAv0lEQVQ4jWNgoAdIjZEsQOYb6fKYe7sIBTMwMDAwEWOAsR6vhaQYmzSM7+smEgpjE2XA5l1vVs/sUV8F4/sgGcBIjAFPLlj9ReYf2f6ZobD/ptzzV7+eskiKsUk/f/XrKT4DZAyOMXclqaEYAtPDZKcrWMjPxSKNXSt2kNJzAs5mZGBgYPA1E+05dOV9f3WE0iNiDSmbd4sZbgDMEFsdwUJiNCEDeCxsPvW6hFjbsRpANQALbVw01V1AfS/QHQAAdCc6pgupm90AAAAASUVORK5CYII=",
    "monster.dark_horse": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAaElEQVQ4jWNgGAVkgSlWx/7C2IzkaGy+Ec3AwMDA8PLdfWa4pLiQ4l/s2hhQ1IgLKf599+7dX5h6RpjEy3f3mYkxBBm8fHefGe4FYjWjOJuBgYEJlwTZAOYSZBdhE8NwAblg4A0YeAAAH4wmVZBYipgAAAAASUVORK5CYII=",
    "monster.dark_knight": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAeklEQVQ4jWNgoBAwoguoqVn9xafh1q1jzDglCWnGpoYFm6J5DAxYDUpiYMCwHasB2BTiAhgGEOMNZAAPRBeX9L8MDAwMjx5dxqtBTk6XgYGBgWHPnpnMWF2AN5QhBuB2ITmxwERIAyFAcULCGo3YFOIymGIvUGzAwAMAI3og9Yw/C4gAAAAASUVORK5CYII=",
    "monster.dark_skeleton": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAaklEQVQ4jWNgGGjAiE3QxcXvLzbxPXs2MRM0EaZ5hdVfuCEwNjaDmXAZFHGMmRkbmygD3r1799fFxe8vOo1NLW3CAJsBuMRxhgE+TciABZ8kMU6mOAzwemHPnk3MRAUcIRfgCwe8LhgaAAC5+T2l229ETwAAAABJRU5ErkJggg==",
    "monster.death_knight": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAeklEQVQ4jWNgoBAwoguIi8v8xafh5csnzDglCWnGpoYFm6InT25hNUhGRg3DdqwGYFOIC2AYQIw3kAE8ELW0jP4yMDAwvH37Cq8GYWExBgYGBoZr184xY3UB3lCGGIDbheTEAhMhDYQAxQkJazRiU4jLYIq9QLEBAw8Abugh1CPsVxwAAAAASUVORK5CYII=",
    "monster.elemental_pedra": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAfUlEQVQ4jWNgGGjAiEsiKSL4LzJ/3oq1zNjUMVHqAooNQPECurOxAXSvMGLT+OjpMwY5aSkGfGIwg7B6AaYww+wDQ4bZBxQxdEBUGDx6+gynHAs+jTNOCUBtF8CpBmcgYgsHBgbMQMTpBVx+RgfUTUjzVqxlRnciriQ8eAAA6hgndjiBxe8AAAAASUVORK5CYII=",
    "monster.feiticeira": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAWElEQVQ4jWNgGGjAiEvCVDvpLzL/9NV5zNjUMVHqApwGxC+djZWNDljwmY5PI0EDFkanEtTMwECFMMAaC+gxAAPYYoL6LsBlOy5XUNcFhGzH5gqKXTDwAACkShZXXNmt+gAAAABJRU5ErkJggg==",
    "monster.fire_hound": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAaElEQVQ4jWNgGAVkgb8r1P7C2IzkaJw+6Q0DAwMDQ86xd8xwySlWQn+xa2NAUTPFSujvu3fv/sLUM8Ikco69YybGEGSQc+wdM9wLxGpGcTYDAwMTLgmyAcwlyC7CJobhAnLBwBsw8AAA0tUqphKCahEAAAAASUVORK5CYII=",
    "monster.goblin": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAhUlEQVQ4jcWRwQ2AIAxFn+LBxI04OkAX8uxCHYIFXIMBuJB4IiERi8aD/wT9v7/wC39jKAdRySrqRCVbDUWjog5gqslC5EBe1pmUkgOo7+aA3vSWZuoJehhaxTuT8m/T4EmI5pMsgxY3mm4P8DmDyxYA4hEBCFtwAH73rzZzabAMPmfwP07LOkBuDBC6ugAAAABJRU5ErkJggg==",
    "monster.imp": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABRklEQVQ4jbWSv07CUBTGv/uH9qYBIwohgANTBxOdSGjYnNxVArO8gA9CggOrK8HwHERmN9gkUhftQA0JbW/rVCzagon62845373n3O8e4D9IE1I7oPQyKY5C45I5xho5xhpJ8U6qqvpUF0ImxVFIXPKQ0qt2qXSfU1VojGG2XOLONJu27z84wDy2q55KDdKEGGFsWZbs6brs6bq0LGvdXQHKFc47ClAGIh7Yvj8+VdXRiaKM0oQYfWN9F/qGsT5YFWIGAOEkLBS9B8G4wFhbo/Q4y9i5nsnspeinx5PF4qjAeRsAJo7TlIC9MQEAzD2v6wTB8+NqVdcYi5Ywdd3Wq5RD0/O6UR94VPQi5e2blMMko6au2wrfHvJtDxJd/mF9g/AXtmliN/FPuS4WB/ucl3crt3CRz3fOstmbX11SEcKoCFH7mv8AsM1qCmBhFPkAAAAASUVORK5CYII=",
    "monster.lyzardman": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAiElEQVQ4jWNgGPKAEZeEWo7LX2T+rSl7mLGpY8Jn+pYKLhQD0Q1lYGBgYMFngE/HN4IuwOoFbDbhMgSnF3gURfE5jrABX+6/pswAYl2D1wCYRnyuwTBA1EatB8Y+V7ycGVfoYwAWbnZpSQ/dFSzc7NLosYArVhBOVRELQbaZZMCjIhZCtmZKAQCEHSO4bI63kwAAAABJRU5ErkJggg==",
    "monster.ogro": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAY0lEQVQ4jWNgGGjAiEsix0/tLzJ/yqZbzNjUMVHqArwGVDQ1ETSABV0A3eno4uheYYJJYtPYUVeH1VZk9bQNA7oYgJEOcAUiDOBKDyggzE7ub5id3F9cfGRAsRdwugAff3ABAMInIoDQyFmzAAAAAElFTkSuQmCC",
    "monster.serpente": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAzklEQVQ4jWNgGAUkAQV3hR4Fd4UeZDEWQpqEtYRDFD0Ue9n42GQYGBgYdEQYGA7wscncWn0rgoGBgYGRWI0woCPCwHDlDQPDsYZjzFhdgEsjDFx5w8Bwc9XNcBgfxQVsfGzSJkUmj3C56tenX09urLoR/uXJlxMwMbgL2PjYpPVS9I7h0vjm6pvVz44/6//16ddTZDm4C0yKTB6iOxufRhQXsPGxSSNrJkYjigHoTr8055IVIY0wwIQu8OvTryfEaoYDaOg/hIaDNEmaKQUAQrtiALtiIH0AAAAASUVORK5CYII=",
    "monster.skeleton": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAcElEQVQ4jWNgGGjAiE3wyZMnf7GJy8jIMBM0Eab5GAMD3BAYG5vBTLgMsmJgYMbGRgcs2ATfvXv399u3bwxcXFwMyDQ2QJswwGYALnGcYYBPEzLAGgYwQIyTKQ4DvF6QkZFhJirgCLkAXzjgdcHQAACd+EJcRqvXVQAAAABJRU5ErkJggg==",
    "monster.treant": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA8UlEQVQ4jWNgoBAw45KQlOUrMI1WXaloKlb48+UPhi+ffp7Apo4Ru2beAvtu815ksYOlJ4ufP/48AV0tEzYDNHwUCokRQzFAV0FoBT8XmwU2RchATpSngJ+L1RzGZ0SX5GBjlvnNwcRg3mqMYuPJ6rP9rD/+Mbx8/33Nx2+/TmA1gIGBgYGdlUlaXoy3UEiCJ5TTTJCBgYGB4cX+F8f/fv795OGrz/0/f/97SsiVDAwMDAz8XGwWLgYyf10MZP7KifIU4FKHNRYYGBgYXAxk/iLz91x4gjXKscYCKYBiAzC8gOx0mLOxiWEFsEAjV36IAgC+u0tBq2NRWwAAAABJRU5ErkJggg==",
    "monster.troll": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAY0lEQVQ4jWNgGGjAiEsittDzLzJ/cf92ZmzqmCh1AV4DiuNrCRrAgi6A7nR0cXSvMMEksWnsXdiM1VZk9bQNA7oYgJEOcAUiDOBKDyjAK8rqr1eU1V9cfGRAsRdwugAff3ABAGCmJJv62RxXAAAAAElFTkSuQmCC",
    "monster.verme": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAw0lEQVQ4jWNgGAUkAV8btR5fG7UeZDEWQpr0VMRCfG3Ue/l52GUYGBgY3n/8ysDPoyuzZMflCLwGoGtElRMPZWDAYQA+jQwMDAyC/NwMS3ZcCsfqBX5udukYD72VuFz18cvPJ4t3XAp/9OLjCQwD+LnZpXNCzY7h0njpzsvVh84/7P/49edTZDm4ATmhZsfQnY1PI4oB/Nzs0siaidGIYgC606esPmVFSCMMMKELfPzy8wmxmhkYGBgYGRhQA5AU26kCAHttZCvI4RuKAAAAAElFTkSuQmCC",
    "monster.zumbi": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAaklEQVQ4jWNgGGjAiE0wpyHiLzbxKQ0rmAmaCNOspiYDNwTGxmYwEy6Dbt16woyNTZQB7969+5vTEPEXncamljZhgM0AXOI4wwCfJmTAgk+SGCdTHAZ4vTClYQUzUQFHyAX4wgGvC4YGAACx2UHxBu+tOQAAAABJRU5ErkJggg==",
    "item.antidote": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZxktCPiPTfxcwgYM9RgCuDTjMoQFm6IoNzc4e9muXfjMGwSBOAwMwBoLhEIeGVCckAYeAAAEjBU1w8TAmQAAAABJRU5ErkJggg==",
    "item.elixir_arcane": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZwXI7fuPTXzDIycM9RgCuDTjMoQFmyIbGyM4+8iRc/jMGwSBOAwMwBoLhEIeGVCckAYeAAA8rhVxjMztcwAAAABJRU5ErkJggg==",
    "item.elixir_champion": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ11fr/Efm7hm4A0M9RgCuDTjMoQFmyINowA4+8a5DfjMGwSBOAwMwBoLhEIeGVCckAYeAABlgBVxTKhMOQAAAABJRU5ErkJggg==",
    "item.elixir_crimson": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZy3gkvuPTTzh2yMM9RgCuDTjMoQFmyIbIyM4+8i5c/jMGwSBOAwMwBoLhEIeGVCckAYeAAAmQhV7Pw2gmgAAAABJRU5ErkJggg==",
    "item.elixir_guardian": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAU0lEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ9lUrPqPTfxIRxiGegwBXJpxGcKC1QU25ggNR07iM28QBOIwMABrLBAKeWRAcUIaeAAAR+kVbGAWS1EAAAAASUVORK5CYII=",
    "item.elixir_hunter": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVElEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ7k1Gf3HJr6r7hyGegwBXJpxGcKCTZGNjRGcfeTIOXzmDYJAHAYGYI0FQiGPDChOSAMPAC0OFXHX0rr0AAAAAElFTkSuQmCC",
    "item.health_potion": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ53Q0PiPTdzixg0M9RgCuDTjMoQFmyJzNzc4++SuXfjMGwSBOAwMwBoLhEIeGVCckAYeAAAgdRVYiNNpiQAAAABJRU5ErkJggg==",
    "item.mana_potion": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ2lEXfqPTfzGMj0M9RgCuDTjMoQFmyI3N104e9euy/jMGwSBOAwMwBoLhEIeGVCckAYeAAA74RVi4oYyOAAAAABJRU5ErkJggg==",
    "item.potion_black": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ0lKyvzHJv78+RMM9RgCuDTjMoQFmyJdXSM4+/Llc/jMGwSBOAwMwBoLhEIeGVCckAYeAAAR2RWPs7fLtwAAAABJRU5ErkJggg==",
    "item.potion_brown": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ+W5Kf/HJj5p110M9RgCuDTjMoQFmyIbI2U4+8i5u/jMGwSBOAwMwBoLhEIeGVCckAYeAAA4IRWK94+r3wAAAABJRU5ErkJggg==",
    "item.potion_cyan": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ8lt2fcfm/gjHycM9RgCuDTjMoQFm6IAI104e8O5y/jMGwSBOAwMwBoLhEIeGVCckAYeAABXaxVsld8dcwAAAABJRU5ErkJggg==",
    "item.potion_darkblue": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVElEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ0nqNv3HJv78ch2GegwBXJpxGcKCTZGuuRucffnkLnzmDYJAHAYGYI0FQiGPDChOSAMPAB2RFXG4Dh8lAAAAAElFTkSuQmCC",
    "item.potion_darkred": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ+Xxi/zHJj7p4xsM9RgCuDTjMoQFmyIbZWU4+8jdu/jMGwSBOAwMwBoLhEIeGVCckAYeAAAvfxWZ1D5wGQAAAABJRU5ErkJggg==",
    "item.potion_gold": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ11aKvcfm7he9CMM9RgCuDTjMoQFmyJdczc4+/LJXfjMGwSBOAwMwBoLhEIeGVCckAYeAABdoRVxXm3ibwAAAABJRU5ErkJggg==",
    "item.potion_gray": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVElEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ1VUNPzHJt7R0YChHkMAl2ZchrBgU2RjYwNnHzlyBJ95gyAQh4EBWGOBUMgjA4oT0sADAEkkFWdbSahfAAAAAElFTkSuQmCC",
    "item.potion_green": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ2lMs/mPTfxG1hEM9RgCuDTjMoQFmyI3Nzc4e9euXfjMGwSBOAwMwBoLhEIeGVCckAYeAAAJyBVJQ/PloQAAAABJRU5ErkJggg==",
    "item.potion_orange": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVElEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ92pkPuPTVyl4xGGegwBXJpxGcKCTZGyuQ2cfffkEXzmDYJAHAYGYI0FQiGPDChOSAMPAGRZFYVn821mAAAAAElFTkSuQmCC",
    "item.potion_pink": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZz3MW/Ufm7j8pDAM9RgCuDTjMoQFmyI5Nw04+9GuG/jMGwSBOAwMwBoLhEIeGVCckAYeAACXThWPqJtY6gAAAABJRU5ErkJggg==",
    "item.potion_purple": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVElEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ1VobPmPTbzjhg+GegwBXJpxGcKCTZGNmxGcfWTXOXzmDYJAHAYGYI0FQiGPDChOSAMPAEBaFWdUFVFRAAAAAElFTkSuQmCC",
    "item.potion_ruby": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ+0TsfmPTdzpzREM9RgCuDTjMoQFmyIjGxs4+9yRI/jMGwSBOAwMwBoLhEIeGVCckAYeAAAzYhVxL/SCEQAAAABJRU5ErkJggg==",
    "item.potion_silver": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ61av/M/NvGwQHcM9RgCuDTjMoQFmyJzUyM4++Tpc/jMGwSBOAwMwBoLhEIeGVCckAYeAACPKxV9ZwPWwQAAAABJRU5ErkJggg==",
    "item.potion_turquoise": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ8ktmPYfm/ijhCwM9RgCuDTjMoQFmyI3G3M4e9eRk/jMGwSBOAwMwBoLhEIeGVCckAYeAAA76xVinx5qVgAAAABJRU5ErkJggg==",
    "item.potion_violet": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ02zOfEfm3jWEQsM9RgCuDTjMoQFmyIjNw04+9yuG/jMGwSBOAwMwBoLhEIeGVCckAYeAABn4hV7PjWnvwAAAABJRU5ErkJggg==",
    "item.potion_white": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ126dP0/NnE9PU0M9RgCuDTjMoQFmyINDQ04+8aNG/jMGwSBOAwMwBoLhEIeGVCckAYeAADRjBWjH4T/agAAAABJRU5ErkJggg==",
    "item.potion_yellow": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAVUlEQVQ4jWNgoBAw4pLoaar4j8wvqevAqpaJUhdQbABWZ905Ifcfm7iKxSMM9RgCuDTjMoQFmyJljQA4++6NDfjMGwSBOAwMwBoLhEIeGVCckAYeAAB5AxWAGXeAaQAAAABJRU5ErkJggg==",
}
# total entries: 45


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
    # Stage L1.5 (tools/coop_harness.py): pygbag's own boot bundle resolver
    # has a bug tied to the literal hostname "localhost" specifically -
    # confirmed live, reproduces every time - it resolves the pygame_ce
    # wheel's CDN path relative to whatever origin served index.html
    # instead of the real pygame-web.github.io CDN, a 404 that stops boot
    # dead before Python ever runs. Never reproduces on 127.0.0.1, so the
    # multi-BrowserContext coop harness serves from there instead - needs
    # its own CORS entry since it's a distinct origin from localhost:8000
    # even though both mean "this machine".
    "http://127.0.0.1:8000",
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


@app.get("/appearance")
def get_appearance():
    """Stage K18: public, no auth - same shape/reasoning as GET /balance
    (game/net.py's trigger_appearance_fetch() fetches this at boot). Only
    ever returns overrides that exist; an absent key means the caller's
    own procedural painter stands."""
    with get_session() as session:
        rows = session.query(AppearanceOverride).all()
        return {row.key: row.data_url for row in rows}


@app.get("/appearance/defaults")
def get_appearance_defaults():
    """Stage K23: public, no auth - only ever consumed by the admin page's
    pixel editor (loadAppearance() below), as a fallback so an entity that
    was never overridden shows its actual current in-game look instead of
    a blank canvas. Not fetched by the game itself (game/net.py has no
    caller for this) - the game already knows its own procedural sprites
    without asking the backend."""
    return SPRITE_DEFAULTS


class AppearanceUpdateBody(BaseModel):
    data_url: str


@app.put("/admin/appearance/{key}")
def put_appearance_admin(key: str, body: AppearanceUpdateBody, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    now = time.time()
    with get_session() as session:
        row = session.query(AppearanceOverride).filter_by(key=key).one_or_none()
        if row is None:
            row = AppearanceOverride(key=key, data_url=body.data_url, updated_at=now)
            session.add(row)
        else:
            row.data_url = body.data_url
            row.updated_at = now
        session.commit()
    return {"ok": True}


@app.delete("/admin/appearance/{key}")
def delete_appearance_admin(key: str, authorization: str | None = Header(default=None)):
    """Reverts one entity back to its procedural default - deletes the row
    rather than storing some "no override" sentinel value, same "absent
    key = default stands" contract every other override table here uses."""
    _require_admin(authorization)
    with get_session() as session:
        row = session.query(AppearanceOverride).filter_by(key=key).one_or_none()
        if row is not None:
            session.delete(row)
            session.commit()
    return {"ok": True}


# Stage L1 (docs/coop-implementation-plan.md): coop room relay. Process-local,
# in-memory, never touches SQLite - a room is efficient garbage the moment
# its last player leaves (see feasibility study's "never persisted, it's
# ephemeral" call). The server is a dumb relay: it stamps the sender's
# player_id onto every message and rebroadcasts to the rest of the room
# verbatim, never inspecting game content - no game rules live here, same
# "backend never imports game/" boundary BALANCE_DEFAULTS documents above.
# Host-authoritative simulation (who actually runs monster AI/damage) is a
# Fase 2 (L5+) client-side concern, not this endpoint's.
_ROOM_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O/1/I/L - short enough for a mobile virtual keyboard (game/input_system.py already handles those well)
_ROOM_CODE_LEN = 4
_coop_rooms: dict[str, dict[str, dict[str, Any]]] = {}  # room_id -> {player_id: {"ws": WebSocket, "name": str}}


def _new_room_code() -> str:
    while True:
        code = "".join(secrets.choice(_ROOM_CODE_ALPHABET) for _ in range(_ROOM_CODE_LEN))
        if code not in _coop_rooms:
            return code


@app.post("/coop/room")
def create_coop_room():
    """No auth - "login never required to play" (docs/architecture.md)
    extends to coop: a room code is not an account. Reserves the code with
    an empty player dict immediately, so two concurrent creates can never
    land on the same code; a room nobody ever joins is cleaned up the same
    lazy way an emptied one is (see coop_ws's finally block)."""
    code = _new_room_code()
    _coop_rooms[code] = {}
    return {"room_id": code}


async def _coop_broadcast(room: dict[str, dict[str, Any]], payload: dict, exclude: str | None = None) -> None:
    dead = []
    for pid, entry in room.items():
        if pid == exclude:
            continue
        try:
            await entry["ws"].send_json(payload)
        except Exception:
            dead.append(pid)
    for pid in dead:
        room.pop(pid, None)


@app.websocket("/coop/ws/{room_id}")
async def coop_ws(websocket: WebSocket, room_id: str, player_id: str, name: str = "?"):
    room = _coop_rooms.get(room_id)
    if room is None:
        await websocket.close(code=4404)  # custom app-level code (RFC 6455 reserves 4000-4999) - "no such room"
        return
    await websocket.accept()
    # Stage L5 (docs/coop-implementation-plan.md): "quem cria a room é o
    # host" cai direto de "primeira conexão numa room vazia" - a room só
    # existe porque POST /coop/room acabou de reservá-la (ver
    # create_coop_room acima), então o primeiro WS a chegar é sempre quem
    # criou. Isso NÃO é o servidor entendendo regra de jogo (continua um
    # relay burro) - só um rótulo de qual conexão chegou primeiro, do
    # mesmo jeito que já rotula quem é quem via player_id.
    is_host = len(room) == 0
    room[player_id] = {"ws": websocket, "name": name, "is_host": is_host}

    await _coop_broadcast(room, {"type": "join", "player_id": player_id, "name": name, "is_host": is_host}, exclude=player_id)
    # The broadcast above only reaches players who were already connected -
    # the newcomer needs its own snapshot of who's already in the room.
    await websocket.send_json({
        "type": "roster",
        "players": [
            {"player_id": pid, "name": entry["name"], "is_host": entry["is_host"]}
            for pid, entry in room.items() if pid != player_id
        ],
    })

    try:
        while True:
            msg = await websocket.receive_json()
            msg["player_id"] = player_id  # server-stamped - never trust a client's own claim of who it is
            await _coop_broadcast(room, msg, exclude=player_id)
    except WebSocketDisconnect:
        pass  # the expected case - any other error propagates (visible in server logs) but still hits `finally` below
    finally:
        room.pop(player_id, None)
        if room:
            await _coop_broadcast(room, {"type": "leave", "player_id": player_id})
        else:
            _coop_rooms.pop(room_id, None)


_ADMIN_PAGE = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Dungeon Quest - Balanceamento</title>
<style>
body { font-family: monospace; background: #14141c; color: #ddd; padding: 24px; }
h1 { color: #e0b84c; letter-spacing: 0.5px; }
table { border-collapse: collapse; width: 100%; max-width: 900px; }
td, th { border: 1px solid #383844; padding: 7px 10px; text-align: left; }
th { background: #262633; color: #b8b8c8; }
tr:hover td { background: #20202c; }
input { width: 120px; background: #1e1e28; color: #ddd; border: 1px solid #555; padding: 5px; border-radius: 3px; }
input:focus { outline: none; border-color: #e0b84c; }
input.changed { border-color: #e0b84c; }
button { background: #e0b84c; color: #14141c; border: none; padding: 8px 18px; font-weight: bold; cursor: pointer; border-radius: 3px; }
button:hover { background: #f0c95c; }
/* Stage K19: card-style login box instead of a bare inline row - the
   first thing anyone hitting /admin sees. */
#login { background: #1a1a24; border: 1px solid #333; border-radius: 6px; padding: 20px; max-width: 340px; }
#login input { width: 100%; box-sizing: border-box; margin-bottom: 10px; }
#status { margin-left: 12px; color: #e08c8c; }
/* Stage K17: tab bar + collapsible per-entity sections - the flat table
   above stopped scaling once BALANCE_DEFAULTS grew past ~300 keys
   (Stage K16's monster/buff/debuff/stance categories). */
#tabs { display: flex; gap: 6px; margin: 16px 0; flex-wrap: wrap; }
.tab-btn { background: #232330; color: #aaa; border: 1px solid #444; padding: 7px 16px; cursor: pointer; font-family: monospace; border-radius: 4px; transition: background 0.1s; }
.tab-btn:hover { background: #2c2c3c; color: #ddd; }
.tab-btn.active { background: #e0b84c; color: #14141c; font-weight: bold; }
.tab-btn.active:hover { background: #e0b84c; }
.tab-content { display: none; }
.tab-content.active { display: block; }
/* Stage K19: entity cards - a subtle gold left-border + hover lift reads
   as "clickable card", not just a table row that happens to collapse. */
details { max-width: 900px; margin-bottom: 8px; border: 1px solid #333; border-left: 3px solid #55552a; background: #1a1a24; border-radius: 4px; overflow: hidden; }
details[open] { border-left-color: #e0b84c; }
summary { cursor: pointer; padding: 10px 12px; background: #232330; font-weight: bold; color: #e0b84c; list-style: none; }
summary:hover { background: #282838; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "\\25B8"; display: inline-block; margin-right: 8px; transition: transform 0.1s; }
details[open] summary::before { transform: rotate(90deg); }
details table { margin: 0; }
</style></head>
<body>
<h1>Dungeon Quest - Painel de Balanceamento</h1>
<div id="login">
  <input id="pw" type="password" placeholder="Senha de admin">
  <button onclick="doLogin()">Entrar</button>
  <span id="status"></span>
</div>
<div id="panel" style="display:none">
  <div id="tabs"></div>
  <div id="tab-contents"></div>
  <br><button onclick="doSave()">Salvar Tudo</button>
  <span id="save-status"></span>
</div>

<!-- Stage K18: pixel editor overlay - a 16x16 grid (game/appearance_
     overrides.py's native size), click/drag to paint with the color
     picker, Shift+click to erase to transparent. -->
<div id="pe-overlay" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.75); align-items:center; justify-content:center; z-index:10;">
  <div style="background:#1a1a24; border:1px solid #444; padding:20px;">
    <h3 id="pe-title" style="color:#e0b84c; margin-top:0;"></h3>
    <canvas id="pe-canvas" style="image-rendering:pixelated; border:1px solid #555; cursor:crosshair;"></canvas>
    <div style="margin-top:10px;">
      <input type="color" id="pe-color" value="#c83232">
      <button onclick="savePixelEditor()">Salvar</button>
      <button onclick="revertPixelEditor()">Reverter para padrao</button>
      <button onclick="closePixelEditor()">Fechar</button>
      <span id="pe-status"></span>
    </div>
    <p style="color:#888; max-width:340px;">Clique/arraste para pintar. Shift+clique apaga (transparente).</p>
  </div>
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

// Stage K17: tabs, in a fixed display order - "geral" bundles the two
// smallest/system-wide categories (stats.* + item.max_stock) rather than
// giving each its own single-row tab.
const TABS = [
  {id: "geral", label: "Geral"},
  {id: "dificuldade", label: "Dificuldade"},
  {id: "monstros", label: "Monstros"},
  {id: "magias", label: "Magias"},
  {id: "itens", label: "Itens"},
  {id: "buffs", label: "Buffs"},
  {id: "debuffs", label: "Debuffs"},
  {id: "posturas", label: "Posturas"},
];

function categoryOf(key) {
  const seg = key.split(".")[0];
  const map = {stats: "geral", difficulty: "dificuldade", item: "itens", spell: "magias",
               player: "magias", monster: "monstros", buff: "buffs", debuff: "debuffs", stance: "posturas"};
  return map[seg] || "geral";
}

// Groups a category's keys by their 2nd dotted segment (the "entity" -
// a monster id, a spell id, a profession name...) so each renders as its
// own collapsible <details> block instead of one giant flat list. Stage
// K18's "Editar aparencia" button will hang off these same per-entity
// blocks once it exists.
function groupEntities(keys) {
  const groups = {};
  for (const key of keys) {
    const parts = key.split(".");
    const entity = parts.length >= 3 ? parts[1] : "_";
    const field = parts.length >= 3 ? parts.slice(2).join(".") : parts.slice(1).join(".");
    (groups[entity] = groups[entity] || []).push({key, field});
  }
  return groups;
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tabId));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.toggle("active", c.dataset.tab === tabId));
}

// Stage K18: fetched once alongside the balance table (same GET /appearance
// the game itself calls, no auth needed for reading) so openPixelEditor()
// can pre-populate its grid with whatever's already there.
let appearanceCache = {};
// Stage K23: pre-rendered snapshots of each entity's actual current
// procedural sprite (GET /appearance/defaults) - openPixelEditor() falls
// back to this when appearanceCache has nothing for the key, i.e. every
// entity that's never been manually overridden. Without this the editor
// opened on a totally blank canvas for anything not already overridden,
// which in practice was every entity on first use - it looked broken/empty
// even though nothing was actually wrong.
let defaultsCache = {};

async function loadAppearance() {
  try {
    const res = await fetch(API + "/appearance");
    appearanceCache = await res.json();
  } catch (e) {
    appearanceCache = {};
  }
  try {
    const res = await fetch(API + "/appearance/defaults");
    defaultsCache = await res.json();
  } catch (e) {
    defaultsCache = {};
  }
}

async function loadBalance() {
  const res = await fetch(API + "/admin/balance", {headers: {"Authorization": "Bearer " + token()}});
  if (!res.ok) {
    sessionStorage.removeItem("dq_admin_token");
    document.getElementById("status").textContent = "Sessao expirada, logue de novo.";
    return;
  }
  await loadAppearance();
  const data = await res.json();
  const byCategory = {};
  for (const tab of TABS) byCategory[tab.id] = [];
  for (const key of Object.keys(data.defaults).sort()) byCategory[categoryOf(key)].push(key);

  const tabsEl = document.getElementById("tabs");
  const contentsEl = document.getElementById("tab-contents");
  tabsEl.innerHTML = "";
  contentsEl.innerHTML = "";

  for (const tab of TABS) {
    const keys = byCategory[tab.id];
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.dataset.tab = tab.id;
    btn.textContent = `${tab.label} (${keys.length})`;
    btn.onclick = () => switchTab(tab.id);
    tabsEl.appendChild(btn);

    const content = document.createElement("div");
    content.className = "tab-content";
    content.dataset.tab = tab.id;
    const groups = groupEntities(keys);
    for (const entity of Object.keys(groups).sort()) {
      const rows = groups[entity];
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = entity === "_" ? tab.label : entity;
      // Stage K18: pixel editor only wired up for monster/item sprites so
      // far (game/assets.py's create_enemy_sprite()/create_potion_icon()) -
      // other categories get the button once their sprite function is
      // hooked up too, same 3-line pattern each time.
      if (entity !== "_" && (tab.id === "monstros" || tab.id === "itens")) {
        const appearanceKey = tab.id === "monstros" ? `monster.${entity}` : `item.${entity}`;
        const editBtn = document.createElement("button");
        editBtn.textContent = "Editar aparencia";
        editBtn.style.marginLeft = "12px";
        editBtn.style.padding = "2px 10px";
        editBtn.onclick = (ev) => { ev.preventDefault(); openPixelEditor(appearanceKey); };
        summary.appendChild(editBtn);
      }
      details.appendChild(summary);
      const table = document.createElement("table");
      table.innerHTML = "<thead><tr><th>Campo</th><th>Default</th><th>Valor atual</th></tr></thead>";
      const tbody = document.createElement("tbody");
      for (const {key, field} of rows) {
        const def = data.defaults[key];
        const cur = data.overrides.hasOwnProperty(key) ? data.overrides[key] : String(def);
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${field}</td><td>${def}</td><td><input data-key="${key}" value="${cur}"></td>`;
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      details.appendChild(table);
      content.appendChild(details);
    }
    contentsEl.appendChild(content);
  }
  switchTab(TABS[0].id);

  document.getElementById("login").style.display = "none";
  document.getElementById("panel").style.display = "block";
}

async function doSave() {
  // Every tab's inputs stay in the DOM (hidden via CSS, not destroyed) -
  // this still captures edits made before switching tabs away.
  const inputs = document.querySelectorAll("#tab-contents input");
  const values = {};
  inputs.forEach(inp => { values[inp.dataset.key] = inp.value; });
  const res = await fetch(API + "/admin/balance", {
    method: "PUT",
    headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token()},
    body: JSON.stringify({values}),
  });
  document.getElementById("save-status").textContent = res.ok ? "Salvo!" : "Erro ao salvar.";
}

// ─── Stage K18: pixel editor ────────────────────────────────────────────
// Two canvases: `dataCanvas` (16x16, the real pixel truth - what actually
// gets PNG-encoded and saved) and the visible `pe-canvas` (scaled up +
// grid-lines overlaid for editing). Painting writes to dataCanvas only,
// then redrawView() re-composites the visible canvas from it - keeps the
// grid-line overlay from ever being baked into the saved image.
const PIXEL_GRID = 16, PIXEL_SCALE = 20;
let editorKey = null;
let dataCanvas, dataCtx, viewCanvas, viewCtx, painting = false;

function initPixelEditor() {
  dataCanvas = document.createElement("canvas");
  dataCanvas.width = PIXEL_GRID; dataCanvas.height = PIXEL_GRID;
  dataCtx = dataCanvas.getContext("2d");
  viewCanvas = document.getElementById("pe-canvas");
  viewCanvas.width = PIXEL_GRID * PIXEL_SCALE;
  viewCanvas.height = PIXEL_GRID * PIXEL_SCALE;
  viewCtx = viewCanvas.getContext("2d");
  viewCtx.imageSmoothingEnabled = false;
  viewCanvas.addEventListener("mousedown", (e) => { painting = true; pixelPaint(e); });
  viewCanvas.addEventListener("mousemove", (e) => { if (painting) pixelPaint(e); });
  window.addEventListener("mouseup", () => { painting = false; });
}

function redrawView() {
  viewCtx.clearRect(0, 0, viewCanvas.width, viewCanvas.height);
  viewCtx.drawImage(dataCanvas, 0, 0, viewCanvas.width, viewCanvas.height);
  viewCtx.strokeStyle = "rgba(255,255,255,0.15)";
  for (let i = 0; i <= PIXEL_GRID; i++) {
    viewCtx.beginPath(); viewCtx.moveTo(i * PIXEL_SCALE, 0); viewCtx.lineTo(i * PIXEL_SCALE, viewCanvas.height); viewCtx.stroke();
    viewCtx.beginPath(); viewCtx.moveTo(0, i * PIXEL_SCALE); viewCtx.lineTo(viewCanvas.width, i * PIXEL_SCALE); viewCtx.stroke();
  }
}

function openPixelEditor(key) {
  if (!dataCanvas) initPixelEditor();
  editorKey = key;
  document.getElementById("pe-title").textContent = "Editando: " + key;
  document.getElementById("pe-status").textContent = "";
  dataCtx.clearRect(0, 0, PIXEL_GRID, PIXEL_GRID);
  // Stage K23: an actual admin override wins if one exists; otherwise fall
  // back to the entity's real current procedural sprite (defaultsCache)
  // instead of leaving the canvas blank - only if NEITHER exists (an
  // unrecognized key) does this stay empty.
  const existing = appearanceCache[key] || defaultsCache[key];
  if (existing) {
    const img = new Image();
    img.onload = () => { dataCtx.drawImage(img, 0, 0, PIXEL_GRID, PIXEL_GRID); redrawView(); };
    img.src = existing;
  } else {
    redrawView();
  }
  document.getElementById("pe-overlay").style.display = "flex";
}

function pixelPaint(e) {
  const rect = viewCanvas.getBoundingClientRect();
  const x = Math.floor((e.clientX - rect.left) / (rect.width / PIXEL_GRID));
  const y = Math.floor((e.clientY - rect.top) / (rect.height / PIXEL_GRID));
  if (x < 0 || y < 0 || x >= PIXEL_GRID || y >= PIXEL_GRID) return;
  if (e.shiftKey) {
    dataCtx.clearRect(x, y, 1, 1);
  } else {
    dataCtx.fillStyle = document.getElementById("pe-color").value;
    dataCtx.fillRect(x, y, 1, 1);
  }
  redrawView();
}

function closePixelEditor() {
  document.getElementById("pe-overlay").style.display = "none";
  editorKey = null;
}

async function savePixelEditor() {
  const dataUrl = dataCanvas.toDataURL("image/png");
  const res = await fetch(API + `/admin/appearance/${encodeURIComponent(editorKey)}`, {
    method: "PUT",
    headers: {"Content-Type": "application/json", "Authorization": "Bearer " + token()},
    body: JSON.stringify({data_url: dataUrl}),
  });
  document.getElementById("pe-status").textContent = res.ok ? "Salvo!" : "Erro ao salvar.";
  if (res.ok) appearanceCache[editorKey] = dataUrl;
}

async function revertPixelEditor() {
  const res = await fetch(API + `/admin/appearance/${encodeURIComponent(editorKey)}`, {
    method: "DELETE",
    headers: {"Authorization": "Bearer " + token()},
  });
  if (res.ok) {
    delete appearanceCache[editorKey];
    dataCtx.clearRect(0, 0, PIXEL_GRID, PIXEL_GRID);
    redrawView();
    document.getElementById("pe-status").textContent = "Revertido para padrao.";
  }
}

if (token()) { loadBalance(); }
</script>
</body></html>"""


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return _ADMIN_PAGE
