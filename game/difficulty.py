"""
Difficulty tiers (Stage B5). Each tier replays the same 12-level campaign
with the dial turned up - deliberately NOT through flat damage/hp
multipliers (the original design brief explicitly asked for something more
thought-through than that), but through the same levers Stages B1/B3/B4
already built:

  - ml_bonus shifts every level's monster_level up the SAME growth curve
    (game/stats.py's MONSTER_GROWTH_VECTOR) that already drives monster
    stats *and* xp/gold reward - harder tiers are stronger AND worth more,
    with no separate multiplier table to keep in sync.
  - champion_chance reuses game/affixes.py's AFFIXES (built for Paragon) to
    make some ordinary spawns tougher/stranger, not just bigger.
  - level_affixes are environment-wide effects for the whole level, drawn
    from the "level"-scoped entries of that same AFFIXES dict (see
    game/affixes.py's docstring) - Chao Amaldicoado, Penumbra, Horda
    Apressada.
  - boss_enrage_frac moves the boss's phase-2 threshold earlier, so higher
    tiers spend more of the fight in the harder phase - a structural
    change to the fight, not a bigger number.

Tiers unlock sequentially by clearing the previous one (reaching the
"victory" result at level 12) - see is_unlocked(). Clearing Inferno is
what gates the secret level (13, Cacodemon) open.
"""

DIFFICULTIES = {
    "normal": dict(
        name="Normal", order=0, ml_bonus=0, champion_chance=0.0,
        level_affixes=[], boss_enrage_frac=0.5,
    ),
    "hard": dict(
        name="Dificil", order=1, ml_bonus=6, champion_chance=0.08,
        level_affixes=["cursed_ground"], boss_enrage_frac=0.55,
    ),
    "very_hard": dict(
        name="Muito Dificil", order=2, ml_bonus=14, champion_chance=0.14,
        level_affixes=["cursed_ground", "dimming"], boss_enrage_frac=0.6,
    ),
    "nightmare": dict(
        name="Pesadelo", order=3, ml_bonus=24, champion_chance=0.20,
        level_affixes=["cursed_ground", "dimming", "hastened"], boss_enrage_frac=0.65,
    ),
    "inferno": dict(
        name="Inferno", order=4, ml_bonus=36, champion_chance=0.28,
        level_affixes=["cursed_ground", "dimming", "hastened"], boss_enrage_frac=0.7,
    ),
}

ORDER = ["normal", "hard", "very_hard", "nightmare", "inferno"]


def next_difficulty(diff_id):
    idx = ORDER.index(diff_id)
    return ORDER[idx + 1] if idx + 1 < len(ORDER) else None


def is_unlocked(diff_id, cleared_difficulties):
    """normal is always unlocked; every other tier requires the *previous*
    tier's campaign (level 12, "victory") to have been cleared at least
    once - a ladder, not independent switches."""
    if diff_id == ORDER[0]:
        return True
    idx = ORDER.index(diff_id)
    return ORDER[idx - 1] in cleared_difficulties
