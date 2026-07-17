"""
Estagios M1/M2 (leva de conteudo - kits de classe): profession -> {ataque
basico, kit de 3 magias}. Substitui o antigo esquema onde toda profissao
compartilhava a mesma lista global de magias (game/spells.py's antigo
ORDER) gateada por atributo - agora cada profissao tem seu proprio trio
fixo (ofensiva/utilitaria/ultimate, seguindo a sugestao do proprio pedido
do usuario), e "ter a profissao" e o unico requisito.

Todas as 15 profissoes (menos Aventureiro, que ainda nao tem build - cai
em DEFAULT_KIT) tem kit autoral completo a partir do Estagio M2.

basic_attack e um dict de multiplicadores em cima do ataque universal de
sempre (game/player.py's get_attack_rect()/try_attack()) - não uma forma
geometrica nova (nenhum "arco"/cone existe no motor de colisao hoje), so
alcance/tamanho/velocidade/dano escalados por profissao. Continua fisico
mesmo pros casters puros (Mago/Feiticeiro/etc) - um "ataque basico magico"
de verdade exigiria um formato de dano novo, fora do escopo desta leva;
o ataque basico de todo mundo e so a arma corpo-a-corpo re-escalada.
"""

DEFAULT_BASIC_ATTACK = {"range_mult": 1.0, "size_mult": 1.0, "cooldown_mult": 1.0, "damage_mult": 1.0}
# "utility"=frost_nova aqui e so pra preservar o F/Q/R exato de antes desta
# leva (game/spells.py's antigo ORDER = [fireball, frost_nova,
# healing_light], key F/Q/R nessa ordem) - nao e uma reclassificacao real
# de Nova de Gelo como "utilitaria" (continua sendo dano em area).
# Achado ao vivo: rotular como "ultimate" (key R) trocava o binding de
# Q/R sem querer, quebrando o teste de PvP de Nova de Gelo do coop
# harness (tools/coop_harness.py) que pressiona "q" esperando ela.
DEFAULT_SPELLS = {"offense": "fireball", "utility": "frost_nova", "ultimate": "healing_light"}
DEFAULT_KIT = {"basic_attack": DEFAULT_BASIC_ATTACK, "spells": DEFAULT_SPELLS}

