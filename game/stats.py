"""
Shared attribute/derived-stat system (Stage A3 of the RPG redesign). Every
combatant - player, common enemy, boss - gets a StatBlock instead of ad-hoc
hp/damage/speed fields, so gear, level-ups, and difficulty affixes (Stage B)
have one formula set to hook into instead of four.

weapon_base/base_speed are per-archetype constants (a dagger vs. a warhammer,
a goblin's skitter vs. a dark knight's plod) that STR/DEX then modify - the
same role weapon_base already plays for physical_damage, just extended to
speed so DEX gives every unit the same *proportional* nudge without making
slow monsters suddenly outrun the player.

MAX_LEVEL = 30: current campaign content tops out around L10-12; monster
levels reach up to ~ML50 in the highest difficulty tier (see progression.py,
Stage B), but the player's own level curve caps at 30 by design.
"""

MAX_LEVEL = 30
POINTS_PER_LEVEL = 4


class StatBlock:
    def __init__(self, strength=10, dexterity=10, intelligence=10, wisdom=10,
                 vigor=10, weapon_base=4, base_speed=190, level=1):
        self.strength = strength
        self.dexterity = dexterity
        self.intelligence = intelligence
        self.wisdom = wisdom
        self.vigor = vigor
        self.weapon_base = weapon_base
        self.base_speed = base_speed
        self.level = level

    @property
    def max_hp(self):
        return round(20 + 3 * self.vigor)

    @property
    def physical_damage(self):
        return round(self.weapon_base + 0.5 * self.strength)

    @property
    def max_mana(self):
        return round(5 + 2 * self.intelligence)

    @property
    def mana_regen(self):
        return 1.0 + 0.05 * self.intelligence

    def magic_damage(self, spell_base):
        return round(spell_base * (1 + 0.04 * self.wisdom))

    @property
    def speed(self):
        return min(self.base_speed + 60, self.base_speed + 1.2 * self.dexterity)

    @property
    def attack_cooldown(self):
        return 0.45 * (1 - min(0.35, 0.003 * self.dexterity))


def xp_to_next(level):
    return round(20 * level ** 1.4)


# Attribute blocks calibrated so physical_damage/max_hp land close to the
# target numbers from the RPG redesign plan (goblin 20hp/7dmg, dark_knight
# 44hp/16dmg) while dexterity stays 0 - i.e. speed is untouched by this pass;
# monster movement speed still comes straight from base_speed (Stage B tunes
# monster DEX deliberately, once balance_sim.py exists to check the fallout).
ENEMY_ARCHETYPES = {
    "goblin":      dict(strength=3,  dexterity=0, vigor=0, weapon_base=5.5, base_speed=110),
    "skeleton":    dict(strength=10, dexterity=0, vigor=2, weapon_base=3,   base_speed=70),
    "dark_knight": dict(strength=12, dexterity=0, vigor=8, weapon_base=10,  base_speed=55),
}

# Base XP/gold per kill at monster level (ML) 1 - see scale_by_ml() below for
# how these grow with ML. Bosses aren't part of the ML system (they're
# hand-calibrated unique encounters, not fungible common mobs), so their
# xp_reward/gold_reward stay flat constants on the Boss/CacodemonBoss classes.
BASE_XP = {
    "skeleton": 10,
    "goblin": 8,
    "dark_knight": 25,
}
GOLD_DROPS = {
    "skeleton": 4,
    "goblin": 3,
    "dark_knight": 10,
}

# Per-monster-level growth (Stage B1 "divergence" pass) - same curve for
# every archetype, applied on top of its ENEMY_ARCHETYPES base block so ML1
# reproduces the Stage A3 calibration exactly (no change at ML1).
MONSTER_GROWTH_VECTOR = {"vigor": 2.0, "strength": 1.0, "dexterity": 0.5}


def scale_archetype(base_kwargs, ml):
    """ENEMY_ARCHETYPES[etype] grown to monster level `ml` (ml=1 is a no-op)."""
    scaled = dict(base_kwargs)
    for attr, per_ml in MONSTER_GROWTH_VECTOR.items():
        scaled[attr] = scaled.get(attr, 0) + per_ml * (ml - 1)
    return scaled


def scale_by_ml(base_amount, ml):
    """XP/gold growth per monster level - same formula for both, no separate
    multiplier table (per the RPG systems expansion plan's note)."""
    return base_amount * (1 + 0.35 * (ml - 1))


def xp_for_kill(base_xp, monster_level, player_level):
    """Anti-farm rule: a monster 5+ levels below the player gives only 10%
    XP, so grinding early content for late-game gold doesn't trivially also
    grind XP - farming still has to happen on level-appropriate content."""
    xp = scale_by_ml(base_xp, monster_level)
    if player_level - monster_level >= 5:
        xp *= 0.1
    return round(xp)


def gold_for_kill(base_gold, monster_level):
    """No anti-farm penalty, deliberately - farming already-cleared content
    for gold (to afford potions before the next difficulty) is the intended
    loop, not something to suppress the way trivial XP farming is."""
    return round(scale_by_ml(base_gold, monster_level))
