"""
Estagio M1 (leva de conteudo - kits de classe): profession -> {ataque
basico, kit de 3 magias}. Substitui o antigo esquema onde toda profissao
compartilhava a mesma lista global de magias (game/spells.py's antigo
ORDER) gateada por atributo - agora cada profissao tem seu proprio trio
fixo (ofensiva/utilitaria/ultimate, seguindo a sugestao do proprio pedido
do usuario), e "ter a profissao" e o unico requisito.

Só Guerreiro e Assassino tem kit 100% autoral nesta sessao (ataque basico
proprio + as 3 magias pensadas pra eles). As outras 13 profissoes (menos
Aventureiro) recebem um kit de transicao: quem ja tem uma magia nova de
prova-de-conceito (Cavaleiro/Campeao/Druida/Xama/Ranger/Paladino/Duelista)
usa ela numa das 3 posicoes; o resto das posicoes (e as 6 profissoes sem
nenhuma magia nova ainda - Mago/Feiticeiro/Cavaleiro Arcano/Monge/
Arcanista/Templario) caem no DEFAULT_KIT, exatamente as 3 magias que já
existiam. Kits completos para as 13 restantes ficam pros Estagios M2-M6
(ver .claude/plans/jiggly-whistling-valley.md).

basic_attack e um dict de multiplicadores em cima do ataque universal de
sempre (game/player.py's get_attack_rect()/try_attack()) - não uma forma
geometrica nova (nenhum "arco"/cone existe no motor de colisao hoje), so
alcance/tamanho/velocidade/dano escalados por profissao.
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
    # --- Kits de transicao (prova de conceito de 1 sistema novo cada;
    # kit completo autoral fica pro Estagio M2-M6) ---
    "Cavaleiro": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "provocacao", "ultimate": "frost_nova"},
    },
    "Campeao": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "healing_light", "ultimate": "impacto_sismico"},
    },
    "Druida": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "raizes_prendentes", "ultimate": "frost_nova"},
    },
    "Xama": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "totem_curativo", "ultimate": "frost_nova"},
    },
    "Ranger": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "armadilha", "utility": "healing_light", "ultimate": "frost_nova"},
    },
    "Paladino": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "healing_light", "ultimate": "julgamento"},
    },
    "Duelista": {
        "basic_attack": DEFAULT_BASIC_ATTACK,
        "spells": {"offense": "fireball", "utility": "healing_light", "ultimate": "danca_das_laminas"},
    },
}


def kit_for(profession):
    """Aventureiro e as 6 profissoes ainda sem kit autoral (Mago,
    Feiticeiro, Cavaleiro Arcano, Monge, Arcanista, Templario) caem aqui -
    exatamente o que qualquer profissao tinha antes deste estagio."""
    return CLASS_KITS.get(profession, DEFAULT_KIT)


def spells_for(profession):
    """[offense_id, utility_id, ultimate_id] - ordem canonica pro hotbar/
    CAST_1/2/3, posicional em vez do antigo game/spells.py's ORDER fixo."""
    spells = kit_for(profession)["spells"]
    return [spells["offense"], spells["utility"], spells["ultimate"]]


def basic_attack_for(profession):
    return kit_for(profession)["basic_attack"]
