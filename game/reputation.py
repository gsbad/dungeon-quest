"""
Reputation title (Stage F5), inspired by Ultima Online's fame/karma: fame is
approximated by total monster kills, karma by how many times the hero has
died. Same shape as game/professions.py's determine_profession - DERIVED
from existing counters (game/save.py's counters.kills/boss_kills/deaths),
not persisted separately, so there's nothing new to keep in sync.
"""

# (min_score, title) - score = total kills - deaths*3 (each death costs 3
# kills' worth of reputation, so a death is a real setback without needing
# a full run of grinding to recover from). Numbers are a starting point,
# easy to retune later without touching how the title is derived.
REPUTATION_TIERS = [
    (0, "Novato"),
    (25, "Combatente"),
    (75, "Veterano"),
    (150, "Heroi"),
    (300, "Lenda Viva"),
]

# A death-heavy record (negative score) reads as its own title rather than
# clamping to "Novato" - it should be visibly worse, not just "no progress".
CURSED_TITLE = "Amaldicoado"


def determine_reputation(kills_total, deaths):
    score = kills_total - deaths * 3
    if score < 0:
        return CURSED_TITLE
    title = REPUTATION_TIERS[0][1]
    for threshold, name in REPUTATION_TIERS:
        if score >= threshold:
            title = name
        else:
            break
    return title


def kills_total(player, save_state):
    """Lifetime kills = persisted counters + this run's not-yet-synced
    kills (game/save.py's sync_counters() merges player.kills into
    save_state and resets it, so both must be summed to avoid undercounting
    mid-run)."""
    total = sum(player.kills.values()) + sum(player.boss_kills.values())
    if save_state is not None:
        counters = save_state.get("counters", {})
        total += sum(counters.get("kills", {}).values())
        total += sum(counters.get("boss_kills", {}).values())
    return total


def deaths_total(save_state):
    if save_state is None:
        return 0
    return save_state.get("counters", {}).get("deaths", 0)
