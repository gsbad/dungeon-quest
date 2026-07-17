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

    # --- Estagio M2: 31 magias novas, kits completos das 13 profissoes
    # restantes. Cada uma usa um dos 4 "shapes" genericos ja estabelecidos
    # (projetil/aoe-ao-redor/buff-proprio/cura) - ver os _cast_generic_*
    # em game/states.py, que os _cast_<id> individuais so encaminham pra.

    # --- Mago (Bola de Fogo reusa "fireball" ja existente) ---
    "raio_de_gelo": {
        "name": "Raio de Gelo", "description": "Projetil gelado que aplica Lentidao.",
        "mana_cost": 9, "cooldown": 2.5, "spell_base": 10,
        "status_effect": "slow", "status_chance": 0.8, "color": (140, 210, 255),
    },
    "explosao_arcana": {
        "name": "Explosao Arcana", "description": "Explosao magica em area ao redor.",
        "mana_cost": 22, "cooldown": 8.0, "spell_base": 20, "radius": 130,
        "dtype": "magic", "aimable": False,
    },

    # --- Feiticeiro ---
    "correntes_malditas": {
        "name": "Correntes Malditas", "description": "Projetil amaldicoado que aplica Fraqueza.",
        "mana_cost": 9, "cooldown": 2.5, "spell_base": 9,
        "status_effect": "weakness", "status_chance": 0.7, "color": (90, 40, 110),
    },
    "chama_negra": {
        "name": "Chama Negra", "description": "Projetil sombrio que aplica Fogo.",
        "mana_cost": 11, "cooldown": 3.5, "spell_base": 8,
        "status_effect": "burn", "status_chance": 0.9, "color": (40, 20, 40),
    },
    "tempestade_sombria": {
        "name": "Tempestade Sombria", "description": "Tempestade magica em area, enfraquece quem for atingido.",
        "mana_cost": 24, "cooldown": 9.0, "spell_base": 18, "radius": 130,
        "dtype": "magic", "status_to_enemy": "weakness", "aimable": False,
    },

    # --- Cavaleiro (Provocacao ja existe) ---
    "investida_do_guardiao": {
        "name": "Investida do Guardiao", "description": "Investida curta, dano fisico ao redor.",
        "mana_cost": 10, "cooldown": 3.0, "spell_base": 14, "radius": 80,
    },
    "escudo_de_ferro": {
        "name": "Escudo de Ferro", "description": "+35% defesa fisica, +20% defesa magica por 12s.",
        "mana_cost": 20, "cooldown": 16.0, "buff_id": "escudo_de_ferro", "aimable": False,
    },

    # --- Duelista (Danca das Laminas ja existe) ---
    "corte_cruzado": {
        "name": "Corte Cruzado", "description": "Corte em X, dano fisico ao redor.",
        "mana_cost": 9, "cooldown": 2.5, "spell_base": 13, "radius": 75, "aimable": False,
    },
    "ripostar": {
        "name": "Ripostar", "description": "+20% critico, +15% defesa fisica por 8s.",
        "mana_cost": 12, "cooldown": 12.0, "buff_id": "ripostar", "aimable": False,
    },

    # --- Cavaleiro Arcano ---
    "lamina_arcana": {
        "name": "Lamina Arcana", "description": "Lamina de energia, dano magico ao redor.",
        "mana_cost": 10, "cooldown": 2.5, "spell_base": 13, "radius": 75,
        "dtype": "magic", "aimable": False,
    },
    "escudo_arcano": {
        "name": "Escudo Arcano", "description": "+35% defesa magica por 12s.",
        "mana_cost": 14, "cooldown": 12.0, "buff_id": "escudo_arcano", "aimable": False,
    },
    "explosao_runica": {
        "name": "Explosao Runica", "description": "Runas explodem em area ao redor.",
        "mana_cost": 23, "cooldown": 9.0, "spell_base": 20, "radius": 125,
        "dtype": "magic", "aimable": False,
    },

    # --- Paladino (Julgamento ja existe) ---
    "aura_sagrada": {
        "name": "Aura Sagrada", "description": "+15% dano fisico e magico por 8s.",
        "mana_cost": 12, "cooldown": 10.0, "buff_id": "aura_sagrada", "aimable": False,
    },
    "cura_divina": {
        "name": "Cura Divina", "description": "Cura 35% da vida maxima.",
        "mana_cost": 20, "cooldown": 9.0, "heal_frac": 0.35, "aimable": False,
    },

    # --- Campeao (Impacto Sismico ja existe) ---
    "furia_do_campeao": {
        "name": "Furia do Campeao", "description": "+25% dano fisico por 10s.",
        "mana_cost": 12, "cooldown": 10.0, "buff_id": "furia_do_campeao", "aimable": False,
    },
    "resistencia_inabalavel": {
        "name": "Resistencia Inabalavel", "description": "+30% defesa fisica e magica, -10% velocidade, por 12s.",
        "mana_cost": 16, "cooldown": 12.0, "buff_id": "resistencia_inabalavel", "aimable": False,
    },

    # --- Monge ---
    "palma_espiritual": {
        "name": "Palma Espiritual", "description": "Golpe espiritual, dano fisico ao redor.",
        "mana_cost": 8, "cooldown": 2.0, "spell_base": 11, "radius": 65, "aimable": False,
    },
    "meditacao": {
        "name": "Meditacao", "description": "+60% regen. de vida e mana por 8s.",
        "mana_cost": 10, "cooldown": 14.0, "buff_id": "meditacao", "aimable": False,
    },
    "chute_giratorio": {
        "name": "Chute Giratorio", "description": "Chute giratorio, dano fisico pesado em area.",
        "mana_cost": 20, "cooldown": 8.0, "spell_base": 18, "radius": 110, "aimable": False,
    },

    # --- Xama (Totem Curativo ja existe) ---
    "raio_da_natureza": {
        "name": "Raio da Natureza", "description": "Projetil de energia natural.",
        "mana_cost": 8, "cooldown": 2.0, "spell_base": 10, "color": (120, 200, 90),
    },
    "espirito_do_lobo": {
        "name": "Espirito do Lobo", "description": "+25% velocidade, +20% velocidade de ataque por 10s.",
        "mana_cost": 18, "cooldown": 13.0, "buff_id": "espirito_do_lobo", "aimable": False,
    },

    # --- Ranger (Armadilha ja existe) ---
    "disparo_perfurante": {
        "name": "Disparo Perfurante", "description": "Flechada forte e precisa.",
        "mana_cost": 10, "cooldown": 3.0, "spell_base": 14, "color": (180, 150, 90),
    },
    "chuva_de_flechas": {
        "name": "Chuva de Flechas", "description": "Chuva de flechas em area ao redor.",
        "mana_cost": 20, "cooldown": 8.0, "spell_base": 17, "radius": 120, "aimable": False,
    },

    # --- Arcanista ---
    "prisma_arcano": {
        "name": "Prisma Arcano", "description": "Projetil de luz arcana.",
        "mana_cost": 9, "cooldown": 2.2, "spell_base": 11, "color": (180, 120, 255),
    },
    "tempestade_astral": {
        "name": "Tempestade Astral", "description": "Tempestade de estrelas em area ao redor.",
        "mana_cost": 16, "cooldown": 7.0, "spell_base": 13, "radius": 95,
        "dtype": "magic", "aimable": False,
    },
    "meteoro": {
        "name": "Meteoro", "description": "Meteoro cai sobre uma area grande ao redor.",
        "mana_cost": 26, "cooldown": 11.0, "spell_base": 24, "radius": 140,
        "dtype": "magic", "aimable": False,
    },

    # --- Druida (Raizes Prendentes ja existe) ---
    "regeneracao_natural": {
        "name": "Regeneracao Natural", "description": "+80% regen. de vida por 10s.",
        "mana_cost": 10, "cooldown": 9.0, "buff_id": "regeneracao_natural", "aimable": False,
    },
    "furia_da_natureza": {
        "name": "Furia da Natureza", "description": "A natureza se volta contra os inimigos ao redor.",
        "mana_cost": 22, "cooldown": 9.0, "spell_base": 19, "radius": 120, "aimable": False,
    },

    # --- Templario ---
    "luz_purificadora": {
        "name": "Luz Purificadora", "description": "Cura 20% da vida maxima. Recarga curta.",
        "mana_cost": 14, "cooldown": 6.0, "heal_frac": 0.20, "aimable": False,
    },
    "escudo_divino": {
        "name": "Escudo Divino", "description": "+25% defesa fisica e magica por 13s.",
        "mana_cost": 16, "cooldown": 13.0, "buff_id": "escudo_divino", "aimable": False,
    },
    "sentenca_celestial": {
        "name": "Sentenca Celestial", "description": "Julgamento celestial em area ao redor.",
        "mana_cost": 25, "cooldown": 10.0, "spell_base": 21, "radius": 130,
        "dtype": "magic", "aimable": False,
    },
}

ORDER = ["fireball", "frost_nova", "healing_light"]  # legacy default kit order
