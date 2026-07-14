"""
Debuffs applied to the player by enemy attacks (Stage: RPG systems expansion,
see .claude/plans/cozy-wiggling-pumpkin.md). Same registry-dict pattern as
game/stats.py's ENEMY_ARCHETYPES - a new debuff is one line in STATUS_EFFECTS,
no new class or branching logic.

StatusEffectCarrier is a small standalone component (not hardcoded onto
Player) so it can be attached to Enemy/Boss later too - e.g. the RPG
redesign plan's Frost Nova spell slows enemies, which is the same "speed_mult
while active" shape as the player's own Slow debuff.
"""
from collections import namedtuple

StatusEffectDef = namedtuple("StatusEffectDef", [
    "duration",           # float seconds until auto-expiry
    "tick_interval",      # float | None - None means "pure stat multiplier, no damage"
    "tick_damage",        # float | None
    "max_ticks",          # int | None - caps ticks even if duration would allow more (Fogo: exactly 3)
    "speed_mult",         # float, default 1.0
    "damage_taken_mult",  # float, default 1.0
    "cureable_by",        # frozenset[str] item ids; empty = no cure exists
    # Stage K10: generalized percentage buff/debuff axes, added for the new
    # timed potion buffs (Stage K12) and reused by the separate, permanent
    # Postura layer (Stage K11 - see Player.stance_multiplier/_bonus, not
    # part of this timed carrier at all, just the same field shape). Every
    # existing debuff above only ever set speed_mult/damage_taken_mult, so
    # all of these default to "no effect" (1.0 for multipliers, 0.0 for the
    # flat/additive ones) and none of the 7 entries in STATUS_EFFECTS below
    # need to change to keep behaving exactly as before.
    "physical_damage_mult", "magic_damage_mult",
    "physical_defense_mult", "magic_defense_mult",
    "crit_chance_add", "attack_speed_mult",
    "max_hp_mult", "max_mana_mult", "mana_regen_mult",
    "mana_cost_mult", "debuff_chance_add", "debuff_resist_add",
    "hp_regen_flat_pct", "mana_regen_flat_pct",
    "xp_gain_mult", "gold_gain_mult",
], defaults=(1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0))

# Field names where multiple active effects COMBINE BY MULTIPLYING (a %
# bonus stacks multiplicatively, matching speed_mult/damage_taken_mult
# above) vs. by SUMMING (flat additive bonuses - crit chance, debuff
# chance/resist, hp/mana regen-per-second). StatusEffectCarrier.multiplier()/
# .bonus() below use this to know which aggregation a field wants without
# hardcoding one property per field.
_MULTIPLICATIVE_FIELDS = frozenset({
    "speed_mult", "damage_taken_mult", "physical_damage_mult", "magic_damage_mult",
    "physical_defense_mult", "magic_defense_mult", "attack_speed_mult",
    "max_hp_mult", "max_mana_mult", "mana_regen_mult", "mana_cost_mult",
    "xp_gain_mult", "gold_gain_mult",
})
_ADDITIVE_FIELDS = frozenset({
    "crit_chance_add", "debuff_chance_add", "debuff_resist_add",
    "hp_regen_flat_pct", "mana_regen_flat_pct",
})

STATUS_EFFECTS = {
    # Veneno: 3 dmg/5s, resolves in ~12s on its own, Antidoto cures early.
    "poison":   StatusEffectDef(12.0, 5.0, 3, None, 1.0, 1.0, frozenset({"antidote"})),
    # Lentidao: -45% velocidade de movimento, ~12s, Antidoto cures early.
    "slow":     StatusEffectDef(12.0, None, None, None, 0.55, 1.0, frozenset({"antidote"})),
    # Fraqueza: +30% dano recebido, ~12s, Antidoto cures early.
    "weakness": StatusEffectDef(12.0, None, None, None, 1.0, 1.3, frozenset({"antidote"})),
    # Fogo: 2 dmg/2s for exactly 3 ticks (6s), no cure yet.
    "burn":     StatusEffectDef(6.0, 2.0, 2, 3, 1.0, 1.0, frozenset()),
    # Frio: ambient cold (neve/gelo weather) - milder than Lentidao, no
    # damage, just a persistent chill while exposed. Antidoto cures early.
    "chill":    StatusEffectDef(6.0, None, None, None, 0.85, 1.0, frozenset({"antidote"})),
    # Calor: sandstorm/ashfall weather - light DoT + a small speed penalty.
    # No cure yet, same as Fogo.
    "heat":     StatusEffectDef(8.0, 4.0, 1, 2, 0.90, 1.0, frozenset()),
    # Choque: storm lightning strike - +15% dano recebido, short. Antidoto
    # cures early (same "dispellable debuff" family as Fraqueza).
    "shock":    StatusEffectDef(5.0, None, None, None, 1.0, 1.15, frozenset({"antidote"})),
}


