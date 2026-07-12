"""
Profession determination (Stage A7), inspired by Ultima Online: profession
is DERIVED from spent attribute points, not stored independently, so free
respec (already in game/paperdoll.py) is a feature - change your build,
change your profession - not a bug needing special-case handling.

Algorithm: spent[attr] = current - BASE_ATTR (10, matching the paperdoll's
respec floor). Fewer than 20 total spent points -> Aventureiro (no build
yet). Otherwise rank attributes by spent amount (ties broken by
STR>DEX>INT>WIS>VIG); if the second-highest is under half the highest,
the profession is PURE for the top attribute, else it's the HYBRID of the
top two - one line in PURE/HYBRID per profession, no branching logic to
add a new one.
"""

BASE_ATTR = 10
# Sorte (luck) is deliberately excluded from _PRIORITY/PURE/HYBRID - there's
# no "Gambler" profession, points spent on luck just don't factor into
# profession derivation. Adding it here would need a 6th PURE entry and a
# HYBRID pair for every other attribute, or this KeyErrors.
_PRIORITY = ["strength", "dexterity", "intelligence", "wisdom", "vigor"]

ADVENTURER = "Aventureiro"

PURE = {
    "strength": "Guerreiro",
    "dexterity": "Assassino",
    "intelligence": "Mago",
    "wisdom": "Feiticeiro",
    "vigor": "Cavaleiro",
}

HYBRID = {
    frozenset({"strength", "dexterity"}): "Duelista",
    frozenset({"strength", "intelligence"}): "Cavaleiro Arcano",
    frozenset({"strength", "wisdom"}): "Paladino",
    frozenset({"strength", "vigor"}): "Campeao",
    frozenset({"dexterity", "intelligence"}): "Monge",
    frozenset({"dexterity", "wisdom"}): "Xama",
    frozenset({"dexterity", "vigor"}): "Ranger",
    frozenset({"intelligence", "wisdom"}): "Arcanista",
    frozenset({"intelligence", "vigor"}): "Druida",
    frozenset({"wisdom", "vigor"}): "Templario",
}

# Used to be a color multiply applied over one shared sprite (both the
# in-run Player and the paperdoll portrait) - superseded by real per-
# profession rigs (game/assets.py's PLAYER_SPRITES/create_player_sprite),
# so nothing tints with this anymore. Kept as a per-profession accent
# color in case UI ever wants one (e.g. coloring the profession name in a
# HUD/label) - not currently read anywhere.
TINTS = {
    ADVENTURER: (255, 255, 255),
    "Guerreiro": (255, 90, 90),
    "Assassino": (130, 130, 150),
    "Mago": (90, 130, 255),
    "Feiticeiro": (200, 90, 255),
    "Cavaleiro": (210, 200, 90),
    "Duelista": (255, 150, 70),
    "Cavaleiro Arcano": (110, 170, 255),
    "Paladino": (255, 220, 130),
    "Campeao": (255, 70, 70),
    "Monge": (150, 225, 190),
    "Xama": (185, 255, 150),
    "Ranger": (110, 205, 110),
    "Arcanista": (185, 110, 255),
    "Druida": (110, 225, 130),
    "Templario": (255, 225, 170),
}


def determine_profession(stats):
    spent = {attr: max(0, getattr(stats, attr) - BASE_ATTR) for attr in _PRIORITY}
    total = sum(spent.values())
    if total < 20:
        return ADVENTURER

    ranked = sorted(spent.items(), key=lambda kv: (-kv[1], _PRIORITY.index(kv[0])))
    p1, s1 = ranked[0]
    p2, s2 = ranked[1]

    if s2 / s1 < 0.5:
        return PURE[p1]
    return HYBRID[frozenset({p1, p2})]
