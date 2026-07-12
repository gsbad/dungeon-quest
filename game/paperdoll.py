import math
import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.assets import (
    create_player_sprite, create_attribute_icon, create_level_thumbnail,
    create_debuff_icon, create_spell_icon,
)
from game.spells import SPELLS, ORDER as SPELL_ORDER, meets_requirements, missing_requirements
from game.input_system import Action, HELP_ENTRIES
from game.stats import mitigate
from game.bestiary import (
    BESTIARY, MOB_IDS, BOSS_IDS, is_discovered, mob_sprite, mob_stats, mob_attacks,
    boss_sprite, boss_stats, boss_attacks,
)
from game.level import LEVEL_MAPS
from game.weather import WEATHER_TYPES, WEATHER_DISPLAY_NAME

ATLAS_ORDER = sorted(LEVEL_MAPS.keys())

BESTIARY_ORDER = MOB_IDS + BOSS_IDS

# Keyboard hotkey shown per SPELL_ORDER slot in the Magias tab below - must
# match game/input_system.py's KEYDOWN bindings (K_f/K_q/K_r -> CAST_1/2/3).
SPELL_KEYS = ["F", "Q", "R"]

# (StatBlock field name, on-screen label). Order matches the plan's
# STR/DEX/INT/WIS/VIG/SOR convention.
ATTRS = [
    ("strength", "FOR (dano fis., def.)"),
    ("dexterity", "DES (haste, def.)"),
    ("intelligence", "INT (dano mag., cura)"),
    ("wisdom", "SAB (mana, def. mag.)"),
    ("vigor", "VIG (vida, def.)"),
    ("luck", "SOR (critico)"),
]

BASE_ATTR = 10  # can't respec below this - it's the unbuilt baseline, not spent points

_PANEL_W = 420
_CONTENT_TOP = 40  # room for the tab bar above the header
# Portrait shrunk (96->80) and derived/attr rows compacted to make room for
# the 6th attribute (Sorte) and the two-column secondary-stat grid below
# without the panel overflowing SH=600 - see _draw_stats' two-column layout.
_PORTRAIT_SIZE = 80
_PORTRAIT_MARGIN = 16
# Header row: portrait on the left, name/profession/level text to its right.
_HEADER_H = _PORTRAIT_MARGIN + _PORTRAIT_SIZE + 14
_TITLE_Y = 20
_PROFESSION_Y = 52
_LEVEL_Y = 82

# Derived-stat rows, laid out as two columns (offense left, defense/
# resources right) - 7 rows fits everything from Requirement 2's secondary
# stats (defenses, crit, haste, hp regen, healing power) alongside the
# original hp/damage/mana/speed lines.
_DERIVED_START_Y = _HEADER_H + 10
_DERIVED_LINE_H = 18
_DERIVED_ROWS = 7
_POINTS_Y = _DERIVED_START_Y + _DERIVED_LINE_H * _DERIVED_ROWS + 14
_ATTR_START_Y = _POINTS_Y + 30
_ATTR_LINE_H = 32
_HINT_Y = _ATTR_START_Y + _ATTR_LINE_H * len(ATTRS) + 12
_PANEL_H = _CONTENT_TOP + _HINT_Y + 26

_TAB_ORDER = ["stats", "spells", "bestiary", "atlas", "help"]

# Atlas tab (Stage F3) - a grid of level thumbnails (same shape as the
# Bestiary grid above) over a detail panel for the selected level. 13
# levels at 4 cols = 4 rows, one more than Bestiary's 3 rows of 12 mobs.
_ATLAS_COLS = 4
_ATLAS_CELL = 62
_ATLAS_GAP = 8
_ATLAS_GRID_Y = 10
_ATLAS_DETAIL_Y = _ATLAS_GRID_Y + 4 * _ATLAS_CELL + 3 * _ATLAS_GAP + 20

