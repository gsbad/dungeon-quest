import random
import pygame


class Camera:
    def __init__(self, screen_w, screen_h, level_w, level_h):
        self.x = 0.0
        self.y = 0.0
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.level_w = level_w
        self.level_h = level_h

        self.shake_x = 0.0
        self.shake_y = 0.0
        self._shake_time = 0.0
        self._shake_duration = 0.0
        self._shake_intensity = 0.0

        self.zoom_scale = 1.0
        self._zoom_time = 0.0
        self._zoom_duration = 0.0
        self._zoom_intensity = 0.0

    def follow(self, target, dt):
        # Center on target with smooth lerp
        target_x = target.x + target.width  / 2 - self.screen_w / 2
        target_y = target.y + target.height / 2 - self.screen_h / 2
        speed = 8.0
        self.x += (target_x - self.x) * speed * dt
        self.y += (target_y - self.y) * speed * dt
        # Clamp
        self.x = max(0, min(self.x, self.level_w  - self.screen_w))
        self.y = max(0, min(self.y, self.level_h - self.screen_h))

        self._update_shake(dt)
        self._update_zoom(dt)

    @property
    def render_x(self):
        return self.x + self.shake_x

    @property
    def render_y(self):
        return self.y + self.shake_y

    def shake(self, intensity, duration):
        """Trigger a screen shake. Re-triggering while one is already active
        keeps whichever is stronger, so rapid hits don't reset a bigger one."""
        if intensity >= self._shake_intensity:
            self._shake_intensity = intensity
            self._shake_duration = duration
            self._shake_time = duration

    def _update_shake(self, dt):
        if self._shake_time > 0:
            self._shake_time = max(0.0, self._shake_time - dt)
            falloff = self._shake_time / self._shake_duration if self._shake_duration else 0
            mag = self._shake_intensity * falloff
            self.shake_x = random.uniform(-mag, mag)
            self.shake_y = random.uniform(-mag, mag)
        else:
            self.shake_x = 0.0
            self.shake_y = 0.0

    def zoom_pulse(self, amount, duration):
        """Trigger a brief screen-space punch-in, same falloff curve as shake."""
        if amount >= self._zoom_intensity:
            self._zoom_intensity = amount
            self._zoom_duration = duration
            self._zoom_time = duration

    def _update_zoom(self, dt):
        if self._zoom_time > 0:
            self._zoom_time = max(0.0, self._zoom_time - dt)
            falloff = self._zoom_time / self._zoom_duration if self._zoom_duration else 0
            self.zoom_scale = 1.0 + self._zoom_intensity * falloff
        else:
            self.zoom_scale = 1.0

    def apply_zoom(self, surface):
        """Screen-space punch-in post-effect: scales the already-drawn world
        content around its center. No-op when no zoom pulse is active, so it
        costs nothing on a normal frame."""
        if self.zoom_scale == 1.0:
            return
        w, h = surface.get_size()
        scaled = pygame.transform.smoothscale(
            surface, (max(1, int(w * self.zoom_scale)), max(1, int(h * self.zoom_scale)))
        )
        surface.blit(scaled, ((w - scaled.get_width()) // 2, (h - scaled.get_height()) // 2))
