import pygame
import math
from game.assets import (
    create_player_sprite, create_projectile_sprite,
    create_spell_icon, create_potion_icon, create_debuff_icon,
    create_sword_icon, create_dash_icon,
)
from game.stats import StatBlock, xp_to_next, MAX_LEVEL, POINTS_PER_LEVEL, mitigate
from game.status_effects import StatusEffectCarrier
from game.professions import determine_profession
from game.spells import SPELLS, ORDER as SPELL_ORDER, meets_requirements, missing_requirements

TILE = 48

# Stage J14: Dash - a DEX-gated mobility/damage move, not part of the
# mana-based SPELLS system (game/spells.py) since it's physical/agility
# themed like attack_cooldown/speed above, not magic - no mana cost, no
# spell_base, gated directly on dexterity instead of SPELLS[...]["req"].
DASH_DEX_REQ = 18
DASH_DURATION = 0.18
DASH_SPEED = 780
DASH_COOLDOWN = 3.5
DASH_TRAIL_LEN = 7

# Stage E2/E3 hotbar - 3 spell slots (keys F/Q/R, already cast this way)
# plus 3 item slots (keys 4/5/6, new). Slot background tint + a real pixel
# icon (Stage F1, game/assets.py's create_spell_icon/create_potion_icon) -
# used to be flat-color boxes + a 2-3 letter abbreviation.
_HOTBAR_SLOT = 36
_HOTBAR_GAP = 6
# Stage G2: extra gap between the spell group and the item group, on top of
# the normal _HOTBAR_GAP within each group - makes the "magias | itens"
# split readable at a glance instead of one undifferentiated row of 6.
_HOTBAR_GROUP_GAP = 16
# Below the top-center "Inimigos: N" / exit-hint text (game/level.py draws
# it at y=12) - the hotbar used to sit right on top of it.
_HOTBAR_Y = 34
# Stage J14 hotbar remap: F is melee attack (new slot, was unbound in the
# hotbar), R is now Fireball (was F), Q stays Nova de Gelo, X is now Luz
# Curativa (was R - freed up so R could become Fireball), 1/2/3 are the
# potions (were 4/5/6), SPC is the new Dash spell (was plain ATTACK on
# Space). Order matches hotbar_slots() below: attack, then SPELL_ORDER's
# fixed fireball/frost_nova/healing_light, then the 3 items, then dash.
_HOTBAR_KEYS = ["F", "R", "Q", "X", "1", "2", "3", "SPC"]
# Stage G1: slot background is always black (contrast for the icon, not a
# per-spell/item tint) - the old _SPELL_COLOR/_ITEM_COLOR dicts are gone,
# nothing else read them.
_HOTBAR_BOX_COLOR = (15, 15, 18)


