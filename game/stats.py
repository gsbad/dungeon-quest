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
                 vigor=10, luck=10, weapon_base=4, base_speed=190, level=1):
        self.strength = strength
        self.dexterity = dexterity
        self.intelligence = intelligence
        self.wisdom = wisdom
        self.vigor = vigor
        self.luck = luck
        self.weapon_base = weapon_base
        self.base_speed = base_speed
        self.level = level

    @property
    def max_hp(self):
        return round(20 + 3 * self.vigor)

    @property
    def hp_regen(self):
        return 0.05 + 0.025 * self.vigor

    @property
    def physical_damage(self):
        return round(self.weapon_base + 0.5 * self.strength)

    # Mana/mana regen are Wisdom's resource (Sabedoria governs magic
    # sustain/defense/healing); Intelligence instead drives magic_damage
    # below - the two attributes used to be reversed from this.
    @property
    def max_mana(self):
        return round(5 + 2 * self.wisdom)

    @property
    def mana_regen(self):
        return 1.0 + 0.05 * self.wisdom

    def magic_damage(self, spell_base):
        return round(spell_base * (1 + 0.04 * self.intelligence))

    @property
    def healing_power(self):
        return 1 + 0.01 * self.intelligence + 0.02 * self.wisdom

    @property
    def speed(self):
        return min(self.base_speed + 60, self.base_speed + 1.2 * self.dexterity)

    @property
    def haste(self):
        return min(0.35, 0.003 * self.dexterity)

    @property
    def attack_cooldown(self):
        return 0.45 * (1 - self.haste)

    # Each defense sums to 1.0 total weight across its 3 contributing
    # attributes, so no single attribute can trivialize it - see mitigate()
    # below for how the raw value turns into a % damage reduction.
    @property
    def physical_defense(self):
        return 0.4 * self.vigor + 0.4 * self.strength + 0.2 * self.dexterity

    @property
    def magic_defense(self):
        return 0.4 * self.vigor + 0.4 * self.wisdom + 0.2 * self.dexterity

    @property
    def crit_chance(self):
        return min(0.60, 0.005 * self.luck)

    @property
    def crit_damage_mult(self):
        return 1.5 + 0.005 * self.luck

    def roll_physical(self):
        """(damage, is_crit) for a physical (contact) hit - crit only ever
        applies to physical damage, never magic. Shared by player and
        monster melee alike; monster archetypes default luck=0 so this is
        inert for them until an archetype opts in."""
        import random
        is_crit = random.random() < self.crit_chance
        dmg = self.physical_damage
        if is_crit:
            dmg = round(dmg * self.crit_damage_mult)
        return dmg, is_crit


# Diminishing-returns "armor ratio" mitigation (K = the defense value at
# which damage is halved) - defense can never reach 100% reduction and
# needs no separate cap/floor bookkeeping, unlike a flat %-per-point scheme.
# 120 (not the more obvious round 100) was picked by checking
# tools/balance_sim.py's TTK matrix at the campaign's hardest reachable
# fight (Inferno-tier L11, ML68 dark_knight) - defense now legitimately
# lengthens that fight vs. pre-defense numbers, which reads as "Inferno is
# the hardest tier" rather than a bug, but K=90 stretched it further than
# that; 120 keeps early/mid-game mitigation (ML1-20) nearly identical while
# reining in the endgame tail.
MITIGATION_K = 120


def mitigate(amount, defense):
    return amount * MITIGATION_K / (MITIGATION_K + defense)


def xp_to_next(level):
    return round(20 * level ** 1.4)


