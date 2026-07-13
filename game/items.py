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
