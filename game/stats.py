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
BASE_ATTACK_COOLDOWN = 0.45

# Bugfix round (2a leva): bonus flat de XP pra quem cavou a chave escondida
# num level coop (game/level.py's key_finder_id) - só se aplica em coop
# (key_finder_id fica None em single-player, ver Level.__init__), aplicado
# uma vez na transicao de fase (GameStateManager._transition, "next:" branch).
KEY_FINDER_XP_BONUS = 40


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
        return BASE_ATTACK_COOLDOWN * (1 - self.haste)

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


# Named (not inline) so Stage I4's balance admin panel can override them at
# runtime via game/balance_config.py - xp_to_next() below reads these from
# this module's own globals at call time, so a `stats.XP_CURVE_BASE = x`
# from outside takes effect immediately, no matter who imported xp_to_next
# by reference or when.
XP_CURVE_BASE = 20
XP_CURVE_EXP = 1.4


def xp_to_next(level):
    return round(XP_CURVE_BASE * level ** XP_CURVE_EXP)


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

    # Estagio N (leva de conteudo - familias de monstro): 20 familias x 3
    # tiers, cada tier com sua PROPRIA entrada (nao um multiplicador em
    # cima de uma base compartilhada) - mesma disciplina que a passagem de
    # individualizacao acima já seguiu, pra nao repetir o erro dos
    # recolors aposentados. 7 familias reusam 1-3 monstros ja existentes
    # como algum dos tiers (Skeleton/Spider/Goblin/Demon/Golem/Zombie/
    # Saurian/Witch/Brute) - só as entradas NOVAS aparecem aqui.

    # --- Rato (Rat) ---
    "rato":              dict(strength=2,  dexterity=3,  vigor=0,  luck=0,  weapon_base=3.5, base_speed=140),
    "rato_gigante":      dict(strength=6,  dexterity=5,  vigor=4,  luck=0,  weapon_base=6,   base_speed=125),
    "rato_toxico":       dict(strength=10, dexterity=7,  vigor=8,  luck=8,  weapon_base=8,   base_speed=115),
    # --- Sapo (Toad) ---
    "sapo":              dict(strength=3,  dexterity=1,  vigor=3,  luck=0,  weapon_base=4.5, base_speed=75),
    "sapo_venenoso":     dict(strength=7,  dexterity=3,  vigor=8,  luck=0,  weapon_base=7,   base_speed=65),
    "sapo_rei":          dict(strength=12, dexterity=4,  vigor=14, luck=3,  weapon_base=9.5,  base_speed=60),
    # --- Minotauro (Minotaur) ---
    "minotauro_jovem":   dict(strength=7,  dexterity=1,  vigor=4,  luck=0,  weapon_base=6,   base_speed=85),
    "minotauro":         dict(strength=13, dexterity=2,  vigor=10, luck=0,  weapon_base=9,   base_speed=75),
    "minotauro_ancestral": dict(strength=19, dexterity=3, vigor=16, luck=8, weapon_base=12,  base_speed=65),
    # --- Lobo (Wolf) ---
    "lobo":              dict(strength=4,  dexterity=5,  vigor=1,  luck=0,  weapon_base=5,   base_speed=135),
    "lobo_alfa":         dict(strength=9,  dexterity=8,  vigor=6,  luck=0,  weapon_base=7.5, base_speed=125),
    "lobo_das_sombras":  dict(strength=14, dexterity=11, vigor=11, luck=10, weapon_base=10,  base_speed=115),
    # --- Urso (Bear) ---
    "urso":              dict(strength=6,  dexterity=0,  vigor=6,  luck=0,  weapon_base=6,   base_speed=70),
    "urso_da_matilha":   dict(strength=11, dexterity=1,  vigor=13, luck=0,  weapon_base=9,   base_speed=60),
    "urso_ancestral":    dict(strength=17, dexterity=2,  vigor=20, luck=5,  weapon_base=12,  base_speed=50),
    # --- Orc ---
    "orc_recruta":       dict(strength=6,  dexterity=2,  vigor=2,  luck=0,  weapon_base=5.5, base_speed=95),
    "orc_guerreiro":     dict(strength=12, dexterity=4,  vigor=7,  luck=0,  weapon_base=8.5, base_speed=85),
    "orc_brutamontes":   dict(strength=18, dexterity=5,  vigor=13, luck=5,  weapon_base=11.5, base_speed=75),
    # --- Drake ---
    "drake_jovem":       dict(strength=5,  dexterity=5,  vigor=2,  luck=0,  weapon_base=5.5, base_speed=110),
    "drake":             dict(strength=10, dexterity=8,  vigor=7,  luck=0,  weapon_base=8.5, base_speed=100),
    "drake_anciao":      dict(strength=16, dexterity=10, vigor=13, luck=10, weapon_base=12,  base_speed=90),
    # --- Vampiro (Vampire) ---
    "servo_vampirico":   dict(strength=4,  dexterity=5,  vigor=1,  luck=3,  weapon_base=5,   base_speed=105),
    "vampiro":           dict(strength=9,  dexterity=9,  vigor=6,  luck=10, weapon_base=8,   base_speed=100),
    "lorde_vampiro":     dict(strength=14, dexterity=13, vigor=11, luck=20, weapon_base=11,  base_speed=95),
    # --- Fantasma (Ghost) ---
    "espectro":          dict(strength=3,  dexterity=6,  vigor=0,  luck=0,  weapon_base=5,   base_speed=130),
    "fantasma":          dict(strength=7,  dexterity=10, vigor=3,  luck=5,  weapon_base=7.5, base_speed=120),
    "espirito_vingativo": dict(strength=11, dexterity=14, vigor=6, luck=15, weapon_base=10.5, base_speed=115),
    # --- Geleia (Slime) ---
    "geleia":            dict(strength=2,  dexterity=0,  vigor=4,  luck=0,  weapon_base=4,   base_speed=65),
    "geleia_acida":      dict(strength=6,  dexterity=1,  vigor=10, luck=0,  weapon_base=6.5, base_speed=55),
    "geleia_real":       dict(strength=10, dexterity=2,  vigor=17, luck=5,  weapon_base=9,   base_speed=50),
    # --- Caranguejo (Crab) ---
    "caranguejo":        dict(strength=4,  dexterity=1,  vigor=4,  luck=0,  weapon_base=5,   base_speed=75),
    "caranguejo_blindado": dict(strength=9, dexterity=2, vigor=10, luck=0,  weapon_base=7.5, base_speed=65),
    "rei_caranguejo":    dict(strength=14, dexterity=3,  vigor=17, luck=5,  weapon_base=10.5, base_speed=55),
    # --- Lobisomem (Werewolf) ---
    "licantropo":        dict(strength=6,  dexterity=5,  vigor=2,  luck=0,  weapon_base=6,   base_speed=110),
    "lobisomem":         dict(strength=12, dexterity=9,  vigor=7,  luck=5,  weapon_base=9,   base_speed=105),
    "lobisomem_alfa":    dict(strength=18, dexterity=13, vigor=13, luck=15, weapon_base=12,  base_speed=100),

    # --- Novos tiers de familias que ja tinham monstro(s) existente(s) ---
    # Spider (aranha ja existe como tier 1)
    "aranha_cacadora":   dict(strength=9,  dexterity=13, vigor=7,  luck=0,  weapon_base=7,   base_speed=95),
    "rainha_aranha":     dict(strength=14, dexterity=18, vigor=12, luck=15, weapon_base=10,  base_speed=90),
    # Goblin (goblin ja existe como tier 1)
    "goblin_guerreiro":  dict(strength=9,  dexterity=3,  vigor=5,  luck=0,  weapon_base=8,   base_speed=100),
    "lider_goblin":      dict(strength=14, dexterity=4,  vigor=10, luck=15, weapon_base=11,  base_speed=90),
    # Demon (imp ja existe como tier 1)
    "demonio_menor":     dict(strength=8,  dexterity=10, vigor=6,  luck=0,  weapon_base=7,   base_speed=110),
    "demonio_maior":     dict(strength=13, dexterity=13, vigor=11, luck=15, weapon_base=10.5, base_speed=105),
    # Golem (elemental_pedra ja existe como tier 1)
    "golem_de_ferro":    dict(strength=16, dexterity=1,  vigor=24, luck=0,  weapon_base=10.5, base_speed=30),
    "golem_runico":      dict(strength=20, dexterity=2,  vigor=30, luck=10, weapon_base=13,  base_speed=28),
    # Zombie (zumbi ja existe como tier 1)
    "zumbi_podre":       dict(strength=11, dexterity=1,  vigor=13, luck=0,  weapon_base=8,   base_speed=35),
    "abominacao":        dict(strength=16, dexterity=1,  vigor=20, luck=5,  weapon_base=11,  base_speed=30),
    # Saurian (serpente=tier1, lyzardman=tier2 ja existem)
    "saurio_ancestral":  dict(strength=17, dexterity=10, vigor=12, luck=12, weapon_base=11.5, base_speed=95),
    # Witch (acolito=tier1, feiticeira=tier2 ja existem)
    "bruxa_suprema":     dict(strength=8,  dexterity=6,  vigor=9,  luck=10, weapon_base=12,  base_speed=80),
    # Brute (troll=tier1, ogro=tier2 ja existem)
    "ogro_anciao":       dict(strength=22, dexterity=2,  vigor=22, luck=10, weapon_base=13.5, base_speed=45),
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
    # Estagio N: 49 monstros novos - XP/ouro flat por tier (1=fraco,
    # 2=medio, 3=forte), mesma faixa que os arquétipos ML1-11 acima já
    # cobrem, sem uma calibracao individual por familia (nao existe
    # balance_sim.py ainda pra validar isso com precisao).
    "rato": 9, "rato_gigante": 19, "rato_toxico": 30,
    "sapo": 9, "sapo_venenoso": 19, "sapo_rei": 30,
    "minotauro_jovem": 19, "minotauro": 30, "minotauro_ancestral": 38,
    "lobo": 9, "lobo_alfa": 19, "lobo_das_sombras": 30,
    "urso": 19, "urso_da_matilha": 30, "urso_ancestral": 38,
    "orc_recruta": 9, "orc_guerreiro": 19, "orc_brutamontes": 30,
    "drake_jovem": 19, "drake": 30, "drake_anciao": 38,
    "servo_vampirico": 9, "vampiro": 19, "lorde_vampiro": 30,
    "espectro": 9, "fantasma": 19, "espirito_vingativo": 30,
    "geleia": 9, "geleia_acida": 19, "geleia_real": 30,
    "caranguejo": 9, "caranguejo_blindado": 19, "rei_caranguejo": 30,
    "licantropo": 19, "lobisomem": 30, "lobisomem_alfa": 38,
    "aranha_cacadora": 19, "rainha_aranha": 30,
    "goblin_guerreiro": 19, "lider_goblin": 30,
    "demonio_menor": 19, "demonio_maior": 30,
    "golem_de_ferro": 30, "golem_runico": 38,
    "zumbi_podre": 19, "abominacao": 30,
    "saurio_ancestral": 30,
    "bruxa_suprema": 30,
    "ogro_anciao": 38,
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
    # Estagio N: mesma faixa flat por tier de BASE_XP acima.
    "rato": 4, "rato_gigante": 7, "rato_toxico": 12,
    "sapo": 4, "sapo_venenoso": 7, "sapo_rei": 12,
    "minotauro_jovem": 7, "minotauro": 12, "minotauro_ancestral": 15,
    "lobo": 4, "lobo_alfa": 7, "lobo_das_sombras": 12,
    "urso": 7, "urso_da_matilha": 12, "urso_ancestral": 15,
    "orc_recruta": 4, "orc_guerreiro": 7, "orc_brutamontes": 12,
    "drake_jovem": 7, "drake": 12, "drake_anciao": 15,
    "servo_vampirico": 4, "vampiro": 7, "lorde_vampiro": 12,
    "espectro": 4, "fantasma": 7, "espirito_vingativo": 12,
    "geleia": 4, "geleia_acida": 7, "geleia_real": 12,
    "caranguejo": 4, "caranguejo_blindado": 7, "rei_caranguejo": 12,
    "licantropo": 7, "lobisomem": 12, "lobisomem_alfa": 15,
    "aranha_cacadora": 7, "rainha_aranha": 12,
    "goblin_guerreiro": 7, "lider_goblin": 12,
    "demonio_menor": 7, "demonio_maior": 12,
    "golem_de_ferro": 12, "golem_runico": 15,
    "zumbi_podre": 7, "abominacao": 12,
    "saurio_ancestral": 12,
    "bruxa_suprema": 12,
    "ogro_anciao": 15,
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


