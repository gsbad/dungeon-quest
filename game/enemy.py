import pygame
import math
import random
from game.assets import create_enemy_sprite, create_projectile_sprite, create_item_sprite
from game.player import TILE
from game.stats import StatBlock, ENEMY_ARCHETYPES, BASE_XP, GOLD_DROPS, scale_archetype

class EnemyProjectile:
    def __init__(self, x, y, vx, vy, damage=1, color=(160,100,255),
                 status_effect=None, status_chance=0.0):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.color = color
        self.radius = 6
        self.alive = True
        self.age = 0.0
        # Optional debuff this hit may inflict - see game/status_effects.py.
        self.status_effect = status_effect
        self.status_chance = status_chance

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius * 2, self.radius * 2)

    def update(self, dt, walls):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.age += dt
        if self.age > 4:
            self.alive = False
        for wall in walls:
            if self.rect.colliderect(wall):
                self.alive = False

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        glow = pygame.Surface((self.radius*3, self.radius*3), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.color, 80), (self.radius*3//2, self.radius*3//2), self.radius*3//2)
        surface.blit(glow, (sx - self.radius*1.5, sy - self.radius*1.5))
        pygame.draw.circle(surface, self.color, (sx, sy), self.radius)
        pygame.draw.circle(surface, (255,255,255), (sx, sy), self.radius//2)


class Particle:
    def __init__(self, x, y, color):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(60, 150)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.uniform(0.3, 0.6)
        self.max_life = self.life
        self.size = random.randint(3, 7)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        self.vx *= 0.92
        self.vy *= 0.92

    def draw(self, surface, cam_x, cam_y):
        alpha = int(255 * (self.life / self.max_life))
        alpha = max(0, min(255, alpha))
        if alpha == 0 or self.size <= 0:
            return

        try:
            color = pygame.Color(self.color)
            r, g, b = int(color.r), int(color.g), int(color.b)
        except Exception:
            try:
                r, g, b = int(self.color[0]), int(self.color[1]), int(self.color[2])
            except Exception:
                r, g, b = 255, 255, 255

        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        s = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        s.fill((r, g, b, alpha))
        surface.blit(s, (int(self.x - cam_x), int(self.y - cam_y)))


class Puddle:
    def __init__(self, x, y, damage_interval=1.0):
        # x,y should be tile-aligned world coords
        self.x = float(x)
        self.y = float(y)
        self.damage_interval = float(damage_interval)
        self._tick = 0.0
        w = TILE
        h = TILE // 2
        self.w = w
        self.h = h
        self.rect = pygame.Rect(int(self.x), int(self.y), w, h)

    def update(self, dt):
        # Only advance damage cooldown timer; puddle persists indefinitely
        self._tick -= dt
        if self._tick < 0:
            self._tick = 0

    def can_damage(self):
        if self._tick <= 0:
            self._tick = self.damage_interval
            return True
        return False

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        # Draw an irregular purple acid puddle by compositing several overlapping ellipses
        color = (140, 50, 180, 200)
        offsets = [(-6, 0, self.w-8, self.h), (6, 2, self.w-12, self.h-4), (0, -4, self.w-6, self.h-2)]
        for ox, oy, ow, oh in offsets:
            pygame.draw.ellipse(s, color, (max(0, ox), max(0, oy), max(4, ow), max(4, oh)))
        # add a small darker ring
        pygame.draw.ellipse(s, (90,30,120,140), (4,4,self.w-8,self.h-8), 2)
        surface.blit(s, (sx, sy))


ENEMY_FLAVOR = {
    # AI/animation tuning that isn't a combat stat - stays local to enemy.py.
    "skeleton":    {"atk_cd": 1.0, "color": (230,230,230)},
    "goblin":      {"atk_cd": 0.8, "color": (80,180,80)},
    "dark_knight": {"atk_cd": 1.2, "color": (40,40,60)},
}

# BASE_XP/GOLD_DROPS live in game/stats.py now (Stage B1) - re-exported here
# so existing `from game.enemy import BASE_XP, GOLD_DROPS` call sites don't
# need to change. Monster-level scaling: see game.stats.xp_for_kill()/
# gold_for_kill().


class GoldDrop:
    """A coin pickup left on the ground by a kill. Visible for VISIBLE_S,
    then blinks for BLINK_S before disappearing if never collected -
    same "use it or lose it" shape as the heart pickups, just shorter-lived
    since gold drops on every kill instead of on a timer."""

    VISIBLE_S = 3.0
    BLINK_S = 2.0

    def __init__(self, x, y, amount):
        sprite = create_item_sprite("gold")
        self.x = float(x) - sprite.get_width() / 2
        self.y = float(y) - sprite.get_height() / 2
        self.amount = amount
        self.sprite = sprite
        self.age = 0.0
        self.alive = True
        self._bob = random.uniform(0, math.pi * 2)
        self.offset = 0.0

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.sprite.get_width(), self.sprite.get_height())

    @property
    def blinking(self):
        return self.age >= self.VISIBLE_S

    def update(self, dt):
        self.age += dt
        if self.age >= self.VISIBLE_S + self.BLINK_S:
            self.alive = False
        self._bob += dt * 3.0
        self.offset = math.sin(self._bob) * 3

    def draw(self, surface, cam_x, cam_y):
        if self.blinking and int(self.age * 6) % 2 == 0:
            return
        surface.blit(self.sprite, (int(self.x - cam_x), int(self.y - cam_y + self.offset)))


class Enemy:
    def __init__(self, x, y, etype="skeleton", speed_multiplier=1.0, ml=1):
        self.x = float(x)
        self.y = float(y)
        self.etype = etype
        self.ml = ml
        self.width = 32
        self.height = 36

        self.stats = StatBlock(**scale_archetype(ENEMY_ARCHETYPES[etype], ml))
        flavor = ENEMY_FLAVOR[etype]
        self.max_hp = self.stats.max_hp
        self.hp = self.max_hp
        self.speed = self.stats.speed * speed_multiplier
        self.damage = self.stats.physical_damage
        self.attack_cooldown = 0
        self.attack_cd_max = flavor["atk_cd"]
        self.color = flavor["color"]

        self.hit_flash = 0
        self.sprite = create_enemy_sprite(etype)
        self.flip = False
        self.patrol_timer = random.uniform(0, 3)
        self.patrol_dir = (random.choice([-1,0,1]), random.choice([-1,0,1]))
        self.aggro_range = 200
        self.attack_range = 50
        self.alive = True
        self.particles = []
        self.projectiles = []
        self.projectile_sprite = create_projectile_sprite("fireball")
        # Goblin puddle timer
        self.puddle_timer = random.uniform(4.0, 8.0) if self.etype == "goblin" else None

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def take_damage(self, amount):
        self.hp -= amount
        self.hit_flash = 0.15
        # Spawn hit particles
        for _ in range(8):
            self.particles.append(Particle(self.x + 16, self.y + 18, (255, 100, 50)))
        if self.hp <= 0:
            self.alive = False
            for _ in range(16):
                self.particles.append(Particle(self.x + 16, self.y + 18, self.color))

    def update(self, dt, player, walls, map_width=None, map_height=None, puddles=None):
        # Update particles
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

        # Update projectiles
        for proj in self.projectiles:
            proj.update(dt, walls)
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage)
                if proj.status_effect and random.random() < proj.status_chance:
                    player.status.apply(proj.status_effect)
                proj.alive = False
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Goblin: spawn puddles occasionally
        if self.etype == "goblin" and puddles is not None and self.puddle_timer is not None:
            self.puddle_timer -= dt
            if self.puddle_timer <= 0:
                self.puddle_timer = random.uniform(4.0, 8.0)
                # align to tile
                col = int(self.x // TILE)
                row = int(self.y // TILE)
                spawn_x = col * TILE + 8
                spawn_y = row * TILE + 8
                candidate = pygame.Rect(spawn_x, spawn_y, TILE//2, TILE//2)
                # avoid placing puddles over walls or existing puddles
                if any(candidate.colliderect(w) for w in walls):
                    pass
                elif any(candidate.colliderect(p.rect) for p in puddles):
                    pass
                else:
                    puddles.append(Puddle(spawn_x, spawn_y, damage_interval=1.0))

        if not self.alive:
            return

        if self.hit_flash > 0:
            self.hit_flash -= dt

        px = player.x + player.width / 2
        py = player.y + player.height / 2
        ex = self.x + self.width / 2
        ey = self.y + self.height / 2
        dist = math.hypot(px - ex, py - ey)

        if dist < self.aggro_range:
            # Chase
            if dist > 0:
                dx = (px - ex) / dist
                dy = (py - ey) / dist
                self.flip = dx < 0
                self.x += dx * self.speed * dt
                self._resolve_x(walls, dx)
                self.y += dy * self.speed * dt
                self._resolve_y(walls, dy)

            # Dark knight laser attack when not too close
            if self.etype == "dark_knight" and self.attack_cooldown <= 0 and dist > self.attack_range and dist < self.aggro_range:
                self._shoot_at_player(player)
                self.attack_cooldown = self.attack_cd_max
            elif self.attack_cooldown <= 0 and dist < self.attack_range:
                player.take_damage(self.damage)
                self.attack_cooldown = self.attack_cd_max
        else:
            # Patrol
            self.patrol_timer -= dt
            if self.patrol_timer <= 0:
                self.patrol_timer = random.uniform(1, 3)
                self.patrol_dir = (random.choice([-1,0,1]), random.choice([-1,0,1]))
            self.x += self.patrol_dir[0] * 40 * dt
            self._resolve_x(walls, self.patrol_dir[0])
            self.y += self.patrol_dir[1] * 40 * dt
            self._resolve_y(walls, self.patrol_dir[1])

        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

    def _shoot_at_player(self, player):
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        dist = math.hypot(px - cx, py - cy)
        if dist == 0:
            return
        speed = 220
        vx = (px - cx) / dist * speed
        vy = (py - cy) / dist * speed
        self.projectiles.append(EnemyProjectile(
            cx, cy, vx, vy, self.damage, (180, 100, 255),
            status_effect="weakness", status_chance=0.15
        ))

    def _resolve_x(self, walls, dx):
        r = self.rect
        for wall in walls:
            if r.colliderect(wall):
                if dx > 0:
                    self.x = wall.left - self.width
                elif dx < 0:
                    self.x = wall.right

    def _resolve_y(self, walls, dy):
        r = self.rect
        for wall in walls:
            if r.colliderect(wall):
                if dy > 0:
                    self.y = wall.top - self.height
                elif dy < 0:
                    self.y = wall.bottom

    def draw(self, surface, cam_x, cam_y):
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)

        if not self.alive:
            return

        sprite = self.sprite
        if self.flip:
            sprite = pygame.transform.flip(sprite, True, False)

        if self.hit_flash > 0:
            white = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            white.fill((255, 255, 255, 180))
            sprite = sprite.copy()
            sprite.blit(white, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        surface.blit(sprite, (sx - 8, sy - 10))

        # HP bar
        bar_w = 40
        bar_h = 4
        bx = sx - 4
        by = sy - 16
        pygame.draw.rect(surface, (60, 0, 0), (bx, by, bar_w, bar_h))
        hp_frac = max(0, self.hp / self.max_hp)
        pygame.draw.rect(surface, (220, 50, 50), (bx, by, int(bar_w * hp_frac), bar_h))
        pygame.draw.rect(surface, (200, 200, 200), (bx, by, bar_w, bar_h), 1)
