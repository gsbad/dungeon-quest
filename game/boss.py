import pygame
import os
import math
import random
from game.assets import create_boss_sprite, create_projectile_sprite
from game.enemy import Particle

class Projectile:
    def __init__(self, x, y, vx, vy, damage=1, color=(255,100,0)):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.color = color
        self.radius = 8
        self.alive = True
        self.age = 0

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius*2, self.radius*2)

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
        # Glow
        glow = pygame.Surface((self.radius*4, self.radius*4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.color, 80), (self.radius*2, self.radius*2), self.radius*2)
        surface.blit(glow, (sx - self.radius*2, sy - self.radius*2))
        pygame.draw.circle(surface, self.color, (sx, sy), self.radius)
        pygame.draw.circle(surface, (255,255,200), (sx, sy), self.radius//2)


class Boss:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.width = 96
        self.height = 96
        self.max_hp = 30
        self.hp = self.max_hp
        self._saved_max_hp = None
        self._saved_hp = None
        self.phase = 1
        self.alive = True

        self.speed = 80
        self.projectiles = []
        self.particles = []

        self.attack_timer = 0
        self.attack_interval = 2.0
        self.move_timer = 0
        self.move_dir = (1, 0)
        self.hit_flash = 0

        self.sprite_p1 = create_boss_sprite(1)
        self.sprite_p2 = create_boss_sprite(2)

        self.enrage_timer = 0  # Phase 2 visual effect

        # Auto-enable one-hit boss for testing if env var set
        if os.getenv("ONE_HIT_BOSS", "0") in ("1", "true", "True"):
            self.enable_one_hit()

    def enable_one_hit(self):
        if self._saved_max_hp is None:
            self._saved_max_hp = self.max_hp
            self._saved_hp = self.hp
            self.max_hp = 1
            self.hp = 1

    def restore_hp(self):
        if self._saved_max_hp is not None:
            self.max_hp = self._saved_max_hp
            self.hp = self._saved_hp
            self._saved_max_hp = None
            self._saved_hp = None

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def take_damage(self, amount):
        if self.hit_flash > 0.05:
            return
        self.hp -= amount
        self.hit_flash = 0.12
        for _ in range(10):
            color = (200,50,200) if self.phase == 1 else (255,100,0)
            self.particles.append(Particle(self.x+48, self.y+48, color))
        if self.hp <= 0:
            self.alive = False
            for _ in range(40):
                self.particles.append(Particle(self.x+48, self.y+48, (255,200,0)))
        elif self.hp <= self.max_hp // 2 and self.phase == 1:
            self.phase = 2
            self.attack_interval = 1.2
            self.speed = 130

    def _shoot_circle(self, cx, cy, count, speed, damage, color):
        for i in range(count):
            angle = (2 * math.pi / count) * i
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.projectiles.append(Projectile(cx, cy, vx, vy, damage, color))

    def _shoot_at_player(self, player, speed, damage, color):
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        dist = math.hypot(px - cx, py - cy)
        if dist == 0:
            return
        vx = (px - cx) / dist * speed
        vy = (py - cy) / dist * speed
        self.projectiles.append(Projectile(cx, cy, vx, vy, damage, color))

    def update(self, dt, player, walls):
        # Update particles
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

        # Update projectiles
        for proj in self.projectiles:
            proj.update(dt, walls)
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage)
                proj.alive = False
        self.projectiles = [p for p in self.projectiles if p.alive]

        if not self.alive:
            return

        if self.hit_flash > 0:
            self.hit_flash -= dt

        if self.phase == 2:
            self.enrage_timer += dt

        # Movement - circle/chase
        self.move_timer -= dt
        if self.move_timer <= 0:
            self.move_timer = random.uniform(0.8, 2.0)
            angle = random.uniform(0, math.pi * 2)
            self.move_dir = (math.cos(angle), math.sin(angle))

        self.x += self.move_dir[0] * self.speed * dt
        self.y += self.move_dir[1] * self.speed * dt

        # Keep boss in arena (rough clamp)
        self.x = max(100, min(self.x, 700))
        self.y = max(100, min(self.y, 400))

        for wall in walls:
            r = self.rect
            if r.colliderect(wall):
                self.move_dir = (-self.move_dir[0], -self.move_dir[1])

        # Attack patterns
        self.attack_timer -= dt
        if self.attack_timer <= 0:
            self.attack_timer = self.attack_interval
            cx = self.x + self.width / 2
            cy = self.y + self.height / 2

            pattern = random.choice([0, 1, 2]) if self.phase == 1 else random.choice([0,1,2,3])

            if pattern == 0:
                # Circular burst
                count = 8 if self.phase == 1 else 12
                color = (180,0,255) if self.phase == 1 else (255,80,0)
                self._shoot_circle(cx, cy, count, 160, 1, color)
            elif pattern == 1:
                # Triple shot at player
                for offset in [-20, 0, 20]:
                    px = player.x + player.width/2 + offset
                    py = player.y + player.height/2
                    dist = math.hypot(px-cx, py-cy)
                    if dist > 0:
                        spd = 220
                        vx = (px-cx)/dist*spd
                        vy = (py-cy)/dist*spd
                        clr = (200,50,255) if self.phase==1 else (255,150,0)
                        self.projectiles.append(Projectile(cx,cy,vx,vy,1,clr))
            elif pattern == 2:
                # Spiral
                for i in range(16):
                    angle = (math.pi/8)*i + self.enrage_timer
                    spd = 180
                    vx = math.cos(angle)*spd
                    vy = math.sin(angle)*spd
                    clr = (150,0,200) if self.phase==1 else (255,50,50)
                    self.projectiles.append(Projectile(cx+vx*0.1,cy+vy*0.1,vx,vy,1,clr))
            elif pattern == 3:
                # Phase 2 only: double circle + aimed
                self._shoot_circle(cx, cy, 8, 140, 1, (255,100,0))
                self._shoot_at_player(player, 280, 2, (255,255,0))

    def draw(self, surface, cam_x, cam_y):
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)

        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        if not self.alive:
            return

        sprite = self.sprite_p1 if self.phase == 1 else self.sprite_p2

        if self.hit_flash > 0:
            white = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            white.fill((255, 255, 255, 200))
            sprite = sprite.copy()
            sprite.blit(white, (0,0), special_flags=pygame.BLEND_RGBA_ADD)

        # Phase 2 pulsing aura
        if self.phase == 2:
            radius = int(70 + 10 * math.sin(self.enrage_timer * 6))
            aura = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255,60,0,50), (radius,radius), radius)
            surface.blit(aura, (int(self.x - cam_x + self.width/2 - radius),
                                int(self.y - cam_y + self.height/2 - radius)))

        surface.blit(sprite, (int(self.x - cam_x), int(self.y - cam_y)))

        # HP bar
        bx = int(self.x - cam_x)
        by = int(self.y - cam_y) - 20
        bar_w = self.width
        pygame.draw.rect(surface, (60,0,0), (bx, by, bar_w, 10))
        frac = max(0, self.hp / self.max_hp)
        color = (180,0,220) if self.phase==1 else (255,80,0)
        pygame.draw.rect(surface, color, (bx, by, int(bar_w*frac), 10))
        pygame.draw.rect(surface, (220,220,220), (bx,by,bar_w,10), 1)

    def draw_hud(self, surface, screen_w):
        """Big boss HP bar at top of screen"""
        font = pygame.font.Font(None, 18)
        font.set_bold(True)
        label = font.render("REI DAS SOMBRAS" if self.phase==1 else "⚡ ENRAIVECIDO!", True,
                            (220,180,255) if self.phase==1 else (255,150,50))
        bar_w = 400
        bx = screen_w//2 - bar_w//2
        by = 16
        pygame.draw.rect(surface, (40,0,60), (bx-2, by-2, bar_w+4, 20))
        frac = max(0, self.hp/self.max_hp)
        clr = (160,0,220) if self.phase==1 else (255,80,0)
        pygame.draw.rect(surface, clr, (bx, by, int(bar_w*frac), 16))
        pygame.draw.rect(surface, (200,200,220), (bx,by,bar_w,16),2)
        surface.blit(label, (screen_w//2 - label.get_width()//2, by+20))


# ─── Cacodemon Boss (Secret Level) ─────────────────────────────────────────────
class CacodemonBoss:
    """Infernal demon boss inspired by DOOM's Cacodemon"""
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.width = 80
        self.height = 80
        self.max_hp = 40
        self.hp = self.max_hp
        self.alive = True

        self.speed = 100
        self.projectiles = []
        self.particles = []

        self.attack_timer = 0
        self.attack_interval = 1.5
        self.move_timer = 0
        self.move_dir = (1, 0)
        self.hit_flash = 0
        self.bob_offset = 0  # For hovering animation
        self.bob_timer = 0

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def take_damage(self, amount):
        if self.hit_flash > 0.05:
            return
        self.hp -= amount
        self.hit_flash = 0.12
        # Create damage particles
        for _ in range(4):
            angle = random.uniform(0, 2*math.pi)
            speed = random.uniform(150, 250)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.particles.append(
                Particle(self.x + self.width//2, self.y + self.height//2,
                        (255, 100, 0))
            )

    def update(self, dt, player, walls):
        self.bob_timer += dt
        self.bob_offset = 15 * math.sin(self.bob_timer * 2)
        self.hit_flash = max(0, self.hit_flash - dt)

        # Move towards player
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.sqrt(dx**2 + dy**2)

        if dist > 1:
            self.move_dir = (dx / dist, dy / dist)

        new_x = self.x + self.move_dir[0] * self.speed * dt
        new_y = self.y + self.move_dir[1] * self.speed * dt

        # Simple collision check
        test_rect = pygame.Rect(new_x, new_y, self.width, self.height)
        can_move = True
        for wall in walls:
            if test_rect.colliderect(wall):
                can_move = False
                break

        if can_move:
            self.x = new_x
            self.y = new_y

        # Attacking
        self.attack_timer -= dt
        if self.attack_timer <= 0:
            self.attack_timer = self.attack_interval
            self._shoot_at_player(player)

        # Update projectiles
        for proj in self.projectiles:
            proj.update(dt, walls)
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Update particles
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        if self.hp <= 0:
            self.alive = False

    def _shoot_at_player(self, player):
        """Fire triple shot at player"""
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.sqrt(dx**2 + dy**2)
        if dist < 1:
            dist = 1

        # Three projectiles in spread pattern
        base_angle = math.atan2(dy, dx)
        angles = [base_angle - 0.3, base_angle, base_angle + 0.3]

        for angle in angles:
            vx = math.cos(angle) * 250
            vy = math.sin(angle) * 250
            proj = Projectile(self.x + self.width//2, self.y + self.height//2,
                            vx, vy, damage=1, color=(255, 100, 0))
            self.projectiles.append(proj)

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y + self.bob_offset)

        # Create demon sprite (red/orange sphere with eyes)
        demon_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        # Main body - dark orange sphere
        pygame.draw.circle(demon_surf, (180, 40, 10), (self.width//2, self.height//2), self.width//2)

        # Flame pattern on body
        for i in range(5):
            angle = math.pi * 2 * i / 5 + self.bob_timer
            ex = self.width//2 + math.cos(angle) * 18
            ey = self.height//2 + math.sin(angle) * 18
            pygame.draw.circle(demon_surf, (255, 130, 0), (ex, ey), 8)
            pygame.draw.circle(demon_surf, (255, 190, 0), (ex, ey), 4)

        # Eyes (evil slanted)
        eye_y = self.height//2 - 8
        left_eye = [(self.width//4-12, eye_y), (self.width//4+2, eye_y-8), (self.width//4+12, eye_y)]
        right_eye = [(3*self.width//4-12, eye_y), (3*self.width//4+2, eye_y-8), (3*self.width//4+12, eye_y)]
        pygame.draw.polygon(demon_surf, (255, 80, 0), left_eye)
        pygame.draw.polygon(demon_surf, (255, 80, 0), right_eye)
        pygame.draw.circle(demon_surf, (40, 0, 0), (self.width//4, eye_y+2), 5)
        pygame.draw.circle(demon_surf, (40, 0, 0), (3*self.width//4, eye_y+2), 5)
        pygame.draw.circle(demon_surf, (255, 140, 0), (self.width//4, eye_y+2), 2)
        pygame.draw.circle(demon_surf, (255, 140, 0), (3*self.width//4, eye_y+2), 2)

        # Horns (spikes)
        horn_positions = [
            (self.width//8, 4),
            (self.width//4 - 4, 2),
            (self.width//2, 0),
            (3*self.width//4 + 4, 2),
            (7*self.width//8, 4),
        ]
        for hx, hy in horn_positions:
            pygame.draw.polygon(demon_surf, (255, 120, 0),
                               [(hx-5, hy+8), (hx, hy), (hx+5, hy+8)])
        for hx, hy in [(self.width//4, 12), (3*self.width//4, 12)]:
            pygame.draw.polygon(demon_surf, (255, 100, 0),
                               [(hx-4, hy+8), (hx, hy), (hx+4, hy+8)])

        # Apply hit flash
        if self.hit_flash > 0.06:
            demo_flash = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            demo_flash.fill((255, 255, 255, 128))
            demon_surf.blit(demo_flash, (0, 0))

        surface.blit(demon_surf, (sx, sy))

        # HP bar
        bx = sx
        by = sy - 20
        bar_w = self.width
        pygame.draw.rect(surface, (60, 0, 0), (bx, by, bar_w, 10))
        frac = max(0, self.hp / self.max_hp)
        pygame.draw.rect(surface, (255, 50, 0), (bx, by, int(bar_w*frac), 10))
        pygame.draw.rect(surface, (220, 100, 0), (bx, by, bar_w, 10), 1)

        # Draw projectiles
        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        # Draw particles
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)

    def draw_hud(self, surface, screen_w):
        """Big boss HP bar at top of screen"""
        font = pygame.font.Font(None, 18)
        font.set_bold(True)
        label = font.render("CACODEMON INFERNAL", True, (255, 100, 0))
        bar_w = 400
        bx = screen_w//2 - bar_w//2
        by = 16
        pygame.draw.rect(surface, (60, 0, 0), (bx-2, by-2, bar_w+4, 20))
        frac = max(0, self.hp/self.max_hp)
        pygame.draw.rect(surface, (255, 100, 0), (bx, by, int(bar_w*frac), 16))
        pygame.draw.rect(surface, (255, 150, 0), (bx, by, bar_w, 16), 2)
        surface.blit(label, (screen_w//2 - label.get_width()//2, by+20))
