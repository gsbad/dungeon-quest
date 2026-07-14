"""
Stage K15: Configuracoes overlay - lists every remappable action
(game/keybinds.py's REMAPPABLE) with its current key, lets the player
capture a new one. Same full-screen-panel/row-cursor pattern as
game/merchant.py's ItemsOverlay (no Carousel needed - REMAPPABLE plus the
"restaurar padroes" row fits on one page with room to spare).
"""
import math
import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.input_system import Action
import game.keybinds as keybinds

_ROW_H = 34
_ROWS_START_Y = 90
_PANEL_W = 380
_PANEL_H = 90 + (len(keybinds.REMAPPABLE) + 1) * _ROW_H + 60


class SettingsOverlay:
    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = 40
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.cursor = 0
        self._n_rows = len(keybinds.REMAPPABLE) + 1  # + "Restaurar padroes"
        self._capturing_row = None
        self._collision_msg = ""
        # Wall-clock expiry (pygame.time.get_ticks(), ms) rather than a
        # dt-decremented countdown - handle_keys()/handle_tap() don't
        # receive dt (same signature as ItemsOverlay's), so there's nowhere
        # to tick a countdown down without adding a dt param just for this.
        self._collision_until_ms = 0

    def _row_rect(self, index):
        y = self.py + _ROWS_START_Y + index * _ROW_H
        return pygame.Rect(self.px + 14, y - 16, _PANEL_W - 28, 32)

    def _start_capture(self, input_mgr, index, save_state):
        # "Restaurar padroes" (the row after REMAPPABLE) isn't a capture at
        # all - it takes effect immediately, no keypress to wait for.
        if index >= len(keybinds.REMAPPABLE):
            keybinds.reset_defaults()
            if save_state is not None:
                self._persist(save_state)
            return
        name = keybinds.REMAPPABLE[index]
        self._capturing_row = index

        def on_key(key_code):
            self._capturing_row = None
            if keybinds.is_bound_elsewhere(name, key_code):
                self._collision_msg = "Tecla ja usada por outra acao"
                self._collision_until_ms = pygame.time.get_ticks() + 2000
                return
            keybinds.set_binding(name, key_code)
            if save_state is not None:
                self._persist(save_state)

        input_mgr.begin_key_capture(on_key)

    def handle_keys(self, input_mgr, player=None, save_state=None):
        if self._capturing_row is not None:
            return  # swallowed by InputManager's capture callback instead
        if input_mgr.consume_action(Action.MENU_UP):
            self.cursor = (self.cursor - 1) % self._n_rows
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.cursor = (self.cursor + 1) % self._n_rows
        if input_mgr.consume_action(Action.CONFIRM):
            self._start_capture(input_mgr, self.cursor, save_state)

    def handle_tap(self, input_mgr, player=None, save_state=None):
        for i in range(self._n_rows):
            if input_mgr.tapped_rect(self._row_rect(i)):
                self.cursor = i
                self._start_capture(input_mgr, i, save_state)
                return

    def _persist(self, save_state):
        import game.save as save
        import game.net as net
        save_state["settings"]["keybinds"] = dict(keybinds.BINDINGS)
        save.save(save_state)
        net.trigger_sync(save_state)

    def draw(self, surface, save_state=None):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + _PANEL_W // 2
        label_cx = self.px + 26

        f_title = font(24, bold=True)
        draw_text(surface, "CONFIGURACOES", f_title, ACCENT_GOLD, cx, self.py + 20)

        glow_rect = self._row_rect(self.cursor)
        alpha = int(90 + 60 * abs(math.sin(pygame.time.get_ticks() / 1000.0 * 4)))
        glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
        glow.fill((255, 215, 80, alpha))
        surface.blit(glow, glow_rect.topleft)
        pygame.draw.rect(surface, (255, 225, 120), glow_rect, 2, border_radius=6)

        f_row = font(15)
        f_key = font(14, bold=True)
        for i, name in enumerate(keybinds.REMAPPABLE):
            y = self.py + _ROWS_START_Y + i * _ROW_H
            draw_text(surface, keybinds.ACTION_LABELS[name], f_row, (215, 215, 225), label_cx, y - 8,
                      shadow=False, align="left")
            if self._capturing_row == i:
                key_text = "..."
                color = (255, 225, 120)
            else:
                key_text = keybinds.key_name(keybinds.BINDINGS[name])
                color = (230, 230, 240)
            key_rect = pygame.Rect(self.px + _PANEL_W - 90, y - 14, 66, 26)
            pygame.draw.rect(surface, (45, 45, 55), key_rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), key_rect, 1, border_radius=6)
            draw_text(surface, key_text, f_key, color, key_rect.centerx, key_rect.y + 5, shadow=False)

        reset_y = self.py + _ROWS_START_Y + len(keybinds.REMAPPABLE) * _ROW_H
        reset_label = "..." if self._capturing_row == len(keybinds.REMAPPABLE) else "Restaurar padroes"
        draw_text(surface, reset_label, f_row, (255, 180, 140), cx, reset_y - 8, shadow=False)

        if pygame.time.get_ticks() < self._collision_until_ms:
            draw_text(surface, self._collision_msg, font(13, bold=True), (255, 120, 120),
                       cx, reset_y + 26, shadow=False)

        f_hint = font(13)
        hint = "W/S seleciona | ESPACO captura nova tecla | ESC - Fechar"
        draw_text(surface, hint, f_hint, SUBTEXT, cx, self.py + _PANEL_H - 20)