def hotbar_slots():
    """[(kind, id, rect), ...] for all hotbar slots - a fixed layout derived
    only from SPELL_ORDER/ITEMS and screen width, not from any Player
    instance, so GameplayState's tap handling and Player's own drawing
    always agree on the exact same rects without either side needing to
    own the other's state. Groups (attack, spells, items, dash) separated
    by _HOTBAR_GROUP_GAP (Stage G2), left to right.

    Stage J14: "attack" (melee, key F) and "dash" (key SPACE) are new
    single-slot groups bookending the original spell/item groups - neither
    is keyed off SPELL_ORDER/ITEMS (there's exactly one of each), so `key`
    is None for both; _draw_hotbar below branches on `kind` instead."""
    from game.theme import SW
    from game.items import ITEMS
    spell_ids = [("spell", s) for s in SPELL_ORDER]
    item_ids = [("item", i) for i in ITEMS]
    attack_w = _HOTBAR_SLOT
    spell_w = len(spell_ids) * _HOTBAR_SLOT + (len(spell_ids) - 1) * _HOTBAR_GAP
    item_w = len(item_ids) * _HOTBAR_SLOT + (len(item_ids) - 1) * _HOTBAR_GAP
    dash_w = _HOTBAR_SLOT
    total_w = attack_w + _HOTBAR_GROUP_GAP + spell_w + _HOTBAR_GROUP_GAP + item_w + _HOTBAR_GROUP_GAP + dash_w
    x0 = SW // 2 - total_w // 2
    slots = [("attack", None, pygame.Rect(x0, _HOTBAR_Y, _HOTBAR_SLOT, _HOTBAR_SLOT))]
    spell_x0 = x0 + attack_w + _HOTBAR_GROUP_GAP
    for i, (kind, key) in enumerate(spell_ids):
        x = spell_x0 + i * (_HOTBAR_SLOT + _HOTBAR_GAP)
        slots.append((kind, key, pygame.Rect(x, _HOTBAR_Y, _HOTBAR_SLOT, _HOTBAR_SLOT)))
    item_x0 = spell_x0 + spell_w + _HOTBAR_GROUP_GAP
    for i, (kind, key) in enumerate(item_ids):
        x = item_x0 + i * (_HOTBAR_SLOT + _HOTBAR_GAP)
        slots.append((kind, key, pygame.Rect(x, _HOTBAR_Y, _HOTBAR_SLOT, _HOTBAR_SLOT)))
    dash_x0 = item_x0 + item_w + _HOTBAR_GROUP_GAP
    slots.append(("dash", None, pygame.Rect(dash_x0, _HOTBAR_Y, _HOTBAR_SLOT, _HOTBAR_SLOT)))
    return slots

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
        self.selected_spell = SPELL_ORDER[0]
        self.spell_cooldowns = {}
        # Pity counter for game/affixes.py's Paragon roll - not persisted
        # (it's a short-lived streak-breaker, not meaningful progress).
        self.paragon_pity = 0
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
        # Stage F9: raw XP earned, never reset by a level-up (unlike
        # self.xp, which rolls back over on every level-up threshold) - lets
        # GameplayState snapshot this at level start and diff it at level
        # end for the stage-complete screen's "XP ganho" figure.
        self.xp_earned_total = 0

        self.attacking = False
        self.attack_timer = 0
        self.attack_duration = 0.25
        self.attack_cooldown = 0
        self.attack_range = 60

        # Stage J14: Dash - see DASH_* constants above the class for tuning.
        # dash_trail holds recent (x, y, direction) snapshots for the fading
        # ghost effect (Player.draw() below); _dash_hit_ids is per-activation
        # (cleared in try_dash()) so a single dash only damages each enemy
        # once even though contact is checked every frame it's moving.
        self.dashing = False
        self.dash_timer = 0.0
        self.dash_cooldown = 0.0
        self.dash_dx, self.dash_dy = 0.0, 1.0
        self.dash_trail = []
        self._dash_hit_ids = set()

        self.invincible = False
        self.invincible_timer = 0
        self.invincible_duration = 1.0
        self.flash_timer = 0
        # Debug-only persistent invincibility (game/debug_panel.py's "Modo
        # Deus" row) - deliberately separate from `invincible` above, which
        # is a short i-frame window after a hit, not a toggle. Never
        # persisted (game/save.py) - always False on a fresh/loaded Player.
        self.debug_invincible = False

        self.direction = "down"  # up/down/left/right

        # Stage J13: continuous aim vector for mouse-aimed combat (PC) /
        # touch-drag aim (mobile) - independent of movement. Used by
        # get_attack_rect() and GameplayState._cast_fireball() for the real
        # angle; self.direction above stays quantized to the 4 sprite poses
        # (set_aim() below keeps both in sync from the same vector).
        self.aim_dx, self.aim_dy = 0.0, 1.0

        # Per-profession individualization pass: each profession is now its
        # own rig (game/assets.py's PLAYER_SPRITES/_PLAYER_RIG_PAINTERS), not
        # a color multiply over one shared silhouette - so sprites are built
        # lazily per (direction, attacking, profession) and cached, instead
        # of 8 fixed surfaces built once at construction and re-tinted.
        self.slash_sprite = create_projectile_sprite("slash")
        self._sprite_cache = {}
        # Set by GameplayState.__init__ from the level's WeatherSystem
        # (Stage D5) - a plain float, not a StatusEffectCarrier entry,
        # since it's tied to standing in a level rather than a
        # duration/tick-based debuff.
        self.weather_speed_mult = 1.0

    @property
    def display_name(self):
        """Stage G7/G8: first letter capitalized, rest left as typed (not
        `.capitalize()`, which would also lowercase the rest of the name) -
        shared by the HUD title line and the paperdoll header so both
        capitalize the same way instead of duplicating the rule."""
        if not self.name:
            return "Heroi"
        return self.name[0].upper() + self.name[1:]

    @property
    def speed(self):
        return self.stats.speed * self.status.speed_multiplier * self.weather_speed_mult

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
        self.xp_earned_total += amount
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

    def can_cast(self, spell_id):
        spell = SPELLS[spell_id]
        return (meets_requirements(self.stats, spell_id)
                and self.spell_cooldowns.get(spell_id, 0) <= 0
                and self.mana >= spell["mana_cost"])

    def try_cast(self, spell_id):
        """Deducts mana/sets cooldown and returns True if the cast is valid -
        same split as try_attack(): Player only manages its own state, the
        caller (GameplayState) is responsible for the actual effect (fireball
        projectile / frost nova AoE / heal), same as level.py owns melee hit
        detection instead of Player."""
        if not self.can_cast(spell_id):
            return False
        spell = SPELLS[spell_id]
        self.mana -= spell["mana_cost"]
        # Haste (Destreza) speeds up spell cooldowns the same way it speeds
        # up melee attack_cooldown - one stat for "attack speed" and "cast
        # speed" instead of a second, parallel system.
        self.spell_cooldowns[spell_id] = spell["cooldown"] * (1 - self.stats.haste)
        return True

    @property
    def rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def set_aim(self, dx, dy):
        """Stage J13: normalizes (dx, dy) into aim_dx/aim_dy (used for the
        real attack/fireball angle) and quantizes it into self.direction
        (one of the 4 sprite poses), same vector driving both."""
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return
        self.aim_dx, self.aim_dy = dx / dist, dy / dist
        if abs(dx) >= abs(dy):
            self.direction = "right" if dx > 0 else "left"
        else:
            self.direction = "down" if dy > 0 else "up"

    def get_attack_rect(self):
        # Stage J13: was 4 fixed axis-aligned strips keyed off self.direction
        # - now a square hitbox pushed out from the player's center along
        # the continuous aim_dx/aim_dy vector, so a diagonal aim actually
        # reaches diagonally instead of snapping to one of 4 strips. Sizing
        # (max(width, height) side, centered attack_range/2 + size/2 beyond
        # the player) matches the old cardinal cases closely at dx/dy=(±1,0)
        # or (0,±1).
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        size = max(self.width, self.height)
        offset = size / 2 + self.attack_range / 2
        center_x = cx + self.aim_dx * offset
        center_y = cy + self.aim_dy * offset
        return pygame.Rect(center_x - size / 2, center_y - size / 2, size, size)

    def take_damage(self, amount, dtype="physical"):
        if self.invincible or self.debug_invincible:
            return
        defense = self.stats.physical_defense if dtype == "physical" else self.stats.magic_defense
        amount = mitigate(amount, defense)
        self.hp -= amount * self.status.damage_taken_multiplier
        self.invincible = True
        self.invincible_timer = self.invincible_duration
        self.audio.play("hurt")

    def update(self, dt, walls, movement_vector):
        self.mana = min(self.max_mana, self.mana + self.stats.mana_regen * dt)
        self.hp = min(self.max_hp, self.hp + self.stats.hp_regen * dt)

        for spell_id in list(self.spell_cooldowns):
            self.spell_cooldowns[spell_id] = max(0.0, self.spell_cooldowns[spell_id] - dt)

        # DoT ticks (Veneno/Fogo) go straight to hp, bypassing take_damage -
        # they shouldn't be blocked by melee-hit invincibility frames, and
        # shouldn't themselves grant any.
        tick_dmg = self.status.update(dt)
        if tick_dmg and not self.debug_invincible:
            self.hp -= tick_dmg

        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt

        if self.dashing:
            # Stage J14: dash overrides WASD movement entirely for its short
            # duration - same "one committed motion" feel as the attack
            # animation, not a speed boost layered on top of steering.
            self.dash_timer -= dt
            self.dash_trail.append((self.x, self.y, self.direction))
            if len(self.dash_trail) > DASH_TRAIL_LEN:
                self.dash_trail.pop(0)
            self.x += self.dash_dx * DASH_SPEED * dt
            self._resolve_collisions_x(walls)
            self.y += self.dash_dy * DASH_SPEED * dt
            self._resolve_collisions_y(walls)
            if self.dash_timer <= 0:
                self.dashing = False
        else:
            dx, dy = movement_vector

            # Horizontal facing wins over vertical when both are held
            # (matches the original WASD priority order).
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

    def can_dash(self):
        return (self.stats.dexterity >= DASH_DEX_REQ
                and self.dash_cooldown <= 0 and not self.dashing)

    def try_dash(self):
        """Stage J14: dashes along the current aim_dx/aim_dy vector (mouse
        angle on PC, drag-aim on mobile - same source J13 already set up),
        multidirectional by design per the user's ask. Contact damage
        against enemies/boss is resolved by the caller (GameplayState),
        matching the existing split where Player never owns combat
        resolution - see get_attack_rect()/try_attack() above."""
        if not self.can_dash():
            return False
        self.dashing = True
        self.dash_timer = DASH_DURATION
        self.dash_dx, self.dash_dy = self.aim_dx, self.aim_dy
        self.dash_cooldown = DASH_COOLDOWN
        self.dash_trail = []
        self._dash_hit_ids = set()
        self.audio.play("attack")
        return True

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

    def _get_sprite(self, key):
        # Cached per (key, profession, god mode) - each profession is its
        # own rig now (game/assets.py's create_player_sprite(...,
        # profession=...)), so switching build/profession must rebuild, not
        # just re-tint. Stage J7: god mode overrides profession entirely
        # with a fixed "Super Sayajin" costume - included in the cache key
        # (not just passed through) so toggling debug_invincible off
        # doesn't keep serving the transformed sprite from cache.
        # Accumulates at most 8 sprites x every profession/mode combo the
        # player has had this run, trivial for pygame.Surface objects this
        # small.
        god_mode = self.debug_invincible
        cache_key = (key, self.profession, god_mode)
        cached = self._sprite_cache.get(cache_key)
        if cached is None:
            attacking = key.endswith("_atk")
            direction = key[:-4] if attacking else key
            cached = create_player_sprite(direction, attacking, self.profession, super_saiyan=god_mode)
            self._sprite_cache[cache_key] = cached
        return cached

    def draw(self, surface, cam_x, cam_y):
        # Flash when invincible
        if self.invincible and int(self.flash_timer * 8) % 2 == 0:
            return

        if self.dash_trail:
            self._draw_dash_trail(surface, cam_x, cam_y)

        key = self.direction
        if self.attacking:
            key = self.direction + "_atk"

        sprite = self._get_sprite(key)
        # Flip left
        if self.direction == "left":
            sprite = pygame.transform.flip(self._get_sprite("right_atk" if self.attacking else "right"), True, False)

        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        surface.blit(sprite, (sx - 8, sy - 12))

    def _draw_dash_trail(self, surface, cam_x, cam_y):
        """Stage J14: a short fading "ghost" trail behind the hero during a
        dash - each dash_trail entry is a past (x, y, direction) snapshot,
        drawn oldest-to-newest with increasing alpha via a per-copy
        set_alpha() (same principle as a mouse-cursor trail), so the dash
        reads as a fast, deliberate streak rather than a plain teleport."""
        n = len(self.dash_trail)
        for i, (tx, ty, tdir) in enumerate(self.dash_trail):
            ghost = self._get_sprite(tdir)
            if tdir == "left":
                ghost = pygame.transform.flip(self._get_sprite("right"), True, False)
            ghost = ghost.copy()
            ghost.set_alpha(int(160 * (i + 1) / n))
            gx = int(tx - cam_x)
            gy = int(ty - cam_y)
            surface.blit(ghost, (gx - 8, gy - 12))

    def draw_hud(self, surface, save_state=None, touch_active=False):
        # HP/mana/XP bars - stats.py's bigger hp range (see Stage A3) no
        # longer maps cleanly onto discrete heart icons, so it's bars like
        # bosses already use.
        from game.ui import ProgressBar
        from game.theme import font, ACCENT_GOLD
        if not hasattr(self, "_hp_bar"):
            self._hp_bar = ProgressBar(160, 16, (60, 0, 0), (220, 220, 220), border_width=2)
            self._mana_bar = ProgressBar(160, 10, (0, 0, 50), (180, 180, 220), border_width=2)
            self._xp_bar = ProgressBar(160, 6, (40, 40, 40), (140, 140, 140), border_width=1)

        # Stage F5/G7: reputation + profession + name, above the bars.
        # Pushes the whole dock down to make room for the bigger G7 font
        # instead of overlapping it.
        self._draw_title_line(surface, save_state)
        dock_y = 42

        hp_frac = max(0.0, self.hp / self.max_hp)
        self._hp_bar.draw(surface, 12, dock_y, hp_frac, (220, 40, 40))

        mana_frac = max(0.0, self.mana / self.max_mana)
        self._mana_bar.draw(surface, 12, dock_y + 20, mana_frac, (60, 110, 230))

        self._xp_bar.draw(surface, 12, dock_y + 34, self.xp_frac, ACCENT_GOLD)

        f = font(16, bold=True)
        lvl_txt = f.render(f"Lv {self.level}", True, ACCENT_GOLD)
        surface.blit(lvl_txt, (178, dock_y))

        gold_txt = f.render(f"{self.gold}g", True, (230, 200, 80))
        surface.blit(gold_txt, (178, dock_y + 20))

        self._draw_status_chips(surface, dock_y + 46)
        self._draw_hotbar(surface, touch_active)

    def _draw_title_line(self, surface, save_state):
        # Stage G7: "Reputacao Profissao Nome", same style as the hero name
        # in the paperdoll header (game/paperdoll.py's _draw_header - 24pt
        # bold ACCENT_GOLD), 2px smaller. Nudged a few px off the top edge
        # (Stage H11) - it used to sit flush at y=0.
        from game.theme import font, ACCENT_GOLD
        from game.reputation import determine_reputation, kills_total, deaths_total
        reputation = determine_reputation(kills_total(self, save_state), deaths_total(save_state))
        text = f"{reputation} {self.profession} {self.display_name}"
        f = font(22, bold=True)
        txt_surf = f.render(text, True, ACCENT_GOLD)
        shadow = f.render(text, True, (0, 0, 0))
        surface.blit(shadow, (13, 7))
        surface.blit(txt_surf, (12, 6))

    def _draw_hotbar(self, surface, touch_active=False):
        from game.theme import font, ACCENT_GOLD
        from game.items import ITEMS
        f_key = font(11, bold=True)
        f_count = font(11, bold=True)
        for i, (kind, key, rect) in enumerate(hotbar_slots()):
            # Stage H10: on touch devices, both spell casting and item use
            # have their own dedicated button rows next to the joystick
            # (game/input_system.py's spell_buttons/item_buttons), so the
            # top hotbar slots for both kinds would just be smaller,
            # harder-to-tap duplicates - skip drawing them entirely.
            if touch_active:
                continue
            on_cooldown = False
            if kind == "spell":
                locked = bool(missing_requirements(self.stats, key))
                on_cooldown = self.spell_cooldowns.get(key, 0) > 0
                affordable = self.mana >= SPELLS[key]["mana_cost"]
                usable = not locked and not on_cooldown and affordable
                icon = create_spell_icon(key)
                selected = self.selected_spell == key
            elif kind == "item":
                count = self.inventory.get(key, 0)
                usable = count > 0
                icon = create_potion_icon(key)
                selected = False
            elif kind == "attack":
                usable = self.attack_cooldown <= 0
                icon = create_sword_icon()
                selected = False
            else:  # kind == "dash"
                on_cooldown = self.dash_cooldown > 0
                usable = self.stats.dexterity >= DASH_DEX_REQ and not on_cooldown
                icon = create_dash_icon()
                selected = False

            pygame.draw.rect(surface, _HOTBAR_BOX_COLOR, rect, border_radius=6)
            pygame.draw.rect(surface, (230, 230, 235) if usable else (90, 90, 95), rect, 2, border_radius=6)
            if selected:
                pygame.draw.rect(surface, ACCENT_GOLD, rect.inflate(4, 4), 2, border_radius=8)

            icon_x = rect.centerx - icon.get_width() // 2
            icon_y = rect.centery - icon.get_height() // 2
            surface.blit(icon, (icon_x, icon_y))
            if not usable:
                dim = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 130))
                surface.blit(dim, (icon_x, icon_y))

            key_surf = f_key.render(_HOTBAR_KEYS[i], True, (255, 255, 255))
            key_bg = pygame.Rect(rect.x - 2, rect.y - 2, key_surf.get_width() + 4, key_surf.get_height() + 2)
            pygame.draw.rect(surface, (20, 20, 30), key_bg, border_radius=3)
            surface.blit(key_surf, (key_bg.x + 2, key_bg.y + 1))

            if kind == "spell" and on_cooldown:
                cd_frac = min(1.0, self.spell_cooldowns[key] / SPELLS[key]["cooldown"]) if SPELLS[key]["cooldown"] else 1.0
                wipe_h = int(rect.height * cd_frac)
                wipe = pygame.Surface((rect.width, wipe_h), pygame.SRCALPHA)
                wipe.fill((0, 0, 0, 160))
                surface.blit(wipe, (rect.x, rect.bottom - wipe_h))
            elif kind == "dash" and on_cooldown:
                cd_frac = min(1.0, self.dash_cooldown / DASH_COOLDOWN)
                wipe_h = int(rect.height * cd_frac)
                wipe = pygame.Surface((rect.width, wipe_h), pygame.SRCALPHA)
                wipe.fill((0, 0, 0, 160))
                surface.blit(wipe, (rect.x, rect.bottom - wipe_h))
            elif kind == "item":
                count = self.inventory.get(key, 0)
                # Stage G1: inverted from the old dark-bg/white-text badge -
                # white bg/black text reads better against the now-black
                # slot background than a same-tone dark badge did.
                count_surf = f_count.render(str(count), True, (20, 20, 25))
                cbg = pygame.Rect(rect.right - count_surf.get_width() - 4, rect.bottom - count_surf.get_height() - 2,
                                   count_surf.get_width() + 4, count_surf.get_height() + 2)
                pygame.draw.rect(surface, (245, 245, 248), cbg, border_radius=3)
                surface.blit(count_surf, (cbg.x + 2, cbg.y + 1))

    def _draw_status_chips(self, surface, y=58):
        # Debuff indicator row, below the HP/mana/XP dock - not optional
        # polish: Poison/Slow/Weakness last ~12s each and have no other
        # on-screen cue, so without this the player has no way to tell
        # why they're sluggish or bleeding hp.
        from game.status_effects import STATUS_DISPLAY
        if not self.status.active:
            return
        x = 12
        for effect_id in self.status.active:
            _, color = STATUS_DISPLAY.get(effect_id, (effect_id[:3].upper(), (200, 200, 200)))
            chip = pygame.Surface((36, 18), pygame.SRCALPHA)
            chip.fill((*color, 70))
            pygame.draw.rect(chip, color, (0, 0, 36, 18), 1)
            surface.blit(chip, (x, y))
            icon = create_debuff_icon(effect_id)
            surface.blit(icon, (x + 18 - icon.get_width() // 2, y + 9 - icon.get_height() // 2))
            x += 40
