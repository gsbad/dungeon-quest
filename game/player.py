import pygame
import math
from game.assets import create_player_sprite, create_projectile_sprite

TILE = 48

class Player:
    def __init__(self, x, y, audio_mgr):
        self.x = float(x)
        self.y = float(y)
        self.audio = audio_mgr
        self.speed = 200
        self.max_hp = 6
        self.hp = self.max_hp
        self.width = 32
        self.height = 36

        self.attacking = False
        self.attack_timer = 0
        self.attack_duration = 0.25
        self.attack_cooldown = 0
        self.attack_damage = 1
        self.attack_range = 60

        self.invincible = False
        self.invincible_timer = 0
        self.invincible_duration = 1.0
        self.flash_timer = 0

        self.direction = "down"  # up/down/left/right

        self.sprites = {
            "down":  create_player_sprite("down",  False),
            "up":    create_player_sprite("up",    False),
            "left":  create_player_sprite("left",  False),
            "right": create_player_sprite("right", False),
            "down_atk":  create_player_sprite("down",  True),
            "up_atk":    create_player_sprite("up",    True),
            "left_atk":  create_player_sprite("left",  True),
            "right_atk": create_player_sprite("right", True),
        }
        self.slash_sprite = create_projectile_sprite("slash")

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def get_attack_rect(self):
        if self.direction == "right":
            return pygame.Rect(self.x + self.width, self.y, self.attack_range, self.height)
        elif self.direction == "left":
            return pygame.Rect(self.x - self.attack_range, self.y, self.attack_range, self.height)
        elif self.direction == "down":
            return pygame.Rect(self.x, self.y + self.height, self.width, self.attack_range)
        else:  # up
            return pygame.Rect(self.x, self.y - self.attack_range, self.width, self.attack_range)

    def take_damage(self, amount):
        if self.invincible:
            return
        self.hp -= amount
        self.invincible = True
        self.invincible_timer = self.invincible_duration
        self.audio.play("hurt")

    def update(self, dt, walls, movement_vector):
        dx, dy = movement_vector

        # Horizontal facing wins over vertical when both are held (matches
        # the original WASD priority order).
        if dx > 0.05:
            self.direction = "right"
        elif dx < -0.05:
            self.direction = "left"
        elif dy > 0.05:
            self.direction = "down"
        elif dy < -0.05:
            self.direction = "up"

        # Move X
        self.x += dx * self.speed * dt
        self._resolve_collisions_x(walls)

        # Move Y
        self.y += dy * self.speed * dt
        self._resolve_collisions_y(walls)

        # Attack timers
        if self.attacking:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attacking = False
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        # Invincibility
        if self.invincible:
            self.invincible_timer -= dt
            self.flash_timer += dt
            if self.invincible_timer <= 0:
                self.invincible = False
                self.flash_timer = 0

    def try_attack(self):
        if self.attack_cooldown <= 0 and not self.attacking:
            self.attacking = True
            self.attack_timer = self.attack_duration
            self.attack_cooldown = 0.4
            self.audio.play("attack")
            return True
        return False

    def _resolve_collisions_x(self, walls):
        r = self.rect
        for wall in walls:
            if r.colliderect(wall):
                if self.x > wall.x:
                    self.x = wall.right
                else:
                    self.x = wall.left - self.width

    def _resolve_collisions_y(self, walls):
        r = self.rect
        for wall in walls:
            if r.colliderect(wall):
                if self.y > wall.y:
                    self.y = wall.bottom
                else:
                    self.y = wall.top - self.height

    def draw(self, surface, cam_x, cam_y):
        # Flash when invincible
        if self.invincible and int(self.flash_timer * 8) % 2 == 0:
            return

        key = self.direction
        if self.attacking:
            key = self.direction + "_atk"

        sprite = self.sprites[key]
        # Flip left
        if self.direction == "left":
            sprite = pygame.transform.flip(self.sprites.get("right_atk" if self.attacking else "right"), True, False)

        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        surface.blit(sprite, (sx - 8, sy - 12))

        # Draw attack hitbox visual
        if self.attacking:
            ar = self.get_attack_rect()
            slash_surf = pygame.Surface((ar.width, ar.height), pygame.SRCALPHA)
            slash_surf.fill((255, 255, 200, 80))
            surface.blit(slash_surf, (ar.x - cam_x, ar.y - cam_y))

    def draw_hud(self, surface):
        # Hearts
        from game.assets import create_heart_sprite
        full_h = create_heart_sprite(True)
        empty_h = create_heart_sprite(False)
        for i in range(self.max_hp // 2):
            x = 12 + i * 28
            y = 12
            filled = self.hp - i * 2
            if filled >= 2:
                surface.blit(full_h, (x, y))
            elif filled == 1:
                # Half heart
                surface.blit(empty_h, (x, y))
                surface.blit(full_h, (x, y), (0, 0, 12, 24))
            else:
                surface.blit(empty_h, (x, y))
