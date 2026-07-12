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
import pygame
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
    "swamp_troll":  {"name": "Troll do Pantano",
                      "description": "Criatura pantanosa e resistente - seu toque envenenado apodrece a carne aos poucos."},
    "cursed_mage":  {"name": "Mago Amaldicoado",
                      "description": "Um conjurador fragil de corpo, mas seus feiticos gelados lentificam quem ousa se aproximar."},
    "crypt_wraith": {"name": "Espectro da Cripta",
                      "description": "Veloz e silencioso, o mais agil dos mortos-vivos - seu toque gela os ossos de quem alcança."},
    "ash_fiend":    {"name": "Demonio de Cinzas",
                      "description": "Nascido das cinzas do Abismo, cospe bolas de fogo que incendeiam tudo ao redor."},
    "royal_guard":  {"name": "Guarda Real",
                      "description": "Elite da guarda caida - ataca com precisao mortal, e golpes certeiros o tornam temido ate por veteranos."},
    "orc_warlord":  {"name": "Senhor da Guerra Orc",
                      "description": "Lidera pela força bruta - sua investida e capaz de esmagar quem estiver no caminho."},
    "necromancer":  {"name": "Necromante",
                      "description": "Comanda os mortos, invocando esqueletos e lançando maldiçoes a distancia."},
    "shadow_king":  {"name": "Rei das Sombras",
                      "description": "O tirano final do reino - mestre em rajadas de magia sombria em todas as direçoes."},
    "cacodemon":    {"name": "Cacodemonio",
                      "description": "Demonio infernal da fase secreta - uma esfera de furia flutuante que cospe fogo em todas as direçoes."},
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
    if boss_id == "cacodemon":
        # CacodemonBoss draws itself procedurally straight to the target
        # surface each frame (no reusable sprite Surface of its own, unlike
        # Boss's sprite_p1/p2) - a small static icon in its established
        # palette (game/boss.py's draw()) stands in for a bestiary preview.
        s = pygame.Surface((48, 48), pygame.SRCALPHA)
        pygame.draw.circle(s, (180, 40, 10), (24, 24), 22)
        pygame.draw.circle(s, (255, 130, 0), (16, 20), 6)
        pygame.draw.circle(s, (255, 130, 0), (32, 20), 6)
        pygame.draw.circle(s, (40, 0, 0), (16, 20), 3)
        pygame.draw.circle(s, (40, 0, 0), (32, 20), 3)
        return s
    archetype = BOSS_ARCHETYPES[boss_id]
    return create_boss_sprite(1, archetype["body_colors"], archetype["eye_colors"])


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
