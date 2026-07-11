import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.assets import create_player_sprite
from game.professions import TINTS

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
_PANEL_H = _HINT_Y + 26


class Paperdoll:
    """Aba 1 do redesign de RPG (Stage A7): retrato/profissao/stats, gasto
    de pontos, respec gratuito. Abas 2 (magias) e 3 (ajuda) chegam no Stage
    B, junto com os sistemas (spells.py, dificuldades) que dao a elas o
    que mostrar."""

    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = 40
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.plus_buttons = {}
        self.minus_buttons = {}
        for i, (attr, _) in enumerate(ATTRS):
            y = self.py + _ATTR_START_Y + i * _ATTR_LINE_H
            self.minus_buttons[attr] = pygame.Rect(self.px + 260, y - 14, 28, 28)
            self.plus_buttons[attr] = pygame.Rect(self.px + 300, y - 14, 28, 28)
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

    def draw(self, surface, player):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + _PANEL_W // 2
        header_cx = self.px + _PORTRAIT_MARGIN + _PORTRAIT_SIZE + (
            _PANEL_W - _PORTRAIT_MARGIN * 2 - _PORTRAIT_SIZE) // 2

        portrait = self._portrait_for(player.profession)
        surface.blit(portrait, (self.px + _PORTRAIT_MARGIN, self.py + _PORTRAIT_MARGIN))

        f_title = font(24, bold=True)
        draw_text(surface, player.name or "Heroi", f_title, ACCENT_GOLD, header_cx, self.py + _TITLE_Y)

        f_prof = font(17, bold=True)
        draw_text(surface, player.profession, f_prof, (210, 200, 235), header_cx, self.py + _PROFESSION_Y)

        f = font(16, bold=True)
        draw_text(surface, f"Nivel {player.level}  (XP {player.xp}/{self._xp_next(player)})",
                  f, (230, 230, 240), header_cx, self.py + _LEVEL_Y)

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
                      self.py + _DERIVED_START_Y + i * _DERIVED_LINE_H, shadow=False)

        pts_color = ACCENT_GOLD if player.unspent_points > 0 else SUBTEXT
        f3 = font(17, bold=True)
        draw_text(surface, f"Pontos disponiveis: {player.unspent_points}", f3, pts_color,
                  cx, self.py + _POINTS_Y)

        f_row = font(16)
        for i, (attr, label) in enumerate(ATTRS):
            y = self.py + _ATTR_START_Y + i * _ATTR_LINE_H
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
                  cx, self.py + _HINT_Y)

    @staticmethod
    def _xp_next(player):
        from game.stats import xp_to_next, MAX_LEVEL
        if player.level >= MAX_LEVEL:
            return player.xp
        return xp_to_next(player.level)
