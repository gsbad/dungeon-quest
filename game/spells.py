"""
Player spells (Stage B2). Reuses existing combat primitives on purpose -
Fireball is a Projectile (game/boss.py) with a spell-shaped damage formula,
Frost Nova reuses the same circular-burst geometry bosses already fire
(and the existing "slow" status effect - see game/status_effects.py - not
a second, near-duplicate debuff), and Healing Light is a direct heal, the
same shape as a Health Potion. No new rendering system for any of the three.

A spell is "unlocked" purely by meeting its attribute requirements - there's
no separate flag to persist (same reasoning as game/professions.py not
being in the save schema).
"""

SPELLS = {
    "fireball": {
        "name": "Bola de Fogo",
        "description": "Projetil de fogo em linha reta.",
        "mana_cost": 8,
        "cooldown": 2.0,
        "req": {"intelligence": 15},
        "spell_base": 12,
    },
    "frost_nova": {
        "name": "Nova de Gelo",
        "description": "Dano em area + Lentidao ao redor do jogador.",
        "mana_cost": 12,
        "cooldown": 3.0,
        "req": {"intelligence": 20, "wisdom": 15},
        # Stage H3: bumped above fireball's spell_base (12) - it's still an
        # AoE hit, so it's meant to out-damage the single-target bolt now
        # that both have the same short cooldown.
        "spell_base": 14,
    },
    "healing_light": {
        "name": "Luz Curativa",
        "description": "Cura 25% da vida maxima. Recarga de 7s.",
        "mana_cost": 15,
        "cooldown": 7.0,
        "req": {},  # falls back to the generic wisdom req below
        "heal_frac": 0.25,
    },
}
SPELLS["healing_light"]["req"] = {"wisdom": 25}

ORDER = ["fireball", "frost_nova", "healing_light"]  # keys F/Q/R, in this order

_ATTR_LABEL = {"strength": "FOR", "dexterity": "DES", "intelligence": "INT", "wisdom": "SAB", "vigor": "VIG"}


def meets_requirements(stats, spell_id):
    req = SPELLS[spell_id]["req"]
    return all(getattr(stats, attr) >= value for attr, value in req.items())


def missing_requirements(stats, spell_id):
    """[(label, have, need), ...] for whatever's not met yet - drives the
    paperdoll's "o que falta" display."""
    req = SPELLS[spell_id]["req"]
    return [(_ATTR_LABEL[attr], getattr(stats, attr), value)
            for attr, value in req.items() if getattr(stats, attr) < value]


def requirement_text(spell_id):
    req = SPELLS[spell_id]["req"]
    return ", ".join(f"{_ATTR_LABEL[attr]} {value}" for attr, value in req.items())
