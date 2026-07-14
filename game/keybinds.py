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
    "DASH": "MOUSE1",
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


# Stage K22: a binding can now also be a mouse button, represented as this
# plain string ("MOUSE1"/"MOUSE2"/"MOUSE3") instead of a pygame keycode int -
# feed()'s MOUSEBUTTONDOWN handling builds/matches this same string, and
# nothing here needs to know pygame.key.name() doesn't understand it. Kept
# as short as a 2-3 letter key name (e.g. "SPACE") since every caller of
# display_key() - the Settings row badge, the hotbar's auto-sized badge,
# the Help tab - was already sized around keyboard-length labels, not a
# full "CLIQUE ESQUERDO".
MOUSE_LABELS = {
    "MOUSE1": "M.ESQ",
    "MOUSE2": "M.DIR",
    "MOUSE3": "M.MEIO",
}


def key_name(key_code):
    if isinstance(key_code, str):
        return MOUSE_LABELS.get(key_code, key_code)
    return pygame.key.name(key_code).upper()


def display_key(action_name):
    """Stage K20: the label every UI that shows a remappable action's key
    (hotbar slots in game/player.py, the Help tab's shortcut list and
    Magias tab in game/paperdoll.py) should call instead of a hardcoded
    literal - those all baked in "F"/"X"/"C"/etc. before Stage K15's
    remapping existed, which went stale the moment a player actually
    rebound one. Falls back to the action name itself for a typo'd/
    non-remappable name rather than raising, same defensive shape
    ACTION_LABELS.get() callers already use elsewhere."""
    key_code = BINDINGS.get(action_name)
    return key_name(key_code) if key_code is not None else action_name


def set_binding(name, key_code):
    BINDINGS[name] = key_code


# Stage K22: DASH's default moved from K_x to MOUSE1, but every save made
# before that change already has "DASH": <K_x's int> persisted in
# settings.keybinds - a plain BINDINGS.update() would keep restoring that
# stale value forever, since it's indistinguishable from a deliberate
# rebind. One-time migration: a saved binding that still matches the OLD
# default for its action is treated as "never touched", so the new default
# takes over instead. A player who explicitly rebinds after this (to X or
# anything else) is unaffected - set_binding()/the Settings overlay write
# straight to BINDINGS, bypassing this entirely.
_LEGACY_DEFAULTS = {"DASH": pygame.K_x}


def apply_saved_bindings(saved):
    """GameStateManager.__init__ calls this instead of BINDINGS.update()
    directly, right after load - see game/states.py."""
    for name, code in saved.items():
        if name not in BINDINGS:
            continue
        if _LEGACY_DEFAULTS.get(name) == code:
            continue
        BINDINGS[name] = code


def reset_defaults():
    BINDINGS.clear()
    BINDINGS.update(DEFAULT_BINDINGS)


def is_bound_elsewhere(name, key_code):
    """True if key_code already triggers a DIFFERENT remappable action -
    the Settings overlay uses this to reject a collision instead of
    silently letting two actions share one key."""
    return any(other != name and code == key_code for other, code in BINDINGS.items())
