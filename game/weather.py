"""
Ambient weather (RPG systems expansion, see .claude/plans/cozy-wiggling-pumpkin.md;
biome fit + real gameplay effects added in Stage D5). Same registry-dict
pattern as game/stats.py's ENEMY_ARCHETYPES - a new weather type is a line
in WEATHER_TYPES, not a new class.

speed_mult/visibility_mult now have real effects (see game/states.py's
GameplayState, which multiplies them into player speed and enemy aggro
range) instead of the neutral 1.0 placeholders this module shipped with
originally. The optional "debuff" field is (effect_id, interval_seconds) -
GameplayState applies that game/status_effects.py effect to the player on
that interval while the weather is active; one generic mechanism, no
per-weather branching code.
"""
import pygame
import random
from game.theme import SW, SH

WEATHER_TYPES = {
    "fog":   {"kind": "overlay", "color": (200, 200, 210), "alpha": 70,
              "speed_mult": 1.0, "visibility_mult": 0.70},
    "rain":  {"kind": "particles", "color": (150, 180, 220), "count": 60,
              "speed_mult": 0.93, "visibility_mult": 1.0},
    "snow":  {"kind": "particles", "color": (240, 240, 250), "count": 40,
              "speed_mult": 1.0, "visibility_mult": 0.90, "debuff": ("chill", 10.0)},
    "storm": {"kind": "particles", "color": (150, 180, 220), "count": 90,
              "speed_mult": 0.95, "visibility_mult": 0.90, "lightning": True},
    # Difficulty tier's "Penumbra" affix (Stage B5, game/difficulty.py) -
    # deliberately darker than plain fog, not just relabeled, so the tier's
    # visibility hit is actually visible.
    "dimming_fog": {"kind": "overlay", "color": (25, 25, 35), "alpha": 130,
                     "speed_mult": 1.0, "visibility_mult": 0.6},
    # Desert biome (Stage D5) - fast sand streaks (drawn like rain) plus a
    # heat debuff, replacing the old rain-on-a-desert mismatch.
    "sandstorm": {"kind": "particles", "color": (210, 180, 120), "count": 70,
                  "speed_mult": 0.90, "visibility_mult": 0.75, "debuff": ("heat", 8.0)},
    # Crypt/tower biome - a darker overlay than plain fog, no particles.
    "gloom": {"kind": "overlay", "color": (40, 40, 60), "alpha": 95,
              "speed_mult": 1.0, "visibility_mult": 0.80},
    # Ashen/volcanic biome - slow falling ash (drawn like snow) plus heat.
    "ashfall": {"kind": "particles", "color": (170, 150, 140), "count": 45,
                "speed_mult": 1.0, "visibility_mult": 0.85, "debuff": ("heat", 10.0)},
}

# Weather ids whose particles fall slowly like snowflakes rather than
# streaking down like rain - drives both spawn speed (__init__) and which
# draw method each drop uses (draw()).
_SLOW_FALL = {"snow", "ashfall"}


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
        self._lightning_struck = False
        if self.defn and self.defn["kind"] == "particles":
            is_slow = weather_id in _SLOW_FALL
            min_speed, max_speed = (30, 80) if is_slow else (350, 550)
            for _ in range(self.defn["count"]):
                size = random.randint(2, 4) if is_slow else random.randint(8, 16)
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
                self._lightning_struck = True
            elif self._flash_alpha > 0:
                self._flash_alpha = max(0.0, self._flash_alpha - dt * 400)

    def consume_lightning(self):
        """True exactly once per flash (the frame it starts) - lets
        GameplayState roll a Choque debuff synced to the visible strike
        instead of a second, independent timer."""
        struck, self._lightning_struck = self._lightning_struck, False
        return struck

    def draw(self, surface):
        if not self.defn:
            return
        if self.defn["kind"] == "particles":
            draw_fn = "draw_snow" if self.weather_id in _SLOW_FALL else "draw_rain"
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
