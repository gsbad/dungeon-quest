"""
Stage A5: the real save system. Same localStorage/native-file split proven
by the Stage A2 spike (game/persist_spike.py, now retired - this covers its
mute-flag contract plus everything else that needs to persist).

Versioned from day one (SAVE_VERSION) so a future schema change has
somewhere to hook a migration in _migrate() instead of breaking old saves.
Achievements/difficulty-tier fields from the full design aren't here yet
because those systems don't exist yet (Stage B) - adding empty placeholders
for them now would just be dead schema to migrate around later. Profession
is NOT in the schema on purpose - it's derived from spent attribute points
(game/professions.py), so persisting it would just be a second value that
could drift out of sync with the attributes that actually define it.
"""
import sys
import os
import json
import copy

from game.player import Player
from game.professions import determine_profession

SAVE_VERSION = 7
_KEY = "dungeon_quest_save"
_NATIVE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_save.json")


def new_game_state():
    return {
        "version": SAVE_VERSION,
        "character": {
            "name": "", "level": 1, "xp": 0, "unspent_points": 0,
            "attributes": {"str": 10, "dex": 10, "int": 10, "wis": 10, "vig": 10, "lck": 10},
        },
        "progression": {
            "current_difficulty": "normal",
            "highest_level_cleared": {"normal": 0},
            "cleared_difficulties": [],
            # Stage F3 (Atlas tab): levels ever loaded, regardless of
            # difficulty or death - unlike highest_level_cleared this never
            # regresses, since a death shouldn't re-hide a map the player
            # has already seen.
            "levels_seen": [],
        },
        "counters": {"kills": {}, "boss_kills": {}, "deaths": 0, "playtime_s": 0.0},
        "settings": {"muted": False},
        "gold": 0,
        "inventory": {},
        "hotbar_items": ["health_potion", "mana_potion", "antidote"],
    }


