"""
Leaderboard overlay (Stage J8-J10) - read-only ranking fetched from the
backend's public GET /leaderboard (backend/app/main.py's get_leaderboard()).
Viewing needs no login, but only players who've synced via Google at least
once ever appear in the results - a fully-offline save has no SaveRow on
the server at all, so "offline play doesn't affect the rank" falls out of
the existing sync architecture for free, nothing new to enforce here.

First real consumer of game/net.py's schedule()/poll_result() fire-and-
forget pair (built in Stage I6 for exactly this "one-off GET, apply the
result whenever it lands" shape, never actually used until now).
"""
import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.assets import create_trophy_icon
from game.input_system import Action
import game.net as net

_PANEL_W = 400
_PANEL_H = 440
_FILTERS = [
    ("level", "NIVEL"),
    ("playtime", "HORAS"),
    ("achievements", "CONQUISTAS"),
    ("gold", "OURO"),
]
_ROW_H = 30
_MAX_ROWS = 10
_RANK_TIERS = {0: "gold", 1: "silver", 2: "bronze"}


def _format_value(sort_id, value):
    if sort_id == "playtime":
        return f"{value / 3600:.1f}h"
    if sort_id == "gold":
        return f"{int(value)}g"
    return str(int(value))


class LeaderboardOverlay:
    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = SH // 2 - _PANEL_H // 2
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.filter_idx = 0
        # sort_id -> "loading" | "error" | list[{"name","value"}] - kept
        # across filter switches so flipping back to an already-fetched
        # filter is instant, not a re-fetch.
        self._cache = {}
        self._pending_tag = None
        self._pending_sort = None

        n = len(_FILTERS)
        gap = 6
        btn_w = (_PANEL_W - 24 - gap * (n - 1)) // n
        self.filter_buttons = []
        for i in range(n):
            x = self.px + 12 + i * (btn_w + gap)
            self.filter_buttons.append(pygame.Rect(x, self.py + 44, btn_w, 26))

    def _current_sort(self):
        return _FILTERS[self.filter_idx][0]

    def open(self):
        """Called every time the overlay is opened (states.py's
        toggle_leaderboard()) - cheap no-op if that filter's already
        cached, so reopening the panel doesn't spam refetches."""
        self._fetch_if_needed()

    def _fetch_if_needed(self):
        sort_id = self._current_sort()
        if sort_id in self._cache or self._pending_tag is not None:
            return
        self._cache[sort_id] = "loading"
        self._pending_sort = sort_id
        self._pending_tag = net.schedule(f"/leaderboard?sort={sort_id}", "GET", jwt=net.get_jwt())

    def update(self):
        if self._pending_tag is None:
            return
        result = net.poll_result(self._pending_tag)
        if result is None:
            return
        status, value = result
        self._cache[self._pending_sort] = value.get("entries", []) if status == "ok" else "error"
        self._pending_tag = None
        self._pending_sort = None

    def handle_tap(self, input_mgr):
        for i, rect in enumerate(self.filter_buttons):
            if input_mgr.tapped_rect(rect):
                self.filter_idx = i
                self._fetch_if_needed()
                return

    def handle_keys(self, input_mgr):
        if input_mgr.consume_action(Action.MENU_LEFT):
            self.filter_idx = (self.filter_idx - 1) % len(_FILTERS)
            self._fetch_if_needed()
        if input_mgr.consume_action(Action.MENU_RIGHT):
            self.filter_idx = (self.filter_idx + 1) % len(_FILTERS)
            self._fetch_if_needed()

    def draw(self, surface):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))
        self.panel.draw(surface, (self.px, self.py))

        cx = self.px + _PANEL_W // 2
        f_title = font(20, bold=True)
        draw_text(surface, "RANKING", f_title, ACCENT_GOLD, cx, self.py + 12)

        f_tab = font(13, bold=True)
        sort_id = self._current_sort()
        for i, (fid, label) in enumerate(_FILTERS):
            rect = self.filter_buttons[i]
            active = i == self.filter_idx
            pygame.draw.rect(surface, (90, 60, 140) if active else (45, 40, 60), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 190, 220), rect, 1, border_radius=6)
            draw_text(surface, label, f_tab, (255, 255, 255) if active else (170, 165, 185),
                      rect.centerx, rect.y + 6, shadow=False)

        list_top = self.py + 84
        data = self._cache.get(sort_id)
        f_row = font(14)
        f_name = font(14, bold=True)
        if data is None or data == "loading":
            draw_text(surface, "Carregando...", f_row, SUBTEXT, cx, list_top + 20)
        elif data == "error":
            draw_text(surface, "Nao foi possivel carregar o ranking.", f_row, (220, 120, 120), cx, list_top + 20)
        elif not data:
            draw_text(surface, "Ninguem no ranking ainda.", f_row, SUBTEXT, cx, list_top + 20)
            draw_text(surface, "Faca login com Google para aparecer aqui.", f_row, SUBTEXT, cx, list_top + 44)
        else:
            for i, entry in enumerate(data[:_MAX_ROWS]):
                y = list_top + i * _ROW_H
                tier = _RANK_TIERS.get(i)
                if tier:
                    icon = pygame.transform.scale(create_trophy_icon(tier), (22, 22))
                    surface.blit(icon, (self.px + 20, y))
                else:
                    draw_text(surface, str(i + 1), f_row, SUBTEXT, self.px + 31, y + 3, shadow=False)
                draw_text(surface, entry["name"], f_name, (225, 225, 235), self.px + 54, y + 3,
                          shadow=False, align="left")
                value_text = _format_value(sort_id, entry["value"])
                value_surf = f_name.render(value_text, True, ACCENT_GOLD)
                surface.blit(value_surf, (self.px + _PANEL_W - 20 - value_surf.get_width(), y + 3))

        f_hint = font(13)
        draw_text(surface, "A/D muda filtro | L/ESC - Fechar", f_hint, SUBTEXT,
                  cx, self.py + _PANEL_H - 20)
