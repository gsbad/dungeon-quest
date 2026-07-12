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
