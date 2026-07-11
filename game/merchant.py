import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.items import ITEMS, use_item, buy_item

_ROW_H = 34
_SEUS_ITENS_START_Y = 110
_LOJA_HEADER_Y = 230
_LOJA_START_Y = 260
_HINT_Y = 410
_PANEL_H = 440


class ItemsOverlay:
    """Overlay "Itens" (RPG systems expansion, step 4/6): seus itens (usar)
    + loja (comprar) na mesma tela - mesmo padrão do Paperdoll (tela cheia,
    congela o jogo, tecla + botao mobile)."""

    def __init__(self):
        self.px = SW // 2 - 190
        self.py = 50
        self.panel = Panel(380, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.use_buttons = {}
        self.buy_buttons = {}
        for i, item_id in enumerate(ITEMS):
            y_use = self.py + _SEUS_ITENS_START_Y + i * _ROW_H
            self.use_buttons[item_id] = pygame.Rect(self.px + 280, y_use - 13, 66, 26)
        for i, item_id in enumerate(ITEMS):
            y_buy = self.py + _LOJA_START_Y + i * _ROW_H
            self.buy_buttons[item_id] = pygame.Rect(self.px + 280, y_buy - 13, 66, 26)

    def handle_tap(self, input_mgr, player, save_state=None):
        for item_id, rect in self.use_buttons.items():
            if input_mgr.tapped_rect(rect):
                use_item(player, item_id)
                return
        for item_id, rect in self.buy_buttons.items():
            if input_mgr.tapped_rect(rect):
                # Persisted immediately (not just at the next level-exit
                # checkpoint) - spending gold is a deliberate action, same
                # tier of importance as the mute-toggle immediate-persist.
                if buy_item(player, item_id) and save_state is not None:
                    import game.save as save
                    save.sync_economy(save_state, player)
                    save.save(save_state)
                return

    def draw(self, surface, player):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + 190
        label_cx = self.px + 130

        f_title = font(26, bold=True)
        draw_text(surface, "ITENS", f_title, ACCENT_GOLD, cx, self.py + 16)

        f_gold = font(17, bold=True)
        draw_text(surface, f"Ouro: {player.gold}", f_gold, (230, 200, 80), cx, self.py + 48)

        f_section = font(18, bold=True)
        f_row = font(15)
        fb = font(14, bold=True)

        draw_text(surface, "SEUS ITENS", f_section, (220, 220, 230), cx, self.py + 78, shadow=False)
        for i, item_id in enumerate(ITEMS):
            y = self.py + _SEUS_ITENS_START_Y + i * _ROW_H
            count = player.inventory.get(item_id, 0)
            name = ITEMS[item_id]["name"]
            draw_text(surface, f"{name} x{count}", f_row, (215, 215, 225), label_cx, y - 8, shadow=False)

            rect = self.use_buttons[item_id]
            can_use = count > 0
            pygame.draw.rect(surface, (30, 140, 60) if can_use else (50, 50, 50), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), rect, 1, border_radius=6)
            draw_text(surface, "Usar", fb, (255, 255, 255) if can_use else (120, 120, 120),
                      rect.centerx, rect.y + 5, shadow=False)

        draw_text(surface, "LOJA", f_section, (220, 220, 230), cx, self.py + _LOJA_HEADER_Y, shadow=False)
        for i, item_id in enumerate(ITEMS):
            y = self.py + _LOJA_START_Y + i * _ROW_H
            item = ITEMS[item_id]
            draw_text(surface, f"{item['name']} - {item['price']}g", f_row, (215, 215, 225),
                      label_cx, y - 8, shadow=False)

            rect = self.buy_buttons[item_id]
            can_buy = player.gold >= item["price"]
            pygame.draw.rect(surface, (150, 110, 20) if can_buy else (50, 50, 50), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 200, 210), rect, 1, border_radius=6)
            draw_text(surface, "Comprar", fb, (255, 255, 255) if can_buy else (120, 120, 120),
                      rect.centerx, rect.y + 5, shadow=False)

        f_hint = font(14)
        draw_text(surface, "I / toque no botao - Fechar", f_hint, SUBTEXT, cx, self.py + _HINT_Y)
