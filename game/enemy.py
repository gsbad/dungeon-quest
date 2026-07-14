import pygame
import math
import random
from game.assets import create_enemy_sprite, create_projectile_sprite, create_item_sprite
from game.player import TILE
from game.stats import StatBlock, ENEMY_ARCHETYPES, BASE_XP, GOLD_DROPS, scale_archetype, mitigate
from game.status_effects import StatusEffectCarrier
from game.affixes import AFFIXES
from game.combat_fx import (
    FloatingNumber, PHYSICAL_COLOR, MAGIC_COLOR, DOT_COLOR,
    knockback_vector, KNOCKBACK_DURATION,
)

# Stage K5: display name shown above a regular enemy's head (draw() below).
# Duplicated from game/bestiary.py's BESTIARY[etype]["name"] rather than
# imported from it - bestiary.py already imports ENEMY_FLAVOR from this
# module, so the reverse import would be circular. Same small-duplication
# tradeoff already accepted elsewhere in this codebase (e.g. the backend's
# BALANCE_DEFAULTS) when the import direction can't go both ways.
ENEMY_DISPLAY_NAMES = {
    "skeleton": "Esqueleto", "goblin": "Goblin", "dark_knight": "Cavaleiro Negro",
    "aranha": "Aranha", "serpente": "Serpente", "treant": "Treant",
    "troll": "Troll", "death_knight": "Cavaleiro da Morte",
    "zumbi": "Zumbi", "verme": "Verme", "imp": "Imp",
    "dark_horse": "Dark Horse", "acolito": "Acolito", "feiticeira": "Feiticeira",
    "fire_hound": "Fire Hound", "ogro": "Ogro", "elemental_pedra": "Elemental de Pedra",
    "chimera": "Quimera", "lyzardman": "Lyzardman", "dark_skeleton": "Esqueleto Sombrio",
}

class EnemyProjectile:
    def __init__(self, x, y, vx, vy, damage=1, color=(160,100,255),
                 status_effect=None, status_chance=0.0, dtype="magic"):
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
        # Ranged bolt = the mob's "spell", never contact - see
        # game/boss.py's Projectile for why this defaults to magic.
        self.dtype = dtype

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


