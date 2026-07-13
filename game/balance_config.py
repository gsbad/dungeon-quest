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

_STATS_KEYS = {
    "mitigation_k", "xp_curve_base", "xp_curve_exp",
    "ml_growth_rate", "anti_farm_level_gap", "anti_farm_xp_mult",
}


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

    if len(parts) == 2 and parts[0] == "stats" and parts[1] in _STATS_KEYS:
        attr = parts[1].upper()
        setattr(stats, attr, type(getattr(stats, attr))(raw_value))
        return

    # Unknown key (stale override from a removed item/spell, typo, etc.) -
    # ignored on purpose, never raises.
