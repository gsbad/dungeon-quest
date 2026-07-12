"""
Headless balance simulator (Stage B1) - no pygame import, no display needed.
Run with `python tools/balance_sim.py`. Prints tables from the formulas in
game/stats.py so tuning a constant is a 5-minute read instead of a manual
playtest loop. Extend this file, don't hand-roll a one-off script, when a
new number needs checking - one place all the balance math can be eyeballed
together.
"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.stats import (
    StatBlock, ENEMY_ARCHETYPES, MAX_LEVEL, POINTS_PER_LEVEL,
    xp_to_next, scale_archetype, xp_for_kill, gold_for_kill, mitigate, MITIGATION_K,
)
from game.status_effects import STATUS_EFFECTS
from game.difficulty import DIFFICULTIES, ORDER as DIFFICULTY_ORDER

ATTR_ORDER = ["strength", "dexterity", "intelligence", "wisdom", "vigor", "luck"]


def balanced_player_stats(level):
    """A player who spreads every point evenly - not a real build (min-maxed
    builds are the whole point of the attribute system), just a reference
    baseline so TTK numbers below don't require picking a specific build."""
    points = POINTS_PER_LEVEL * (level - 1)
    per_attr, remainder = divmod(points, len(ATTR_ORDER))
    attrs = {name: 10 + per_attr + (1 if i < remainder else 0) for i, name in enumerate(ATTR_ORDER)}
    return StatBlock(weapon_base=4, base_speed=190, **attrs)


def mitig_pct(defense):
    return defense / (defense + MITIGATION_K) * 100


def monster_stats(etype, ml):
    return StatBlock(**scale_archetype(ENEMY_ARCHETYPES[etype], ml))


def ttk(attacker_dmg, defender_hp):
    return math.ceil(defender_hp / attacker_dmg) if attacker_dmg > 0 else float("inf")


def print_xp_curve():
    print("=== Curva de XP (xp_to_next) ===")
    print(f"{'Nivel':>6} {'XP p/ prox':>12} {'XP acumulado':>14}")
    cumulative = 0
    for level in range(1, MAX_LEVEL + 1):
        need = xp_to_next(level)
        cumulative += need
        if level in (1, 2, 5, 10, 15, 20, 25, 29):
            print(f"{level:>6} {need:>12} {cumulative:>14}")
    print()


def print_player_progression():
    print("=== Jogador (build balanceado) por nivel ===")
    print(f"{'Nivel':>6} {'HP':>5} {'Dano':>5} {'Mana':>5} {'Vel.mov':>8} {'Atq/s':>6} "
          f"{'DefFis':>7} {'Mit%':>5} {'DefMag':>7} {'Mit%':>5} {'Crit%':>6}")
    for level in [1, 5, 10, 15, 20, 25, 30]:
        s = balanced_player_stats(level)
        print(f"{level:>6} {s.max_hp:>5} {s.physical_damage:>5} {s.max_mana:>5} "
              f"{s.speed:>8.0f} {1/s.attack_cooldown:>6.2f} "
              f"{s.physical_defense:>7.1f} {mitig_pct(s.physical_defense):>4.0f}% "
              f"{s.magic_defense:>7.1f} {mitig_pct(s.magic_defense):>4.0f}% "
              f"{s.crit_chance*100:>5.1f}%")
    print()


def print_monster_progression():
    print("=== Monstros por nivel (ML) ===")
    for etype in ENEMY_ARCHETYPES:
        print(f"-- {etype} --")
        print(f"{'ML':>4} {'HP':>5} {'Dano':>5} {'Vel':>6} {'DefFis':>7} {'Mit%':>5} {'DefMag':>7} {'Mit%':>5}")
        for ml in [1, 4, 8, 12, 16, 20]:
            s = monster_stats(etype, ml)
            print(f"{ml:>4} {s.max_hp:>5} {s.physical_damage:>5} {s.speed:>6.0f} "
                  f"{s.physical_defense:>7.1f} {mitig_pct(s.physical_defense):>4.0f}% "
                  f"{s.magic_defense:>7.1f} {mitig_pct(s.magic_defense):>4.0f}%")
    print()


