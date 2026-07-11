"""
Paragon spawns and affixes (Stage B3). One registry, two consumers by
design: Paragon monsters draw an affix now, and Stage B5's difficulty-tier
level affixes (Cursed Ground, Hastened, etc.) will draw from this same
AFFIXES dict later - one system, not two parallel ones, per the RPG
redesign plan.

Paragon-ness is rolled once at spawn time (see apply_paragon_rolls(),
called by GameplayState right after building a Level) and mutates the
already-constructed Enemy in place - Level.py itself stays unaware that
Paragon exists at all, same separation-of-concerns as game/weather.py not
needing to know about difficulty.
"""
import random
import pygame
from game.stats import StatBlock, ENEMY_ARCHETYPES, scale_archetype

PARAGON_CHANCE = 0.03  # Normal tier; Stage B5 adds +2%/difficulty on top
PARAGON_PITY_SPAWNS = 20  # ~ one 3-level "act" worth of monsters (see B4)
PARAGON_REWARD_MULT = 4  # xp and gold alike, per the RPG redesign plan

AFFIXES = {
    "frenzied": {"name": "Frenetico", "color": (255, 120, 40)},
    "colossal": {"name": "Colossal", "color": (200, 160, 60)},
    "volatile": {"name": "Volatil", "color": (220, 60, 200)},
    "swift": {"name": "Veloz", "color": (100, 220, 255)},
    "warded": {"name": "Protegido", "color": (140, 200, 140)},
    "vampiric": {"name": "Vampirico", "color": (200, 30, 60)},
}


def roll_paragon(player):
    """True if the next spawn should be a Paragon - also advances/resets
    the pity counter on game/player.py's Player."""
    player.paragon_pity += 1
    if player.paragon_pity >= PARAGON_PITY_SPAWNS or random.random() < PARAGON_CHANCE:
        player.paragon_pity = 0
        return True
    return False


def apply_paragon_rolls(enemies, player):
    for enemy in enemies:
        if roll_paragon(player):
            make_paragon(enemy)


def make_paragon(enemy):
    """+2 monster levels, one random affix, x4 xp/gold, golden aura +
    floating name (game/enemy.py's Enemy.draw() checks is_paragon)."""
    enemy.is_paragon = True
    enemy.ml += 2
    enemy.stats = StatBlock(**scale_archetype(ENEMY_ARCHETYPES[enemy.etype], enemy.ml))
    enemy.max_hp = enemy.stats.max_hp
    enemy.hp = enemy.max_hp
    enemy.damage = enemy.stats.physical_damage
    enemy.speed = enemy.stats.speed * enemy._speed_mult

    enemy.affix = random.choice(list(AFFIXES))
    if enemy.affix == "frenzied":
        enemy.attack_cd_max /= 1.4
    elif enemy.affix == "colossal":
        enemy.max_hp = round(enemy.max_hp * 1.8)
        enemy.hp = enemy.max_hp
        enemy.width = round(enemy.width * 1.15)
        enemy.height = round(enemy.height * 1.15)
        enemy.sprite = pygame.transform.scale(
            enemy.sprite, (enemy.sprite.get_width() * 115 // 100, enemy.sprite.get_height() * 115 // 100)
        )
    elif enemy.affix == "swift":
        enemy.speed *= 1.3
    # "volatile" (death explosion), "warded" (block chance), and "vampiric"
    # (lifesteal) are pure combat-side hooks with no spawn-time stat change -
    # see game/level.py's kill/attack sites for where they actually apply.
