"""
Stage I4: applies numeric overrides fetched from the backend's /balance
endpoint (admin panel, backend/app/main.py) on top of the game's own
defaults. Never required for the game to run - every key is optional, an
unknown/malformed one is skipped rather than raising, same offline-first
spirit as game/net.py's sync (a backend that's down/misconfigured must
never cost more than "the code defaults stand").

ITEMS/DIFFICULTIES/SPELLS are mutated key-by-key IN PLACE, never reassigned
- every other module already did `from game.X import DICT` at import time
and holds the same dict object, so an in-place mutation is visible
everywhere without a second pass to "refresh" anyone. game.stats's scalar
constants (MITIGATION_K, XP_CURVE_BASE, ...) are set via the qualified
`stats.NAME = value` form - safe because every function that reads them
(mitigate(), xp_to_next(), scale_by_ml(), xp_for_kill()) looks its globals
up from game.stats's own namespace at CALL time, not at their own
definition/import time - standard Python behavior, not a hack.
"""
import game.stats as stats
from game.difficulty import DIFFICULTIES
from game.items import ITEMS
import game.items as items
from game.spells import SPELLS
from game.status_effects import STATUS_EFFECTS, ORIGINAL_DEBUFF_IDS, PVP_DEBUFF_IDS
from game.stances import STANCES
import game.player as player
import game.level as level

_STATS_KEYS = {
    "mitigation_k", "xp_curve_base", "xp_curve_exp",
    "ml_growth_rate", "anti_farm_level_gap", "anti_farm_xp_mult",
    "base_attack_cooldown", "key_finder_xp_bonus",
}

# Stage K23: Dash (game/player.py's DASH_* module constants) - not a dict
# entry like SPELLS/ITEMS, so this maps the admin panel's dotted field name
# straight to the module attribute name, same setattr-on-the-module-object
# approach _STATS_KEYS above already uses for game.stats.
_DASH_KEYS = {
    "dex_req": "DASH_DEX_REQ", "duration": "DASH_DURATION",
    "speed": "DASH_SPEED", "cooldown": "DASH_COOLDOWN",
}

# Same setattr-on-module pattern as _DASH_KEYS, for the pickaxe's own lone
# cooldown constant.
_PICKAXE_KEYS = {"cooldown": "PICKAXE_COOLDOWN"}


def apply_overrides(config):
    for key, raw_value in config.items():
        try:
            _apply_one(key, raw_value)
        except (ValueError, TypeError):
            continue  # malformed value for this key - skip it, default stands


def _apply_one(key, raw_value):
    parts = key.split(".")

    if parts == ["item", "max_stock"]:
        items.MAX_STOCK = type(items.MAX_STOCK)(raw_value)
        return

    if len(parts) == 3 and parts[0] == "item" and parts[1] in ITEMS and parts[2] in ITEMS[parts[1]]:
        target = ITEMS[parts[1]]
        target[parts[2]] = type(target[parts[2]])(raw_value)
        return

    if len(parts) == 3 and parts[0] == "difficulty" and parts[1] in DIFFICULTIES and parts[2] in DIFFICULTIES[parts[1]]:
        target = DIFFICULTIES[parts[1]]
        target[parts[2]] = type(target[parts[2]])(raw_value)
        return

    if len(parts) == 3 and parts[0] == "spell" and parts[1] in SPELLS and parts[2] in SPELLS[parts[1]]:
        target = SPELLS[parts[1]]
        target[parts[2]] = type(target[parts[2]])(raw_value)
        return

    if len(parts) == 3 and parts[0] == "player" and parts[1] == "dash" and parts[2] in _DASH_KEYS:
        attr = _DASH_KEYS[parts[2]]
        setattr(player, attr, type(getattr(player, attr))(raw_value))
        return

    if len(parts) == 3 and parts[0] == "player" and parts[1] == "pickaxe" and parts[2] in _PICKAXE_KEYS:
        attr = _PICKAXE_KEYS[parts[2]]
        setattr(player, attr, type(getattr(player, attr))(raw_value))
        return

    if len(parts) == 2 and parts[0] == "level" and parts[1] == "respawn_interval":
        level.RESPAWN_INTERVAL = type(level.RESPAWN_INTERVAL)(raw_value)
        return

    if len(parts) == 2 and parts[0] == "stats" and parts[1] in _STATS_KEYS:
        attr = parts[1].upper()
        setattr(stats, attr, type(getattr(stats, attr))(raw_value))
        return

    # Stage K16: monster.<etype>.base_xp/gold_drop are flat scalar dicts
    # (etype -> number), a different shape from monster.<etype>.<combat
    # stat>, which indexes into ENEMY_ARCHETYPES' per-etype dict - same
    # "field must already exist on the target" guard as item/difficulty/
    # spell above, just checked against two different tables.
    if len(parts) == 3 and parts[0] == "monster" and parts[1] in stats.BASE_XP and parts[2] == "base_xp":
        stats.BASE_XP[parts[1]] = type(stats.BASE_XP[parts[1]])(raw_value)
        return
    if len(parts) == 3 and parts[0] == "monster" and parts[1] in stats.GOLD_DROPS and parts[2] == "gold_drop":
        stats.GOLD_DROPS[parts[1]] = type(stats.GOLD_DROPS[parts[1]])(raw_value)
        return
    if (len(parts) == 3 and parts[0] == "monster" and parts[1] in stats.ENEMY_ARCHETYPES
            and parts[2] in stats.ENEMY_ARCHETYPES[parts[1]]):
        target = stats.ENEMY_ARCHETYPES[parts[1]]
        target[parts[2]] = type(target[parts[2]])(raw_value)
        return

    # Stage K16: debuff.<id>.<field> and buff.<id>.<field> both resolve
    # into the SAME STATUS_EFFECTS dict (see ORIGINAL_DEBUFF_IDS import
    # above) - StatusEffectDef is a namedtuple (immutable), so unlike every
    # dict-of-dicts case above this needs a ._replace() + reassignment into
    # the dict rather than an in-place field set.
    if len(parts) == 3 and parts[0] in ("debuff", "buff") and parts[1] in STATUS_EFFECTS:
        is_debuff = parts[1] in ORIGINAL_DEBUFF_IDS or parts[1] in PVP_DEBUFF_IDS
        if (parts[0] == "debuff") != is_debuff:
            return  # e.g. "buff.poison.*" - wrong prefix for this id, ignore
        defn = STATUS_EFFECTS[parts[1]]
        if not hasattr(defn, parts[2]):
            return
        current = getattr(defn, parts[2])
        STATUS_EFFECTS[parts[1]] = defn._replace(**{parts[2]: type(current)(raw_value)})
        return

    # Stage K16: stance.<profession>.<field> - game/stances.py's STANCES,
    # same dict-of-dicts shape as item/difficulty/spell (profession names
    # contain spaces, e.g. "Cavaleiro Arcano" - fine, "." is still the only
    # split delimiter).
    if len(parts) == 3 and parts[0] == "stance" and parts[1] in STANCES and parts[2] in STANCES[parts[1]]:
        target = STANCES[parts[1]]
        target[parts[2]] = type(target[parts[2]])(raw_value)
        return

    # Unknown key (stale override from a removed item/spell, typo, etc.) -
    # ignored on purpose, never raises.
