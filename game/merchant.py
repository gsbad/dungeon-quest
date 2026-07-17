import math
import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text, Carousel, draw_tooltip
from game.items import ITEMS, MAX_STOCK, use_item, buy_item, item_tooltip_line
from game.assets import create_potion_icon
from game.input_system import Action

_ROW_H = 34
_ROWS_START_Y = 108
_ROWS_PER_PAGE = 8
_HINT_Y = 428
_PANEL_H = 460
_PANEL_W = 420
_MAX_HOTBAR = 3

_TAB_ORDER = ["use", "buy"]
_TAB_LABEL = {"use": "SEUS ITENS", "buy": "LOJA"}


class ItemsOverlay:
    """Overlay "Itens": seus itens (usar/marcar p/ hotbar) + loja (comprar)
    - Stage K12: ITEMS grew from 3 to ~25 entries, so this is now a 2-tab
    (TAB key, same Action.TAB_NEXT the Paperdoll uses) + paginated (Carousel,
    same widget/pattern as Paperdoll's Help/Achievements and the debug
    panel's row list) layout instead of a fixed flat list."""

    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = 40
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)
        self.tab = "use"
        self.cursor = 0
        self._item_ids = list(ITEMS)

        n_tabs = len(_TAB_ORDER)
        tab_w, tab_h, gap = 150, 28, 10
        tab_x0 = self.px + _PANEL_W // 2 - (n_tabs * tab_w + (n_tabs - 1) * gap) // 2
        tab_y = self.py + 66
        self.tab_buttons = {}
        for i, tab_id in enumerate(_TAB_ORDER):
            self.tab_buttons[tab_id] = pygame.Rect(tab_x0 + i * (tab_w + gap), tab_y, tab_w, tab_h)

        # Same "page follows the keyboard cursor" linkage as debug_panel.py -
        # the Carousel's arrows are the mouse/tap path, W/S walking past a
        # page edge flips pages naturally since page = cursor // per-page.
        arrow_cy = self.py + _ROWS_START_Y + (_ROWS_PER_PAGE * _ROW_H) // 2
        self.carousel = Carousel(self.px - 34, _PANEL_W + 68, arrow_cy)

        self.hotbar_buttons = {}
        self.action_buttons = {}
        for i, item_id in enumerate(self._item_ids):
            y = self.py + _ROWS_START_Y + (i % _ROWS_PER_PAGE) * _ROW_H
            self.hotbar_buttons[item_id] = pygame.Rect(self.px + 268, y - 13, 30, 26)
            self.action_buttons[item_id] = pygame.Rect(self.px + 306, y - 13, 96, 26)

    def _sync_carousel(self):
        n = len(self._item_ids)
        self.carousel.set_num_pages((n + _ROWS_PER_PAGE - 1) // _ROWS_PER_PAGE)

    def _row_rect(self, row_in_page):
        y = self.py + _ROWS_START_Y + row_in_page * _ROW_H
        return pygame.Rect(self.px + 14, y - 16, _PANEL_W - 28, 32)

    def _switch_tab(self, tab_id):
        self.tab = tab_id
        self.cursor = 0
        self.carousel.page = 0

    def _toggle_hotbar(self, player, item_id, input_mgr=None):
        if item_id in player.hotbar_items:
            player.hotbar_items.remove(item_id)
        else:
            if len(player.hotbar_items) >= _MAX_HOTBAR:
                # Selecting a 4th item evicts the oldest pick (index 0)
                # instead of silently no-op'ing - hotbar_slots() (game/
                # player.py) lays slots out left to right in list order,
                # so this also reads naturally as "everyone shifts left,
                # new pick lands on the right."
                player.hotbar_items.pop(0)
            player.hotbar_items.append(item_id)
        if input_mgr is not None:
            input_mgr.refresh_item_icons(player)

    def handle_keys(self, input_mgr, player, save_state=None):
        self._sync_carousel()
        if input_mgr.consume_action(Action.TAB_NEXT):
            idx = _TAB_ORDER.index(self.tab)
            self._switch_tab(_TAB_ORDER[(idx + 1) % len(_TAB_ORDER)])
            return

        n = len(self._item_ids)
        if input_mgr.consume_action(Action.MENU_UP):
            self.cursor = (self.cursor - 1) % n
            self.carousel.page = self.cursor // _ROWS_PER_PAGE
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.cursor = (self.cursor + 1) % n
            self.carousel.page = self.cursor // _ROWS_PER_PAGE
        if self.carousel.handle_keys(input_mgr):
            self.cursor = self.carousel.page * _ROWS_PER_PAGE

        item_id = self._item_ids[self.cursor]
        if input_mgr.consume_action(Action.CONFIRM):
            if self.tab == "use":
                use_item(player, item_id)
            elif buy_item(player, item_id) and save_state is not None:
                import game.save as save
                import game.net as net
                save.sync_economy(save_state, player)
                save.save(save_state)
                net.trigger_sync(save_state)
        if self.tab == "use" and input_mgr.consume_action(Action.TOGGLE_HOTBAR):
            self._toggle_hotbar(player, item_id, input_mgr)

    def handle_tap(self, input_mgr, player, save_state=None):
        self._sync_carousel()
        for tab_id, rect in self.tab_buttons.items():
            if input_mgr.tapped_rect(rect):
                self._switch_tab(tab_id)
                return
        if self.carousel.handle_tap(input_mgr):
            self.cursor = self.carousel.page * _ROWS_PER_PAGE
            return

        page_start = self.carousel.page * _ROWS_PER_PAGE
        page_ids = self._item_ids[page_start:page_start + _ROWS_PER_PAGE]
        if self.tab == "use":
            for item_id in page_ids:
                if input_mgr.tapped_rect(self.hotbar_buttons[item_id]):
                    self._toggle_hotbar(player, item_id, input_mgr)
                    return
                if input_mgr.tapped_rect(self.action_buttons[item_id]):
                    use_item(player, item_id)
                    return
        else:
            for item_id in page_ids:
                if input_mgr.tapped_rect(self.action_buttons[item_id]):
                    if buy_item(player, item_id) and save_state is not None:
                        # Persisted immediately (not just at the next
                        # level-exit checkpoint) - spending gold is a
                        # deliberate action, same tier of importance as the
                        # mute-toggle immediate-persist.
                        import game.save as save
                        import game.net as net
                        save.sync_economy(save_state, player)
                        save.save(save_state)
                        net.trigger_sync(save_state)
                    return

    def draw(self, surface, player, mouse_pos=None):
        self._sync_carousel()
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + _PANEL_W // 2
        label_cx = self.px + 150

        f_title = font(26, bold=True)
        draw_text(surface, "ITENS", f_title, ACCENT_GOLD, cx, self.py + 16)

        f_gold = font(17, bold=True)
        gold_line = f"Ouro: {player.gold}"
        if self.tab == "use":
            gold_line += f"   |   Hotbar: {len(player.hotbar_items)}/{_MAX_HOTBAR}"
        draw_text(surface, gold_line, f_gold, (230, 200, 80), cx, self.py + 44)

        f_tab = font(14, bold=True)
        for tab_id, rect in self.tab_buttons.items():
            active = tab_id == self.tab
            pygame.draw.rect(surface, (90, 70, 20) if active else (40, 40, 48), rect, border_radius=6)
            pygame.draw.rect(surface, ACCENT_GOLD if active else (120, 120, 130), rect, 2, border_radius=6)
            draw_text(surface, _TAB_LABEL[tab_id], f_tab, (255, 255, 255) if active else (170, 170, 180),
                      rect.centerx, rect.y + 7, shadow=False)

        page_start = self.carousel.page * _ROWS_PER_PAGE
        page_ids = self._item_ids[page_start:page_start + _ROWS_PER_PAGE]

        row_in_page = self.cursor - page_start
        if 0 <= row_in_page < len(page_ids):
            glow_rect = self._row_rect(row_in_page)
            alpha = int(90 + 60 * abs(math.sin(pygame.time.get_ticks() / 1000.0 * 4)))
            glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
            glow.fill((255, 215, 80, alpha))
            surface.blit(glow, glow_rect.topleft)
            pygame.draw.rect(surface, (255, 225, 120), glow_rect, 2, border_radius=6)

        f_row = font(14)
        fb = font(13, bold=True)
        for i, item_id in enumerate(page_ids):
            y = self.py + _ROWS_START_Y + i * _ROW_H
            item = ITEMS[item_id]
            surface.blit(create_potion_icon(item_id), (self.px + 20, y - 16))

            if self.tab == "use":
                count = player.inventory.get(item_id, 0)
                draw_text(surface, f"{item['name']} x{count}", f_row, (215, 215, 225),
                          label_cx, y - 8, shadow=False)

                hb_rect = self.hotbar_buttons[item_id]
                in_hotbar = item_id in player.hotbar_items
                pygame.draw.rect(surface, (150, 110, 20) if in_hotbar else (45, 45, 52), hb_rect, border_radius=6)
                pygame.draw.rect(surface, (200, 200, 210), hb_rect, 1, border_radius=6)
                # Filled dot = in the hotbar, hollow ring = not - plain
                # pygame primitives instead of a unicode glyph (star chars
                # aren't guaranteed to be in whatever font pygbag's WASM
                # build subsets, this codebase's fonts are drawn via
                # pygame.font.Font(None, size), a bitmap default font).
                if in_hotbar:
                    pygame.draw.circle(surface, (255, 225, 140), hb_rect.center, 7)
                else:
                    pygame.draw.circle(surface, (150, 150, 160), hb_rect.center, 7, 2)

                rect = self.action_buttons[item_id]
                can_use = count > 0
                pygame.draw.rect(surface, (30, 140, 60) if can_use else (50, 50, 50), rect, border_radius=6)
                pygame.draw.rect(surface, (200, 200, 210), rect, 1, border_radius=6)
                draw_text(surface, "Usar", fb, (255, 255, 255) if can_use else (120, 120, 120),
                          rect.centerx, rect.y + 6, shadow=False)
            else:
                owned = player.inventory.get(item_id, 0)
                at_cap = owned >= MAX_STOCK
                draw_text(surface, f"{item['name']} - {item['price']}g ({owned}/{MAX_STOCK})", f_row,
                          (215, 215, 225), label_cx, y - 8, shadow=False)

                rect = self.action_buttons[item_id]
                can_buy = player.gold >= item["price"] and not at_cap
                pygame.draw.rect(surface, (150, 110, 20) if can_buy else (50, 50, 50), rect, border_radius=6)
                pygame.draw.rect(surface, (200, 200, 210), rect, 1, border_radius=6)
                label = "Max" if at_cap else "Comprar"
                draw_text(surface, label, fb, (255, 255, 255) if can_buy else (120, 120, 120),
                          rect.centerx, rect.y + 6, shadow=False)

            tip = [item["name"], item_tooltip_line(item_id)]
            draw_tooltip(surface, mouse_pos, self._row_rect(i), tip, SW, SH)

        self.carousel.draw(surface, font(13), indicator_y=self.py + _ROWS_START_Y + _ROWS_PER_PAGE * _ROW_H + 14)

        f_hint = font(13)
        hint = ("W/S seleciona | ESPACO usa | H marca p/ hotbar | A/D pagina | TAB troca aba | I/ESC - Fechar"
                if self.tab == "use" else
                "W/S seleciona | ESPACO compra | A/D pagina | TAB troca aba | I/ESC - Fechar")
        draw_text(surface, hint, f_hint, SUBTEXT, cx, self.py + _HINT_Y)
