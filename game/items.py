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
    "potion_black":    {"name": "Pocao do Veu Arcano",     "price": 100, "buff": "buff_black"},
    "potion_orange":   {"name": "Pocao da Forca Bruta",    "price": 100, "buff": "buff_orange"},
    "potion_purple":   {"name": "Pocao da Mente Arcana",   "price": 100, "buff": "buff_purple"},
    "potion_white":    {"name": "Pocao da Brisa",          "price": 100, "buff": "buff_white"},
    "potion_green":    {"name": "Pocao do Vigor",          "price": 100, "buff": "buff_green"},
    "potion_darkblue": {"name": "Pocao da Sabedoria",      "price": 100, "buff": "buff_darkblue"},
    "potion_yellow":   {"name": "Pocao da Presteza",       "price": 100, "buff": "buff_yellow"},

    # --- Pocoes Defensivas (3, 120g, 3min) ---
    "potion_gray":   {"name": "Pocao da Couraca",          "price": 120, "buff": "buff_gray"},
    "potion_silver": {"name": "Pocao da Vontade de Aco",   "price": 120, "buff": "buff_silver"},
    "potion_brown":  {"name": "Pocao da Muralha",          "price": 120, "buff": "buff_brown"},

    # --- Pocoes Ofensivas (3, 150g, 3min) ---
    "potion_darkred": {"name": "Pocao do Sangue Fervente", "price": 150, "buff": "buff_darkred"},
    "potion_violet":  {"name": "Pocao da Chama Interior",  "price": 150, "buff": "buff_violet"},
    "potion_ruby":    {"name": "Pocao do Golpe Certeiro",  "price": 150, "buff": "buff_ruby"},

    # --- Pocoes Utilitarias (4) ---
    "potion_cyan":      {"name": "Pocao da Fonte Viva",         "price": 100, "buff": "buff_cyan"},
    "potion_pink":      {"name": "Pocao da Seiva Vital",        "price": 100, "buff": "buff_pink"},
    "potion_gold":      {"name": "Pocao da Iluminacao",         "price": 250, "buff": "buff_gold"},
    "potion_turquoise": {"name": "Pocao da Sorte do Mercador",  "price": 250, "buff": "buff_turquoise"},

    # --- Elixires (5, mais raros) ---
    "elixir_crimson":  {"name": "Elixir da Furia Carmesim",  "price": 400, "buff": "elixir_crimson"},
    "elixir_arcane":   {"name": "Elixir do Arquimago",       "price": 400, "buff": "elixir_arcane"},
    "elixir_guardian": {"name": "Elixir do Bastiao",         "price": 400, "buff": "elixir_guardian"},
    "elixir_hunter":   {"name": "Elixir do Predador",        "price": 400, "buff": "elixir_hunter"},
    "elixir_champion": {"name": "Elixir da Ascensao",        "price": 600, "buff": "elixir_champion"},
}

MAX_STOCK = 50


def item_tooltip_line(item_id):
    """Stage K8: ITEMS has no stored description field - this reads the
    same effect keys use_item() branches on and turns them into one
    objective-numbers sentence, so a new potion just works here without
    also needing hand-written tooltip text kept in sync."""
    item = ITEMS[item_id]
    parts = []
    if "heal_hp_frac" in item:
        parts.append(f"Cura {round(item['heal_hp_frac'] * 100)}% da vida")
    if "heal_mana_frac" in item:
        parts.append(f"Restaura {round(item['heal_mana_frac'] * 100)}% da mana")
    if "cures" in item:
        from game.status_effects import STATUS_HELP
        names = [STATUS_HELP.get(cure_id, (cure_id, ""))[0] for cure_id in sorted(item["cures"])]
        parts.append("Cura: " + ", ".join(names))
    if "buff" in item:
        from game.status_effects import STATUS_HELP
        _, desc = STATUS_HELP.get(item["buff"], (item["buff"], ""))
        parts.append(desc)
    return " | ".join(parts) if parts else ""


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
