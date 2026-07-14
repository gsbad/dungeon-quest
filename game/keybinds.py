"""
Stage K15: remappable keybinds for the "core ability" keys (attack/spells/
dash/pickaxe/menu-shortcuts) - the Settings overlay (game/settings_overlay.py)
lets the player capture a new physical key for any of these.

Deliberately NOT everything on the keyboard is remappable: movement (WASD)
is polled continuously via InputManager.movement_vector(), a different code
path than the press-based Action system below, and pure menu navigation
(CONFIRM/PAUSE/TAB_NEXT/RESTART/MENU_UP/DOWN/LEFT/RIGHT) stays fixed since
every menu's keyboard-nav assumptions are built around those never moving.
game/input_system.py's feed() checks BINDINGS for exactly the actions
listed in REMAPPABLE below; everything else keeps its old hardcoded
pygame.K_* check.

Plain string keys (not the Action enum itself) so this module has zero
dependency on game/input_system.py - which needs to import BINDINGS back,
and a two-way module import would be circular.
"""
import pygame

REMAPPABLE = [
    "ATTACK", "CAST_1", "CAST_2", "CAST_3", "DASH", "PICKAXE",
    "PAPERDOLL", "ITEMS", "LEADERBOARD", "TOGGLE_HOTBAR",
]

DEFAULT_BINDINGS = {
    "ATTACK": pygame.K_SPACE,
    "CAST_1": pygame.K_f,
    "CAST_2": pygame.K_q,
    "CAST_3": pygame.K_r,
    "DASH": pygame.K_x,
    "PICKAXE": pygame.K_e,
    "PAPERDOLL": pygame.K_c,
    "ITEMS": pygame.K_i,
    "LEADERBOARD": pygame.K_l,
    "TOGGLE_HOTBAR": pygame.K_h,
}

# The live, possibly-remapped bindings InputManager.feed() actually checks -
# a copy so DEFAULT_BINDINGS above always stays available for "restaurar
# padroes". Loaded from save_state["settings"]["keybinds"] at startup
# (GameStateManager.__init__, same spot settings["muted"] is applied).
BINDINGS = dict(DEFAULT_BINDINGS)

ACTION_LABELS = {
    "ATTACK": "Ataque",
    "CAST_1": "Bola de Fogo",
    "CAST_2": "Nova de Gelo",
    "CAST_3": "Luz Curativa",
    "DASH": "Investida (Dash)",
    "PICKAXE": "Picareta",
    "PAPERDOLL": "Menu Personagem",
    "ITEMS": "Menu Itens",
    "LEADERBOARD": "Ranking",
    "TOGGLE_HOTBAR": "Marcar item p/ hotbar",
}


def key_name(key_code):
    return pygame.key.name(key_code).upper()


def set_binding(name, key_code):
    BINDINGS[name] = key_code


def reset_defaults():
    BINDINGS.clear()
    BINDINGS.update(DEFAULT_BINDINGS)


def is_bound_elsewhere(name, key_code):
    """True if key_code already triggers a DIFFERENT remappable action -
    the Settings overlay uses this to reject a collision instead of
    silently letting two actions share one key."""
    return any(other != name and code == key_code for other, code in BINDINGS.items())
