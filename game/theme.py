import pygame

# ─── Screen ─────────────────────────────────────────────────────────────────
# Single source of truth for the fixed logical resolution - main.py, states.py
# and camera setup all import this instead of redefining the same literals.
SW, SH = 800, 600


# ─── Fonts ──────────────────────────────────────────────────────────────────
# Playtest bug: the game would gradually slow down and eventually freeze
# solid after an extended session, with no console error - the classic
# signature of resource exhaustion, not an exception. This was the prime
# suspect: font() is called from dozens of draw() sites across the whole
# UI (HUD, tooltips, menus, hotbar, damage numbers...), many of them every
# single frame for the entire session, and every call built a brand new
# pygame.font.Font from scratch. Cheap-ish on native pygame; on WASM/
# emscripten (a heap that grows but rarely shrinks, allocation costlier
# than native) that's exactly the kind of steady churn that degrades a tab
# into unresponsive over time. Memoized by (size, bold) - same Font object
# reused instead of rebuilt, identical behavior at every call site, no
# call site needed to change.
_FONT_CACHE = {}


def font(size, bold=False):
    key = (size, bold)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    f = pygame.font.Font(None, size)
    f.set_bold(bold)
    _FONT_CACHE[key] = f
    return f


# ─── Sprite palette (procedural pixel art in game/assets.py) ────────────────
GREEN       = (34, 139, 34)
DARK_GREEN  = (0, 80, 0)
BROWN       = (101, 67, 33)
DARK_BROWN  = (60, 30, 10)
SAND        = (210, 180, 140)
STONE       = (120, 120, 130)
DARK_STONE  = (60, 60, 70)
GOLD        = (255, 215, 0)
RED         = (200, 40, 40)
DARK_RED    = (120, 20, 20)
BLUE        = (50, 100, 200)
CYAN        = (0, 200, 220)
PURPLE      = (120, 0, 180)
DARK_PURPLE = (60, 0, 90)
WHITE       = (240, 240, 240)
BLACK       = (10, 10, 10)
ORANGE      = (220, 120, 30)
PINK        = (220, 100, 150)
LIGHT_BLUE  = (100, 180, 255)
GRAY        = (150, 150, 160)


# ─── UI palette (menus/HUD in game/states.py, game/level.py, game/boss.py) ──
# Colors that already repeat across two or more screens/files get a shared
# name here; one-off flavor colors (stars, particles, per-boss accents) stay
# as local literals since they aren't shared infrastructure.
BG_MENU      = (5, 5, 20)
BG_GAME_OVER = (20, 0, 0)
BG_VICTORY   = (5, 10, 30)

TITLE_MENU   = (220, 160, 255)
TITLE_PAUSE  = (220, 180, 255)
ACCENT_GOLD  = (255, 220, 100)
SELECTED     = (255, 220, 50)
UNSELECTED   = (160, 140, 200)
SUBTEXT      = (180, 180, 220)

PANEL_FILL   = (20, 10, 40, 180)
PANEL_BORDER = (120, 80, 200)
