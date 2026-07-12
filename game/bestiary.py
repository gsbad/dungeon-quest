"""
Bestiario (Stage E4) - the paperdoll's 3rd tab, presentation-only. BESTIARY
only holds the two things that don't exist anywhere else (name/description
flavor text); everything else an entry shows - attributes, derived stats,
attacks - is read live from the combat-data registries that already exist
(game/stats.py's ENEMY_ARCHETYPES/BOSS_ARCHETYPES, game/enemy.py's
ENEMY_FLAVOR, game/boss.py's BOSS_PATTERNS), so a future new mob/boss
already has *something* to show here before anyone writes its flavor text.

Discovery is derived, not stored (same "derived, never a second value that
can drift" precedent as game/professions.py) - see is_discovered() below.
"""
from game.stats import ENEMY_ARCHETYPES, BOSS_ARCHETYPES, StatBlock, scale_archetype
from game.enemy import ENEMY_FLAVOR
from game.boss import BOSS_PATTERNS, CacodemonBoss
from game.assets import create_enemy_sprite, create_boss_sprite

MOB_IDS = list(ENEMY_ARCHETYPES)
BOSS_IDS = list(BOSS_ARCHETYPES) + ["cacodemon"]

BESTIARY = {
    "skeleton":     {"name": "Esqueleto",
                      "description": "Um guerreiro morto reanimado por magia negra - ataca sem hesitar e sem sentir dor."},
    "goblin":       {"name": "Goblin",
                      "description": "Pequeno e covarde sozinho, mas perigoso em grupo - suas poças de veneno cobrem o chao de armadilhas."},
    "dark_knight":  {"name": "Cavaleiro Negro",
                      "description": "Um cavaleiro caido, blindado e implacavel - dispara um raio arcano de longe quando nao pode alcançar."},
    # Individualization pass (levels 5/6/7/9/10/11) - retired
    # swamp_troll/cursed_mage/crypt_wraith/ash_fiend/royal_guard, replaced
    # by a per-level roster below.

    # Level 5 - Pantano Sombrio
    "aranha":   {"name": "Aranha",
                  "description": "Uma aranha peconhenta que emboscada suas presas nas sombras do pantano - sua mordida envenena quem chega perto demais."},
    "serpente": {"name": "Serpente",
                  "description": "Furtiva e traicoeira - sua picada injeta um veneno que corroi aos poucos."},
    "treant":   {"name": "Treant",
                  "description": "Uma arvore ancestral desperta para proteger o pantano - arremessa espinhos em leque que prendem quem tenta fugir."},

    # Level 6 - Torre Amaldicoada
    "troll":        {"name": "Troll",
                       "description": "Um troll amaldicoado pela torre - seus golpes carregam uma maldicao que enfraquece o alvo."},
    "death_knight": {"name": "Cavaleiro da Morte",
                       "description": "Um cavaleiro morto que jurou lealdade alem da morte - dispara rajadas sombrias que corroem a vontade de quem e atingido."},

    # Level 7 - Cripta Perdida
    "zumbi": {"name": "Zumbi",
               "description": "Um cadaver reanimado que so ataca de perto - seu toque podre transmite uma infeccao venenosa."},
    "verme": {"name": "Verme",
               "description": "Verme cadaverico que se arrasta pela cripta - sua mordida acida corroi a carne."},
    "imp":   {"name": "Imp",
               "description": "Pequeno demonio travesso e rapido - dispara rajadas erraticas de energia que chocam quem e atingido."},

    # Level 9 - Salao dos Ecos
    "dark_horse": {"name": "Dark Horse",
                     "description": "Um corcel espectral que galopa entre as sombras - seu coice gelado congela quem ousa se aproximar."},
    "acolito":    {"name": "Acolito",
                     "description": "Um seguidor devoto de rituais profanos - lanca maldicoes que enfraquecem seus inimigos a distancia."},
    "feiticeira": {"name": "Feiticeira",
                     "description": "Uma feiticeira poderosa do salao gelado - conjura rajadas de gelo que lentificam quem e atingido."},

    # Level 10 - Abismo de Cinzas
    "fire_hound":      {"name": "Fire Hound",
                          "description": "Um cao infernal veloz - cospe baforadas de fogo que incendeiam a distancia."},
    "ogro":            {"name": "Ogro",
                          "description": "Um ogro brutal e resistente - seus golpes brutos nao perdoam quem fica no caminho."},
    "elemental_pedra": {"name": "Elemental de Pedra",
                          "description": "Um elemental de pedra vivo - quando aproximado, libera uma explosao radial de estilhacos em todas as direcoes."},

    # Level 11 - Corredor Final
    "chimera":       {"name": "Quimera",
                        "description": "Fusao monstruosa de leao, cabra e serpente - alterna baforadas de fogo a distancia com garras que enfraquecem no corpo a corpo."},
    "lyzardman":     {"name": "Lyzardman",
                        "description": "Guerreiro reptiliano agil - sua mordida venenosa e rapida e traicoeira."},
    "dark_skeleton": {"name": "Esqueleto Sombrio",
                        "description": "Uma versao sombria e elite do esqueleto comum - seus tiros carregam uma chance de critico devastador."},

    "orc_warlord":  {"name": "Senhor da Guerra Orc",
                      "description": "Lidera pela força bruta - sua investida e capaz de esmagar quem estiver no caminho."},
    "necromancer":  {"name": "Necromante",
                      "description": "Comanda os mortos, invocando esqueletos e lançando maldiçoes a distancia."},
    "shadow_king":  {"name": "Rei das Sombras",
                      "description": "O tirano final do reino - mestre em rajadas de magia sombria em todas as direçoes."},
    "cacodemon":    {"name": "Cacodemonio",
                      "description": "Demonio infernal da fase secreta - um demonio humanoide, chifrudo e de olho unico, que cospe fogo em todas as direçoes."},
}

