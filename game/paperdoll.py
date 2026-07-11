import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text

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

# Layout, relative to the panel's top (self.py). Six derived-stat lines now
# (was four) - DEX's speed formula (game/stats.py) buffs movement speed with
# a small capped bonus but attack speed is DEX's *primary* effect, so both
# get their own row instead of a single ambiguous "Velocidade".
_TITLE_Y = 16
_LEVEL_Y = 50
_DERIVED_START_Y = 82
_DERIVED_LINE_H = 22
_DERIVED_LINES = 6
_POINTS_Y = _DERIVED_START_Y + _DERIVED_LINE_H * _DERIVED_LINES + 20
_ATTR_START_Y = _POINTS_Y + 40
_ATTR_LINE_H = 36
_HINT_Y = _ATTR_START_Y + _ATTR_LINE_H * len(ATTRS) + 16
_PANEL_H = _HINT_Y + 30


class Paperdoll:
    """Aba 1 do redesign de RPG (Stage A6): retrato/stats, gasto de pontos,
    respec gratuito. Abas 2 (magias) e 3 (ajuda) chegam no Stage B, junto
    com os sistemas (spells.py, dificuldades) que dão a elas o que mostrar."""

    def __init__(self):
        self.px = SW // 2 - 180
        self.py = 55
        self.panel = Panel(360, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.plus_buttons = {}
        self.minus_buttons = {}
        for i, (attr, _) in enumerate(ATTRS):
            y = self.py + _ATTR_START_Y + i * _ATTR_LINE_H
            self.minus_buttons[attr] = pygame.Rect(self.px + 260, y - 14, 28, 28)
            self.plus_buttons[attr] = pygame.Rect(self.px + 300, y - 14, 28, 28)

    def handle_tap(self, input_mgr, player):
        for attr, rect in self.plus_buttons.items():
            if input_mgr.tapped_rect(rect):
                if player.unspent_points > 0:
                    setattr(player.stats, attr, getattr(player.stats, attr) + 1)
                    player.unspent_points -= 1
                return
        for attr, rect in self.minus_buttons.items():
            if input_mgr.tapped_rect(rect):
                current = getattr(player.stats, attr)
                if current > BASE_ATTR:
                    setattr(player.stats, attr, current - 1)
                    player.unspent_points += 1
                return

    def draw(self, surface, player):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + 180

        f_title = font(26, bold=True)
        draw_text(surface, player.name or "Heroi", f_title, ACCENT_GOLD, cx, self.py + _TITLE_Y)

        f = font(18, bold=True)
        draw_text(surface, f"Nivel {player.level}  (XP {player.xp}/{self._xp_next(player)})",
                  f, (230, 230, 240), cx, self.py + _LEVEL_Y)

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
                      self.px + 140, y - 9, shadow=False)

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
