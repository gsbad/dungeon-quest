"""
Consumable items and the player's gold-based economy (RPG systems expansion,
see .claude/plans/cozy-wiggling-pumpkin.md). Same registry-dict pattern as
game/stats.py's ENEMY_ARCHETYPES - a new item is one line in ITEMS, no new
class or branching logic in use_item().

Gold itself isn't an item (it's player.gold, a plain counter) - these are
the stackable things that live in player.inventory.
"""

ITEMS = {
    "health_potion": {"name": "Pocao de Vida", "price": 30, "heal_hp_frac": 0.5},
    "mana_potion":   {"name": "Pocao de Mana", "price": 24, "heal_mana_frac": 0.6},
    "antidote":      {"name": "Antidoto",      "price": 40, "cures": frozenset({"poison", "slow", "weakness"})},

    # --- Stage K12: Pocoes de Atributo (7, 100g, 3min cada) ---
    "potion_black":    {"name": "Pocao Preta",        "price": 100, "buff": "buff_black"},
    "potion_orange":   {"name": "Pocao Laranja",      "price": 100, "buff": "buff_orange"},
    "potion_purple":   {"name": "Pocao Roxa",         "price": 100, "buff": "buff_purple"},
    "potion_white":    {"name": "Pocao Branca",       "price": 100, "buff": "buff_white"},
    "potion_green":    {"name": "Pocao Verde",        "price": 100, "buff": "buff_green"},
    "potion_darkblue": {"name": "Pocao Azul-Escura",  "price": 100, "buff": "buff_darkblue"},
    "potion_yellow":   {"name": "Pocao Amarela",      "price": 100, "buff": "buff_yellow"},

    # --- Pocoes Defensivas (3, 120g, 3min) ---
    "potion_gray":   {"name": "Pocao Cinza",     "price": 120, "buff": "buff_gray"},
    "potion_silver": {"name": "Pocao Prateada",  "price": 120, "buff": "buff_silver"},
    "potion_brown":  {"name": "Pocao Marrom",    "price": 120, "buff": "buff_brown"},

    # --- Pocoes Ofensivas (3, 150g, 3min) ---
    "potion_darkred": {"name": "Pocao Vermelho-Escura", "price": 150, "buff": "buff_darkred"},
    "potion_violet":  {"name": "Pocao Violeta",         "price": 150, "buff": "buff_violet"},
    "potion_ruby":    {"name": "Pocao Rubra",           "price": 150, "buff": "buff_ruby"},

    # --- Pocoes Utilitarias (4) ---
    "potion_cyan":      {"name": "Pocao Ciano",     "price": 100, "buff": "buff_cyan"},
    "potion_pink":      {"name": "Pocao Rosa",      "price": 100, "buff": "buff_pink"},
    "potion_gold":      {"name": "Pocao Dourada",   "price": 250, "buff": "buff_gold"},
    "potion_turquoise": {"name": "Pocao Turquesa",  "price": 250, "buff": "buff_turquoise"},

    # --- Elixires (5, mais raros) ---
    "elixir_crimson":  {"name": "Elixir Carmesim",     "price": 400, "buff": "elixir_crimson"},
    "elixir_arcane":   {"name": "Elixir Arcano",       "price": 400, "buff": "elixir_arcane"},
    "elixir_guardian": {"name": "Elixir do Guardiao",  "price": 400, "buff": "elixir_guardian"},
    "elixir_hunter":   {"name": "Elixir do Cacador",   "price": 400, "buff": "elixir_hunter"},
    "elixir_champion": {"name": "Elixir do Campeao",   "price": 600, "buff": "elixir_champion"},
}

MAX_STOCK = 50


def use_item(player, item_id):
    """Applies the item's effect and decrements player.inventory[item_id].
    Returns False (no-op) if the player doesn't own one."""
    if player.inventory.get(item_id, 0) <= 0:
        return False

    item = ITEMS[item_id]
    if "heal_hp_frac" in item:
        player.hp = min(player.max_hp, player.hp + player.max_hp * item["heal_hp_frac"])
    if "heal_mana_frac" in item:
        player.mana = min(player.max_mana, player.mana + player.max_mana * item["heal_mana_frac"])
    if "cures" in item:
        player.status.cure(item["cures"])
    if "buff" in item:
        # Self-applied (potion the player chose to drink), not an enemy
        # debuff - skips try_apply_debuff's resist roll entirely.
        player.status.apply(item["buff"])

    player.inventory[item_id] -= 1
    return True


def buy_item(player, item_id):
    """Returns False if the player can't afford it or already holds the max
    stack (MAX_STOCK), without side effects."""
    price = ITEMS[item_id]["price"]
    if player.gold < price:
        return False
    if player.inventory.get(item_id, 0) >= MAX_STOCK:
        return False
    player.gold -= price
    player.inventory[item_id] = player.inventory.get(item_id, 0) + 1
    return True
