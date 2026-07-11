import pygame
import math
from game.assets import create_player_sprite, create_projectile_sprite
from game.stats import StatBlock, xp_to_next, MAX_LEVEL, POINTS_PER_LEVEL
from game.status_effects import StatusEffectCarrier
from game.professions import determine_profession

TILE = 48

class Player:
    def __init__(self, x, y, audio_mgr):
        self.x = float(x)
        self.y = float(y)
        self.audio = audio_mgr
        self.stats = StatBlock(strength=10, dexterity=10, intelligence=10,
                                wisdom=10, vigor=10, weapon_base=4, base_speed=190)
        self.hp = self.max_hp
        self.mana = self.stats.max_mana
        self.width = 32
        self.height = 36

        self.name = ""
        self.level = 1
        self.xp = 0
        self.unspent_points = 0
        self.gold = 0
        self.inventory = {}
        self.status = StatusEffectCarrier()
        self.profession = determine_profession(self.stats)
        # Set by refresh_profession() when spending/respec-ing points changes
        # the derived profession; GameplayState reads and clears it each
        # frame to trigger a toast (same pattern as pending_level_up below).
        self.pending_profession_change = None
        # In-run kill tallies; GameStateManager merges these into the
        # persisted save (game/save.py's sync_counters) and resets them.
        self.kills = {}
        self.boss_kills = {}
        # Set by gain_xp() when a kill crosses a level threshold; GameplayState
        # reads and clears it each frame to trigger the fanfare (it owns the
        # camera/particles gain_xp() has no access to).
        self.pending_level_up = 0

        self.attacking = False
        self.attack_timer = 0
        self.attack_duration = 0.25
        self.attack_cooldown = 0
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
    def speed(self):
        return self.stats.speed * self.status.speed_multiplier

    @property
    def max_hp(self):
        return self.stats.max_hp

    @property
    def attack_damage(self):
        return self.stats.physical_damage

    @property
    def max_mana(self):
        return self.stats.max_mana

    @property
    def xp_frac(self):
        if self.level >= MAX_LEVEL:
            return 1.0
        return self.xp / xp_to_next(self.level)

    def gain_xp(self, amount):
        if self.level >= MAX_LEVEL:
            return
        self.xp += amount
        while self.level < MAX_LEVEL and self.xp >= xp_to_next(self.level):
            self.xp -= xp_to_next(self.level)
            self.level += 1
            self.unspent_points += POINTS_PER_LEVEL
            self.pending_level_up += 1

    def use_item(self, item_id):
        from game.items import use_item as _use_item
        return _use_item(self, item_id)

    def refresh_profession(self):
        """Called after spending/respec-ing points (game/paperdoll.py) -
        profession is derived, not stored, so this just recomputes it."""
        new_profession = determine_profession(self.stats)
        if new_profession != self.profession:
            self.profession = new_profession
            self.pending_profession_change = new_profession

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
        self.hp -= amount * self.status.damage_taken_multiplier
        self.invincible = True
        self.invincible_timer = self.invincible_duration
        self.audio.play("hurt")

    def update(self, dt, walls, movement_vector):
        self.mana = min(self.max_mana, self.mana + self.stats.mana_regen * dt)

        # DoT ticks (Veneno/Fogo) go straight to hp, bypassing take_damage -
        # they shouldn't be blocked by melee-hit invincibility frames, and
        # shouldn't themselves grant any.
        tick_dmg = self.status.update(dt)
        if tick_dmg:
            self.hp -= tick_dmg

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
            self.attack_cooldown = self.stats.attack_cooldown
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
        # HP/mana/XP bars - stats.py's bigger hp range (see Stage A3) no
        # longer maps cleanly onto discrete heart icons, so it's bars like
        # bosses already use.
        from game.ui import ProgressBar
        from game.theme import font, ACCENT_GOLD
        if not hasattr(self, "_hp_bar"):
            self._hp_bar = ProgressBar(160, 16, (60, 0, 0), (220, 220, 220), border_width=2)
            self._mana_bar = ProgressBar(160, 10, (0, 0, 50), (180, 180, 220), border_width=2)
            self._xp_bar = ProgressBar(160, 6, (40, 40, 40), (140, 140, 140), border_width=1)

        hp_frac = max(0.0, self.hp / self.max_hp)
        self._hp_bar.draw(surface, 12, 12, hp_frac, (220, 40, 40))

        mana_frac = max(0.0, self.mana / self.max_mana)
        self._mana_bar.draw(surface, 12, 32, mana_frac, (60, 110, 230))

        self._xp_bar.draw(surface, 12, 46, self.xp_frac, ACCENT_GOLD)

        f = font(16, bold=True)
        lvl_txt = f.render(f"Lv {self.level}", True, ACCENT_GOLD)
        surface.blit(lvl_txt, (178, 12))

        gold_txt = f.render(f"{self.gold}g", True, (230, 200, 80))
        surface.blit(gold_txt, (178, 32))

        self._draw_status_chips(surface)

    def _draw_status_chips(self, surface):
        # Debuff indicator row, below the HP/mana/XP dock - not optional
        # polish: Poison/Slow/Weakness last ~12s each and have no other
        # on-screen cue, so without this the player has no way to tell
        # why they're sluggish or bleeding hp.
        from game.status_effects import STATUS_DISPLAY
        from game.theme import font
        if not self.status.active:
            return
        f = font(13, bold=True)
        x = 12
        for effect_id in self.status.active:
            label, color = STATUS_DISPLAY.get(effect_id, (effect_id[:3].upper(), (200, 200, 200)))
            chip = pygame.Surface((36, 18), pygame.SRCALPHA)
            chip.fill((*color, 70))
            pygame.draw.rect(chip, color, (0, 0, 36, 18), 1)
            surface.blit(chip, (x, 58))
            txt = f.render(label, True, color)
            surface.blit(txt, (x + 18 - txt.get_width() // 2, 58 + 2))
            x += 40
