"""
Player spells (Stage B2). Reuses existing combat primitives on purpose -
Fireball is a Projectile (game/boss.py) with a spell-shaped damage formula,
Frost Nova reuses the same circular-burst geometry bosses already fire
(and the existing "slow" status effect - see game/status_effects.py - not
a second, near-duplicate debuff), and Healing Light is a direct heal, the
same shape as a Health Potion. No new rendering system for any of the three.

Estagio M1 (leva de conteudo - kits de classe): SPELLS agora guarda a
DEFINICAO de toda magia do jogo (as 3 originais + as novas por profissao),
mas "quem pode lancar o que" nao mora mais aqui - virou game/class_kits.py's
CLASS_KITS (profession -> 3 magia-ids). O antigo `req` (limiar de atributo)
foi removido: ele so existia porque nao havia gate por profissao ainda, e
duplicava a mesma distribuicao de atributos que ja determina a profissao
(game/professions.py's determine_profession()) - ter a profissao certa ja
e o requisito, uma segunda checagem de atributo seria redundante. Continua
"sem flag pra persistir" pela mesma razao de antes: profissao/kit sao
sempre derivados, nunca salvos.
"""

SPELLS = {
    "fireball": {
        "name": "Bola de Fogo",
        "description": "Projetil de fogo em linha reta.",
        "mana_cost": 8,
        "cooldown": 2.0,
        "spell_base": 12,
    },
    "frost_nova": {
        "name": "Nova de Gelo",
        "description": "Dano em area + Lentidao ao redor do jogador.",
        "mana_cost": 12,
        "cooldown": 3.0,
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
        "heal_frac": 0.25,
        "aimable": False,
    },

    # --- Guerreiro ---
    "investida_brutal": {
        "name": "Investida Brutal",
        "description": "Investida curta com dano fisico pesado a frente.",
        "mana_cost": 10,
        "cooldown": 2.5,
        "spell_base": 16,
    },
    "grito_de_guerra": {
        "name": "Grito de Guerra",
        "description": "+25% dano fisico por 10s.",
        "mana_cost": 14,
        "cooldown": 14.0,
        "buff_id": "grito_de_guerra",
        "aimable": False,
    },
    "terremoto": {
        "name": "Terremoto",
        "description": "Onda de choque ao redor, dano fisico pesado em area.",
        "mana_cost": 24,
        "cooldown": 9.0,
        "spell_base": 22,
        "aimable": False,
    },

    # --- Assassino ---
    "veneno_mortal": {
        "name": "Veneno Mortal",
        "description": "Golpe curto que envenena tudo ao redor.",
        "mana_cost": 10,
        "cooldown": 4.0,
        "spell_base": 6,
        "aimable": False,
    },
    "passo_sombrio": {
        "name": "Passo Sombrio",
        "description": "Teleporte curto na direcao mirada.",
        "mana_cost": 12,
        "cooldown": 6.0,
        "teleport_dist": 160,
    },
    "laminas_giratorias": {
        "name": "Laminas Giratorias",
        "description": "Rodopio com laminas, dano fisico pesado em area.",
        "mana_cost": 22,
        "cooldown": 9.0,
        "spell_base": 20,
        "aimable": False,
    },

    # --- Cavaleiro ---
    "provocacao": {
        "name": "Provocacao",
        "description": "Deixa inimigos proximos mais agressivos contra voce.",
        "mana_cost": 8,
        "cooldown": 8.0,
        "aimable": False,
    },

    # --- Campeao ---
    "impacto_sismico": {
        "name": "Impacto Sismico",
        "description": "Atordoa e causa dano em area ao redor.",
        "mana_cost": 26,
        "cooldown": 12.0,
        "spell_base": 10,
        "aimable": False,
    },

    # --- Druida ---
    "raizes_prendentes": {
        "name": "Raizes Prendentes",
        "description": "Prende inimigos proximos no lugar.",
        "mana_cost": 14,
        "cooldown": 9.0,
        "aimable": False,
    },

    # --- Xama ---
    "totem_curativo": {
        "name": "Totem Curativo",
        "description": "Planta um totem que cura quem estiver perto.",
        "mana_cost": 18,
        "cooldown": 14.0,
        "heal_frac": 0.05,
        "aimable": False,
    },

    # --- Ranger ---
    "armadilha": {
        "name": "Armadilha",
        "description": "Planta uma armadilha que fere o primeiro inimigo a pisar nela.",
        "mana_cost": 10,
        "cooldown": 5.0,
        "spell_base": 18,
        "aimable": False,
    },

    # --- Paladino ---
    "julgamento": {
        "name": "Julgamento",
        "description": "Dano sagrado no inimigo mais proximo, mais forte contra inimigos feridos.",
        "mana_cost": 20,
        "cooldown": 10.0,
        "spell_base": 10,
        "aimable": False,
    },

    # --- Duelista ---
    "danca_das_laminas": {
        "name": "Danca das Laminas",
        "description": "3 golpes rapidos em sequencia ao redor.",
        "mana_cost": 20,
        "cooldown": 10.0,
        "spell_base": 9,
        "aimable": False,
    },
}

ORDER = ["fireball", "frost_nova", "healing_light"]  # legacy default kit order
