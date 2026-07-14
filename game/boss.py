import pygame
import os
import math
import random
from game.assets import create_boss_sprite, create_projectile_sprite
from game.enemy import Particle
from game.theme import font, TITLE_PAUSE
from game.ui import ProgressBar
from game.stats import StatBlock, mitigate
from game.combat_fx import FloatingNumber, PHYSICAL_COLOR, MAGIC_COLOR

def _draw_boss_hud_box(surface, screen_w, label_text, label_color, hud_bar, hp, max_hp, bar_color):
    """Stage G3: black 80%-opacity box wrapping the boss name + HP bar,
    anchored to the screen bottom (above the difficulty tag / "Fase N"
    title stack drawn by GameplayState/Level - see game/level.py's
    draw_hud_info) instead of floating unboxed at the top. Shared by Boss
    and CacodemonBoss's near-identical draw_hud() so the box exists once,
    not copy-pasted twice."""
    screen_h = surface.get_height()
    box_w = hud_bar.w + 40
    box_h = 60
    box_x = screen_w // 2 - box_w // 2
    box_y = screen_h - 116
    box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    box.fill((0, 0, 0, 204))
    surface.blit(box, (box_x, box_y))

    f = font(18, bold=True)
    label = f.render(label_text, True, label_color)
    surface.blit(label, (screen_w // 2 - label.get_width() // 2, box_y + 8))

    bar_x = screen_w // 2 - hud_bar.w // 2
    bar_y = box_y + 34
    frac = max(0, hp / max_hp)
    hud_bar.draw(surface, bar_x, bar_y, frac, bar_color)


class Projectile:
    def __init__(self, x, y, vx, vy, damage=1, color=(255,100,0),
                 status_effect=None, status_chance=0.0, dtype="magic"):
        self.x = float(x)
        self.y = float(y)
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.color = color
        self.radius = 8
        self.alive = True
        self.age = 0
        # Optional debuff this hit may inflict - see game/status_effects.py.
        self.status_effect = status_effect
        self.status_chance = status_chance
        # Every projectile in the game today is a spell-shaped ranged
        # attack (player Fireball, boss bolts, dark_knight's laser) - never
        # contact - so "magic" is the type for anything not thrown via a
        # melee hit; see game/stats.py's physical/magic defense split.
        self.dtype = dtype

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


# Per-boss, per-phase attack pattern pool (Stage D6) - AI/behavior tuning,
# same "stays local, not in game/stats.py's numbers-only archetypes" spirit
# as game/enemy.py's ENEMY_FLAVOR. shadow_king keeps its exact pre-D6 set
# unchanged; orc_warlord (Act 1) and necromancer (Act 2) get a distinct
# specialty pattern (charge / summon+curse) instead of sharing 100% of
# Boss's attack list the way all 3 did before.
BOSS_PATTERNS = {
    "orc_warlord": {1: ["charge", "triple"], 2: ["charge", "charge", "circle"]},
    "necromancer": {1: ["summon", "circle", "curse"], 2: ["summon", "spiral", "curse"]},
    "shadow_king": {1: ["circle", "triple", "spiral"], 2: ["circle", "triple", "spiral", "circle_aimed"]},
}


class Boss:
    """One rig, several bosses (Stage B4) - the campaign's 3 acts each end
    in their own boss (Orc Warlord, Necromancer, Shadow King), but they
    share this exact class/attack-pattern shape. Only the attribute block,
    name, and palette differ per boss_id (game/stats.py's BOSS_ARCHETYPES) -
    same "one rig, palette-swapped" idea already used for Paragon."""

    def __init__(self, x, y, boss_id="shadow_king", enrage_frac=0.5, audio_mgr=None):
        self.audio = audio_mgr
        from game.stats import BOSS_ARCHETYPES
        archetype = BOSS_ARCHETYPES[boss_id]
        self.boss_id = boss_id
        self.name = archetype["name"]
        # Difficulty-tier boss remix (Stage B5): higher tiers move phase 2
        # earlier instead of just padding hp/damage numbers - a structural
        # change to how the fight plays, not a bigger stat.
        self.enrage_frac = enrage_frac

        self.x = float(x)
        self.y = float(y)
        self.width = 96
        self.height = 96
        # vigor=83.33 (shadow_king) -> max_hp=270, i.e. the same 30-hit TTK
        # as before now that the player's attack_damage went from a flat 1
        # to stats-driven 9 (see states.py's boss.take_damage(...) call).
        self.stats = StatBlock(strength=archetype["strength"], dexterity=archetype["dexterity"],
                                vigor=archetype["vigor"], luck=archetype["luck"],
                                weapon_base=archetype["weapon_base"],
                                base_speed=archetype["base_speed"])
        self.max_hp = self.stats.max_hp
        self.hp = self.max_hp
        self.burst_dmg = self.stats.physical_damage
        self.aimed_dmg = self.burst_dmg * 2
        self.xp_reward = archetype["xp_reward"]
        self.gold_reward = archetype["gold_reward"]
        self._saved_max_hp = None
        self._saved_hp = None
        self.phase = 1
        self.alive = True

        self.speed = self.stats.speed
        self.projectiles = []
        self.particles = []
        self.floating_numbers = []

        # Charge attack state (orc_warlord's "charge" pattern, Stage D6) -
        # None outside a charge; windup->dashing while it plays out, taking
        # over update() from the normal movement/attack-roll flow. The one
        # boss attack that's contact/physical instead of a Projectile.
        self.charge_state = None
        self.charge_timer = 0.0
        self.charge_dir = (0.0, 0.0)
        self.charge_hit = False

        # Spawn requests from necromancer's "summon" pattern (Stage D6) -
        # (x, y) tuples GameplayState drains into real Enemy instances each
        # frame (Boss itself doesn't touch game/level.py's enemy list).
        self.pending_summons = []

        self.attack_timer = 0
        self.attack_interval = 2.0
        self.move_timer = 0
        self.move_dir = (1, 0)
        self.hit_flash = 0

        self.sprite_p1 = create_boss_sprite(self.boss_id, phase=1)
        self.sprite_p2 = create_boss_sprite(self.boss_id, phase=2)

        self.hp_bar = ProgressBar(self.width, 10, (60,0,0), (220,220,220), border_width=1)
        self.hud_bar = ProgressBar(400, 16, (40,0,60), (200,200,220), border_width=2, margin=2)

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

    def take_damage(self, amount, dtype="physical", crit=False):
        if self.hit_flash > 0.05:
            return
        defense = self.stats.physical_defense if dtype == "physical" else self.stats.magic_defense
        mitigated = mitigate(amount, defense)
        self.hp -= mitigated
        self.hit_flash = 0.12
        # Stage K6: floating damage number.
        number_color = PHYSICAL_COLOR if dtype == "physical" else MAGIC_COLOR
        self.floating_numbers.append(FloatingNumber(self.x + 48, self.y, mitigated, number_color))
        for _ in range(10):
            color = (200,50,200) if self.phase == 1 else (255,100,0)
            self.particles.append(Particle(self.x+48, self.y+48, color))
        if crit:
            for _ in range(8):
                self.particles.append(Particle(self.x+48, self.y+48, (255, 215, 0)))
        if self.hp <= 0:
            self.alive = False
            for _ in range(40):
                self.particles.append(Particle(self.x+48, self.y+48, (255,200,0)))
        elif self.hp <= self.max_hp * self.enrage_frac and self.phase == 1:
            self.phase = 2
            self.attack_interval = 1.2
            self.speed = self.stats.speed * 1.625  # same enrage ratio as the original 80->130

    def _shoot_circle(self, cx, cy, count, speed, damage, color,
                       status_effect=None, status_chance=0.0):
        for i in range(count):
            angle = (2 * math.pi / count) * i
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.projectiles.append(Projectile(cx, cy, vx, vy, damage, color,
                                                status_effect, status_chance))

    def _shoot_at_player(self, player, speed, damage, color,
                          status_effect=None, status_chance=0.0):
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        px = player.x + player.width / 2
        py = player.y + player.height / 2
        dist = math.hypot(px - cx, py - cy)
        if dist == 0:
            return
        vx = (px - cx) / dist * speed
        vy = (py - cy) / dist * speed
        self.projectiles.append(Projectile(cx, cy, vx, vy, damage, color,
                                            status_effect, status_chance))

    # Circle/triple/spiral/circle_aimed are shadow_king's exact original
    # (pre-Stage D6) attack set, now named methods so BOSS_PATTERNS can
    # mix-and-match them per boss_id instead of every boss sharing one
    # hardcoded pattern list.
    def _pattern_circle(self):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        count = 8 if self.phase == 1 else 12
        color = (180,0,255) if self.phase == 1 else (255,80,0)
        self._shoot_circle(cx, cy, count, 160, self.burst_dmg, color,
                            status_effect="slow", status_chance=0.10)

    def _pattern_triple(self, player):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        for offset in [-20, 0, 20]:
            px = player.x + player.width/2 + offset
            py = player.y + player.height/2
            dist = math.hypot(px-cx, py-cy)
            if dist > 0:
                spd = 220
                vx = (px-cx)/dist*spd
                vy = (py-cy)/dist*spd
                clr = (200,50,255) if self.phase==1 else (255,150,0)
                self.projectiles.append(Projectile(cx,cy,vx,vy,self.burst_dmg,clr))

    def _pattern_spiral(self):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        for i in range(16):
            angle = (math.pi/8)*i + self.enrage_timer
            spd = 180
            vx = math.cos(angle)*spd
            vy = math.sin(angle)*spd
            clr = (150,0,200) if self.phase==1 else (255,50,50)
            self.projectiles.append(Projectile(cx+vx*0.1,cy+vy*0.1,vx,vy,self.burst_dmg,clr,
                                                status_effect="slow", status_chance=0.10))

    def _pattern_circle_aimed(self, player):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        self._shoot_circle(cx, cy, 8, 140, self.burst_dmg, (255,100,0))
        self._shoot_at_player(player, 280, self.aimed_dmg, (255,255,0),
                               status_effect="weakness", status_chance=0.25)

    # orc_warlord's specialty (Act 1, the physical brawler) - the only boss
    # attack that's contact/physical instead of a Projectile, so the
    # player's physical defense (not spell defense) is what matters here.
    def _start_charge(self, player):
        self.charge_state = "windup"
        self.charge_timer = 0.6

    def _update_charge(self, dt, player):
        if self.charge_state == "windup":
            self.charge_timer -= dt
            if self.charge_timer <= 0:
                cx, cy = self.x + self.width/2, self.y + self.height/2
                px, py = player.x + player.width/2, player.y + player.height/2
                dist = math.hypot(px-cx, py-cy) or 1.0
                self.charge_dir = ((px-cx)/dist, (py-cy)/dist)
                self.charge_state = "dashing"
                self.charge_timer = 0.7
                self.charge_hit = False
        elif self.charge_state == "dashing":
            self.charge_timer -= dt
            dash_speed = self.stats.speed * 4
            self.x += self.charge_dir[0] * dash_speed * dt
            self.y += self.charge_dir[1] * dash_speed * dt
            self.x = max(100, min(self.x, 700))
            self.y = max(100, min(self.y, 400))
            if not self.charge_hit and self.rect.colliderect(player.rect):
                player.take_damage(round(self.stats.physical_damage * 2), dtype="physical")
                self.charge_hit = True
            if self.charge_timer <= 0:
                self.charge_state = None

    # necromancer's specialty (Act 2, the magic summoner).
    def _pattern_summon(self):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        for dx in (-70, 70):
            self.pending_summons.append((cx + dx, cy))

    def _pattern_curse(self, player):
        cx, cy = self.x + self.width/2, self.y + self.height/2
        for offset in (-15, 0, 15):
            px = player.x + player.width/2 + offset
            py = player.y + player.height/2
            dist = math.hypot(px-cx, py-cy)
            if dist > 0:
                spd = 200
                vx = (px-cx)/dist*spd
                vy = (py-cy)/dist*spd
                self.projectiles.append(Projectile(cx, cy, vx, vy, self.burst_dmg, (90,255,140),
                                                     status_effect="weakness", status_chance=0.30))

    def update(self, dt, player, walls):
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
                player.take_damage(proj.damage, dtype=proj.dtype)
                if proj.status_effect and random.random() < proj.status_chance:
                    player.status.apply(proj.status_effect)
                proj.alive = False
        self.projectiles = [p for p in self.projectiles if p.alive]

        if not self.alive:
            return

        if self.hit_flash > 0:
            self.hit_flash -= dt

        if self.phase == 2:
            self.enrage_timer += dt

        if self.charge_state:
            # Charging suppresses normal movement/attack rolls entirely
            # until the dash finishes - it's a windup+commit, not just
            # another projectile pattern layered on top of everything else.
            self._update_charge(dt, player)
            return

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

        # Attack patterns - which ones are in the pool at all is per boss_id
        # (BOSS_PATTERNS below), so each Act's boss plays differently
        # instead of every boss sharing shadow_king's exact original set.
        self.attack_timer -= dt
        if self.attack_timer <= 0:
            self.attack_timer = self.attack_interval
            if self.audio:
                self.audio.play(f"attack_{self.boss_id}")
            pattern = random.choice(BOSS_PATTERNS[self.boss_id][self.phase])
            if pattern == "circle":
                self._pattern_circle()
            elif pattern == "triple":
                self._pattern_triple(player)
            elif pattern == "spiral":
                self._pattern_spiral()
            elif pattern == "circle_aimed":
                self._pattern_circle_aimed(player)
            elif pattern == "charge":
                self._start_charge(player)
            elif pattern == "summon":
                self._pattern_summon()
            elif pattern == "curse":
                self._pattern_curse(player)

    def draw(self, surface, cam_x, cam_y):
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)
        for n in self.floating_numbers:
            n.draw(surface, cam_x, cam_y)

        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        if not self.alive:
            return

        sprite = self.sprite_p1 if self.phase == 1 else self.sprite_p2

        if self.hit_flash > 0:
            white = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            white.fill((255, 255, 255, 200))
            sprite = sprite.copy()
            # BLEND_RGB_ADD (not RGBA_ADD) - RGBA_ADD also adds the alpha
            # channel, so a transparent margin pixel (alpha=0) plus this
            # overlay's alpha=200 became a translucent white square around
            # the whole sprite canvas instead of just tinting the visible
            # silhouette - very noticeable on the individualized rigs,
            # which have a lot more transparent margin than the old
            # rig. RGB_ADD only touches color channels, leaving alpha (and
            # therefore the sprite's actual silhouette) untouched.
            sprite.blit(white, (0,0), special_flags=pygame.BLEND_RGB_ADD)

        # Charge windup tell (orc_warlord) - a red pulse during the 0.6s
        # wind-up gives the player a fair warning before the dash commits.
        if self.charge_state == "windup":
            red = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            red.fill((255, 40, 40, 130))
            sprite = sprite.copy()
            sprite.blit(red, (0,0), special_flags=pygame.BLEND_RGB_ADD)

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
        frac = max(0, self.hp / self.max_hp)
        color = (180,0,220) if self.phase==1 else (255,80,0)
        self.hp_bar.draw(surface, bx, by, frac, color)

        # Stage K5: name above the HP bar, in-world - draw_hud() below
        # already shows it in the bottom HUD box, but that's easy to miss
        # mid-fight; this puts it right where the player is looking.
        from game.theme import font, SUBTEXT
        f_name = font(12, bold=True)
        txt = f_name.render(self.name, True, SUBTEXT)
        surface.blit(txt, (bx + self.hp_bar.w // 2 - txt.get_width() // 2, by - 16))

    def draw_hud(self, surface, screen_w):
        """Boss HP bar + name, boxed, at the bottom of the screen (Stage G3)."""
        # Stage H4: pygame's default embedded font (game/theme.py's font(),
        # Font(None, size)) has no glyph for U+26A1 - rendered as a tofu box.
        label_text = self.name.upper() if self.phase == 1 else "ENRAIVECIDO!"
        label_color = TITLE_PAUSE if self.phase == 1 else (255, 150, 50)
        bar_color = (160, 0, 220) if self.phase == 1 else (255, 80, 0)
        _draw_boss_hud_box(surface, screen_w, label_text, label_color,
                            self.hud_bar, self.hp, self.max_hp, bar_color)


# ─── Cacodemon Boss (Secret Level) ─────────────────────────────────────────────
class CacodemonBoss:
    """Infernal demon boss inspired by DOOM's Cacodemon"""
    def __init__(self, x, y, audio_mgr=None):
        self.audio = audio_mgr
        self.x = float(x)
        self.y = float(y)
        self.width = 80
        self.height = 80
        # vigor=113.33 -> max_hp=360, same 40-hit TTK as before at the
        # player's new stats-driven attack_damage (see game/stats.py).
        self.stats = StatBlock(strength=10, dexterity=0, vigor=113.33, luck=0, weapon_base=3, base_speed=100)
        self.max_hp = self.stats.max_hp
        self.hp = self.max_hp
        self.dmg = self.stats.physical_damage
        self.xp_reward = 300
        self.gold_reward = 120
        self.alive = True

        self.speed = 100
        self.projectiles = []
        self.particles = []
        self.floating_numbers = []
        # No summon pattern of its own, but GameplayState's boss branch
        # (Stage D6) checks every boss for pending_summons unconditionally.
        self.pending_summons = []

        self.attack_timer = 0
        self.attack_interval = 1.5
        self.move_timer = 0
        self.move_dir = (1, 0)
        self.hit_flash = 0
        self.bob_offset = 0  # For hovering animation
        self.bob_timer = 0

        # Humanoid demon rig (Stage B4b) - replaces the old inline
        # floating-sphere drawing in draw(); cached once like Boss's
        # sprite_p1/p2, since it never changes per-frame.
        self.sprite = create_boss_sprite("cacodemon", phase=1)

        self.hp_bar = ProgressBar(self.width, 10, (60,0,0), (220,100,0), border_width=1)
        self.hud_bar = ProgressBar(400, 16, (60,0,0), (255,150,0), border_width=2, margin=2)

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def take_damage(self, amount, dtype="physical", crit=False):
        if self.hit_flash > 0.05:
            return
        defense = self.stats.physical_defense if dtype == "physical" else self.stats.magic_defense
        mitigated = mitigate(amount, defense)
        self.hp -= mitigated
        self.hit_flash = 0.12
        # Stage K6: floating damage number.
        number_color = PHYSICAL_COLOR if dtype == "physical" else MAGIC_COLOR
        self.floating_numbers.append(FloatingNumber(self.x + self.width / 2, self.y, mitigated, number_color))
        # Create damage particles
        particle_color = (255, 215, 0) if crit else (255, 100, 0)
        for _ in range(4):
            angle = random.uniform(0, 2*math.pi)
            speed = random.uniform(150, 250)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.particles.append(
                Particle(self.x + self.width//2, self.y + self.height//2,
                        particle_color)
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
            if self.audio:
                self.audio.play("attack_cacodemon")
            self._shoot_at_player(player)

        # Update projectiles - and check them against the player. This boss
        # was missing this check entirely (unlike Boss/Enemy, which both
        # have it), so it could never actually deal damage; found while
        # wiring the Fogo debuff onto this attack.
        for proj in self.projectiles:
            proj.update(dt, walls)
            if proj.rect.colliderect(player.rect):
                player.take_damage(proj.damage, dtype=proj.dtype)
                if proj.status_effect and random.random() < proj.status_chance:
                    player.status.apply(proj.status_effect)
                proj.alive = False
        self.projectiles = [p for p in self.projectiles if p.alive]

        # Update particles
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        # Stage K6: floating damage numbers
        for n in self.floating_numbers:
            n.update(dt)
        self.floating_numbers = [n for n in self.floating_numbers if n.alive]

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
                            vx, vy, damage=self.dmg, color=(255, 100, 0),
                            status_effect="burn", status_chance=0.15)
            self.projectiles.append(proj)

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y + self.bob_offset)

        demon_surf = self.sprite
        if self.hit_flash > 0.06:
            demo_flash = pygame.Surface(demon_surf.get_size(), pygame.SRCALPHA)
            demo_flash.fill((255, 255, 255))
            demon_surf = demon_surf.copy()
            # BLEND_RGB_ADD, not a plain alpha blit - a plain blit composites
            # this overlay's alpha over the destination's, so a transparent
            # margin pixel (alpha=0) would still end up translucent white
            # (same bug as Boss.draw()'s hit_flash - see its comment).
            # RGB_ADD only touches color channels, leaving alpha untouched.
            demon_surf.blit(demo_flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        # Sprite canvas (96x96) is a bit larger than the hitbox (80x80) -
        # center it over the hitbox instead of top-left aligning, so the
        # bigger humanoid rig doesn't visually drift off to one side.
        ox = (self.width - demon_surf.get_width()) // 2
        oy = (self.height - demon_surf.get_height()) // 2
        surface.blit(demon_surf, (sx + ox, sy + oy))

        # HP bar
        bx = sx
        by = sy - 20
        frac = max(0, self.hp / self.max_hp)
        self.hp_bar.draw(surface, bx, by, frac, (255, 50, 0))

        # Stage K5: name above the HP bar, in-world (see Boss.draw()).
        from game.theme import font, SUBTEXT
        f_name = font(12, bold=True)
        txt = f_name.render("CACODEMON INFERNAL", True, SUBTEXT)
        surface.blit(txt, (bx + self.hp_bar.w // 2 - txt.get_width() // 2, by - 16))

        # Draw projectiles
        for proj in self.projectiles:
            proj.draw(surface, cam_x, cam_y)

        # Draw particles
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)
        for n in self.floating_numbers:
            n.draw(surface, cam_x, cam_y)

    def draw_hud(self, surface, screen_w):
        """Boss HP bar + name, boxed, at the bottom of the screen (Stage G3)."""
        _draw_boss_hud_box(surface, screen_w, "CACODEMON INFERNAL", (255, 100, 0),
                            self.hud_bar, self.hp, self.max_hp, (255, 100, 0))