# Bestiary tab (Stage E4, individualization pass) - an icon grid (row count
# derived from BESTIARY_ORDER's length, not hardcoded - the mob roster grew
# from 8 to 20 common mobs + 4 bosses, so a fixed "3 rows" assumption would
# make the detail panel overlap the grid) above a detail panel for
# whichever entry is selected. 6 cols/56px cells (down from 4/70) keep the
# grid width inside the panel while fitting the bigger roster in fewer rows.
_BESTIARY_COLS = 6
_BESTIARY_CELL = 56
_BESTIARY_GAP = 6
# Relative to content_top (self.py + _CONTENT_TOP), same convention as
# _DERIVED_START_Y etc. above - callers add content_top themselves.
_BESTIARY_GRID_Y = 10
_BESTIARY_ROWS = math.ceil(len(BESTIARY_ORDER) / _BESTIARY_COLS)
_BESTIARY_DETAIL_Y = (_BESTIARY_GRID_Y + _BESTIARY_ROWS * _BESTIARY_CELL
                      + (_BESTIARY_ROWS - 1) * _BESTIARY_GAP + 20)

_SPELL_START_Y = _HEADER_H + 16
_SPELL_BLOCK_H = 100


class Paperdoll:
    """Painel do personagem (Stage A7/B2), tres abas: Status (retrato,
    profissao, stats, gasto de pontos), Magias (requisitos, status,
    selecao) e Bestiario (Stage E4 - mobs/bosses ja descobertos)."""

    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = 20
        self.active_tab = "stats"
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)

        # Keyboard-only navigation (mouse clicks are unreliable in the pygbag
        # browser build - see docs/design.md's known-bugs section) - a
        # highlighted row cursor per tab, moved with W/S, acted on with
        # A/D (stats) or Space (spells).
        self.stats_cursor = 0
        self.spell_cursor = 0
        self.bestiary_cursor = 0
        self.atlas_cursor = 0

        # Tab bar width is derived from however many tabs _TAB_ORDER has -
        # was hardcoded for exactly 3 (Stage E4); Stage F3/F4 added a 4th
        # (Atlas) and 5th (Help) tab, so this now scales down tab_w instead
        # of overflowing the fixed _PANEL_W.
        n_tabs = len(_TAB_ORDER)
        gap = 6
        tab_w = min(130, (_PANEL_W - 24 - gap * (n_tabs - 1)) // n_tabs)
        tab_h = 28
        row_w = tab_w * n_tabs + gap * (n_tabs - 1)
        tab_x0 = self.px + (_PANEL_W - row_w) // 2
        tab_y = self.py + 8
        self.tab_buttons = {}
        for i, tab_id in enumerate(_TAB_ORDER):
            self.tab_buttons[tab_id] = pygame.Rect(tab_x0 + i * (tab_w + gap), tab_y, tab_w, tab_h)

        self.bestiary_buttons = []
        grid_w = _BESTIARY_COLS * _BESTIARY_CELL + (_BESTIARY_COLS - 1) * _BESTIARY_GAP
        grid_x0 = self.px + (_PANEL_W - grid_w) // 2
        for i, key in enumerate(BESTIARY_ORDER):
            col, row = i % _BESTIARY_COLS, i // _BESTIARY_COLS
            x = grid_x0 + col * (_BESTIARY_CELL + _BESTIARY_GAP)
            y = self.py + _CONTENT_TOP + _BESTIARY_GRID_Y + row * (_BESTIARY_CELL + _BESTIARY_GAP)
            # (self.py + _CONTENT_TOP) matches _draw_bestiary's `top` param
            self.bestiary_buttons.append(pygame.Rect(x, y, _BESTIARY_CELL, _BESTIARY_CELL))

        self.atlas_buttons = []
        atlas_grid_w = _ATLAS_COLS * _ATLAS_CELL + (_ATLAS_COLS - 1) * _ATLAS_GAP
        atlas_grid_x0 = self.px + (_PANEL_W - atlas_grid_w) // 2
        for i, level_num in enumerate(ATLAS_ORDER):
            col, row = i % _ATLAS_COLS, i // _ATLAS_COLS
            x = atlas_grid_x0 + col * (_ATLAS_CELL + _ATLAS_GAP)
            y = self.py + _CONTENT_TOP + _ATLAS_GRID_Y + row * (_ATLAS_CELL + _ATLAS_GAP)
            self.atlas_buttons.append(pygame.Rect(x, y, _ATLAS_CELL, _ATLAS_CELL))

        self.plus_buttons = {}
        self.minus_buttons = {}
        for i, (attr, _) in enumerate(ATTRS):
            y = self.py + _CONTENT_TOP + _ATTR_START_Y + i * _ATTR_LINE_H
            self.minus_buttons[attr] = pygame.Rect(self.px + 260, y - 14, 28, 28)
            self.plus_buttons[attr] = pygame.Rect(self.px + 300, y - 14, 28, 28)

        self.select_buttons = {}
        for i, spell_id in enumerate(SPELL_ORDER):
            y = self.py + _CONTENT_TOP + _SPELL_START_Y + i * _SPELL_BLOCK_H
            btn_x = self.px + _PANEL_W // 2 - 55
            self.select_buttons[spell_id] = pygame.Rect(btn_x, y + 66, 110, 26)

        self._portrait_cache = {}
        self._bestiary_sprite_cache = {}

    def _portrait_for(self, profession):
        # Each profession is its own rig now (game/assets.py's
        # create_player_sprite(..., profession=...)) - no more shared base
        # sprite + color multiply. Base sprite is 48x48 (16px canvas at 3x
        # scale) - 2x again to fill the portrait box; regular (not smooth)
        # scale keeps the pixel-art edges crisp instead of blurring them.
        if profession not in self._portrait_cache:
            sprite = create_player_sprite("down", False, profession)
            self._portrait_cache[profession] = pygame.transform.scale(
                sprite, (_PORTRAIT_SIZE, _PORTRAIT_SIZE))
        return self._portrait_cache[profession]

    def _bestiary_sprite_for(self, key):
        if key not in self._bestiary_sprite_cache:
            sprite = boss_sprite(key) if key in BOSS_IDS else mob_sprite(key)
            self._bestiary_sprite_cache[key] = sprite
        return self._bestiary_sprite_cache[key]

    def handle_tap(self, input_mgr, player, save_state=None):
        for tab_id, rect in self.tab_buttons.items():
            if input_mgr.tapped_rect(rect):
                self.active_tab = tab_id
                return
        if self.active_tab == "stats":
            self._handle_tap_stats(input_mgr, player)
        elif self.active_tab == "spells":
            self._handle_tap_spells(input_mgr, player)
        elif self.active_tab == "bestiary":
            self._handle_tap_bestiary(input_mgr)
        elif self.active_tab == "atlas":
            self._handle_tap_atlas(input_mgr)

    def _handle_tap_bestiary(self, input_mgr):
        for i, rect in enumerate(self.bestiary_buttons):
            if input_mgr.tapped_rect(rect):
                self.bestiary_cursor = i
                return

    def _handle_tap_atlas(self, input_mgr):
        for i, rect in enumerate(self.atlas_buttons):
            if input_mgr.tapped_rect(rect):
                self.atlas_cursor = i
                return

    def _handle_tap_stats(self, input_mgr, player):
        for attr, rect in self.plus_buttons.items():
            if input_mgr.tapped_rect(rect):
                if player.unspent_points > 0:
                    setattr(player.stats, attr, getattr(player.stats, attr) + 1)
                    player.unspent_points -= 1
                    player.refresh_profession()
                return
        for attr, rect in self.minus_buttons.items():
            if input_mgr.tapped_rect(rect):
                current = getattr(player.stats, attr)
                if current > BASE_ATTR:
                    setattr(player.stats, attr, current - 1)
                    player.unspent_points += 1
                    player.refresh_profession()
                return

    def _handle_tap_spells(self, input_mgr, player):
        for spell_id, rect in self.select_buttons.items():
            if input_mgr.tapped_rect(rect):
                if meets_requirements(player.stats, spell_id):
                    player.selected_spell = spell_id
                return

    def handle_keys(self, input_mgr, player, save_state=None):
        if input_mgr.consume_action(Action.TAB_NEXT):
            idx = _TAB_ORDER.index(self.active_tab)
            self.active_tab = _TAB_ORDER[(idx + 1) % len(_TAB_ORDER)]
            return
        if self.active_tab == "stats":
            self._handle_keys_stats(input_mgr, player)
        elif self.active_tab == "spells":
            self._handle_keys_spells(input_mgr, player)
        elif self.active_tab == "bestiary":
            self._handle_keys_bestiary(input_mgr)
        elif self.active_tab == "atlas":
            self._handle_keys_atlas(input_mgr)

    def _handle_keys_bestiary(self, input_mgr):
        if input_mgr.consume_action(Action.MENU_LEFT):
            self.bestiary_cursor = (self.bestiary_cursor - 1) % len(BESTIARY_ORDER)
        if input_mgr.consume_action(Action.MENU_RIGHT):
            self.bestiary_cursor = (self.bestiary_cursor + 1) % len(BESTIARY_ORDER)
        if input_mgr.consume_action(Action.MENU_UP):
            self.bestiary_cursor = (self.bestiary_cursor - _BESTIARY_COLS) % len(BESTIARY_ORDER)
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.bestiary_cursor = (self.bestiary_cursor + _BESTIARY_COLS) % len(BESTIARY_ORDER)

    def _handle_keys_atlas(self, input_mgr):
        n = len(ATLAS_ORDER)
        if input_mgr.consume_action(Action.MENU_LEFT):
            self.atlas_cursor = (self.atlas_cursor - 1) % n
        if input_mgr.consume_action(Action.MENU_RIGHT):
            self.atlas_cursor = (self.atlas_cursor + 1) % n
        if input_mgr.consume_action(Action.MENU_UP):
            self.atlas_cursor = (self.atlas_cursor - _ATLAS_COLS) % n
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.atlas_cursor = (self.atlas_cursor + _ATLAS_COLS) % n

    def _handle_keys_stats(self, input_mgr, player):
        if input_mgr.consume_action(Action.MENU_UP):
            self.stats_cursor = (self.stats_cursor - 1) % len(ATTRS)
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.stats_cursor = (self.stats_cursor + 1) % len(ATTRS)
        attr, _ = ATTRS[self.stats_cursor]
        if input_mgr.consume_action(Action.MENU_LEFT):
            current = getattr(player.stats, attr)
            if current > BASE_ATTR:
                setattr(player.stats, attr, current - 1)
                player.unspent_points += 1
                player.refresh_profession()
        if input_mgr.consume_action(Action.MENU_RIGHT) or input_mgr.consume_action(Action.CONFIRM):
            if player.unspent_points > 0:
                setattr(player.stats, attr, getattr(player.stats, attr) + 1)
                player.unspent_points -= 1
                player.refresh_profession()

    def _handle_keys_spells(self, input_mgr, player):
        if input_mgr.consume_action(Action.MENU_UP):
            self.spell_cursor = (self.spell_cursor - 1) % len(SPELL_ORDER)
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.spell_cursor = (self.spell_cursor + 1) % len(SPELL_ORDER)
        if input_mgr.consume_action(Action.CONFIRM):
            spell_id = SPELL_ORDER[self.spell_cursor]
            if meets_requirements(player.stats, spell_id):
                player.selected_spell = spell_id

    @staticmethod
    def _glow_alpha():
        return int(90 + 60 * abs(math.sin(pygame.time.get_ticks() / 1000.0 * 4)))

    def _draw_glow(self, surface, rect):
        glow = pygame.Surface(rect.size, pygame.SRCALPHA)
        glow.fill((255, 215, 80, self._glow_alpha()))
        surface.blit(glow, rect.topleft)
        pygame.draw.rect(surface, (255, 225, 120), rect, 2, border_radius=6)

    def draw(self, surface, player, save_state=None, forced=False):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))

        f_tab = font(15 if len(_TAB_ORDER) <= 3 else 11, bold=True)
        tab_labels = {"stats": "STATUS", "spells": "MAGIAS", "bestiary": "BESTIARIO",
                      "atlas": "ATLAS", "help": "AJUDA"}
        for tab_id, rect in self.tab_buttons.items():
            active = tab_id == self.active_tab
            pygame.draw.rect(surface, (90, 60, 140) if active else (45, 40, 60), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 190, 220), rect, 1, border_radius=6)
            draw_text(surface, tab_labels[tab_id], f_tab, (255, 255, 255) if active else (170, 165, 185),
                      rect.centerx, rect.y + 6, shadow=False)

        content_top = self.py + _CONTENT_TOP
        if self.active_tab == "stats":
            self._draw_stats(surface, player, save_state, content_top, forced=forced and player.unspent_points > 0)
        elif self.active_tab == "spells":
            self._draw_spells(surface, player, save_state, content_top)
        elif self.active_tab == "bestiary":
            self._draw_bestiary(surface, player, save_state, content_top)
        elif self.active_tab == "atlas":
            self._draw_atlas(surface, save_state, content_top)
        elif self.active_tab == "help":
            self._draw_help(surface, content_top)

    def _draw_header(self, surface, player, save_state, top):
        cx = self.px + _PANEL_W // 2
        header_cx = self.px + _PORTRAIT_MARGIN + _PORTRAIT_SIZE + (
            _PANEL_W - _PORTRAIT_MARGIN * 2 - _PORTRAIT_SIZE) // 2

        portrait = self._portrait_for(player.profession)
        surface.blit(portrait, (self.px + _PORTRAIT_MARGIN, top + _PORTRAIT_MARGIN))

        f_title = font(24, bold=True)
        draw_text(surface, player.display_name, f_title, ACCENT_GOLD, header_cx, top + _TITLE_Y)

        # Stage G8: "Reputacao Profissao", same pattern as the HUD title
        # line (game/player.py's _draw_title_line) - replaces the
        # profession-only text that used to be here.
        from game.reputation import determine_reputation, kills_total, deaths_total
        reputation = determine_reputation(kills_total(player, save_state), deaths_total(save_state))
        f_prof = font(17, bold=True)
        draw_text(surface, f"{reputation} {player.profession}", f_prof, (210, 200, 235), header_cx, top + _PROFESSION_Y)

        f = font(16, bold=True)
        draw_text(surface, f"Nivel {player.level}  (XP {player.xp}/{self._xp_next(player)})",
                  f, (230, 230, 240), header_cx, top + _LEVEL_Y)
        return cx

    def _draw_stats(self, surface, player, save_state, top, forced=False):
        cx = self._draw_header(surface, player, save_state, top)

        f2 = font(14)
        s = player.stats
        attack_per_sec = 1.0 / s.attack_cooldown
        magic_bonus_pct = round(4 * s.intelligence)
        phys_mit = 100 - mitigate(100, s.physical_defense)
        magic_mit = 100 - mitigate(100, s.magic_defense)
        left_col = [
            f"Vida: {player.max_hp}",
            f"Dano fisico: {player.attack_damage}",
            f"Critico: {s.crit_chance*100:.0f}%",
            f"Dano critico: x{s.crit_damage_mult:.2f}",
            f"Haste: {attack_per_sec:.2f} atq/s",
            f"Dano magico: +{magic_bonus_pct}%",
            f"Poder de cura: +{(s.healing_power-1)*100:.0f}%",
        ]
        right_col = [
            f"Regen. vida: {s.hp_regen:.1f}/s",
            f"Def. fisica: {s.physical_defense:.0f} ({phys_mit:.0f}%)",
            f"Def. magica: {s.magic_defense:.0f} ({magic_mit:.0f}%)",
            f"Mana: {player.max_mana}",
            f"Regen. mana: {s.mana_regen:.2f}/s",
            f"Vel. movimento: {int(player.speed)}",
        ]
        left_x = self.px + 24
        right_x = self.px + _PANEL_W // 2 + 8
        for i, line in enumerate(left_col):
            draw_text(surface, line, f2, (210, 210, 225), left_x,
                      top + _DERIVED_START_Y + i * _DERIVED_LINE_H, shadow=False, align="left")
        for i, line in enumerate(right_col):
            draw_text(surface, line, f2, (210, 210, 225), right_x,
                      top + _DERIVED_START_Y + i * _DERIVED_LINE_H, shadow=False, align="left")

        pts_color = ACCENT_GOLD if player.unspent_points > 0 else SUBTEXT
        f3 = font(17, bold=True)
        draw_text(surface, f"Pontos disponiveis: {player.unspent_points}", f3, pts_color,
                  cx, top + _POINTS_Y)

        f_row = font(16)
        for i, (attr, label) in enumerate(ATTRS):
            y = top + _ATTR_START_Y + i * _ATTR_LINE_H
            if i == self.stats_cursor:
                self._draw_glow(surface, pygame.Rect(self.px + 12, y - 16, _PANEL_W - 24, 32))
            value = getattr(player.stats, attr)
            icon = create_attribute_icon(attr)
            surface.blit(icon, (self.px + 20, y - 8 - icon.get_height() // 2))
            draw_text(surface, f"{label}: {int(value)}", f_row, (225, 225, 235),
                      self.px + 150, y - 9, shadow=False)

            minus_rect = self.minus_buttons[attr]
            plus_rect = self.plus_buttons[attr]
            can_minus = value > BASE_ATTR
            can_plus = player.unspent_points > 0

            pygame.draw.rect(surface, (90, 25, 25) if can_minus else (45, 45, 45), minus_rect, border_radius=6)
            pygame.draw.rect(surface, (30, 210, 90) if can_plus else (45, 45, 45), plus_rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), minus_rect, 1, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), plus_rect, 1, border_radius=6)

            fb = font(18, bold=True)
            draw_text(surface, "-", fb, (255, 255, 255) if can_minus else (110, 110, 110),
                      minus_rect.centerx, minus_rect.y + 3, shadow=False)
            draw_text(surface, "+", fb, (255, 255, 255) if can_plus else (110, 110, 110),
                      plus_rect.centerx, plus_rect.y + 3, shadow=False)

        f_hint = font(14)
        if forced:
            hint = "Voce subiu de nivel! Distribua todos os pontos para continuar"
            hint_color = ACCENT_GOLD
        else:
            hint = "TAB troca aba | W/S seleciona | A/D distribui | C/ESC - Fechar"
            hint_color = SUBTEXT
        draw_text(surface, hint, f_hint, hint_color, cx, top + _HINT_Y)

    def _draw_spells(self, surface, player, save_state, top):
        self._draw_header(surface, player, save_state, top)

        f_name = font(17, bold=True)
        f_body = font(14)
        f_btn = font(13, bold=True)
        spell_cx = self.px + _PANEL_W // 2
        for i, spell_id in enumerate(SPELL_ORDER):
            spell = SPELLS[spell_id]
            y = top + _SPELL_START_Y + i * _SPELL_BLOCK_H
            if i == self.spell_cursor:
                self._draw_glow(surface, pygame.Rect(self.px + 12, y - 8, _PANEL_W - 24, _SPELL_BLOCK_H - 8))
            unlocked = meets_requirements(player.stats, spell_id)
            is_selected = player.selected_spell == spell_id
            status_color = (110, 230, 140) if unlocked else (220, 90, 90)

            # Stage G4 - fixed left gutter, independent of the row's
            # centered text block below (spell_cx), so it doesn't need to
            # restructure that existing layout.
            icon = pygame.transform.scale(create_spell_icon(spell_id), (28, 28))
            surface.blit(icon, (self.px + 20, y - 4))

            draw_text(surface, f"{SPELL_KEYS[i]} - {spell['name']}", f_name, (230, 225, 240),
                      spell_cx, y, shadow=False)
            draw_text(surface, spell["description"], f_body, (195, 195, 210),
                      spell_cx, y + 22, shadow=False)

            cost_bits = [f"Mana {spell['mana_cost']}"]
            if spell.get("cooldown"):
                cost_bits.append(f"CD {spell['cooldown']:.0f}s")
            req_bits = [f"{label} {have}/{need}" for label, have, need in missing_requirements(player.stats, spell_id)]
            if not req_bits:
                status_text = " | ".join(cost_bits) + " - Desbloqueada"
            else:
                status_text = " | ".join(cost_bits) + " - falta " + ", ".join(req_bits)
            draw_text(surface, status_text, f_body, status_color, spell_cx, y + 42, shadow=False)

            rect = self.select_buttons[spell_id]
            if is_selected:
                color, label = (30, 210, 90), "Selecionada"
            elif unlocked:
                color, label = (60, 100, 200), "Selecionar"
            else:
                color, label = (55, 55, 60), "Bloqueada"
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), rect, 1, border_radius=6)
            draw_text(surface, label, f_btn, (240, 240, 245), rect.centerx, rect.y + 6, shadow=False)

        f_hint = font(14)
        draw_text(surface, "TAB troca aba | W/S seleciona | ESPACO seleciona magia | C/ESC - Fechar", f_hint, SUBTEXT,
                  self.px + _PANEL_W // 2, top + _SPELL_START_Y + len(SPELL_ORDER) * _SPELL_BLOCK_H + 10)

    def _draw_bestiary(self, surface, player, save_state, top):
        f_key = font(12, bold=True)
        for i, key in enumerate(BESTIARY_ORDER):
            rect = self.bestiary_buttons[i]
            discovered = save_state is not None and is_discovered(save_state, player, key)
            if i == self.bestiary_cursor:
                self._draw_glow(surface, rect.inflate(6, 6))
            pygame.draw.rect(surface, (35, 30, 50), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210) if discovered else (90, 90, 100), rect, 1, border_radius=6)
            if discovered:
                sprite = self._bestiary_sprite_for(key)
                scaled = pygame.transform.scale(sprite, (rect.width - 12, rect.height - 12))
                surface.blit(scaled, (rect.x + 6, rect.y + 6))
            else:
                q = f_key.render("?", True, (110, 110, 120))
                surface.blit(q, (rect.centerx - q.get_width() // 2, rect.centery - q.get_height() // 2))

        cx = self.px + _PANEL_W // 2
        key = BESTIARY_ORDER[self.bestiary_cursor]
        discovered = save_state is not None and is_discovered(save_state, player, key)

        f_name = font(19, bold=True)
        f_body = font(14)
        if not discovered:
            draw_text(surface, "???", f_name, SUBTEXT, cx, top + _BESTIARY_DETAIL_Y)
            draw_text(surface, "Derrote esse inimigo para descobri-lo.", f_body, SUBTEXT,
                      cx, top + _BESTIARY_DETAIL_Y + 30)
        else:
            entry = BESTIARY[key]
            is_boss = key in BOSS_IDS
            stats = boss_stats(key) if is_boss else mob_stats(key)
            attacks = boss_attacks(key) if is_boss else mob_attacks(key)

            y = top + _BESTIARY_DETAIL_Y
            draw_text(surface, entry["name"], f_name, ACCENT_GOLD, cx, y)
            y += 28

            for line in self._wrap_text(entry["description"], f_body, _PANEL_W - 48):
                draw_text(surface, line, f_body, (210, 210, 225), cx, y, shadow=False)
                y += 18
            y += 6

            attrs_line = (f"FOR {stats.strength:.0f}  DES {stats.dexterity:.0f}  INT {stats.intelligence:.0f}  "
                          f"SAB {stats.wisdom:.0f}  VIG {stats.vigor:.0f}  SOR {stats.luck:.0f}")
            draw_text(surface, attrs_line, f_body, (190, 190, 210), cx, y, shadow=False)
            y += 18
            derived_line = (f"Vida {stats.max_hp}  Dano fis. {stats.physical_damage}  "
                             f"Def. fis. {stats.physical_defense:.0f}  Def. mag. {stats.magic_defense:.0f}")
            draw_text(surface, derived_line, f_body, (190, 190, 210), cx, y, shadow=False)
            y += 22

            if attacks:
                for line in attacks:
                    draw_text(surface, f"- {line}", f_body, (200, 175, 220), cx, y, shadow=False)
                    y += 18
            else:
                draw_text(surface, "- Apenas ataque corpo a corpo", f_body, (200, 175, 220), cx, y, shadow=False)

        f_hint = font(14)
        draw_text(surface, "TAB troca aba | setas navegam | C/ESC - Fechar", f_hint, SUBTEXT,
                  cx, self.py + _PANEL_H - 30)

    def _draw_atlas(self, surface, save_state, top):
        levels_seen = set(save_state["progression"]["levels_seen"]) if save_state else set()
        levels_seen.add(1)  # the first level is always visible, even on a fresh save

        f_key = font(20, bold=True)
        for i, level_num in enumerate(ATLAS_ORDER):
            rect = self.atlas_buttons[i]
            seen = level_num in levels_seen
            if i == self.atlas_cursor:
                self._draw_glow(surface, rect.inflate(6, 6))
            pygame.draw.rect(surface, (35, 30, 50), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210) if seen else (90, 90, 100), rect, 1, border_radius=6)
            if seen:
                thumb = create_level_thumbnail(LEVEL_MAPS[level_num]["floor"], LEVEL_MAPS[level_num]["bg"])
                scaled = pygame.transform.scale(thumb, (rect.width - 10, rect.height - 18))
                surface.blit(scaled, (rect.x + 5, rect.y + 5))
                num = font(11, bold=True).render(str(level_num), True, (220, 220, 230))
                surface.blit(num, (rect.centerx - num.get_width() // 2, rect.bottom - 14))
            else:
                q = f_key.render("?", True, (110, 110, 120))
                surface.blit(q, (rect.centerx - q.get_width() // 2, rect.centery - q.get_height() // 2))

        cx = self.px + _PANEL_W // 2
        level_num = ATLAS_ORDER[self.atlas_cursor]
        seen = level_num in levels_seen
        data = LEVEL_MAPS[level_num]

        f_name = font(19, bold=True)
        f_body = font(14)
        y = top + _ATLAS_DETAIL_Y
        if not seen:
            draw_text(surface, "???", f_name, SUBTEXT, cx, y)
            draw_text(surface, "Alcance esta fase para revela-la no Atlas.", f_body, SUBTEXT, cx, y + 30)
        else:
            draw_text(surface, f"Fase {level_num}: {data['title']}", f_name, ACCENT_GOLD, cx, y)
            y += 26

            for line in self._wrap_text(data.get("description", ""), f_body, _PANEL_W - 48):
                draw_text(surface, line, f_body, (210, 210, 225), cx, y, shadow=False)
                y += 18
            y += 4

            mob_ids = list(dict.fromkeys(data.get("enemies", [])))
            mob_names = ", ".join(BESTIARY[m]["name"] for m in mob_ids if m in BESTIARY)
            boss_key = data.get("boss")
            if boss_key and boss_key in BESTIARY:
                mob_names = (mob_names + ", " if mob_names else "") + f"{BESTIARY[boss_key]['name']} (Chefe)"
            draw_text(surface, f"Monstros: {mob_names or 'nenhum'}", f_body, (200, 175, 220), cx, y, shadow=False)
            y += 20

            weather_id = data.get("weather")
            if weather_id:
                weather_name = WEATHER_DISPLAY_NAME.get(weather_id, weather_id)
                debuff = WEATHER_TYPES.get(weather_id, {}).get("debuff")
                draw_text(surface, f"Clima: {weather_name}", f_body, (190, 210, 230), cx, y, shadow=False)
                if debuff:
                    icon = create_debuff_icon(debuff[0])
                    icon_x = cx + f_body.size(f"Clima: {weather_name}")[0] // 2 + 8
                    surface.blit(icon, (icon_x, y + 1))
            else:
                draw_text(surface, "Clima: nenhum", f_body, (190, 210, 230), cx, y, shadow=False)

        f_hint = font(14)
        draw_text(surface, "TAB troca aba | setas navegam | C/ESC - Fechar", f_hint, SUBTEXT,
                  cx, self.py + _PANEL_H - 30)

    def _draw_help(self, surface, top):
        cx = self.px + _PANEL_W // 2
        f_title = font(19, bold=True)
        draw_text(surface, "ATALHOS", f_title, ACCENT_GOLD, cx, top + 6)

        f_key = font(15, bold=True)
        f_desc = font(14)
        key_x = self.px + 24
        desc_x = self.px + 190
        y = top + 42
        for key_label, description in HELP_ENTRIES:
            draw_text(surface, key_label, f_key, ACCENT_GOLD, key_x, y, shadow=False, align="left")
            for line in self._wrap_text(description, f_desc, self.px + _PANEL_W - 24 - desc_x):
                draw_text(surface, line, f_desc, (210, 210, 225), desc_x, y, shadow=False, align="left")
                y += 17
            y += 12

        f_hint = font(14)
        draw_text(surface, "TAB troca aba | C/ESC - Fechar", f_hint, SUBTEXT,
                  cx, self.py + _PANEL_H - 30)

    @staticmethod
    def _wrap_text(text, f, max_width):
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if f.size(trial)[0] > max_width and current:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines

    @staticmethod
    def _xp_next(player):
        from game.stats import xp_to_next, MAX_LEVEL
        if player.level >= MAX_LEVEL:
            return player.xp
        return xp_to_next(player.level)
