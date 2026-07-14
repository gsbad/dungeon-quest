"""
Stage K18: pixel-art overrides fetched from the backend's /appearance
endpoint (admin panel's canvas pixel editor, backend/app/main.py). Each
entry is a full "data:image/png;base64,..." string, decoded once into a
pygame.Surface and cached here - checked by the small set of sprite
functions listed in ENTITY_KEY's docstring below, at the very top, before
they fall back to their procedural painter.

Same offline-first shape as game/balance_config.py: an empty/unreachable
/appearance response just means every entity keeps its code-drawn look,
nothing here is required for the game to run.
"""
import base64
import io
import pygame

_OVERRIDES = {}  # key -> decoded pygame.Surface


def apply_overrides(config):
    for key, data_url in config.items():
        try:
            _OVERRIDES[key] = _decode(data_url)
        except Exception:
            continue  # malformed data URL for this key - skip, default stands


def _decode(data_url):
    # "data:image/png;base64,AAAA..." - only the part after the comma is
    # real image data; tolerate a bare base64 string too (no such prefix).
    b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
    raw = base64.b64decode(b64)
    return pygame.image.load(io.BytesIO(raw)).convert_alpha()


def get_override(key):
    """None if no override exists for this key - callers fall back to
    their normal procedural painter in that case. Checked fresh every
    call (no separate per-caller cache) rather than needing explicit
    invalidation when a new override arrives mid-session - see
    create_enemy_sprite()/create_potion_icon() in game/assets.py, the
    first two entity types wired up to this (K18's initial rollout;
    hooking up another create_*_sprite() later is the same 3-line pattern
    at the top of that function)."""
    return _OVERRIDES.get(key)