def _read_raw():
    if sys.platform == "emscripten":
        import js
        val = js.localStorage.getItem(_KEY)
        return json.loads(val) if val else None
    try:
        with open(_NATIVE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_raw(data):
    text = json.dumps(data)
    if sys.platform == "emscripten":
        import js
        js.localStorage.setItem(_KEY, text)
    else:
        with open(_NATIVE_PATH, "w") as f:
            f.write(text)


def _migrate(data):
    if data.get("version", 1) < 2:
        data["character"]["name"] = data["character"].get("name", "")
        data["gold"] = data.get("gold", 0)
        data["inventory"] = data.get("inventory", {})
        data["version"] = 2
    if data["version"] < 3:
        # POINTS_PER_LEVEL went 3->4. A character at level L already received
        # 3*(L-1) points but was owed 4*(L-1) - the deficit is exactly L-1.
        level = data["character"]["level"]
        data["character"]["unspent_points"] += (level - 1)
        data["version"] = 3
    if data["version"] < 4:
        # Difficulty tiers (Stage B5) turn "highest_level_cleared" from one
        # global int into a per-tier dict. Stage B4 also renumbered the
        # campaign in this same window (old level 4 = Shadow King is now
        # level 12) without its own migration - only levels 1-3 kept
        # identical content across that renumbering, so a stale int beyond
        # that can't be trusted to mean the same level anymore. Clamping to
        # 3 here is the correction that renumbering should have shipped
        # with.
        old_highest = data["progression"].get("highest_level_cleared", 0)
        safe_highest = min(old_highest, 3) if isinstance(old_highest, int) else 0
        data["progression"] = {
            "current_difficulty": "normal",
            "highest_level_cleared": {"normal": safe_highest},
            "cleared_difficulties": [],
        }
        data["version"] = 4
    if data["version"] < 5:
        # Sorte (luck) attribute added (Stage D). Existing characters get
        # the same baseline every attribute starts at (BASE_ATTR = 10) -
        # it's a new sink, not a rebalance of points already spent
        # elsewhere, so no deficit correction like the v2->3 step needed.
        data["character"]["attributes"].setdefault("lck", 10)
        data["version"] = 5
    if data["version"] < 6:
        data["progression"]["levels_seen"] = data["progression"].get("levels_seen", [])
        data["version"] = 6
    if data["version"] < 7:
        # Stage K12: hotbar item selection (max 3) is now player-editable -
        # existing saves get the exact 3 potions the hotbar always showed
        # before this was selectable, so nobody's hotbar changes on load.
        data["hotbar_items"] = data.get("hotbar_items", ["health_potion", "mana_potion", "antidote"])
        data["version"] = 7
    return data


def update_browser_title(player):
    """Stage F6: browser tab title reflects who's playing, once a player
    exists - "Dungeon Master - {Nome} - Lvl {N}". Desktop keeps the fixed
    caption set once in main.py; same emscripten-only bridge as
    _read_raw/_write_raw's localStorage calls above, just targeting
    document.title instead."""
    if sys.platform != "emscripten":
        return
    import js
    js.document.title = f"Dungeon Master - {player.name or 'Heroi'} - Lvl {player.level}"


def load():
    """A full state dict (migrated to SAVE_VERSION), or None if no save exists."""
    data = _read_raw()
    if data is None:
        return None
    return _migrate(data)


def save(state):
    state["version"] = SAVE_VERSION
    _write_raw(state)


def character_from_state(state, x, y, audio_mgr):
    char = state["character"]
    p = Player(x, y, audio_mgr)
    attrs = char["attributes"]
    p.stats.strength = attrs["str"]
    p.stats.dexterity = attrs["dex"]
    p.stats.intelligence = attrs["int"]
    p.stats.wisdom = attrs["wis"]
    p.stats.vigor = attrs["vig"]
    p.stats.luck = attrs.get("lck", 10)
    p.profession = determine_profession(p.stats)
    p.name = char.get("name", "")
    p.level = char["level"]
    p.xp = char["xp"]
    p.unspent_points = char["unspent_points"]
    p.gold = state.get("gold", 0)
    p.inventory = dict(state.get("inventory", {}))
    p.hotbar_items = list(state.get("hotbar_items", ["health_potion", "mana_potion", "antidote"]))
    p.hp = p.max_hp
    p.mana = p.max_mana
    return p


def sync_character(state, player):
    char = state["character"]
    char["name"] = player.name
    char["level"] = player.level
    char["xp"] = player.xp
    char["unspent_points"] = player.unspent_points
    char["attributes"] = {
        "str": player.stats.strength, "dex": player.stats.dexterity,
        "int": player.stats.intelligence, "wis": player.stats.wisdom,
        "vig": player.stats.vigor, "lck": player.stats.luck,
    }


def sync_economy(state, player):
    state["gold"] = player.gold
    state["inventory"] = dict(player.inventory)
    state["hotbar_items"] = list(player.hotbar_items)


def sync_counters(state, player):
    """Merges the player's in-run kill counters into the persisted totals
    and resets them, so a later call never double-counts the same kill."""
    counters = state["counters"]
    for etype, n in player.kills.items():
        counters["kills"][etype] = counters["kills"].get(etype, 0) + n
    player.kills = {}
    for boss_key, n in player.boss_kills.items():
        counters["boss_kills"][boss_key] = counters["boss_kills"].get(boss_key, 0) + n
    player.boss_kills = {}


_SYNCED_AT_KEY = "dungeon_quest_synced_at"


def get_synced_at():
    """The server `updated_at` this client last successfully synced against -
    sync plumbing, not game state, so it lives in its own localStorage key
    (same pattern as the JWT in game/net.py) rather than inside the
    SAVE_VERSION-migrated blob. 0.0 (never synced) if absent/native."""
    if sys.platform != "emscripten":
        return 0.0
    import js
    val = js.localStorage.getItem(_SYNCED_AT_KEY)
    return float(val) if val else 0.0


def set_synced_at(updated_at):
    if sys.platform != "emscripten":
        return
    import js
    js.localStorage.setItem(_SYNCED_AT_KEY, str(updated_at))


def merge_states(local, remote, local_synced_at, remote_updated_at):
    """local, remote: full save dicts, both already migrated to SAVE_VERSION.
    local_synced_at: the remote `updated_at` this client had at its last
    successful sync (get_synced_at()).
    remote_updated_at: the `updated_at` GET /save just returned alongside
    `remote`.

    Returns a merged dict, ready to both persist locally (save()) and PUT
    back to the server.

    Two merge policies, matching what sync_counters() already established
    for kills/boss_kills (additive/never-regress) vs. what sync_economy()
    already established for gold/inventory (flat overwrite):

    - character/gold/inventory/hotbar_items/settings/current_difficulty: whichever side
      wrote more recently than our last known sync point wins wholesale. If
      the server has moved forward since we last synced (another device
      wrote), the server's version wins; otherwise our own local edits (made
      since that same sync point) win. This is last-write-wins using the
      server's clock as the single source of truth, instead of trusting two
      devices' independent clocks against each other.
    - counters/progression's monotonic fields: always max/union-merge
      regardless of timestamp - safe in both directions, generalizes
      sync_counters()'s "kills/boss_kills never regress" policy to every
      monotonic field in the schema. playtime_s uses max (not sum)
      deliberately: two devices can't be reliably summed without session
      boundaries neither device knows about, and max never fabricates play
      time that didn't happen - same never-regress/don't-overclaim spirit as
      kills/deaths.
    """
    merged = copy.deepcopy(local)

    if remote_updated_at > local_synced_at:
        merged["character"] = remote["character"]
        merged["gold"] = remote["gold"]
        merged["inventory"] = remote["inventory"]
        merged["hotbar_items"] = remote.get("hotbar_items", merged["hotbar_items"])
        merged["settings"] = remote["settings"]
        merged["progression"]["current_difficulty"] = remote["progression"]["current_difficulty"]

    c, rc = merged["counters"], remote["counters"]
    for etype, n in rc["kills"].items():
        c["kills"][etype] = max(c["kills"].get(etype, 0), n)
    for bkey, n in rc["boss_kills"].items():
        c["boss_kills"][bkey] = max(c["boss_kills"].get(bkey, 0), n)
    c["deaths"] = max(c["deaths"], rc["deaths"])
    c["playtime_s"] = max(c["playtime_s"], rc["playtime_s"])

    p, rp = merged["progression"], remote["progression"]
    p["levels_seen"] = sorted(set(p["levels_seen"]) | set(rp["levels_seen"]))
    p["cleared_difficulties"] = sorted(set(p["cleared_difficulties"]) | set(rp["cleared_difficulties"]))
    for tier, lvl in rp["highest_level_cleared"].items():
        p["highest_level_cleared"][tier] = max(p["highest_level_cleared"].get(tier, 0), lvl)

    return merged
