import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.assets import create_player_sprite
from game.professions import TINTS
from game.spells import SPELLS, ORDER as SPELL_ORDER, meets_requirements, missing_requirements

# (StatBlock field name, on-screen label). Order matches the plan's
# STR/DEX/INT/WIS/VIG convention.
ATTRS = [
    ("strength", "FOR (dano)"),
    ("dexterity", "DES (vel. ataque)"),
    ("intelligence", "INT (mana)"),
    ("wisdom", "SAB (dano magico)"),
    ("vigor", "VIG (vida)"),
]

BASE_ATTR = 10  # can't respec below this - it's the unbuilt baseline, not spent points

_PANEL_W = 420
_CONTENT_TOP = 40  # room for the tab bar above the header
_PORTRAIT_SIZE = 96
_PORTRAIT_MARGIN = 16
# Header row: portrait on the left, name/profession/level text to its right.
_HEADER_H = _PORTRAIT_MARGIN + _PORTRAIT_SIZE + 14
_TITLE_Y = 20
_PROFESSION_Y = 52
_LEVEL_Y = 82

# Six derived-stat lines - DEX's speed formula (game/stats.py) buffs movement
# speed with a small capped bonus but attack speed is DEX's *primary*
# effect, so both get their own row instead of a single ambiguous "Velocidade".
_DERIVED_START_Y = _HEADER_H + 10
_DERIVED_LINE_H = 22
_DERIVED_LINES = 6
_POINTS_Y = _DERIVED_START_Y + _DERIVED_LINE_H * _DERIVED_LINES + 14
_ATTR_START_Y = _POINTS_Y + 30
_ATTR_LINE_H = 36
_HINT_Y = _ATTR_START_Y + _ATTR_LINE_H * len(ATTRS) + 12
_PANEL_H = _CONTENT_TOP + _HINT_Y + 26

_SPELL_START_Y = _HEADER_H + 16
_SPELL_BLOCK_H = 100


