"""
Ambient weather (RPG systems expansion, see .claude/plans/cozy-wiggling-pumpkin.md).
Same registry-dict pattern as game/stats.py's ENEMY_ARCHETYPES - a new
weather type is a line in WEATHER_TYPES, not a new class.

Purely visual for now. speed_mult/visibility_mult on each entry are neutral
(1.0) placeholders so a later pass can make e.g. Nevoeiro actually shrink
enemy aggro range, or Tempestade slow movement, without redesigning this
module - same "leave the hook, wire it later" spirit as ENEMY_ARCHETYPES'
dexterity=0 pending Stage B tuning.
"""
import pygame
import random
from game.theme import SW, SH

WEATHER_TYPES = {
    "fog":   {"kind": "overlay", "color": (200, 200, 210), "alpha": 70,
              "speed_mult": 1.0, "visibility_mult": 1.0},
    "rain":  {"kind": "particles", "color": (150, 180, 220), "count": 60,
              "speed_mult": 1.0, "visibility_mult": 1.0},
    "snow":  {"kind": "particles", "color": (240, 240, 250), "count": 40,
              "speed_mult": 1.0, "visibility_mult": 1.0},
    "storm": {"kind": "particles", "color": (150, 180, 220), "count": 90,
              "speed_mult": 1.0, "visibility_mult": 1.0, "lightning": True},
}


class _FallingDrop:
    """One rain streak or snowflake - falls straight down, wraps to the top
    when it passes the bottom of the screen. Continuous ambient weather,
    unlike game/enemy.py's Particle (a one-shot fade-out burst for hit
    effects/level-up fanfare - the wrong lifecycle for weather)."""

    def __init__(self, color, min_speed, max_speed, size):
        self.color = color
        self.size = size
        self.speed = random.uniform(min_speed, max_speed)
        self.x = random.uniform(0, SW)
        self.y = random.uniform(0, SH)

    def update(self, dt):
        self.y += self.speed * dt
        if self.y > SH:
            self.y = 0
            self.x = random.uniform(0, SW)

    def draw_rain(self, surface):
        pygame.draw.line(surface, self.color, (self.x, self.y), (self.x - 2, self.y + self.size), 1)

    def draw_snow(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.size)


class WeatherSystem:
    """weather_id=None is a no-op (clear skies) - every method short-circuits
    so callers don't need to check before calling."""

    def __init__(self, weather_id):
        self.weather_id = weather_id
        self.defn = WEATHER_TYPES.get(weather_id)
        self.drops = []
        self._flash_alpha = 0.0
        self._lightning_timer = random.uniform(3.0, 7.0)
        if self.defn and self.defn["kind"] == "particles":
            is_snow = weather_id == "snow"
            min_speed, max_speed = (30, 80) if is_snow else (350, 550)
            for _ in range(self.defn["count"]):
                size = random.randint(2, 4) if is_snow else random.randint(8, 16)
                self.drops.append(_FallingDrop(self.defn["color"], min_speed, max_speed, size))

    @property
    def speed_multiplier(self):
        return self.defn["speed_mult"] if self.defn else 1.0

    @property
    def visibility_multiplier(self):
        return self.defn["visibility_mult"] if self.defn else 1.0

    def update(self, dt):
        if not self.defn:
            return
        for d in self.drops:
            d.update(dt)
        if self.defn.get("lightning"):
            self._lightning_timer -= dt
            if self._lightning_timer <= 0:
                self._lightning_timer = random.uniform(4.0, 9.0)
                self._flash_alpha = 160
            elif self._flash_alpha > 0:
                self._flash_alpha = max(0.0, self._flash_alpha - dt * 400)

    def draw(self, surface):
        if not self.defn:
            return
        if self.defn["kind"] == "particles":
            draw_fn = "draw_snow" if self.weather_id == "snow" else "draw_rain"
            for d in self.drops:
                getattr(d, draw_fn)(surface)
            if self._flash_alpha > 0:
                flash = pygame.Surface((SW, SH), pygame.SRCALPHA)
                flash.fill((255, 255, 255, int(self._flash_alpha)))
                surface.blit(flash, (0, 0))
        elif self.defn["kind"] == "overlay":
            overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
            overlay.fill((*self.defn["color"], self.defn["alpha"]))
            surface.blit(overlay, (0, 0))
