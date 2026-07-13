import pygame


def draw_text(surface, text, f, color, cx, y, shadow=True, align="center"):
    """cx is a center x by default; align="left" treats it as a left edge
    instead (e.g. paperdoll.py's two-column stat grid, where centering each
    line independently would make the columns ragged)."""
    if align == "left":
        if shadow:
            s = f.render(text, True, (0, 0, 0))
            surface.blit(s, (cx + 2, y+2))
        r = f.render(text, True, color)
        surface.blit(r, (cx, y))
        return r.get_height()
    if shadow:
        s = f.render(text, True, (0, 0, 0))
        surface.blit(s, (cx - s.get_width()//2 + 2, y+2))
    r = f.render(text, True, color)
    surface.blit(r, (cx - r.get_width()//2, y))
    return r.get_height()


class TextButton:
    """A clickable, horizontally-centered text label. Draws itself (with the
    same drop shadow as draw_text) and derives its own tap/click hit-rect
    from the rendered text size + padding - the pattern every menu screen
    used to hand-roll independently (one pygame.Rect per option/label)."""

    def __init__(self, label, cx, y, pad_x=20, pad_y=12):
        self.label = label
        self.cx = cx
        self.y = y
        self.pad_x = pad_x
        self.pad_y = pad_y
        self.rect = pygame.Rect(0, 0, 0, 0)

    def draw(self, surface, f, color, shadow=True):
        draw_text(surface, self.label, f, color, self.cx, self.y, shadow=shadow)
        w, h = f.size(self.label)
        self.rect = pygame.Rect(
            self.cx - w // 2 - self.pad_x, self.y - self.pad_y,
            w + self.pad_x * 2, h + self.pad_y * 2,
        )


class Panel:
    """A translucent SRCALPHA box with a border, blitted at a fixed
    top-left position - e.g. the controls box on the main menu."""

    def __init__(self, w, h, fill_color, border_color, border_width=2):
        self.w = w
        self.h = h
        self.fill_color = fill_color
        self.border_color = border_color
        self.border_width = border_width

    def draw(self, surface, topleft):
        box = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        box.fill(self.fill_color)
        if self.border_width:
            pygame.draw.rect(box, self.border_color, (0, 0, self.w, self.h), self.border_width)
        surface.blit(box, topleft)


class Carousel:
    """Stage J3: horizontal page-flipper for panels whose content outgrew
    their fixed height (the paperdoll's Help/Achievements tabs and the F1
    debug panel all just kept drawing past the panel edge before this).
    Owns only page state + the lateral < > arrows + a "n/N" indicator;
    the OWNER slices its own content by self.page - this widget never
    knows what a "page" contains, which is what lets the same class serve
    both the paperdoll tabs and the debug panel's row list."""

    _ARROW_W = 26
    _ARROW_H = 44

    def __init__(self, panel_x, panel_w, arrow_cy):
        self.page = 0
        self.num_pages = 1
        self.left_rect = pygame.Rect(
            panel_x + 4, arrow_cy - self._ARROW_H // 2, self._ARROW_W, self._ARROW_H)
        self.right_rect = pygame.Rect(
            panel_x + panel_w - 4 - self._ARROW_W, arrow_cy - self._ARROW_H // 2,
            self._ARROW_W, self._ARROW_H)
        self._panel_cx = panel_x + panel_w // 2

    def set_num_pages(self, n):
        """Owners call this every draw (content can grow at runtime, e.g.
        HELP_ENTRIES gaining lines) - clamps the current page rather than
        resetting it, so a mid-session content change doesn't yank the
        user back to page 0."""
        self.num_pages = max(1, n)
        self.page = min(self.page, self.num_pages - 1)

    def prev_page(self):
        self.page = (self.page - 1) % self.num_pages

    def next_page(self):
        self.page = (self.page + 1) % self.num_pages

    def handle_keys(self, input_mgr):
        """A/D-or-arrows page flip. Returns True if it consumed the action,
        so owners whose tab ALSO uses left/right (e.g. stats +/-) know not
        to wire this in at all - only conflict-free tabs should call it."""
        from game.input_system import Action
        if self.num_pages <= 1:
            return False
        if input_mgr.consume_action(Action.MENU_LEFT):
            self.prev_page()
            return True
        if input_mgr.consume_action(Action.MENU_RIGHT):
            self.next_page()
            return True
        return False

    def handle_tap(self, input_mgr):
        if self.num_pages <= 1:
            return False
        if input_mgr.tapped_rect(self.left_rect):
            self.prev_page()
            return True
        if input_mgr.tapped_rect(self.right_rect):
            self.next_page()
            return True
        return False

    def draw(self, surface, f, indicator_y=None):
        if self.num_pages <= 1:
            return
        for rect, pointing_left in ((self.left_rect, True), (self.right_rect, False)):
            pygame.draw.rect(surface, (45, 40, 60), rect, border_radius=6)
            pygame.draw.rect(surface, (200, 190, 220), rect, 1, border_radius=6)
            tip_x = rect.x + 8 if pointing_left else rect.right - 8
            base_x = rect.right - 8 if pointing_left else rect.x + 8
            pygame.draw.polygon(surface, (230, 225, 245), [
                (tip_x, rect.centery),
                (base_x, rect.centery - 10),
                (base_x, rect.centery + 10),
            ])
        if indicator_y is not None:
            draw_text(surface, f"{self.page + 1}/{self.num_pages}", f,
                      (170, 165, 185), self._panel_cx, indicator_y, shadow=False)


class ProgressBar:
    """A background rect + proportional fill + border, optionally wrapped in
    a slightly larger backing box (margin>0). Covers both the small in-world
    boss HP bar and the bigger top-of-screen HUD variant, which used to be
    four near-identical hand-coded implementations in boss.py."""

    def __init__(self, w, h, bg_color, border_color, border_width=1, margin=0):
        self.w = w
        self.h = h
        self.bg_color = bg_color
        self.border_color = border_color
        self.border_width = border_width
        self.margin = margin

    def draw(self, surface, x, y, frac, fill_color):
        frac = max(0.0, min(1.0, frac))
        if self.margin:
            m = self.margin
            pygame.draw.rect(surface, self.bg_color, (x - m, y - m, self.w + m*2, self.h + m*2))
        else:
            pygame.draw.rect(surface, self.bg_color, (x, y, self.w, self.h))
        pygame.draw.rect(surface, fill_color, (x, y, int(self.w * frac), self.h))
        pygame.draw.rect(surface, self.border_color, (x, y, self.w, self.h), self.border_width)