# Named for the same Stage I4 override reason as XP_CURVE_BASE/EXP above.
ML_GROWTH_RATE = 0.35
ANTI_FARM_LEVEL_GAP = 5
ANTI_FARM_XP_MULT = 0.1


def scale_by_ml(base_amount, ml):
    """XP/gold growth per monster level - same formula for both, no separate
    multiplier table (per the RPG systems expansion plan's note)."""
    return base_amount * (1 + ML_GROWTH_RATE * (ml - 1))


def xp_for_kill(base_xp, monster_level, player_level):
    """Anti-farm rule: a monster ANTI_FARM_LEVEL_GAP+ levels below the player
    gives only ANTI_FARM_XP_MULT of the XP, so grinding early content for
    late-game gold doesn't trivially also grind XP - farming still has to
    happen on level-appropriate content."""
    xp = scale_by_ml(base_xp, monster_level)
    if player_level - monster_level >= ANTI_FARM_LEVEL_GAP:
        xp *= ANTI_FARM_XP_MULT
    return round(xp)


def gold_for_kill(base_gold, monster_level):
    """No anti-farm penalty, deliberately - farming already-cleared content
    for gold (to afford potions before the next difficulty) is the intended
    loop, not something to suppress the way trivial XP farming is."""
    return round(scale_by_ml(base_gold, monster_level))