# Attribute blocks calibrated so physical_damage/max_hp land close to the
# target numbers from the RPG redesign plan (goblin 20hp/7dmg, dark_knight
# 44hp/16dmg) while dexterity stays 0 - i.e. speed is untouched by this pass;
# monster movement speed still comes straight from base_speed (Stage B tunes
# monster DEX deliberately, once balance_sim.py exists to check the fallout).
ENEMY_ARCHETYPES = {
    "goblin":      dict(strength=3,  dexterity=0, vigor=0, luck=0, weapon_base=5.5, base_speed=110),
    "skeleton":    dict(strength=10, dexterity=0, vigor=2, luck=0, weapon_base=3,   base_speed=70),
    "dark_knight": dict(strength=12, dexterity=0, vigor=8, luck=0, weapon_base=10,  base_speed=55),
    # Individualization pass (levels 5/6/7/9/10/11) - swamp_troll/cursed_mage/
    # crypt_wraith/ash_fiend/royal_guard retired (they were only ever
    # recolors of skeleton/goblin/dark_knight, ENEMY_SPRITES-wise, and only
    # appeared inside these 6 levels) in favor of a per-level, per-monster
    # roster with its own rig (game/assets.py's ENEMY_SPRITES) and attack
    # (game/enemy.py's ENEMY_FLAVOR). Sprite/attack flavor lives in those two
    # files, not here - this is combat stats only.
    # Level 5 - Pantano Sombrio
    "aranha":          dict(strength=4,  dexterity=8, vigor=2,  luck=0, weapon_base=4,  base_speed=100),
    "serpente":        dict(strength=5,  dexterity=6, vigor=2,  luck=0, weapon_base=5,  base_speed=90),
    "treant":          dict(strength=10, dexterity=0, vigor=12, luck=0, weapon_base=5,  base_speed=40),
    # Level 6 - Torre Amaldicoada (skeleton reused, not redefined)
    "troll":           dict(strength=9,  dexterity=0, vigor=10, luck=0, weapon_base=6,  base_speed=55),
    "death_knight":    dict(strength=14, dexterity=2, vigor=12, luck=0, weapon_base=11, base_speed=55),
    # Level 7 - Cripta Perdida
    "zumbi":           dict(strength=8,  dexterity=0, vigor=8,  luck=0, weapon_base=6,  base_speed=40),
    "verme":           dict(strength=5,  dexterity=2, vigor=4,  luck=0, weapon_base=4,  base_speed=70),
    "imp":             dict(strength=3,  dexterity=6, vigor=2,  luck=0, weapon_base=4,  base_speed=100),
    # Level 9 - Salao dos Ecos
    "dark_horse":      dict(strength=10, dexterity=8, vigor=6,  luck=0, weapon_base=7,  base_speed=130),
    "acolito":         dict(strength=3,  dexterity=0, vigor=4,  luck=0, weapon_base=6,  base_speed=65),
    "feiticeira":      dict(strength=4,  dexterity=2, vigor=5,  luck=0, weapon_base=8,  base_speed=70),
    # Level 10 - Abismo de Cinzas
    "fire_hound":      dict(strength=7,  dexterity=6, vigor=5,  luck=0, weapon_base=6,  base_speed=120),
    "ogro":            dict(strength=16, dexterity=0, vigor=14, luck=0, weapon_base=10, base_speed=50),
    "elemental_pedra": dict(strength=12, dexterity=0, vigor=18, luck=0, weapon_base=8,  base_speed=35),
    # Level 11 - Corredor Final
    "chimera":         dict(strength=14, dexterity=6, vigor=14, luck=0,  weapon_base=10, base_speed=75),
    "lyzardman":       dict(strength=10, dexterity=8, vigor=7,  luck=0,  weapon_base=8,  base_speed=100),
    # Elite crit archetype (role royal_guard used to fill) - luck>0 telegraphs
    # "this one can crit" without a whole new mechanic.
    "dark_skeleton":   dict(strength=13, dexterity=6, vigor=9,  luck=15, weapon_base=9,  base_speed=60),
}

# Base XP/gold per kill at monster level (ML) 1 - see scale_by_ml() below for
# how these grow with ML. Bosses aren't part of the ML system (they're
# hand-calibrated unique encounters, not fungible common mobs), so their
# xp_reward/gold_reward stay flat constants on the Boss/CacodemonBoss classes.
BASE_XP = {
    "skeleton": 10,
    "goblin": 8,
    "dark_knight": 25,
    "aranha": 9, "serpente": 9, "treant": 20,
    "troll": 20, "death_knight": 28,
    "zumbi": 16, "verme": 14, "imp": 18,
    "dark_horse": 24, "acolito": 20, "feiticeira": 26,
    "fire_hound": 22, "ogro": 28, "elemental_pedra": 30,
    "chimera": 32, "lyzardman": 24, "dark_skeleton": 28,
}
GOLD_DROPS = {
    "skeleton": 4,
    "goblin": 3,
    "dark_knight": 10,
    "aranha": 4, "serpente": 4, "treant": 8,
    "troll": 8, "death_knight": 11,
    "zumbi": 6, "verme": 6, "imp": 7,
    "dark_horse": 9, "acolito": 8, "feiticeira": 10,
    "fire_hound": 9, "ogro": 11, "elemental_pedra": 12,
    "chimera": 13, "lyzardman": 9, "dark_skeleton": 11,
}

# Boss identities (Stage B4) - the campaign now has 3 acts, each ending in
# its own boss, instead of one boss for the whole game. All 3 share the
# exact same Boss class/attack-pattern shape (see game/boss.py) - only the
# attribute block, name, and reward differ. Sprite look is no longer a
# palette on this dict (Stage B4b individualization) - each boss_id has its
# own dedicated rig in game/assets.py's BOSS_SPRITES/create_boss_sprite();
# this dict stays stats/reward-only. Shadow King's own numbers are
# untouched from Stage A3's calibration (still 270 hp) - only its reward
# moved up, since it's now the campaign's true final boss (Act 3) rather
# than its only one.
BOSS_ARCHETYPES = {
    "orc_warlord": dict(
        name="Senhor da Guerra Orc", strength=10, dexterity=0, vigor=46.67, luck=0,
        weapon_base=2, base_speed=90, xp_reward=100, gold_reward=40,
    ),
    "necromancer": dict(
        name="Necromante", strength=10, dexterity=0, vigor=63.33, luck=0,
        weapon_base=2.5, base_speed=70, xp_reward=200, gold_reward=80,
    ),
    "shadow_king": dict(
        name="Rei das Sombras", strength=10, dexterity=0, vigor=83.33, luck=0,
        weapon_base=3, base_speed=80, xp_reward=300, gold_reward=120,
    ),
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