# Full-name translations for the 2-3 letter STATUS_DISPLAY codes
# (game/status_effects.py) - the bestiary spells out attacks in prose,
# the HUD chips stay abbreviated.
_STATUS_NAME = {
    "poison": "Veneno", "slow": "Lentidao", "weakness": "Fraqueza",
    "burn": "Queimadura", "chill": "Frio", "heat": "Calor", "shock": "Choque",
}

_BOSS_PATTERN_TEXT = {
    "circle": "Rajada circular de projeteis",
    "triple": "Tiro triplo mirado",
    "spiral": "Espiral de projeteis",
    "circle_aimed": "Rajada circular + tiro mirado pesado",
    "charge": "Investida (dano fisico de contato)",
    "summon": "Invoca ate 3 esqueletos",
    "curse": "Maldicao a distancia: Fraqueza",
}


def is_discovered(save_state, player, key):
    """A mob/boss counts as discovered once the player has killed at least
    one - reuses game/save.py's existing kill counters (no new save field)
    plus the current run's not-yet-synced tally on `player`, so a kill
    earlier THIS run already unlocks the entry before the run ends."""
    if key in BOSS_ARCHETYPES or key == "cacodemon":
        persisted = save_state["counters"]["boss_kills"].get(key, 0)
        this_run = player.boss_kills.get(key, 0)
    else:
        persisted = save_state["counters"]["kills"].get(key, 0)
        this_run = player.kills.get(key, 0)
    return (persisted + this_run) > 0


def mob_sprite(etype):
    return create_enemy_sprite(etype)


def boss_sprite(boss_id):
    # Every boss now has its own dedicated rig (game/assets.py's
    # BOSS_SPRITES/create_boss_sprite, Stage B4b) including Cacodemon
    # (which used to need a hardcoded mini-sprite here since it had no
    # reusable Surface of its own) - one call covers all 4 boss_ids.
    return create_boss_sprite(boss_id, phase=1)


def mob_stats(etype):
    """A representative ML1 StatBlock - same baseline tools/balance_sim.py
    uses, not persisted/cached anywhere."""
    return StatBlock(**scale_archetype(ENEMY_ARCHETYPES[etype], ml=1))


def boss_stats(boss_id):
    if boss_id == "cacodemon":
        return CacodemonBoss(0, 0).stats
    archetype = BOSS_ARCHETYPES[boss_id]
    return StatBlock(strength=archetype["strength"], dexterity=archetype["dexterity"],
                      vigor=archetype["vigor"], luck=archetype["luck"],
                      weapon_base=archetype["weapon_base"], base_speed=archetype["base_speed"])


def mob_attacks(etype):
    """[str, ...] readable attack descriptions, from ENEMY_FLAVOR - empty
    list for a pure-melee mob with no extra "spell" (contact damage alone
    isn't listed, it's implied by every mob having a physical attack)."""
    flavor = ENEMY_FLAVOR[etype]
    lines = []
    ranged = flavor.get("ranged")
    if ranged:
        status_name = _STATUS_NAME.get(ranged["status_effect"], ranged["status_effect"])
        lines.append(f"Ataque a distancia: {status_name} ({ranged['status_chance']*100:.0f}%)")
    melee_status = flavor.get("melee_status")
    if melee_status:
        effect_id, chance = melee_status
        lines.append(f"Toque: {_STATUS_NAME.get(effect_id, effect_id)} ({chance*100:.0f}%)")
    if flavor.get("puddles"):
        lines.append("Deixa poças venenosas pelo chao")
    return lines


def boss_attacks(boss_id):
    if boss_id == "cacodemon":
        return ["Rajada de projeteis de fogo em todas as direcoes"]
    patterns = BOSS_PATTERNS[boss_id][1]  # phase 1 pool is enough for a bestiary summary
    seen = []
    for p in patterns:
        text = _BOSS_PATTERN_TEXT.get(p, p)
        if text not in seen:
            seen.append(text)
    return seen
