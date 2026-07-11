class Camera:
    def __init__(self, screen_w, screen_h, level_w, level_h):
        self.x = 0.0
        self.y = 0.0
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.level_w = level_w
        self.level_h = level_h

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