# AI/animation tuning that isn't a combat stat - stays local to enemy.py.
# Stage D6 generalizes the two hardcoded etype-specific behaviors
# (dark_knight's laser, goblin's puddles) into data here, so a new
# archetype's "spell" (ranged bolt, on-hit debuff, ground hazard) is a
# dict entry instead of a new `if self.etype == ...` branch:
#   "ranged": {color, status_effect, status_chance, speed} - fires an
#     EnemyProjectile (always magic-typed, see game/boss.py's Projectile)
#     at the player from range instead of/before closing to melee.
#   "melee_status": (effect_id, chance) - rolled on every successful melee
#     hit, on top of the normal physical damage.
#   "puddles": True - spawns goblin-style damage-over-time floor hazards
#     while chasing the player (game/level.py applies them, dtype=magic).
ENEMY_FLAVOR = {
    # Stage F7 - every archetype gets a "ranged" entry now (previously only
    # dark_knight/cursed_mage/ash_fiend did); Enemy only actually fires it
    # once self.level_num >= 3 (see the ranged-attack branch in update()
    # below), so levels 1-2 still play exactly as before even though
    # skeleton/goblin keep spawning there.
    "skeleton":    {"atk_cd": 1.0, "color": (230,230,230),
                     "ranged": {"color": (220,220,210), "status_effect": None,
                                "status_chance": 0.0, "speed": 210}},
    "goblin":      {"atk_cd": 0.8, "color": (80,180,80), "puddles": True,
                     "ranged": {"color": (180,220,120), "status_effect": None,
                                "status_chance": 0.0, "speed": 230}},
    "dark_knight": {"atk_cd": 1.2, "color": (40,40,60),
                     "ranged": {"color": (180,100,255), "status_effect": "weakness",
                                "status_chance": 0.15, "speed": 220}},

    # Individualization pass (levels 5/6/7/9/10/11) - swamp_troll/cursed_mage/
    # crypt_wraith/ash_fiend/royal_guard retired, replaced by a per-level
    # roster. "ranged_shape" (optional, default "single") picks how
    # _shoot_at_player fires the flavor's "ranged" bolt(s) - see that method
    # below for "spread3"/"spread5"/"circle6". A missing "ranged" key means
    # the mob never shoots (pure melee, e.g. zumbi/ogro).

    # Level 5 - Pantano Sombrio
    "aranha":   {"atk_cd": 0.9, "color": (60,40,70),
                  "melee_status": ("poison", 0.30)},
    "serpente": {"atk_cd": 0.8, "color": (60,120,60),
                  "melee_status": ("poison", 0.25)},
    "treant":   {"atk_cd": 1.6, "color": (60,45,25),
                  "ranged": {"color": (120,200,90), "status_effect": "slow",
                             "status_chance": 0.25, "speed": 150},
                  "ranged_shape": "spread3"},

    # Level 6 - Torre Amaldicoada (skeleton reused as-is)
    "troll":        {"atk_cd": 1.3, "color": (90,110,70),
                       "melee_status": ("weakness", 0.25)},
    "death_knight": {"atk_cd": 1.1, "color": (30,30,40),
                       "ranged": {"color": (150,80,220), "status_effect": "weakness",
                                  "status_chance": 0.22, "speed": 230}},

    # Level 7 - Cripta Perdida
    "zumbi": {"atk_cd": 1.4, "color": (90,110,70),
               "melee_status": ("poison", 0.30)},
    "verme": {"atk_cd": 1.0, "color": (110,90,50),
               "melee_status": ("poison", 0.25)},
    "imp":   {"atk_cd": 1.0, "color": (150,40,40),
               "ranged": {"color": (255,240,120), "status_effect": "shock",
                          "status_chance": 0.20, "speed": 210},
               "ranged_shape": "spread5"},

    # Level 9 - Salao dos Ecos
    "dark_horse": {"atk_cd": 0.9, "color": (30,25,40),
                     "melee_status": ("chill", 0.25)},
    "acolito":    {"atk_cd": 1.2, "color": (110,90,60),
                     "ranged": {"color": (200,120,220), "status_effect": "weakness",
                                "status_chance": 0.20, "speed": 210}},
    "feiticeira": {"atk_cd": 1.3, "color": (60,70,120),
                     "ranged": {"color": (150,210,255), "status_effect": "chill",
                                "status_chance": 0.25, "speed": 220}},

    # Level 10 - Abismo de Cinzas
    "fire_hound":      {"atk_cd": 0.9, "color": (150,60,20),
                          "ranged": {"color": (255,140,40), "status_effect": "burn",
                                     "status_chance": 0.25, "speed": 240}},
    "ogro":            {"atk_cd": 1.5, "color": (110,80,40)},
    "elemental_pedra": {"atk_cd": 2.0, "color": (100,90,85),
                          "ranged": {"color": (160,140,120), "status_effect": None,
                                     "status_chance": 0.0, "speed": 170},
                          "ranged_shape": "circle6"},

    # Level 11 - Corredor Final
    "chimera":       {"atk_cd": 1.2, "color": (140,100,40),
                        "melee_status": ("weakness", 0.20),
                        "ranged": {"color": (255,120,30), "status_effect": "burn",
                                   "status_chance": 0.25, "speed": 230}},
    "lyzardman":     {"atk_cd": 0.9, "color": (40,110,70),
                        "melee_status": ("poison", 0.25)},
    # First archetype with luck>0 (crit) since royal_guard's retirement -
    # its ranged attack is a plain shock bolt, elite-guard role again.
    "dark_skeleton": {"atk_cd": 1.0, "color": (50,50,55),
                        "ranged": {"color": (255,255,140), "status_effect": "shock",
                                   "status_chance": 0.20, "speed": 250}},
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
    def __init__(self, x, y, etype="skeleton", speed_multiplier=1.0, ml=1, level_num=1, audio_mgr=None):
        self.x = float(x)
        self.y = float(y)
        self.etype = etype
        self.ml = ml
        # Stage H7: optional - only Level-spawned/summoned enemies pass one
        # in; None is safe everywhere audio is played (guarded).
        self.audio = audio_mgr
        # Stage F7: which stage this mob spawned in - gates flavor["ranged"]
        # below (level_num >= 3), independent of `ml` (monster level, which
        # already diverges per difficulty tier and isn't 1:1 with the stage
        # number a player would recognize as "fase 3").
        self.level_num = level_num
        self.width = 32
        self.height = 36

        self.stats = StatBlock(**scale_archetype(ENEMY_ARCHETYPES[etype], ml))
        flavor = ENEMY_FLAVOR[etype]
        self.flavor = flavor
        self.max_hp = self.stats.max_hp
        self.hp = self.max_hp
        self._speed_mult = speed_multiplier
        self.speed = self.stats.speed * speed_multiplier
        self.damage = self.stats.physical_damage
        # Reusable debuff carrier (game/status_effects.py) - lets Frost Nova
        # (Stage B2) slow enemies with the same "slow" effect monster attacks
        # already apply to the player, instead of a second implementation.
        self.status = StatusEffectCarrier()
        self.attack_cooldown = 0
        self.attack_cd_max = flavor["atk_cd"]
        self.color = flavor["color"]
        # Set by game/affixes.py's make_paragon() - a rare upgraded monster
        # with x4 xp/gold and one random affix (Stage B3).
        self.is_paragon = False
        # Set by game/affixes.py's make_champion() - a difficulty-tier
        # (Stage B5) common upgrade, milder than Paragon, no pity counter.
        self.is_champion = False
        self.affix = None

        self.hit_flash = 0
        self.sprite = create_enemy_sprite(etype)
        self.flip = False
        self.patrol_timer = random.uniform(0, 3)
        self.patrol_dir = (random.choice([-1,0,1]), random.choice([-1,0,1]))
        self.aggro_range = 200
        self.attack_range = 50
        self.alive = True
        self.particles = []
        self.floating_numbers = []
        self.knockback_vx, self.knockback_vy, self.knockback_timer = 0.0, 0.0, 0.0  # Stage K9
        self.projectiles = []
        self.projectile_sprite = create_projectile_sprite("fireball")
        # Puddle timer - any archetype whose flavor opts in (goblin, and
        # Stage D6's swamp_troll)
        self.puddle_timer = random.uniform(4.0, 8.0) if flavor.get("puddles") else None

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def take_damage(self, amount, dtype="physical", crit=False, knockback_from=None):
        # dtype=None (status-effect DoT ticks) bypasses defense entirely -
        # poison/burn are fixed-per-tick damage that already accounts for
        # going around armor, same as Player's DoT handling in
        # game/player.py's update() (which skips take_damage altogether).
        if dtype is not None:
            defense = self.stats.physical_defense if dtype == "physical" else self.stats.magic_defense
            amount = mitigate(amount, defense)
        self.hp -= amount
        self.hit_flash = 0.15
        # Stage K9: knockback - None for the DoT-tick call in update() below
        # (a self-inflicted "hit" with no attacker position to push from).
        if knockback_from is not None:
            self.knockback_vx, self.knockback_vy = knockback_vector(
                knockback_from[0], knockback_from[1], self.x + 16, self.y + 18,
            )
            self.knockback_timer = KNOCKBACK_DURATION
        # Stage K6: floating damage number - dtype=None means this call came
        # from a DoT tick (see the comment above), which gets its own dark
        # orange color distinct from a direct physical/magic hit.
        if dtype is None:
            number_color = DOT_COLOR
        elif dtype == "physical":
            number_color = PHYSICAL_COLOR
        else:
            number_color = MAGIC_COLOR
        self.floating_numbers.append(FloatingNumber(self.x + 16, self.y, amount, number_color))
        # Spawn hit particles - a crit gets extra gold-tinted particles on
        # top of the normal red hit-spray, same visual language as the
        # existing level-up/gold-pickup particle bursts.
        particle_color = (255, 100, 50)
        for _ in range(8):
            self.particles.append(Particle(self.x + 16, self.y + 18, particle_color))
        if crit:
            for _ in range(8):
                self.particles.append(Particle(self.x + 16, self.y + 18, (255, 215, 0)))
        if self.hp <= 0:
            self.alive = False
            for _ in range(16):
                self.particles.append(Particle(self.x + 16, self.y + 18, self.color))

    def update(self, dt, player, walls, map_width=None, map_height=None, puddles=None):
        # Debuffs (e.g. Frost Nova's Lentidao) - unlike Player, Enemy has no
        # invincibility-frame concept, so DoT ticks can safely go through
        # take_damage() and get the normal hit-flash/particle feedback.
        self.speed = self.stats.speed * self._speed_mult * self.status.speed_multiplier
        tick_dmg = self.status.update(dt)
        if tick_dmg and self.alive:
            self.take_damage(tick_dmg, dtype=None)

        # Update particles
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

        # Stage K6: floating damage numbers
        self.floating_numbers = [n for n in self.floating_numbers if n.alive]
        for n in self.floating_numbers:
            n.update(dt)

        # Update projectiles
        for proj in self.projectiles:
            proj.update(dt, walls)
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage, dtype=proj.dtype, knockback_from=(proj.x, proj.y))
                if proj.status_effect and random.random() < proj.status_chance:
                    player.try_apply_debuff(proj.status_effect)
                if self.affix == "vampiric":
                    self.hp = min(self.max_hp, self.hp + proj.damage * 0.2)
                proj.alive = False
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Puddle-spawning archetypes only (flavor["puddles"])
        if puddles is not None and self.puddle_timer is not None:
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

        if self.knockback_timer > 0:
            # Stage K9: overrides chase/patrol for its short duration, same
            # "temporary state takes over movement" shape as Player's dash/
            # knockback handling in game/player.py.
            self.knockback_timer -= dt
            self.x += self.knockback_vx * dt
            self._resolve_x(walls, self.knockback_vx)
            self.y += self.knockback_vy * dt
            self._resolve_y(walls, self.knockback_vy)
            ease = max(0.0, self.knockback_timer / KNOCKBACK_DURATION)
            self.knockback_vx *= ease
            self.knockback_vy *= ease
            return

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

            # Ranged attack (flavor["ranged"]) when not too close
            if (self.flavor.get("ranged") and self.level_num >= 3
                    and self.attack_cooldown <= 0 and dist > self.attack_range and dist < self.aggro_range):
                self._shoot_at_player(player)
                self.attack_cooldown = self.attack_cd_max
            elif self.attack_cooldown <= 0 and dist < self.attack_range:
                dmg, is_crit = self.stats.roll_physical()
                player.take_damage(dmg, dtype="physical",
                                    knockback_from=(self.x + self.width / 2, self.y + self.height / 2))
                if self.audio:
                    self.audio.play(f"attack_{self.etype}")
                melee_status = self.flavor.get("melee_status")
                if melee_status:
                    effect_id, chance = melee_status
                    if random.random() < chance:
                        player.try_apply_debuff(effect_id)
                if self.affix == "vampiric":
                    self.hp = min(self.max_hp, self.hp + dmg * 0.2)
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
        """Fires flavor["ranged"] as 1+ EnemyProjectile(s). Most archetypes
        use the default "single" shape (one bolt aimed at the player,
        unchanged from before); a few (treant/imp/elemental_pedra) opt into
        a multi-shot shape via flavor["ranged_shape"], same
        spread/circle-burst techniques game/boss.py's Boss already uses for
        its own patterns, just aimed from an Enemy instead."""
        if self.audio:
            self.audio.play(f"attack_{self.etype}")
        ranged = self.flavor["ranged"]
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        shape = self.flavor.get("ranged_shape", "single")

        if shape == "circle6":
            speed = ranged["speed"]
            for i in range(6):
                angle = (2 * math.pi / 6) * i
                vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
                self.projectiles.append(EnemyProjectile(
                    cx, cy, vx, vy, self.damage, ranged["color"],
                    status_effect=ranged["status_effect"], status_chance=ranged["status_chance"],
                    dtype="magic"
                ))
            return

        px = player.x + player.width / 2
        py = player.y + player.height / 2
        dist = math.hypot(px - cx, py - cy)
        if dist == 0:
            return
        base_angle = math.atan2(py - cy, px - cx)
        if shape == "spread3":
            offsets = (-0.3, 0.0, 0.3)
        elif shape == "spread5":
            offsets = (-0.5, -0.25, 0.0, 0.25, 0.5)
        else:
            offsets = (0.0,)

        speed = ranged["speed"]
        for offset in offsets:
            angle = base_angle + offset
            vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
            self.projectiles.append(EnemyProjectile(
                cx, cy, vx, vy, self.damage, ranged["color"],
                status_effect=ranged["status_effect"], status_chance=ranged["status_chance"],
                dtype="magic"
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
        for n in self.floating_numbers:
            n.draw(surface, cam_x, cam_y)

        if not self.alive:
            return

        sprite = self.sprite
        if self.flip:
            sprite = pygame.transform.flip(sprite, True, False)

        if self.hit_flash > 0:
            white = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            white.fill((255, 255, 255, 180))
            sprite = sprite.copy()
            # BLEND_RGB_ADD (not RGBA_ADD) - see game/boss.py's Boss.draw()
            # for why: RGBA_ADD also adds alpha, turning the sprite's
            # transparent margin into a translucent white box instead of
            # just tinting the visible silhouette.
            sprite.blit(white, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)

        if self.is_paragon:
            import time
            from game.theme import font, GOLD
            t = time.time()
            radius = int(26 + 6 * math.sin(t * 4))
            aura = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 215, 0, 90), (radius, radius), radius)
            surface.blit(aura, (sx + self.width // 2 - radius, sy + self.height // 2 - radius))
            f_name = font(13, bold=True)
            label = f"PARAGON - {AFFIXES[self.affix]['name']}"
            txt = f_name.render(label, True, GOLD)
            surface.blit(txt, (sx + self.width // 2 - txt.get_width() // 2, sy - 26))
        elif self.is_champion:
            import time
            from game.theme import font
            t = time.time()
            radius = int(22 + 5 * math.sin(t * 4))
            aura = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(aura, (210, 215, 230, 90), (radius, radius), radius)
            surface.blit(aura, (sx + self.width // 2 - radius, sy + self.height // 2 - radius))
            f_name = font(12, bold=True)
            label = f"CAMPEAO - {AFFIXES[self.affix]['name']}"
            txt = f_name.render(label, True, (220, 225, 235))
            surface.blit(txt, (sx + self.width // 2 - txt.get_width() // 2, sy - 24))
        else:
            # Stage K5: Paragon/Champion already get their own label above
            # (the affix name reads more useful than the plain etype there),
            # so this is only for the common case.
            from game.theme import font, SUBTEXT
            f_name = font(11, bold=True)
            label = ENEMY_DISPLAY_NAMES.get(self.etype, self.etype)
            txt = f_name.render(label, True, SUBTEXT)
            surface.blit(txt, (sx + self.width // 2 - txt.get_width() // 2, sy - 22))

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