class Paperdoll:
    """Painel do personagem (Stage A7/B2), duas abas: Status (retrato,
    profissao, stats, gasto de pontos) e Magias (requisitos, status,
    selecao). Aba 3 (ajuda) chega no Stage B6 junto do sistema de
    conquistas que ela documenta."""

    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = 20
        self.active_tab = "stats"
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)

        tab_w, tab_h, gap = 150, 28, 10
        pair_w = tab_w * 2 + gap
        tab_x0 = self.px + (_PANEL_W - pair_w) // 2
        tab_y = self.py + 8
        self.tab_buttons = {
            "stats": pygame.Rect(tab_x0, tab_y, tab_w, tab_h),
            "spells": pygame.Rect(tab_x0 + tab_w + gap, tab_y, tab_w, tab_h),
        }

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

        # Base sprite is 48x48 (16px canvas at 3x scale) - 2x again to fill
        # the portrait box. Regular (not smooth) scale keeps the pixel-art
        # edges crisp instead of blurring them.
        base_sprite = create_player_sprite("down", False)
        self._base_portrait = pygame.transform.scale(base_sprite, (_PORTRAIT_SIZE, _PORTRAIT_SIZE))
        self._portrait_cache = {}

    def _portrait_for(self, profession):
        if profession not in self._portrait_cache:
            tint = TINTS.get(profession, (255, 255, 255))
            tinted = self._base_portrait.copy()
            overlay = pygame.Surface((_PORTRAIT_SIZE, _PORTRAIT_SIZE), pygame.SRCALPHA)
            overlay.fill((*tint, 255))
            tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._portrait_cache[profession] = tinted
        return self._portrait_cache[profession]

    def handle_tap(self, input_mgr, player):
        for tab_id, rect in self.tab_buttons.items():
            if input_mgr.tapped_rect(rect):
                self.active_tab = tab_id
                return
        if self.active_tab == "stats":
            self._handle_tap_stats(input_mgr, player)
        elif self.active_tab == "spells":
            self._handle_tap_spells(input_mgr, player)

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

    def draw(self, surface, player):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))

        f_tab = font(15, bold=True)
        for tab_id, rect in self.tab_buttons.items():
            active = tab_id == self.active_tab
            label = "STATUS" if tab_id == "stats" else "MAGIAS"
            pygame.draw.rect(surface, (90, 60, 140) if active else (45, 40, 60), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 190, 220), rect, 1, border_radius=6)
            draw_text(surface, label, f_tab, (255, 255, 255) if active else (170, 165, 185),
                      rect.centerx, rect.y + 6, shadow=False)

        content_top = self.py + _CONTENT_TOP
        if self.active_tab == "stats":
            self._draw_stats(surface, player, content_top)
        elif self.active_tab == "spells":
            self._draw_spells(surface, player, content_top)

    def _draw_header(self, surface, player, top):
        cx = self.px + _PANEL_W // 2
        header_cx = self.px + _PORTRAIT_MARGIN + _PORTRAIT_SIZE + (
            _PANEL_W - _PORTRAIT_MARGIN * 2 - _PORTRAIT_SIZE) // 2

        portrait = self._portrait_for(player.profession)
        surface.blit(portrait, (self.px + _PORTRAIT_MARGIN, top + _PORTRAIT_MARGIN))

        f_title = font(24, bold=True)
        draw_text(surface, player.name or "Heroi", f_title, ACCENT_GOLD, header_cx, top + _TITLE_Y)

        f_prof = font(17, bold=True)
        draw_text(surface, player.profession, f_prof, (210, 200, 235), header_cx, top + _PROFESSION_Y)

        f = font(16, bold=True)
        draw_text(surface, f"Nivel {player.level}  (XP {player.xp}/{self._xp_next(player)})",
                  f, (230, 230, 240), header_cx, top + _LEVEL_Y)
        return cx

    def _draw_stats(self, surface, player, top):
        cx = self._draw_header(surface, player, top)

        f2 = font(16)
        attack_per_sec = 1.0 / player.stats.attack_cooldown
        magic_bonus_pct = round(4 * player.stats.wisdom)
        derived = [
            f"Vida maxima: {player.max_hp}",
            f"Dano de ataque: {player.attack_damage}",
            f"Mana maxima: {player.max_mana}",
            f"Velocidade de movimento: {int(player.speed)}",
            f"Velocidade de ataque: {attack_per_sec:.2f}/s",
            f"Bonus de dano magico: +{magic_bonus_pct}%",
        ]
        for i, line in enumerate(derived):
            draw_text(surface, line, f2, (210, 210, 225), cx,
                      top + _DERIVED_START_Y + i * _DERIVED_LINE_H, shadow=False)

        pts_color = ACCENT_GOLD if player.unspent_points > 0 else SUBTEXT
        f3 = font(17, bold=True)
        draw_text(surface, f"Pontos disponiveis: {player.unspent_points}", f3, pts_color,
                  cx, top + _POINTS_Y)

        f_row = font(16)
        for i, (attr, label) in enumerate(ATTRS):
            y = top + _ATTR_START_Y + i * _ATTR_LINE_H
            value = getattr(player.stats, attr)
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
        draw_text(surface, "C / toque no botao - Fechar", f_hint, SUBTEXT,
                  cx, top + _HINT_Y)

    def _draw_spells(self, surface, player, top):
        self._draw_header(surface, player, top)

        f_name = font(17, bold=True)
        f_body = font(14)
        f_btn = font(13, bold=True)
        spell_cx = self.px + _PANEL_W // 2
        for i, spell_id in enumerate(SPELL_ORDER):
            spell = SPELLS[spell_id]
            y = top + _SPELL_START_Y + i * _SPELL_BLOCK_H
            unlocked = meets_requirements(player.stats, spell_id)
            is_selected = player.selected_spell == spell_id
            status_color = (110, 230, 140) if unlocked else (220, 90, 90)

            draw_text(surface, f"{i+1}. {spell['name']}", f_name, (230, 225, 240),
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
        draw_text(surface, "1/2/3 conjura direto - C / toque no botao - Fechar", f_hint, SUBTEXT,
                  self.px + _PANEL_W // 2, top + _SPELL_START_Y + len(SPELL_ORDER) * _SPELL_BLOCK_H + 10)

    @staticmethod
    def _xp_next(player):
        from game.stats import xp_to_next, MAX_LEVEL
        if player.level >= MAX_LEVEL:
            return player.xp
        return xp_to_next(player.level)
