import pygame
import math
from game.assets import (
    create_player_sprite, create_projectile_sprite,
    create_spell_icon, create_potion_icon, create_debuff_icon,
    create_sword_icon, create_dash_icon, create_stance_icon,
    create_pickaxe_icon,
)
from game.stats import StatBlock, xp_to_next, MAX_LEVEL, POINTS_PER_LEVEL, mitigate
from game.status_effects import StatusEffectCarrier
from game.professions import determine_profession
from game.spells import SPELLS, ORDER as SPELL_ORDER, meets_requirements, missing_requirements
from game.combat_fx import (
    FloatingNumber, PHYSICAL_COLOR, MAGIC_COLOR, DOT_COLOR,
    knockback_vector, KNOCKBACK_DURATION,
)
from game.stances import stance_multiplier, stance_bonus, all_stances_multiplier, all_stances_bonus

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

# Stage K14: Picareta - no attribute gate (unlike Dash's DEX_REQ), any
# profession can dig; the cooldown is the only pacing knob per the user's
# spec ("cooldown de 1s").
PICKAXE_COOLDOWN = 1.0

# Stage K23: how long the "found the key" pose holds before normal control
# returns - long enough to read as a deliberate beat, short enough not to
# feel like a lockout on a hazardous floor.
KEY_POSE_DURATION = 1.4

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
# Stage K7: moved up close to the top edge - the "Inimigos: N" counter
# that used to occupy this top-center spot (game/level.py) is gone, so the
# hotbar no longer needs to sit below it.
_HOTBAR_Y = 6
# Stage K1: reverted Stage J14's remap - SPACE is melee attack again, F is
# Fireball again, Q stays Nova de Gelo, R is Luz Curativa again, 1/2/3 are
# still the potions, and Dash (new in J14, didn't exist pre-J14) moved to
# X since Space went back to attack. Order matches hotbar_slots() below:
# attack, then SPELL_ORDER's fixed fireball/frost_nova/healing_light, then
# up to 3 items, then dash. (Key labels themselves are now derived per-kind
# in _draw_hotbar, Stage K12 - see that method's comment.)
# Stage G1: slot background is always black (contrast for the icon, not a
# per-spell/item tint) - the old _SPELL_COLOR/_ITEM_COLOR dicts are gone,
# nothing else read them.
_HOTBAR_BOX_COLOR = (15, 15, 18)


def hotbar_slots(player):
    """[(kind, id, rect), ...] for all hotbar slots - a fixed layout derived
    from SPELL_ORDER/player.hotbar_items and screen width. Groups (attack,
    spells, items, dash, pickaxe) separated by _HOTBAR_GROUP_GAP (Stage G2),
    left to right.

    Stage J14: "attack" (melee, key F) and "dash" (key SPACE) are new
    single-slot groups bookending the original spell/item groups - neither
    is keyed off SPELL_ORDER/ITEMS (there's exactly one of each), so `key`
    is None for both; _draw_hotbar below branches on `kind` instead.

    Stage K12: ITEMS grew from 3 to ~25 entries (new potions/elixirs), so
    this can no longer iterate ITEMS wholesale - the item group now shows
    only `player.hotbar_items` (max 3, picked in the Items overlay), same
    shape as before for anyone who hasn't touched the new selection UI.

    Stage K22: "pickaxe" is a new trailing bookend after dash - it existed
    as a keybind (game/keybinds.py's PICKAXE) since Stage K14 but was never
    actually visible anywhere in the hotbar, same None-key/kind-branch shape
    as attack/dash above."""
    from game.theme import SW
    spell_ids = [("spell", s) for s in SPELL_ORDER]
    item_ids = [("item", i) for i in player.hotbar_items]
    attack_w = _HOTBAR_SLOT
    spell_w = len(spell_ids) * _HOTBAR_SLOT + (len(spell_ids) - 1) * _HOTBAR_GAP
    item_w = len(item_ids) * _HOTBAR_SLOT + (len(item_ids) - 1) * _HOTBAR_GAP
    dash_w = _HOTBAR_SLOT
    pickaxe_w = _HOTBAR_SLOT
    total_w = (attack_w + _HOTBAR_GROUP_GAP + spell_w + _HOTBAR_GROUP_GAP + item_w
               + _HOTBAR_GROUP_GAP + dash_w + _HOTBAR_GROUP_GAP + pickaxe_w)
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
    pickaxe_x0 = dash_x0 + dash_w + _HOTBAR_GROUP_GAP
    slots.append(("pickaxe", None, pygame.Rect(pickaxe_x0, _HOTBAR_Y, _HOTBAR_SLOT, _HOTBAR_SLOT)))
    return slots


