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
POINTS_PER_LEVEL = 3


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
