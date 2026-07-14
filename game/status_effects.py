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
    "hp_regen_mult",  # Stage K12: symmetric with mana_regen_mult above -
                       # added when Pocao Rosa needed "+20% regen. de vida"
                       # to mean the same "multiply the existing regen tick"
                       # shape mana_regen_mult already had, not another flat
                       # per-second add (hp_regen_flat_pct already covers
                       # that shape, used by the Postura layer instead).
], defaults=(1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0))

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
    "xp_gain_mult", "gold_gain_mult", "hp_regen_mult",
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


def _buff(duration, **kwargs):
    """Stage K12: every new potion/elixir buff below is a pure stat
    multiplier/bonus with no tick damage and no cure (you just wait it
    out, same as Fogo/Calor above) - fills in the 7 required fields with
    that shape so each STATUS_EFFECTS line only has to name the duration
    and whichever K10 field(s) it actually buffs. speed_mult/damage_taken_mult
    are set via this same fields dict (not hardcoded positionally) so a
    buff that DOES want to set speed_mult (e.g. Pocao Branca) can pass it
    through kwargs without colliding with a duplicate positional value."""
    fields = dict(tick_interval=None, tick_damage=None, max_ticks=None,
                  speed_mult=1.0, damage_taken_mult=1.0, cureable_by=frozenset())
    fields.update(kwargs)
    return StatusEffectDef(duration, **fields)