def _item_tooltip_line(item_id):
    """Stage K8: ITEMS (game/items.py) has no stored description field -
    this reads the same effect keys use_item() branches on and turns them
    into one objective-numbers sentence, so a new potion just works here
    without also needing hand-written tooltip text kept in sync."""
    from game.items import ITEMS
    item = ITEMS[item_id]
    parts = []
    if "heal_hp_frac" in item:
        parts.append(f"Cura {round(item['heal_hp_frac'] * 100)}% da vida")
    if "heal_mana_frac" in item:
        parts.append(f"Restaura {round(item['heal_mana_frac'] * 100)}% da mana")
    if "cures" in item:
        parts.append("Cura: " + ", ".join(sorted(item["cures"])))
    if "buff" in item:
        from game.status_effects import STATUS_HELP
        _, desc = STATUS_HELP.get(item["buff"], (item["buff"], ""))
        parts.append(desc)
    return " | ".join(parts) if parts else ""


class Player:
    def __init__(self, x, y, audio_mgr):
        self.x = float(x)
        self.y = float(y)
        self.audio = audio_mgr
        self.stats = StatBlock(strength=10, dexterity=10, intelligence=10,
                                wisdom=10, vigor=10, weapon_base=4, base_speed=190)
        # Stage K10/K11: status and profession must both exist before the
        # max_hp/max_mana property reads below - they go through
        # self._mult(), which reads self.status *and* (via
        # stance_multiplier()) self.profession. Moved up from their old
        # spots further down (order never mattered before this).
        self.status = StatusEffectCarrier()
        self.profession = determine_profession(self.stats)
        # Stage K13: stance_multiplier()/_bonus() (called by the max_hp read
        # right below) check this flag too - same construction-order class
        # of bug as status/profession above, so it moves up here with them.
        self.debug_all_stances = False
        self.hp = self.max_hp
        self.mana = self.max_mana
        self.width = 32
        self.height = 36

        self.name = ""
        self.level = 1
        self.xp = 0
        self.unspent_points = 0
        self.gold = 0
        self.inventory = {}
        # Stage K12: which item ids show up in the hotbar's item group (max
        # 3, enforced by merchant.py's toggle UI, not here) - defaults to
        # the original 3 potions so a player who never opens "SEUS ITENS"
        # sees the exact hotbar the game always had.
        self.hotbar_items = ["health_potion", "mana_potion", "antidote"]
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

        # Stage K14: Picareta - see PICKAXE_COOLDOWN below. Purely a cooldown
        # gate; the actual "what's in front of the player" tile logic lives
        # in Level (GameplayState._attempt_pickaxe() bridges the two), same
        # split try_attack()/get_attack_rect() already established.
        self.pickaxe_cooldown = 0.0

        # Stage K23: the "found the hidden key" pose - turns to face the
        # camera and holds the key overhead for KEY_POSE_DURATION (see
        # trigger_key_found_pose()/update()/draw() below), same "temporary
        # state overrides normal movement" shape as dashing/knockback.
        self.key_pose_timer = 0.0

        self.floating_numbers = []  # Stage K6

        # Stage K9: knockback - a short window where movement_vector-driven
        # input is suppressed and this velocity takes over instead, same
        # "temporary state overrides normal movement" shape as dashing
        # above (see update() below for how the two interact).
        self.knockback_vx, self.knockback_vy, self.knockback_timer = 0.0, 0.0, 0.0

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

    def stance_multiplier(self, field):
        """Stage K11: a Postura is permanent (tied to self.profession, never
        expires) so it's deliberately NOT part of self.status
        (StatusEffectCarrier, timed-only) - this reads game/stances.py's
        STANCES registry instead, keyed by whatever profession is currently
        derived (same "derived, not stored" shape self.profession itself
        already uses - a respec that changes profession changes the active
        Postura for free, no special-case code needed).

        Stage K13: debug_all_stances short-circuits to every Postura
        combined (game/debug_panel.py's "Todas as posturas" toggle) -
        checked here instead of at each of the ~15 call sites so it applies
        uniformly regardless of which stat property triggered the read."""
        if self.debug_all_stances:
            return all_stances_multiplier(field)
        return stance_multiplier(self.profession, field)

    def stance_bonus(self, field):
        """Additive counterpart to stance_multiplier() above."""
        if self.debug_all_stances:
            return all_stances_bonus(field)
        return stance_bonus(self.profession, field)

    def _mult(self, field):
        """Combined timed-buff x permanent-Postura multiplier for one
        StatusEffectDef field - the one place every stat property below
        reads through, so a new debuff (game/status_effects.py), potion
        (Stage K12), or Postura (game/stances.py) all "just work" without
        any of these properties changing again."""
        return self.status.multiplier(field) * self.stance_multiplier(field)

    def _bonus(self, field):
        return self.status.bonus(field) + self.stance_bonus(field)

    @property
    def speed(self):
        return (self.stats.speed * self.status.speed_multiplier
                * self.stance_multiplier("speed_mult") * self.weather_speed_mult)

    @property
    def dodge_chance(self):
        """Stage K11: a wholly new mechanic (no potion/debuff grants this
        today, only Duelista's Postura) - rolled once per incoming hit in
        take_damage() below, same "block outright" shape enemy.py's
        'warded' affix already uses for a monster-side dodge-alike."""
        return self._bonus("dodge_chance_add")

    @property
    def max_hp(self):
        return self.stats.max_hp * self._mult("max_hp_mult")

    @property
    def attack_damage(self):
        return self.stats.physical_damage * self._mult("physical_damage_mult")

    def magic_damage(self, spell_base):
        return round(self.stats.magic_damage(spell_base) * self._mult("magic_damage_mult"))

    def roll_physical(self):
        """Player-level reimplementation of StatBlock.roll_physical() (not
        a thin delegate to it) - crit chance needs to read this class's own
        `crit_chance` property (which adds crit_chance_add on top of
        StatBlock's luck-derived base), and damage needs physical_damage_mult,
        neither of which StatBlock.roll_physical() knows about. Every melee/
        dash hit (game/level.py, game/states.py) should call this instead of
        `player.stats.roll_physical()` to get Postura/potion bonuses."""
        import random
        is_crit = random.random() < self.crit_chance
        dmg = self.attack_damage
        if is_crit:
            dmg = round(dmg * self.stats.crit_damage_mult)
        return dmg, is_crit

    @property
    def physical_defense(self):
        return self.stats.physical_defense * self._mult("physical_defense_mult")

    @property
    def magic_defense(self):
        return self.stats.magic_defense * self._mult("magic_defense_mult")

    @property
    def crit_chance(self):
        return min(0.60, self.stats.crit_chance + self._bonus("crit_chance_add"))

    @property
    def hp_regen(self):
        # Stage K12: hp_regen_mult (Pocao Rosa) multiplies the base regen,
        # same shape mana_regen_mult already had below - hp_regen_flat_pct
        # (Postura layer) stays a separate additive term, same as mana's.
        return self.stats.hp_regen * self._mult("hp_regen_mult") + self._bonus("hp_regen_flat_pct") * self.max_hp

    @property
    def mana_regen(self):
        return self.stats.mana_regen * self._mult("mana_regen_mult") + self._bonus("mana_regen_flat_pct") * self.max_mana

    @property
    def max_mana(self):
        return self.stats.max_mana * self._mult("max_mana_mult")

    @property
    def xp_frac(self):
        if self.level >= MAX_LEVEL:
            return 1.0
        return self.xp / xp_to_next(self.level)

    def gain_xp(self, amount):
        if self.level >= MAX_LEVEL:
            return
        # Stage K12: Pocao Dourada (buff_gold's xp_gain_mult) - same _mult()
        # aggregation every other derived stat reads through.
        amount *= self._mult("xp_gain_mult")
        self.xp += amount
        self.xp_earned_total += amount
        while self.level < MAX_LEVEL and self.xp >= xp_to_next(self.level):
            self.xp -= xp_to_next(self.level)
            self.level += 1
            self.unspent_points += POINTS_PER_LEVEL
            self.pending_level_up += 1

    def credit_gold(self, amount):
        """Stage K12: Pocao Turquesa (buff_gold_gain's gold_gain_mult) - every
        gold credit (boss reward, dropped-coin pickup) should go through this
        instead of a bare `player.gold += n`, same reasoning as gain_xp()
        above needing the xp_gain_mult multiplier applied at the one place
        XP is actually granted."""
        self.gold += round(amount * self._mult("gold_gain_mult"))

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
        # Stage K10: mana_cost_mult < 1.0 (e.g. a "-10% custo de mana"
        # Postura) makes this cheaper; nothing sets it below 1.0 yet.
        self.mana -= spell["mana_cost"] * self._mult("mana_cost_mult")
        # Haste (Destreza) speeds up spell cooldowns the same way it speeds
        # up melee attack_cooldown - one stat for "attack speed" and "cast
        # speed" instead of a second, parallel system. attack_speed_mult
        # (Stage K10) stacks on top - >1.0 shortens the cooldown further.
        self.spell_cooldowns[spell_id] = spell["cooldown"] * (1 - self.stats.haste) / self._mult("attack_speed_mult")
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

    def try_apply_debuff(self, effect_id):
        """Stage K11: debuff_resist_add (Paladino/Templario Posturas) rolls
        a chance to shrug off an incoming debuff entirely before it's ever
        applied - callers that represent a real enemy/hazard attack
        (game/enemy.py, game/boss.py, game/level.py, game/states.py) should
        use this instead of calling self.status.apply() directly. Debug
        Mode's "apply everything" trigger deliberately keeps calling
        status.apply() directly - a debug tool forcing state to inspect it
        shouldn't itself be resistable."""
        import random
        resist = self._bonus("debuff_resist_add")
        if resist > 0 and random.random() < resist:
            return False
        self.status.apply(effect_id)
        return True

    def take_damage(self, amount, dtype="physical", knockback_from=None):
        if self.invincible or self.debug_invincible:
            return
        # Stage K11: dodge (Duelista's Postura only, today) - a clean miss,
        # no i-frames spent, no knockback, nothing. Same "roll once, block
        # outright" shape as enemy.py's 'warded' affix.
        import random
        if self.dodge_chance > 0 and random.random() < self.dodge_chance:
            return
        defense = self.physical_defense if dtype == "physical" else self.magic_defense
        amount = mitigate(amount, defense) * self.status.damage_taken_multiplier * self.stance_multiplier("damage_taken_mult")
        self.hp -= amount
        self.invincible = True
        self.invincible_timer = self.invincible_duration
        self.audio.play("hurt")
        # Stage K6: floating damage number.
        number_color = PHYSICAL_COLOR if dtype == "physical" else MAGIC_COLOR
        self.floating_numbers.append(
            FloatingNumber(self.x + self.width / 2, self.y, amount, number_color)
        )
        # Stage K9: knockback - pushed away from whatever dealt the hit.
        # knockback_from is None for DoT ticks (see game/status_effects.py
        # callers) and anything else that shouldn't shove the player.
        if knockback_from is not None:
            self.knockback_vx, self.knockback_vy = knockback_vector(
                knockback_from[0], knockback_from[1],
                self.x + self.width / 2, self.y + self.height / 2,
            )
            self.knockback_timer = KNOCKBACK_DURATION

    def update(self, dt, walls, movement_vector):
        self.mana = min(self.max_mana, self.mana + self.mana_regen * dt)
        self.hp = min(self.max_hp, self.hp + self.hp_regen * dt)

        for spell_id in list(self.spell_cooldowns):
            self.spell_cooldowns[spell_id] = max(0.0, self.spell_cooldowns[spell_id] - dt)

        # DoT ticks (Veneno/Fogo) go straight to hp, bypassing take_damage -
        # they shouldn't be blocked by melee-hit invincibility frames, and
        # shouldn't themselves grant any.
        tick_dmg = self.status.update(dt)
        if tick_dmg and not self.debug_invincible:
            self.hp -= tick_dmg
            # Stage K6: floating damage number for the DoT tick itself -
            # take_damage() is bypassed here (see comment above), so this
            # is the only place that can show it.
            self.floating_numbers.append(
                FloatingNumber(self.x + self.width / 2, self.y, tick_dmg, DOT_COLOR)
            )

        # Stage K6: floating damage numbers (age/prune every frame,
        # regardless of source - take_damage()/the DoT tick above only add).
        self.floating_numbers = [n for n in self.floating_numbers if n.alive]
        for n in self.floating_numbers:
            n.update(dt)

        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt

        if self.knockback_timer > 0:
            # Stage K9: takes priority over everything else, including a
            # dash in progress - getting hit interrupts it (same cleanup
            # Stage K2's normal dash-end path does, so no stale trail).
            # Stage K23: also cuts the key-found pose short, same reasoning
            # - a hazard tick landing mid-celebration shouldn't leave the
            # player stuck posing while taking free hits.
            self.dashing = False
            self.dash_trail = []
            self.key_pose_timer = 0.0
            self.knockback_timer -= dt
            self.x += self.knockback_vx * dt
            self._resolve_collisions_x(walls)
            self.y += self.knockback_vy * dt
            self._resolve_collisions_y(walls)
            ease = max(0.0, self.knockback_timer / KNOCKBACK_DURATION)
            self.knockback_vx *= ease
            self.knockback_vy *= ease
        elif self.key_pose_timer > 0:
            # Stage K23: movement locked for the duration, same "one
            # committed motion" feel as dash/attack - direction is pinned
            # to "down" (facing the camera) by trigger_key_found_pose()
            # below and never re-derived from movement_vector here.
            self.key_pose_timer -= dt
        elif self.dashing:
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
                # Stage K2: this never ran before - draw() shows the trail
                # whenever dash_trail is non-empty regardless of self.dashing,
                # and nothing else ever cleared it once the dash ended, so
                # the last DASH_TRAIL_LEN ghost frames sat on screen forever
                # (until the *next* dash overwrote them via try_dash()'s own
                # reset). The trail should only exist while actually dashing.
                self.dash_trail = []
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
        if self.pickaxe_cooldown > 0:
            self.pickaxe_cooldown -= dt

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
            self.attack_cooldown = self.stats.attack_cooldown / self._mult("attack_speed_mult")
            self.audio.play("attack")
            return True
        return False

    def try_pickaxe(self):
        if self.pickaxe_cooldown > 0:
            return False
        self.pickaxe_cooldown = PICKAXE_COOLDOWN
        return True

    def trigger_key_found_pose(self):
        """Stage K23: called by GameplayState._attempt_pickaxe() exactly
        once, the frame Level.try_break_tile()'s key branch actually fires
        (not on every dig) - see update()/draw() for how the pose itself
        plays out."""
        self.key_pose_timer = KEY_POSE_DURATION
        self.direction = "down"
        self.dashing = False
        self.dash_trail = []
        self.attacking = False

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
        # Stage K6: drawn before the invincibility-flash early return below,
        # so the number doesn't itself flicker in sync with the hero sprite.
        for n in self.floating_numbers:
            n.draw(surface, cam_x, cam_y)

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

        if self.key_pose_timer > 0:
            self._draw_key_pose(surface, sx, sy)

    def _draw_key_pose(self, surface, sx, sy):
        """Stage K23: a small key icon rising above the hero's head while
        key_pose_timer counts down - the "arm raise" reads through the
        icon's own motion (rises for the first ~35% of the pose, then
        holds overhead) rather than needing a new sprite pose per
        profession/costume in create_player_sprite."""
        from game.assets import create_item_sprite
        progress = 1.0 - (self.key_pose_timer / KEY_POSE_DURATION)
        rise = min(1.0, progress / 0.35)
        y_offset = int(18 - 18 * rise)
        icon = create_item_sprite("key")
        icon_x = sx + self.width // 2 - icon.get_width() // 2
        icon_y = sy - 22 + y_offset
        surface.blit(icon, (icon_x, icon_y))

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

    def draw_hud(self, surface, save_state=None, touch_active=False, mouse_pos=None):
        # HP/mana/XP bars - stats.py's bigger hp range (see Stage A3) no
        # longer maps cleanly onto discrete heart icons, so it's bars like
        # bosses already use.
        from game.ui import ProgressBar, draw_tooltip
        from game.theme import font, ACCENT_GOLD, SW, SH
        from game.stats import xp_to_next
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

        # Stage K8: hover tooltips with the exact numbers behind each bar -
        # the bars themselves only ever show a fraction/color, never digits.
        hp_rect = pygame.Rect(12, dock_y, self._hp_bar.w, self._hp_bar.h)
        draw_tooltip(surface, mouse_pos, hp_rect,
                     f"Vida: {round(self.hp)}/{round(self.max_hp)}", SW, SH)
        mana_rect = pygame.Rect(12, dock_y + 20, self._mana_bar.w, self._mana_bar.h)
        draw_tooltip(surface, mouse_pos, mana_rect,
                     f"Mana: {round(self.mana)}/{round(self.max_mana)}", SW, SH)
        xp_rect = pygame.Rect(12, dock_y + 34, self._xp_bar.w, self._xp_bar.h)
        draw_tooltip(surface, mouse_pos, xp_rect,
                     f"XP: {round(self.xp)}/{round(xp_to_next(self.level))}", SW, SH)

        f = font(16, bold=True)
        lvl_txt = f.render(f"Lv {self.level}", True, ACCENT_GOLD)
        surface.blit(lvl_txt, (178, dock_y))

        gold_txt = f.render(f"{self.gold}g", True, (230, 200, 80))
        surface.blit(gold_txt, (178, dock_y + 20))

        self._draw_status_chips(surface, dock_y + 46, mouse_pos)
        self._draw_hotbar(surface, touch_active, mouse_pos)
        self._draw_stance_badge(surface, mouse_pos)

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

    def _draw_hotbar(self, surface, touch_active=False, mouse_pos=None):
        from game.theme import font, ACCENT_GOLD, SW, SH
        from game.items import ITEMS
        from game.ui import draw_tooltip
        f_key = font(11, bold=True)
        f_count = font(11, bold=True)
        # Stage K12: key labels are derived per-kind, not by flat slot index -
        # player.hotbar_items can hold fewer than 3 entries (nothing forces a
        # full 3 picks), which used to shift every label after the item
        # group (dash's "X" would've slid left into "3"'s spot) when read
        # positionally out of the old fixed-length _HOTBAR_KEYS.
        # Stage K20: read live from game.keybinds instead of a hardcoded
        # letter - Stage K15's remap makes any of these move, and this
        # label went stale (still showing the OLD key) the moment it did.
        import game.keybinds as keybinds

        def _key_label(action_name):
            # SPACE is the one default long enough to not fit this badge's
            # width comfortably - abbreviated here only (Settings/Help have
            # room for the full name). Anything a player rebinds it to
            # instead is shown as-is; only the specific default is special-
            # cased, not a general truncation rule.
            label = keybinds.display_key(action_name)
            return "SPC" if label == "SPACE" else label

        _spell_action = {"fireball": "CAST_1", "frost_nova": "CAST_2", "healing_light": "CAST_3"}
        item_i = 0
        for i, (kind, key, rect) in enumerate(hotbar_slots(self)):
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
            elif kind == "dash":
                on_cooldown = self.dash_cooldown > 0
                usable = self.stats.dexterity >= DASH_DEX_REQ and not on_cooldown
                icon = create_dash_icon()
                selected = False
            else:  # kind == "pickaxe"
                on_cooldown = self.pickaxe_cooldown > 0
                usable = not on_cooldown
                icon = create_pickaxe_icon()
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

            if kind == "attack":
                key_label = _key_label("ATTACK")
            elif kind == "spell":
                key_label = _key_label(_spell_action.get(key, ""))
            elif kind == "item":
                item_i += 1
                key_label = str(item_i)
            elif kind == "dash":
                key_label = _key_label("DASH")
            else:  # pickaxe
                key_label = _key_label("PICKAXE")
            key_surf = f_key.render(key_label, True, (255, 255, 255))
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
            elif kind == "pickaxe" and on_cooldown:
                cd_frac = min(1.0, self.pickaxe_cooldown / PICKAXE_COOLDOWN)
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

            # Stage K8: hover tooltip, objective numbers only.
            if kind == "spell":
                spell = SPELLS[key]
                tip = [spell["name"], spell["description"],
                       f"Custo: {spell['mana_cost']} mana | Recarga: {spell['cooldown']:.1f}s"]
            elif kind == "item":
                tip = [ITEMS[key]["name"], _item_tooltip_line(key)]
            elif kind == "attack":
                tip = ["Ataque", f"Corpo a corpo | Recarga: {self.stats.attack_cooldown:.2f}s"]
            elif kind == "dash":
                tip = ["Investida (Dash)", f"Requer DES {DASH_DEX_REQ} | Recarga: {DASH_COOLDOWN:.1f}s"]
            else:  # pickaxe
                tip = ["Picareta", f"Quebra blocos e cava em busca da chave | Recarga: {PICKAXE_COOLDOWN:.1f}s"]
            draw_tooltip(surface, mouse_pos, rect, tip, SW, SH)

    def _draw_status_chips(self, surface, dock_y, mouse_pos=None):
        # Stage K8: moved from a left-aligned row under the HP/mana/XP dock
        # to a horizontal row centered under the hotbar (now up at the top
        # edge, Stage K7) - same spot future timed buffs (Stage K12) will
        # share, since they'll live in this same self.status.active dict
        # once Stage K10 extends StatusEffectCarrier for percentage buffs,
        # not a separate list. Each chip now also shows a countdown and
        # responds to hover with a tooltip (name + exact numbers).
        from game.status_effects import STATUS_DISPLAY, STATUS_HELP
        from game.theme import font, SW, SH
        from game.ui import draw_tooltip
        if not self.status.active:
            return
        chip_w, chip_h, gap = 40, 34, 4
        n = len(self.status.active)
        total_w = n * chip_w + (n - 1) * gap
        x = SW // 2 - total_w // 2
        y = _HOTBAR_Y + _HOTBAR_SLOT + 6
        f_timer = font(10, bold=True)
        for effect_id, active in self.status.active.items():
            _, color = STATUS_DISPLAY.get(effect_id, (effect_id[:3].upper(), (200, 200, 200)))
            chip = pygame.Surface((chip_w, chip_h), pygame.SRCALPHA)
            chip.fill((*color, 70))
            pygame.draw.rect(chip, color, (0, 0, chip_w, chip_h), 1)
            surface.blit(chip, (x, y))
            icon = create_debuff_icon(effect_id)
            surface.blit(icon, (x + chip_w // 2 - icon.get_width() // 2, y + 4))
            timer_txt = f_timer.render(f"{max(0, active.remaining):.0f}s", True, (235, 235, 245))
            surface.blit(timer_txt, (x + chip_w // 2 - timer_txt.get_width() // 2, y + chip_h - 12))

            name, desc = STATUS_HELP.get(effect_id, (effect_id, ""))
            chip_rect = pygame.Rect(x, y, chip_w, chip_h)
            draw_tooltip(surface, mouse_pos, chip_rect, [name, desc], SW, SH)
            x += chip_w + gap

    def _draw_stance_badge(self, surface, mouse_pos=None):
        # Stage K11: a Postura is permanent (not a ticking timer like
        # self.status.active's debuffs/future potion buffs), so it gets its
        # own always-visible badge instead of living in that row - and per
        # the user's explicit ask, a bigger square than those (46x46 here
        # vs. the debuff row's 40x34 chips) to read as "this one doesn't
        # expire." Aventureiro (no Postura yet, <20 attribute points spent)
        # draws nothing - nothing to show.
        from game.stances import STANCES, STANCE_DESCRIPTIONS
        from game.theme import ACCENT_GOLD, SW, SH
        from game.ui import draw_tooltip
        if self.profession not in STANCES:
            return
        size = 46
        # Left-aligned under the HP/mana/XP dock (matches its x=12 margin)
        # rather than up near the top-right corner - that corner is shared
        # with the browser-only Google-login pill (an HTML overlay, not
        # drawn by pygame at all, so nothing in this file could avoid it by
        # reading its rect) and gets crowded fast at that canvas scale.
        x = 12
        y = 90
        badge = pygame.Surface((size, size), pygame.SRCALPHA)
        badge.fill((15, 15, 20, 210))
        pygame.draw.rect(badge, ACCENT_GOLD, (0, 0, size, size), 2, border_radius=6)
        surface.blit(badge, (x, y))
        icon = create_stance_icon(self.profession)
        surface.blit(icon, (x + size // 2 - icon.get_width() // 2, y + size // 2 - icon.get_height() // 2))
        badge_rect = pygame.Rect(x, y, size, size)
        draw_tooltip(surface, mouse_pos, badge_rect,
                     [f"Postura ({self.profession})", STANCE_DESCRIPTIONS.get(self.profession, "")],
                     SW, SH)
