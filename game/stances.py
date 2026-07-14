"""Stage K11: Posturas - a permanent (not timed) percentage buff tied to
whichever profession (game/professions.py) is currently active. Same
registry-dict pattern as STATUS_EFFECTS (game/status_effects.py) and every
other game/*.py table - one profession, one line, no branching logic.

Deliberately NOT built on StatusEffectCarrier/ActiveEffect (which is
timed-only, expires) - a Postura is derived from self.profession the exact
same way self.profession itself is derived from spent attribute points
(game/professions.py), so it never needs a duration or an apply()/expire()
lifecycle. Each entry is a sparse dict using the same field names Stage
K10 added to StatusEffectDef (physical_damage_mult, crit_chance_add, etc.)
so Player.stance_multiplier()/stance_bonus() (game/player.py) can read
both this and the timed carrier through the exact same _mult()/_bonus()
call sites - a stance and a potion buffing "physical_damage_mult" stack
the same way two debuffs already do.

Aventureiro (no build yet, <20 attribute points spent) has no entry -
Player.stance_multiplier()/_bonus() fall back to "no effect" for any
profession missing here, same as an unset field on a StatusEffectDef.
"""

STANCES = {
    "Guerreiro": {
        "name": "Postura do Colosso",
        "physical_damage_mult": 1.15,
        "physical_defense_mult": 1.10,
    },
    "Assassino": {
        "name": "Passos das Sombras",
        "speed_mult": 1.20,
        "crit_chance_add": 0.15,
    },
    "Mago": {
        "name": "Concentracao Arcana",
        "max_mana_mult": 1.20,
        "mana_regen_mult": 1.25,
    },
    "Feiticeiro": {
        "name": "Olho do Oraculo",
        "magic_damage_mult": 1.20,
        "debuff_chance_add": 0.10,
    },
    "Cavaleiro": {
        "name": "Muralha Viva",
        "max_hp_mult": 1.25,
        "damage_taken_mult": 0.90,
    },
    "Duelista": {
        "name": "Postura da Lamina Dancante",
        "physical_damage_mult": 1.10,
        "attack_speed_mult": 1.10,
        "dodge_chance_add": 0.05,
    },
    "Cavaleiro Arcano": {
        "name": "Postura da Espada Encantada",
        # Approximation: the exact ask ("ataques fisicos causam +10% de
        # dano magico") is an on-hit proc system that doesn't exist in the
        # game yet (no attack today deals two typed damage components at
        # once) - modeled instead as a flat magic-damage/mana boost, which
        # gets the "arcane knight" fantasy across without a new proc system.
        "magic_damage_mult": 1.10,
        "max_mana_mult": 1.10,
        "mana_cost_mult": 0.90,
    },
    "Paladino": {
        "name": "Postura da Luz Sagrada",
        "physical_damage_mult": 1.10,
        "debuff_resist_add": 0.15,
        "hp_regen_flat_pct": 0.02,
    },
    "Campeao": {
        "name": "Postura do Conquistador",
        "max_hp_mult": 1.20,
        "physical_damage_mult": 1.10,
        "physical_defense_mult": 1.10,
    },
    "Monge": {
        "name": "Postura da Serenidade",
        "mana_regen_mult": 1.20,
        "attack_speed_mult": 1.10,
        "mana_cost_mult": 0.85,
    },
    "Xama": {
        "name": "Postura dos Espiritos",
        "debuff_chance_add": 0.15,
        "speed_mult": 1.10,
        "magic_damage_mult": 1.10,
    },
    "Ranger": {
        "name": "Postura do Cacador",
        "speed_mult": 1.15,
        "crit_chance_add": 0.10,
        "hp_regen_flat_pct": 0.02,
    },
    "Arcanista": {
        "name": "Postura do Eclipse",
        "magic_damage_mult": 1.25,
        "mana_regen_mult": 1.20,
    },
    "Druida": {
        "name": "Postura da Natureza",
        "hp_regen_flat_pct": 0.02,
        "mana_regen_flat_pct": 0.02,
        "speed_mult": 1.10,
        "max_hp_mult": 1.10,
    },
    "Templario": {
        "name": "Postura do Guardiao",
        "damage_taken_mult": 0.85,
        "debuff_resist_add": 0.20,
        "hp_regen_flat_pct": 0.03,
    },
}

