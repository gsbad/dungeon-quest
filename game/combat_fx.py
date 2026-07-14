"""Stage K6: floating damage numbers - shared by Player, Enemy, and Boss/
CacodemonBoss (game/player.py imports game/enemy.py's TILE constant, so
this couldn't live in enemy.py without a circular import; a small shared
module is simpler than restructuring that dependency)."""
import pygame
from game.theme import font

# Physical (contact) hits are red, magic (spell/projectile) hits are
# purple, and damage-over-time ticks (poison/burn/etc.) are a dark orange -
# distinct enough from both to read as "this isn't a direct hit" at a
# glance, matching the user's exact color spec.
PHYSICAL_COLOR = (230, 60, 60)
MAGIC_COLOR = (170, 90, 230)
DOT_COLOR = (200, 110, 20)


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
        self._font = font(16, bold=True)

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
