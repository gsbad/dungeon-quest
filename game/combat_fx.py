"""Stage K6/K9: floating damage numbers + knockback - shared by Player,
Enemy, and Boss/CacodemonBoss (game/player.py imports game/enemy.py's TILE
constant, so this couldn't live in enemy.py without a circular import; a
small shared module is simpler than restructuring that dependency)."""
import math
import pygame
from game.theme import font

# Physical (contact) hits are red, magic (spell/projectile) hits are
# purple, and damage-over-time ticks (poison/burn/etc.) are a dark orange -
# distinct enough from both to read as "this isn't a direct hit" at a
# glance, matching the user's exact color spec.
PHYSICAL_COLOR = (230, 60, 60)
MAGIC_COLOR = (170, 90, 230)
DOT_COLOR = (200, 110, 20)

# Stage K9: knockback - a short, fixed-strength shove away from whatever
# dealt the hit. Deliberately not scaled by damage/stats (that's a whole
# extra balance axis nobody asked for) - every hit knocks back the same
# amount, same "one committed motion, then back to normal" shape as Dash
# (game/player.py's DASH_* constants), just much shorter/lighter.
KNOCKBACK_SPEED = 380
KNOCKBACK_DURATION = 0.15


def knockback_vector(from_x, from_y, to_x, to_y):
    """Unit vector (scaled to KNOCKBACK_SPEED) pointing from the hit's
    source to its target - (0, 0) if the two points coincide (can't
    derive a direction, e.g. a self-targeted debug trigger)."""
    dx, dy = to_x - from_x, to_y - from_y
    dist = math.hypot(dx, dy)
    if dist < 1e-3:
        return 0.0, 0.0
    return dx / dist * KNOCKBACK_SPEED, dy / dist * KNOCKBACK_SPEED


class FloatingNumber:
    """A damage amount that drifts up and fades out, same lifetime shape as
    enemy.py's Particle (age-based alpha fade) but rendering text instead of
    a colored dot."""

    def __init__(self, x, y, amount, color):
        self.x = float(x)
        self.y = float(y)
        self.text = str(round(amount))
        self.color = color
        self.life = 0.7
        self.max_life = self.life
        self._font = font(18, bold=True)

    def update(self, dt):
        self.y -= 28 * dt
        self.life -= dt

    @property
    def alive(self):
        return self.life > 0

    def draw(self, surface, cam_x, cam_y):
        alpha = max(0, min(255, int(255 * (self.life / self.max_life))))
        if alpha == 0:
            return
        txt = self._font.render(self.text, True, self.color)
        txt.set_alpha(alpha)
        sx = int(self.x - cam_x - txt.get_width() / 2)
        sy = int(self.y - cam_y)
        surface.blit(txt, (sx, sy))