# Multiplicative fields default to 1.0 (no change) when absent from a
# stance's sparse dict; additive fields default to 0.0 - mirrors
# game/status_effects.py's StatusEffectDef defaults exactly, since a
# missing key here means the exact same thing an unset StatusEffectDef
# field does.
_MULTIPLICATIVE_FIELDS = frozenset({
    "speed_mult", "damage_taken_mult", "physical_damage_mult", "magic_damage_mult",
    "physical_defense_mult", "magic_defense_mult", "attack_speed_mult",
    "max_hp_mult", "max_mana_mult", "mana_regen_mult", "mana_cost_mult",
    "xp_gain_mult", "gold_gain_mult",
})


def stance_multiplier(profession, field):
    stance = STANCES.get(profession)
    if not stance:
        return 1.0
    return stance.get(field, 1.0)


def stance_bonus(profession, field):
    stance = STANCES.get(profession)
    if not stance:
        return 0.0
    return stance.get(field, 0.0)


def all_stances_multiplier(field):
    """Stage K13: debug-only ("ativar todas as posturas" row) - combines
    every Postura's bonus at once for balance-testing, something no real
    character can normally have (a character only ever has the one Postura
    tied to its current profession). Same aggregation stance_multiplier()
    already does for a single profession, just over every entry in STANCES."""
    mult = 1.0
    for stance in STANCES.values():
        mult *= stance.get(field, 1.0)
    return mult


def all_stances_bonus(field):
    return sum(stance.get(field, 0.0) for stance in STANCES.values())


# Player-facing description text for the Postura badge's tooltip (Stage K8's
# draw_tooltip) - the numbers here are prose renderings of STANCES above,
# same single-source discipline game/status_effects.py's STATUS_HELP follows.
STANCE_DESCRIPTIONS = {
    "Guerreiro": "Postura do Colosso: +15% dano fisico, +10% defesa fisica.",
    "Assassino": "Passos das Sombras: +20% velocidade de movimento, +15% critico.",
    "Mago": "Concentracao Arcana: +20% mana maxima, +25% regen. de mana.",
    "Feiticeiro": "Olho do Oraculo: +20% dano magico, +10% chance de aplicar debuffs.",
    "Cavaleiro": "Muralha Viva: +25% vida maxima, -10% dano recebido.",
    "Duelista": "Lamina Dancante: +10% dano fisico, +10% vel. de ataque, +5% esquiva.",
    "Cavaleiro Arcano": "Espada Encantada: +10% dano magico, +10% mana maxima, -10% custo de mana.",
    "Paladino": "Luz Sagrada: +10% dano fisico, +15% resist. a debuffs, +2% regen. vida/s.",
    "Campeao": "Conquistador: +20% vida maxima, +10% dano fisico, +10% defesa fisica.",
    "Monge": "Serenidade: +20% regen. de mana, +10% vel. de ataque, -15% custo de mana.",
    "Xama": "Espiritos: +15% chance de aplicar debuffs, +10% vel. movimento, +10% dano magico.",
    "Ranger": "Cacador: +15% vel. movimento, +10% critico, +2% regen. vida/s.",
    "Arcanista": "Eclipse: +25% dano magico, +20% regen. de mana.",
    "Druida": "Natureza: +2% regen. vida/s, +2% regen. mana/s, +10% vel. movimento, +10% vida maxima.",
    "Templario": "Guardiao: -15% dano recebido, +20% resist. a debuffs, +3% regen. vida/s.",
}