class ActiveEffect:
    def __init__(self, effect_id):
        self.effect_id = effect_id
        self.defn = STATUS_EFFECTS[effect_id]
        self.remaining = self.defn.duration
        self.tick_timer = self.defn.tick_interval
        self.ticks_done = 0

    def update(self, dt):
        """Returns the tick damage dealt this frame (0 most frames)."""
        self.remaining -= dt
        if self.defn.tick_interval is None:
            return 0.0
        self.tick_timer -= dt
        if self.tick_timer > 0:
            return 0.0
        self.tick_timer += self.defn.tick_interval
        if self.defn.max_ticks is not None and self.ticks_done >= self.defn.max_ticks:
            return 0.0
        self.ticks_done += 1
        return self.defn.tick_damage

    @property
    def expired(self):
        if self.defn.max_ticks is not None and self.ticks_done >= self.defn.max_ticks:
            return True
        return self.remaining <= 0


class StatusEffectCarrier:
    def __init__(self):
        self.active = {}

    def apply(self, effect_id):
        """Refreshes the effect rather than stacking it - reapplying Poison
        while already poisoned just resets its clock, doesn't double the tick."""
        self.active[effect_id] = ActiveEffect(effect_id)

    def cure(self, cures):
        self.active = {k: v for k, v in self.active.items() if k not in cures}

    def has(self, effect_id):
        return effect_id in self.active

    def update(self, dt):
        """Ages/expires active effects, returns total tick damage this frame."""
        total = 0.0
        for effect_id in list(self.active):
            effect = self.active[effect_id]
            total += effect.update(dt)
            if effect.expired:
                del self.active[effect_id]
        return total

    @property
    def speed_multiplier(self):
        mult = 1.0
        for effect in self.active.values():
            mult *= effect.defn.speed_mult
        return mult

    @property
    def damage_taken_multiplier(self):
        mult = 1.0
        for effect in self.active.values():
            mult *= effect.defn.damage_taken_mult
        return mult

    # Stage K10: generic accessors for every field added to StatusEffectDef
    # above - one method instead of 16 near-identical properties (the
    # speed_multiplier/damage_taken_multiplier properties above predate this
    # and are left as-is rather than churned into this shape for no reason).
    def multiplier(self, field):
        """Product across every active effect's `field` - for %-bonus axes
        that stack multiplicatively (see _MULTIPLICATIVE_FIELDS)."""
        mult = 1.0
        for effect in self.active.values():
            mult *= getattr(effect.defn, field)
        return mult

    def bonus(self, field):
        """Sum across every active effect's `field` - for flat/additive
        axes (see _ADDITIVE_FIELDS)."""
        return sum(getattr(effect.defn, field) for effect in self.active.values())


# Display-only metadata for the HUD debuff chips - kept separate from the
# balance numbers above so tweaking a color doesn't touch gameplay data.
STATUS_DISPLAY = {
    "poison":   ("VEN", (140, 220, 90)),
    "slow":     ("LEN", (120, 170, 230)),
    "weakness": ("FRA", (200, 120, 200)),
    "burn":     ("FOG", (255, 130, 40)),
    "chill":    ("FRI", (150, 200, 255)),
    "heat":     ("CAL", (255, 180, 80)),
    "shock":    ("CHO", (255, 255, 120)),
}

# Stage J4: full name + player-facing description per effect, read by the
# paperdoll Help tab's debuff page. The numbers here must mirror
# STATUS_EFFECTS above (they're prose renderings of those exact values, the
# same single-source discipline HELP_ENTRIES follows for keybindings).
STATUS_HELP = {
    "poison":   ("Veneno", "3 de dano a cada 5s, por ate 12s. Cura: Antidoto."),
    "slow":     ("Lentidao", "-45% de velocidade de movimento por 12s. Cura: Antidoto."),
    "weakness": ("Fraqueza", "+30% de dano recebido por 12s. Cura: Antidoto."),
    "burn":     ("Fogo", "2 de dano a cada 2s, 3 vezes. Sem cura - espere passar."),
    "chill":    ("Frio", "-15% de velocidade enquanto exposto a neve/gelo. Cura: Antidoto."),
    "heat":     ("Calor", "Dano leve continuo e -10% de velocidade em areia/cinzas. Sem cura."),
    "shock":    ("Choque", "+15% de dano recebido por 5s (raios de tempestade). Cura: Antidoto."),
}
