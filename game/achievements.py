"""
Achievement definitions (Stage H5). Every achievement is derived purely from
data already present in save_state (cleared_difficulties, counters, gold,
inventory, character level) - same "derive, don't duplicate" reasoning as
game/difficulty.py's is_unlocked(). No new save field/migration needed: there
is nothing here that isn't already reconstructible from the existing schema.
"""
from game.difficulty import DIFFICULTIES, ORDER as DIFFICULTY_ORDER
from game.stats import MAX_LEVEL

SECRET_BOSS_KEY = "cacodemon"  # game/level.py level 13's "boss" key
_STORY_BOSSES = ("orc_warlord", "necromancer", "shadow_king")

# One "clear this difficulty" achievement per tier, in ascending order, plus
# the secret-level boss as the final/capstone achievement.
ACHIEVEMENTS = [
    {
        "id": f"clear_{diff_id}",
        "name": f"Mestre: {DIFFICULTIES[diff_id]['name']}",
        "description": f"Derrote o chefe final no modo {DIFFICULTIES[diff_id]['name']}.",
        "tier": "gold",
    }
    for diff_id in DIFFICULTY_ORDER
] + [
    {
        "id": "first_blood", "tier": "bronze",
        "name": "Primeiro Tombo",
        "description": "Morra pela primeira vez. Faz parte do aprendizado.",
    },
    {
        "id": "veterano", "tier": "bronze",
        "name": "Veterano",
        "description": "Derrote 100 inimigos.",
    },
    {
        "id": "cacador_lendario", "tier": "silver",
        "name": "Cacador Lendario",
        "description": "Derrote 500 inimigos.",
    },
    {
        "id": "rico", "tier": "bronze",
        "name": "Bolso Cheio",
        "description": "Acumule 1000 de ouro.",
    },
    {
        "id": "colecionador", "tier": "bronze",
        "name": "Colecionador",
        "description": "Junte 50 unidades de um mesmo item.",
    },
    {
        "id": "maratonista", "tier": "bronze",
        "name": "Maratonista",
        "description": "Jogue por 1 hora no total.",
    },
    {
        "id": "nivel_maximo", "tier": "silver",
        "name": "Auge do Poder",
        "description": f"Alcance o nivel {MAX_LEVEL}.",
    },
    {
        "id": "tres_reis", "tier": "silver",
        "name": "Flagelo dos Tres",
        "description": "Derrote o Senhor Orc, o Necromante e o Rei das Sombras ao menos uma vez cada.",
    },
    {
        "id": "secret_boss", "tier": "special",
        "name": "Cacador do Abismo",
        "description": "Derrote o Cacodemonio na fase secreta.",
    },
]

ACHIEVEMENT_IDS = [a["id"] for a in ACHIEVEMENTS]


def check_unlocks(save_state):
    """Returns the set of achievement ids unlocked by this save's data."""
    prog = save_state["progression"]
    counters = save_state["counters"]
    cleared = set(prog.get("cleared_difficulties", []))
    boss_kills = counters.get("boss_kills", {})
    total_kills = sum(counters.get("kills", {}).values())

    unlocked = {f"clear_{diff_id}" for diff_id in DIFFICULTY_ORDER if diff_id in cleared}

    if counters.get("deaths", 0) > 0:
        unlocked.add("first_blood")
    if total_kills >= 100:
        unlocked.add("veterano")
    if total_kills >= 500:
        unlocked.add("cacador_lendario")
    if save_state.get("gold", 0) >= 1000:
        unlocked.add("rico")
    if any(count >= 50 for count in save_state.get("inventory", {}).values()):
        unlocked.add("colecionador")
    if counters.get("playtime_s", 0) >= 3600:
        unlocked.add("maratonista")
    if save_state["character"]["level"] >= MAX_LEVEL:
        unlocked.add("nivel_maximo")
    if all(boss_kills.get(b, 0) > 0 for b in _STORY_BOSSES):
        unlocked.add("tres_reis")
    if boss_kills.get(SECRET_BOSS_KEY, 0) > 0:
        unlocked.add("secret_boss")

    return unlocked