def print_ttk_matrix():
    print("=== Time-to-kill (dano mitigado): jogador (nivel correspondente) vs monstro (ML) ===")
    # Pairings match the actual campaign (fase1=ML1, fase2=ML4, fase3=ML8)
    # plus a look-ahead into where the difficulty tiers will sit (Stage B5).
    pairings = [(1, 1), (5, 4), (10, 8), (15, 12), (20, 16)]
    print(f"{'PlyLv/ML':>10} {'Monstro':>12} {'Golpes p/ matar':>16} {'Golpes p/ morrer':>17}")
    for player_level, ml in pairings:
        player = balanced_player_stats(player_level)
        for etype in ENEMY_ARCHETYPES:
            monster = monster_stats(etype, ml)
            player_dmg = mitigate(player.physical_damage, monster.physical_defense)
            monster_dmg = mitigate(monster.physical_damage, player.physical_defense)
            hits_to_kill = ttk(player_dmg, monster.max_hp)
            hits_to_die = ttk(monster_dmg, player.max_hp)
            label = f"L{player_level}/ML{ml}"
            print(f"{label:>10} {etype:>12} {hits_to_kill:>16} {hits_to_die:>17}")
    print()


def print_kill_rewards():
    print("=== XP/ouro por kill (nos MLs da campanha atual) ===")
    from game.stats import BASE_XP, GOLD_DROPS
    print(f"{'ML':>4} {'Monstro':>12} {'XP':>5} {'Ouro':>5}")
    for ml, player_level in [(1, 1), (4, 5), (8, 10)]:
        for etype in BASE_XP:
            xp = xp_for_kill(BASE_XP[etype], ml, player_level)
            gold = gold_for_kill(GOLD_DROPS[etype], ml)
            print(f"{ml:>4} {etype:>12} {xp:>5} {gold:>5}")
    print()
    # Anti-farm rule check: same monster, player far above its level.
    farmed_xp = xp_for_kill(BASE_XP["goblin"], 1, 10)
    normal_xp = xp_for_kill(BASE_XP["goblin"], 1, 1)
    print(f"Anti-farm: goblin ML1 kill por L1 vs L10 -> {normal_xp} XP vs {farmed_xp} XP "
          f"(regra: 5+ niveis abaixo = 10%)")
    print()


def print_status_effect_dps():
    print("=== Contribuicao de DPS dos status effects (dano/segundo) ===")
    print(f"{'Efeito':>10} {'Dano/tick':>10} {'Intervalo':>10} {'DPS efetivo':>12}")
    for effect_id, defn in STATUS_EFFECTS.items():
        if defn.tick_interval is None:
            print(f"{effect_id:>10} {'--':>10} {'--':>10} {'(so multiplicador de stat)':>12}")
            continue
        dps = defn.tick_damage / defn.tick_interval
        print(f"{effect_id:>10} {defn.tick_damage:>10} {defn.tick_interval:>10} {dps:>12.2f}")
    print()
    # Context: how much of the player's HP pool a full Poison application
    # (~2 ticks over its ~12s duration) chips away at a few levels.
    print("Veneno (2 ticks efetivos, 6 dano total) como fracao do HP maximo:")
    for level in [1, 10, 20, 30]:
        s = balanced_player_stats(level)
        print(f"  L{level}: hp={s.max_hp}, veneno tira {6/s.max_hp*100:.1f}% do HP maximo")
    print()


def print_difficulty_bands():
    print("=== Dificuldade (Stage B5): ML efetivo por fase, cada tier ===")
    # Representative levels: one per act (fase1 of Act1/Act2/Act3).
    base_mls = {"Fase 1 (Floresta)": 1, "Fase 5 (Pantano)": 12, "Fase 9 (Salao)": 24}
    header = f"{'Dificuldade':>14} " + " ".join(f"{name:>18}" for name in base_mls)
    print(header)
    for diff_id in DIFFICULTY_ORDER:
        d = DIFFICULTIES[diff_id]
        row = f"{d['name']:>14} "
        row += " ".join(f"ML{base + d['ml_bonus']:>16}" for base in base_mls.values())
        print(row)
    print()
    print(f"{'Dificuldade':>14} {'Champion %':>11} {'Boss enrage':>12}")
    for diff_id in DIFFICULTY_ORDER:
        d = DIFFICULTIES[diff_id]
        print(f"{d['name']:>14} {d['champion_chance']*100:>10.0f}% {d['boss_enrage_frac']*100:>11.0f}%")
    print()


if __name__ == "__main__":
    print_xp_curve()
    print_player_progression()
    print_monster_progression()
    print_ttk_matrix()
    print_kill_rewards()
    print_status_effect_dps()
    print_difficulty_bands()