# Stage K12: ~22 new timed potion/elixir buffs, applied via game/items.py's
# use_item() -> player.status.apply(item["buff"]) - same StatusEffectCarrier
# every debuff above already goes through, so a potion buff and a Postura
# (game/stances.py) stack the same way two debuffs already did (multiply/
# sum through Player._mult()/_bonus(), Stage K10). Field choices approximate
# a couple of the user's asks that don't map to a single existing derived
# stat 1:1 (raw attribute buffs like "+15% Forca"/"+15% Destreza" - the
# whole buff system operates on StatBlock's *derived* stats, not raw
# attributes - mapped to that attribute's most direct combat consequence;
# noted per-entry below).
STATUS_EFFECTS.update({
    # --- Pocoes de Atributo (7, 100g, 3min) ---
    "buff_black":    _buff(180.0, magic_defense_mult=1.15),                    # Preta: +15% Resist. Magica
    "buff_orange":   _buff(180.0, physical_damage_mult=1.15),                  # Laranja: +15% Forca -> dano fisico (consequencia direta de STR)
    "buff_purple":   _buff(180.0, magic_damage_mult=1.15),                     # Roxa: +15% Inteligencia -> dano magico
    "buff_white":    _buff(180.0, speed_mult=1.15),                           # Branca: +15% Vel. Movimento
    "buff_green":    _buff(180.0, max_hp_mult=1.15),                          # Verde: +15% Vigor -> vida maxima
    "buff_darkblue": _buff(180.0, max_mana_mult=1.15),                        # Azul-Escura: +15% Wisdom -> mana maxima
    "buff_yellow":   _buff(180.0, attack_speed_mult=1.15),                    # Amarela: +15% Destreza -> vel. de ataque
    # --- Pocoes Defensivas (3, 120g, 3min) ---
    "buff_gray":     _buff(180.0, physical_defense_mult=1.15),                # Cinza: +15% Resist. Fisica
    "buff_silver":   _buff(180.0, debuff_resist_add=0.20),                    # Prateada: +20% Resist. a Debuffs
    "buff_brown":    _buff(180.0, physical_defense_mult=1.20),                # Marrom: +20% Armadura -> defesa fisica
    # --- Pocoes Ofensivas (3, 150g, 3min) ---
    "buff_darkred":  _buff(180.0, physical_damage_mult=1.20),                 # Vermelho-Escura: +20% Dano Fisico
    "buff_violet":   _buff(180.0, magic_damage_mult=1.20),                    # Violeta: +20% Dano Magico
    "buff_ruby":     _buff(180.0, crit_chance_add=0.10),                      # Rubra: +10% Critico
    # --- Pocoes Utilitarias (4) ---
    "buff_cyan":     _buff(180.0, mana_regen_mult=1.20),                      # Ciano: +20% Regen. Mana, 100g/3min
    "buff_pink":     _buff(180.0, hp_regen_mult=1.20),                        # Rosa: +20% Regen. Vida, 100g/3min
    "buff_gold":     _buff(300.0, xp_gain_mult=1.20),                         # Dourada: +20% XP, 250g/5min
    "buff_turquoise": _buff(300.0, gold_gain_mult=1.20),                      # Turquesa: +20% Ouro, 250g/5min
    # --- Elixires (5, mais raros) ---
    "elixir_crimson":  _buff(300.0, max_hp_mult=1.10, physical_damage_mult=1.10),   # Carmesim: +10% Vida, +10% Forca
    "elixir_arcane":   _buff(300.0, max_mana_mult=1.10, magic_damage_mult=1.10),    # Arcano: +10% Mana, +10% Dano Magico
    "elixir_guardian": _buff(300.0, max_hp_mult=1.10, physical_defense_mult=1.10),  # do Guardiao: +10% Vida, +10% Resist. Fisica
    "elixir_hunter":   _buff(300.0, speed_mult=1.10, attack_speed_mult=1.10),       # do Cacador: +10% Vel. Movimento, +10% Destreza
    # do Campeao: +10% em todos os atributos, 2min (mais curto - o mais forte)
    "elixir_champion": _buff(120.0, physical_damage_mult=1.10, magic_damage_mult=1.10,
                              physical_defense_mult=1.10, magic_defense_mult=1.10,
                              max_hp_mult=1.10, max_mana_mult=1.10,
                              speed_mult=1.10, attack_speed_mult=1.10, crit_chance_add=0.05),
})


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
    # Stage K12: chip color mirrors each potion's own bottle tint
    # (game/assets.py's _POTION_COLORS "light" shade) so the buff-bar icon
    # and the item icon read as the same thing at a glance.
    "buff_black":     ("RMG", (70, 70, 78)),
    "buff_orange":    ("FOR", (255, 175, 90)),
    "buff_purple":    ("INT", (180, 110, 230)),
    "buff_white":     ("VEL", (250, 250, 255)),
    "buff_green":     ("VIG", (110, 220, 130)),
    "buff_darkblue":  ("SAB", (70, 100, 200)),
    "buff_yellow":    ("DES", (255, 240, 110)),
    "buff_gray":      ("RFI", (180, 180, 188)),
    "buff_silver":    ("RDE", (225, 228, 235)),
    "buff_brown":     ("ARM", (170, 120, 70)),
    "buff_darkred":   ("DFI", (170, 50, 55)),
    "buff_violet":    ("DMA", (200, 130, 240)),
    "buff_ruby":      ("CRI", (240, 80, 120)),
    "buff_cyan":      ("RMA", (110, 230, 235)),
    "buff_pink":      ("RVI", (255, 180, 210)),
    "buff_gold":      ("XP+", (255, 220, 100)),
    "buff_turquoise": ("OU+", (100, 220, 205)),
    "elixir_crimson":  ("ECR", (220, 60, 80)),
    "elixir_arcane":   ("EAR", (140, 90, 240)),
    "elixir_guardian": ("EGU", (120, 180, 225)),
    "elixir_hunter":   ("ECA", (130, 190, 100)),
    "elixir_champion": ("ECP", (255, 225, 120)),
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
    # Stage K12: potions/elixirs - same "prose rendering of STATUS_EFFECTS
    # numbers" discipline as the debuffs above.
    "buff_black":     ("Pocao Preta", "+15% resist. magica por 3min."),
    "buff_orange":    ("Pocao Laranja", "+15% dano fisico por 3min."),
    "buff_purple":    ("Pocao Roxa", "+15% dano magico por 3min."),
    "buff_white":     ("Pocao Branca", "+15% velocidade de movimento por 3min."),
    "buff_green":     ("Pocao Verde", "+15% vida maxima por 3min."),
    "buff_darkblue":  ("Pocao Azul-Escura", "+15% mana maxima por 3min."),
    "buff_yellow":    ("Pocao Amarela", "+15% velocidade de ataque por 3min."),
    "buff_gray":      ("Pocao Cinza", "+15% resist. fisica por 3min."),
    "buff_silver":    ("Pocao Prateada", "+20% resist. a debuffs por 3min."),
    "buff_brown":     ("Pocao Marrom", "+20% defesa fisica por 3min."),
    "buff_darkred":   ("Pocao Vermelho-Escura", "+20% dano fisico por 3min."),
    "buff_violet":    ("Pocao Violeta", "+20% dano magico por 3min."),
    "buff_ruby":      ("Pocao Rubra", "+10% critico por 3min."),
    "buff_cyan":      ("Pocao Ciano", "+20% regen. de mana por 3min."),
    "buff_pink":      ("Pocao Rosa", "+20% regen. de vida por 3min."),
    "buff_gold":      ("Pocao Dourada", "+20% XP ganho por 5min."),
    "buff_turquoise": ("Pocao Turquesa", "+20% ouro ganho por 5min."),
    "elixir_crimson":  ("Elixir Carmesim", "+10% vida maxima, +10% dano fisico por 5min."),
    "elixir_arcane":   ("Elixir Arcano", "+10% mana maxima, +10% dano magico por 5min."),
    "elixir_guardian": ("Elixir do Guardiao", "+10% vida maxima, +10% resist. fisica por 5min."),
    "elixir_hunter":   ("Elixir do Cacador", "+10% velocidade de movimento, +10% velocidade de ataque por 5min."),
    "elixir_champion": ("Elixir do Campeao", "+10% em todos os atributos, +5% critico por 2min."),
}