CLASS_KITS = {
    "Guerreiro": {
        # Golpe Devastador: mais lento, mais alcance/area, mais dano por
        # golpe - a "arma pesada" do ataque basico universal.
        "basic_attack": {"range_mult": 1.3, "size_mult": 1.25, "cooldown_mult": 1.35, "damage_mult": 1.3},
        "spells": {"offense": "investida_brutal", "utility": "grito_de_guerra", "ultimate": "terremoto"},
    },
    "Assassino": {
        # Estocada Rapida: mais rapido, hitbox menor, dano por golpe menor
        # (compensado pela cadencia) - o oposto do Guerreiro.
        "basic_attack": {"range_mult": 0.85, "size_mult": 0.8, "cooldown_mult": 0.65, "damage_mult": 0.8},
        "spells": {"offense": "veneno_mortal", "utility": "passo_sombrio", "ultimate": "laminas_giratorias"},
    },
    # --- Estagio M2: as 13 profissoes restantes, kit autoral completo ---
    "Mago": {
        # Missil Arcano: reusa o ataque fisico universal (ver docstring),
        # so um pouco mais fraco/longo que a media - o "dano de verdade" do
        # Mago sempre veio das magias, nao do corpo-a-corpo.
        "basic_attack": {"range_mult": 1.15, "size_mult": 0.9, "cooldown_mult": 1.1, "damage_mult": 0.85},
        "spells": {"offense": "fireball", "utility": "raio_de_gelo", "ultimate": "explosao_arcana"},
    },
    "Feiticeiro": {
        "basic_attack": {"range_mult": 1.1, "size_mult": 0.95, "cooldown_mult": 1.05, "damage_mult": 0.85},
        "spells": {"offense": "correntes_malditas", "utility": "chama_negra", "ultimate": "tempestade_sombria"},
    },
    "Cavaleiro": {
        "basic_attack": {"range_mult": 1.1, "size_mult": 1.15, "cooldown_mult": 1.1, "damage_mult": 1.1},
        "spells": {"offense": "investida_do_guardiao", "utility": "provocacao", "ultimate": "escudo_de_ferro"},
    },
    "Duelista": {
        "basic_attack": {"range_mult": 0.95, "size_mult": 0.9, "cooldown_mult": 0.75, "damage_mult": 0.9},
        "spells": {"offense": "corte_cruzado", "utility": "ripostar", "ultimate": "danca_das_laminas"},
    },
    "Cavaleiro Arcano": {
        "basic_attack": {"range_mult": 1.1, "size_mult": 1.05, "cooldown_mult": 1.0, "damage_mult": 1.05},
        "spells": {"offense": "lamina_arcana", "utility": "escudo_arcano", "ultimate": "explosao_runica"},
    },
    "Paladino": {
        "basic_attack": {"range_mult": 1.05, "size_mult": 1.1, "cooldown_mult": 1.15, "damage_mult": 1.15},
        "spells": {"offense": "aura_sagrada", "utility": "cura_divina", "ultimate": "julgamento"},
    },
    "Campeao": {
        # Martelada Colossal: o mais lento/forte de todos - martelo pesado.
        "basic_attack": {"range_mult": 1.2, "size_mult": 1.3, "cooldown_mult": 1.4, "damage_mult": 1.4},
        "spells": {"offense": "furia_do_campeao", "utility": "resistencia_inabalavel", "ultimate": "impacto_sismico"},
    },
    "Monge": {
        # Sequencia de Socos: o mais rapido/fraco por golpe - muitos golpes.
        "basic_attack": {"range_mult": 0.8, "size_mult": 0.85, "cooldown_mult": 0.55, "damage_mult": 0.7},
        "spells": {"offense": "palma_espiritual", "utility": "meditacao", "ultimate": "chute_giratorio"},
    },
    "Xama": {
        "basic_attack": {"range_mult": 1.0, "size_mult": 1.0, "cooldown_mult": 1.0, "damage_mult": 0.9},
        "spells": {"offense": "raio_da_natureza", "utility": "totem_curativo", "ultimate": "espirito_do_lobo"},
    },
    "Ranger": {
        "basic_attack": {"range_mult": 1.2, "size_mult": 0.85, "cooldown_mult": 0.9, "damage_mult": 0.95},
        "spells": {"offense": "armadilha", "utility": "disparo_perfurante", "ultimate": "chuva_de_flechas"},
    },
    "Arcanista": {
        "basic_attack": {"range_mult": 1.15, "size_mult": 0.9, "cooldown_mult": 1.05, "damage_mult": 0.85},
        "spells": {"offense": "prisma_arcano", "utility": "tempestade_astral", "ultimate": "meteoro"},
    },
    "Druida": {
        "basic_attack": {"range_mult": 1.0, "size_mult": 1.05, "cooldown_mult": 1.0, "damage_mult": 0.95},
        "spells": {"offense": "regeneracao_natural", "utility": "raizes_prendentes", "ultimate": "furia_da_natureza"},
    },
    "Templario": {
        "basic_attack": {"range_mult": 1.1, "size_mult": 1.15, "cooldown_mult": 1.2, "damage_mult": 1.2},
        "spells": {"offense": "luz_purificadora", "utility": "escudo_divino", "ultimate": "sentenca_celestial"},
    },
}


def kit_for(profession):
    """Só Aventureiro (build ainda nao definido - <20 pontos gastos) cai
    aqui a partir do Estagio M2; toda profissao real ja tem CLASS_KITS
    proprio."""
    return CLASS_KITS.get(profession, DEFAULT_KIT)


def spells_for(profession):
    """[offense_id, utility_id, ultimate_id] - ordem canonica pro hotbar/
    CAST_1/2/3, posicional em vez do antigo game/spells.py's ORDER fixo."""
    spells = kit_for(profession)["spells"]
    return [spells["offense"], spells["utility"], spells["ultimate"]]


def basic_attack_for(profession):
    return kit_for(profession)["basic_attack"]
