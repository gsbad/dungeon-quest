import math
import sys
import pygame
from enum import Enum, auto
from game.theme import font
from game.assets import (
    create_spell_icon, create_sword_icon, create_potion_icon, create_dash_icon, create_pickaxe_icon,
)
from game.items import ITEMS

TAP_MAX_DURATION = 0.35
TAP_MAX_MOVEMENT = 18
JOYSTICK_DEADZONE = 0.15


def _corrected_mouse_pos(raw_pos):
    """Stage J11: the long-open canvas click-misalignment bug
    ([[project_pygbag_canvas_stretch_bug]]), finally root-caused via a
    Playwright harness that clicked a precise, known canvas-fraction point
    and measured where event.pos actually landed instead of theorizing.
    The canvas's CSS display size (pygbag_template.tmpl's fitCanvas()
    keeps it at 800x600 scaled to fill the window, e.g. 960x720) differs
    from its backing-buffer size (canvas.width/height, always 800x600) -
    clicking the exact center measured event.pos landing at (333,250)
    instead of (400,300), a uniform (800/960)**2 ratio on both axes, not
    (800/960)**1. That's not a wrong single correction or an offset bug -
    it's the SAME css->buffer correction applied TWICE somewhere in this
    pygbag build's SDL2-emscripten mouse-event pipeline (probably
    pygame.SCALED's own logical-size transform stacking with emscripten's
    own canvas-relative coordinate handling). Multiplying back by
    (clientWidth/canvas.width) undoes exactly the extra pass - confirmed
    against the same harness before this was wired in for real (see the
    e2e_click_precision.py script referenced in project memory)."""
    if sys.platform != "emscripten":
        return raw_pos
    try:
        import js
        canvas = js.document.getElementById("canvas")
        client_w, client_h = canvas.clientWidth, canvas.clientHeight
        buf_w, buf_h = canvas.width, canvas.height
        if not client_w or not client_h or not buf_w or not buf_h:
            return raw_pos
        return (raw_pos[0] * client_w / buf_w, raw_pos[1] * client_h / buf_h)
    except Exception:
        return raw_pos


class Action(Enum):
    ATTACK = auto()
    CONFIRM = auto()
    PAUSE = auto()
    RESTART = auto()
    MENU_UP = auto()
    MENU_DOWN = auto()
    MENU_LEFT = auto()
    MENU_RIGHT = auto()
    TAB_NEXT = auto()
    SECRET = auto()
    PAPERDOLL = auto()
    ITEMS = auto()
    LEADERBOARD = auto()
    CAST_1 = auto()
    CAST_2 = auto()
    CAST_3 = auto()
    CAST_SELECTED = auto()
    DASH = auto()
    USE_1 = auto()
    USE_2 = auto()
    USE_3 = auto()
    TOGGLE_HOTBAR = auto()
    PICKAXE = auto()
    DEV_NEXT_LEVEL = auto()
    DEV_PREV_LEVEL = auto()
    DEBUG_PANEL = auto()
    FULLSCREEN = auto()
    MUTE = auto()


# Stage F4 - Help tab content. Single source of truth for player-facing
# keybindings, derived straight from feed()'s KEYDOWN branch above (the
# main menu's old "controles" box had drifted out of sync with the real
# key list - this is read by game/paperdoll.py's Help tab instead of
# duplicating the list there). Debug-only keys (M/N level skip, F1 debug
# panel) are intentionally left out - they're testing tools, not player
# controls. Add a new keybinding here when adding one above to keep the
# Help tab expansible without any layout change.
#
# Stage K20: entries for a Stage K15-remappable action carry a 3rd field -
# the game.keybinds action name - instead of a hardcoded key literal. The
# literal 2nd-position label still shown for these is only the DEFAULT
# (used before the player's live binding is known); game/paperdoll.py's
# Help tab resolves the 3rd field to the CURRENT key via
# keybinds.display_key() at render time, so a remap doesn't leave this
# list showing a stale key. Non-remappable entries (WASD, mouse, item
# slots, TAB, ESC, F11/F12) have no 3rd field and just show their literal.
HELP_ENTRIES = [
    ("WASD / Setas", "Mover o personagem"),
    ("Mouse", "Mirar ataques/feiticos na direcao do cursor"),
    ("ESPACO", "Atacar corpo a corpo", "ATTACK"),
    ("F", "Conjurar Bola de Fogo", "CAST_1"),
    ("Q", "Conjurar Nova de Gelo", "CAST_2"),
    ("R", "Conjurar Luz Curativa / Reiniciar (na tela de pausa ou de morte)", "CAST_3"),
    ("X", "Investida (Dash)", "DASH"),
    ("E", "Picareta - quebra blocos e cava em busca da chave escondida", "PICKAXE"),
    ("1 / 2 / 3", "Usar item (slots do hotbar)"),
    ("C", "Abrir/fechar o menu Personagem", "PAPERDOLL"),
    ("I", "Abrir/fechar o menu Itens", "ITEMS"),
    ("H (no menu Itens)", "Marcar/desmarcar o item selecionado para o hotbar (max. 3)", "TOGGLE_HOTBAR"),
    ("L", "Abrir/fechar o Ranking (requer login Google)", "LEADERBOARD"),
    ("Icone de engrenagem", "Configuracoes - remapear teclas de acao (PC, so pelo mouse/toque)"),
    ("TAB", "Trocar de aba dentro de um menu"),
    ("ESC", "Pausar o jogo / fechar o menu aberto"),
    ("F11 / icone (tela)", "Tela cheia - tecla ou toque"),
    ("F12 / icone (tela)", "Ativar/desativar audio - tecla ou toque"),
]


class VirtualJoystick:
    """Draggable analog base+knob. Tracks whichever pointer id pressed inside it."""

    def __init__(self, cx, cy, radius=70, knob_radius=32):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.knob_radius = knob_radius
        self.pointer_id = None
        self.knob_x = cx
        self.knob_y = cy

    def contains(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= (self.radius * 1.4) ** 2

    def press(self, pointer_id, x, y):
        self.pointer_id = pointer_id
        self._update_knob(x, y)

    def drag(self, pointer_id, x, y):
        if pointer_id == self.pointer_id:
            self._update_knob(x, y)

    def release(self, pointer_id):
        if pointer_id == self.pointer_id:
            self.pointer_id = None
            self.knob_x, self.knob_y = self.cx, self.cy

    def _update_knob(self, x, y):
        dx, dy = x - self.cx, y - self.cy
        dist = math.hypot(dx, dy)
        if dist > self.radius:
            dx = dx / dist * self.radius
            dy = dy / dist * self.radius
        self.knob_x = self.cx + dx
        self.knob_y = self.cy + dy

    @property
    def active(self):
        return self.pointer_id is not None

    @property
    def vector(self):
        if not self.active:
            return 0.0, 0.0
        dx = (self.knob_x - self.cx) / self.radius
        dy = (self.knob_y - self.cy) / self.radius
        if math.hypot(dx, dy) < JOYSTICK_DEADZONE:
            return 0.0, 0.0
        return dx, dy

    def draw(self, surface):
        d = self.radius * 2
        base = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(base, (210, 210, 230, 60), (self.radius, self.radius), self.radius)
        pygame.draw.circle(base, (230, 230, 250, 130), (self.radius, self.radius), self.radius, 3)
        surface.blit(base, (self.cx - self.radius, self.cy - self.radius))

        kd = self.knob_radius * 2
        knob_color = (255, 220, 100, 210) if self.active else (230, 230, 245, 150)
        knob = pygame.Surface((kd, kd), pygame.SRCALPHA)
        pygame.draw.circle(knob, knob_color, (self.knob_radius, self.knob_radius), self.knob_radius)
        surface.blit(knob, (self.knob_x - self.knob_radius, self.knob_y - self.knob_radius))


class VirtualButton:
    """Round tap button. Draws an `icon` surface centered if given, otherwise
    falls back to rendering `label` as text. `action` is fired once on press
    - unless `aimable=True` (Stage J13: mobile attack/spell buttons that
    need a direction), in which case pressing alone does nothing: the
    caller (InputManager._pointer_move) feeds drag() a world position, and
    GameplayState.update() polls `.active and .has_aim` each frame to fire
    repeatedly while held+aimed, same "touch then drag to aim" as the sword
    joystick-style control the user asked for."""

    def __init__(self, cx, cy, radius, label, action, icon=None, aimable=False):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.label = label
        self.action = action
        self.icon = icon
        self.aimable = aimable
        self.aim_dx, self.aim_dy = 0.0, 0.0
        self.pointer_id = None
        self.press_flash = 0.0
        self._font = None

    def contains(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.radius ** 2

    def press(self, pointer_id):
        self.pointer_id = pointer_id
        self.press_flash = 1.0
        if self.aimable:
            self.aim_dx, self.aim_dy = 0.0, 0.0

    def drag(self, pointer_id, x, y):
        if not self.aimable or pointer_id != self.pointer_id:
            return
        dx, dy = x - self.cx, y - self.cy
        # Deadzone in pixels (not normalized, unlike VirtualJoystick's) - a
        # finger that barely moved off dead-center shouldn't snap an aim
        # arrow onto some arbitrary direction.
        if math.hypot(dx, dy) < 10:
            return
        dist = math.hypot(dx, dy)
        self.aim_dx, self.aim_dy = dx / dist, dy / dist

    def release(self, pointer_id):
        if pointer_id == self.pointer_id:
            self.pointer_id = None
            if self.aimable:
                self.aim_dx, self.aim_dy = 0.0, 0.0

    @property
    def active(self):
        return self.pointer_id is not None

    @property
    def has_aim(self):
        return self.aimable and (self.aim_dx != 0.0 or self.aim_dy != 0.0)

    def update(self, dt):
        if self.press_flash > 0:
            self.press_flash = max(0.0, self.press_flash - dt * 3)

    def draw(self, surface):
        d = self.radius * 2
        alpha = 90 + int(100 * self.press_flash)
        color = (255, 220, 100, alpha) if self.active else (230, 230, 245, 90)
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, color, (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (255, 255, 255, 170), (self.radius, self.radius), self.radius, 3)
        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))

        if self.has_aim:
            self._draw_aim_arrow(surface)

        if self.icon is not None:
            size = int(self.radius * 1.4)
            scaled = pygame.transform.scale(self.icon, (size, size))
            surface.blit(scaled, (self.cx - size // 2, self.cy - size // 2))
            return

        if self._font is None:
            self._font = font(20)
        txt = self._font.render(self.label, True, (35, 25, 10))
        surface.blit(txt, (self.cx - txt.get_width() // 2, self.cy - txt.get_height() // 2))

    def _draw_aim_arrow(self, surface):
        """Translucent arrow pointing from the button towards the drag
        direction - the visual the user explicitly asked for so aiming
        while dragging is legible, same idea as the joystick's knob offset
        but drawn as an arrow since there's no separate knob here."""
        length = self.radius * 1.8
        size = int(length * 2 + 24)
        buf = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        tip_x, tip_y = c + self.aim_dx * length, c + self.aim_dy * length
        base_x = c + self.aim_dx * (self.radius * 0.9)
        base_y = c + self.aim_dy * (self.radius * 0.9)
        color = (255, 240, 200, 170)
        pygame.draw.line(buf, color, (base_x, base_y), (tip_x, tip_y), 5)
        ang = math.atan2(self.aim_dy, self.aim_dx)
        for side in (-1, 1):
            hx = tip_x - math.cos(ang + side * 0.5) * 12
            hy = tip_y - math.sin(ang + side * 0.5) * 12
            pygame.draw.line(buf, color, (tip_x, tip_y), (hx, hy), 5)
        surface.blit(buf, (self.cx - c, self.cy - c))


class FullscreenButton:
    """Always-visible fullscreen toggle icon, same tap-target pattern as
    audio.SoundButton - drawn as corner brackets (expand) or inward arrows
    (compress) depending on the current fullscreen state."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface, is_fullscreen):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        color = (235, 235, 245, 230)
        r = self.radius
        arm, thick = 6, 2
        if is_fullscreen:
            # Arrows pointing inward from each corner (compress).
            corners = [(r - 8, r - 8, 1, 1), (r + 8, r - 8, -1, 1), (r - 8, r + 8, 1, -1), (r + 8, r + 8, -1, -1)]
        else:
            # Brackets pointing outward from center (expand).
            corners = [(r - 8, r - 8, -1, -1), (r + 8, r - 8, 1, -1), (r - 8, r + 8, -1, 1), (r + 8, r + 8, 1, 1)]

        for x, y, dx, dy in corners:
            pygame.draw.line(buf, color, (x, y), (x + dx * arm, y), thick)
            pygame.draw.line(buf, color, (x, y), (x, y + dy * arm), thick)

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))


def _draw_shortcut_badge(surface, rect, key_label):
    """Same small rounded dark badge + white bold text as the hotbar's key
    labels (game/player.py's key_surf/key_bg) - reused here (Stage G5) so
    PaperdollButton/ItemsButton read as keyboard shortcuts the same way
    hotbar slots do, not just touch targets."""
    f = font(11, bold=True)
    key_surf = f.render(key_label, True, (255, 255, 255))
    key_bg = pygame.Rect(rect.x - 2, rect.y - 2, key_surf.get_width() + 4, key_surf.get_height() + 2)
    pygame.draw.rect(surface, (20, 20, 30), key_bg, border_radius=3)
    surface.blit(key_surf, (key_bg.x + 2, key_bg.y + 1))


class PaperdollButton:
    """Stage G5 - quick-access to the Paperdoll ("c") menu, same
    translucent-circle + line-art glyph pattern as FullscreenButton/
    SoundButton above (a shield, RPG shorthand for "character sheet"),
    plus a "C" key badge."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        color = (235, 235, 245, 230)
        r = self.radius
        pts = [(r, r - 11), (r + 9, r - 7), (r + 9, r + 4), (r, r + 12), (r - 9, r + 4), (r - 9, r - 7)]
        pygame.draw.polygon(buf, color, pts, 2)
        pygame.draw.line(buf, color, (r, r - 9), (r, r + 9), 2)

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))
        _draw_shortcut_badge(surface, self.rect, "C")


class ItemsButton:
    """Stage G5 - quick-access to the Items ("i") menu, same pattern as
    PaperdollButton above (a backpack), plus an "I" key badge."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        color = (235, 235, 245, 230)
        r = self.radius
        pygame.draw.rect(buf, color, (r - 8, r - 6, 16, 16), 2, border_radius=4)
        pygame.draw.rect(buf, color, (r - 4, r - 11, 8, 6), 2, border_radius=2)
        pygame.draw.line(buf, color, (r - 8, r + 2), (r + 8, r + 2), 1)

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))
        _draw_shortcut_badge(surface, self.rect, "I")


class LeaderboardButton:
    """Stage J8 - quick-access to the Leaderboard ("l") screen, same
    translucent-circle pattern as PaperdollButton/ItemsButton above (a
    trophy, RPG shorthand for "rankings"), plus an "L" key badge."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        color = (235, 200, 90, 230)
        r = self.radius
        # Trophy: cup body, two side handles, stem, base.
        pygame.draw.rect(buf, color, (r - 6, r - 9, 12, 9), 2, border_radius=2)
        pygame.draw.arc(buf, color, (r - 11, r - 9, 8, 8), -1.6, 1.6, 2)
        pygame.draw.arc(buf, color, (r + 3, r - 9, 8, 8), 1.6, 4.7, 2)
        pygame.draw.line(buf, color, (r, r), (r, r + 5), 2)
        pygame.draw.line(buf, color, (r - 5, r + 7), (r + 5, r + 7), 2)

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))
        _draw_shortcut_badge(surface, self.rect, "L")


class SettingsButton:
    """Stage K15 - quick-access to the Settings/keybind-remap overlay,
    same translucent-circle pattern as PaperdollButton/ItemsButton/
    LeaderboardButton above (a gear). No key badge - unlike C/I/L this
    one has no dedicated keyboard shortcut, click/tap-only by design."""

    def __init__(self, cx, cy, radius=22):
        self.cx = cx
        self.cy = cy
        self.radius = radius

    @property
    def rect(self):
        d = self.radius * 2
        return pygame.Rect(self.cx - self.radius, self.cy - self.radius, d, d)

    def draw(self, surface):
        d = self.radius * 2
        buf = pygame.Surface((d, d), pygame.SRCALPHA)
        pygame.draw.circle(buf, (25, 25, 35, 140), (self.radius, self.radius), self.radius)
        pygame.draw.circle(buf, (230, 230, 245, 190), (self.radius, self.radius), self.radius, 2)

        color = (210, 210, 225, 230)
        r = self.radius
        pygame.draw.circle(buf, color, (r, r), 5, 2)
        pygame.draw.circle(buf, color, (r, r), 2)
        for i in range(8):
            angle = i * (math.pi / 4)
            x1, y1 = r + math.cos(angle) * 7, r + math.sin(angle) * 7
            x2, y2 = r + math.cos(angle) * 11, r + math.sin(angle) * 11
            pygame.draw.line(buf, color, (x1, y1), (x2, y2), 2)

        surface.blit(buf, (self.cx - self.radius, self.cy - self.radius))


class InputManager:
    """
    Single translation layer between raw pygame input (keyboard, mouse,
    finger/touch) and the logical actions the game states understand.

    Usage per frame (see main.py):
        for event in pygame.event.get():
            input_mgr.feed(event)
            manager.handle_event(event)   # states call consume_action/tapped_rect
        manager.update(dt)                # states read movement_vector()
        input_mgr.update(dt)              # animates + clears this frame's actions/taps
        manager.draw()
        input_mgr.draw(screen)            # virtual controls overlay (gameplay only)
    """

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._actions = set()
        self._pointers = {}
        self._taps = []
        self.touch_active = False
        self._time = 0.0
        # Stage K15: see begin_key_capture()/feed() above.
        self._capture_callback = None

        # Stage J13: last known corrected mouse position, updated on every
        # MOUSEMOTION/MOUSEBUTTONDOWN regardless of whether a button is
        # held - mouse-aimed combat needs continuous hover position, unlike
        # _pointers (which only tracks a pointer between down and up).
        self._mouse_screen_pos = (screen_w / 2, screen_h / 2)

        # Stage J11: a permanent (not debug-only) crosshair at the raw
        # event.pos of every real mouse click - the diagnostic tool for the
        # long-open canvas-misalignment bug (see
        # [[project_pygbag_canvas_stretch_bug]]) and, per the user's ask,
        # kept on afterward since upcoming mouse-aimed combat needs the
        # same "where does the game think the pointer is" visibility.
        # Replaces the old debug_last_raw/debug_last_scaled attributes,
        # which were written on every click but never read/drawn anywhere.
        self._crosshair_pos = None
        self._crosshair_timer = 0.0
        self._CROSSHAIR_DURATION = 0.6

        self.joystick = VirtualJoystick(100, screen_h - 120, radius=70, knob_radius=32)
        # Stage J13: aimable=True - touch+drag now aims the melee swing
        # (mouse-aimed combat's mobile equivalent) instead of firing once on
        # press towards whatever self.direction happened to be.
        self.attack_button = VirtualButton(screen_w - 90, screen_h - 100, 48, "ATK", Action.ATTACK,
                                            icon=create_sword_icon(), aimable=True)
        self.pause_button = VirtualButton(screen_w - 40, 40, 26, "II", Action.PAUSE)
        # Stage H3: the corner PaperdollButton/ItemsButton (states.py) already
        # cover "C"/"I" on both mobile and desktop, so the touch-only "C"/"I"
        # VirtualButtons that used to sit between the joystick and ATK were
        # pure duplicates - removed to free up that space for the spell arc.
        #
        # 4 buttons in an arc around the attack button (one per spell, plus
        # Dash - Stage K24 follow-up moved Dash in here per the user's ask,
        # out of its previous spot next to the joystick) instead of a single
        # cast-whatever's-selected button - each one fires its own Action
        # directly, same binding as the F/Q/R/Dash keys. Radius shrunk from
        # the original 3-button version's 36 to fit a 4th slot on an 800px-
        # wide screen without the rightmost button (closest to the attack
        # button, steepest angle) clipping off the right edge - the arc's
        # angular span/gap is computed, not hardcoded, so this stays
        # correct if the button count or radius ever changes again.
        atk = self.attack_button
        spell_btn_radius = 30
        arc_distance = atk.radius + 14 + spell_btn_radius
        n_arc_buttons = 4
        arc_start_deg, arc_end_deg = 185, 55  # left-and-slightly-down, to upper-right
        arc_angles_deg = [
            arc_start_deg + (arc_end_deg - arc_start_deg) * i / (n_arc_buttons - 1)
            for i in range(n_arc_buttons)
        ]

        def _arc_pos(angle_deg):
            rad = math.radians(angle_deg)
            return atk.cx + math.cos(rad) * arc_distance, atk.cy - math.sin(rad) * arc_distance

        cast_actions = [Action.CAST_1, Action.CAST_2, Action.CAST_3]
        from game.spells import ORDER as SPELL_ORDER
        self.spell_buttons = []
        for angle_deg, action, spell_id in zip(arc_angles_deg, cast_actions, SPELL_ORDER):
            bx, by = _arc_pos(angle_deg)
            # Stage J13: fireball/frost_nova aim like the attack button
            # (drag to aim, auto-fires while held - see GameplayState.update).
            # Healing Light has no direction to aim, so it keeps the old
            # fire-once-on-press behavior untouched.
            btn = VirtualButton(bx, by, spell_btn_radius, "", action,
                                 icon=create_spell_icon(spell_id),
                                 aimable=(spell_id != "healing_light"))
            self.spell_buttons.append(btn)

        # Stage J14: dashes along the current aim vector - aimable=True so
        # dragging this button (same "touch then drag to aim" the attack/
        # fireball/frost_nova buttons already use) sets that direction,
        # instead of dashing along whatever aim was last set by some other
        # button. The 4th (last) arc slot, closest to the attack button.
        dash_bx, dash_by = _arc_pos(arc_angles_deg[3])
        self.dash_button = VirtualButton(dash_bx, dash_by, spell_btn_radius, "", Action.DASH,
                                          icon=create_dash_icon(), aimable=True)

        # A row of 3 direct-use item buttons, centered in the open gap
        # between the joystick and the spell arc - same "fire the action
        # directly, no menu detour" idea as the spell arc, one per
        # Action.USE_n/ITEMS entry. These replace the item hotbar slots
        # (game/player.py's hotbar_slots(), "item" kind) on the touch HUD:
        # game/states.py only draws those top-of-screen slots when
        # `not self.input.touch_active`, so a mobile player only ever sees
        # this row, never both.
        item_btn_radius = 32
        item_btn_gap = 16
        item_spacing = item_btn_radius * 2 + item_btn_gap
        item_actions = [Action.USE_1, Action.USE_2, Action.USE_3]
        item_cy = atk.cy
        item_cx0 = screen_w // 2
        self.item_buttons = []
        for i, (action, item_id) in enumerate(zip(item_actions, ITEMS)):
            bx = item_cx0 + (i - 1) * item_spacing
            btn = VirtualButton(bx, item_cy, item_btn_radius, "", action,
                                 icon=create_potion_icon(item_id))
            self.item_buttons.append(btn)

        # Stage K24 follow-up: Pickaxe had no mobile control at all - the
        # one clean gap left on this whole HUD is between the joystick's
        # hit-circle and the item row (Dash used to live here too, before
        # moving into the spell arc above), sized/centered from their own
        # geometry rather than a hand-picked coordinate so it stays correct
        # if either one ever moves. Aimable for the same reason the arc
        # buttons are: try_break_tile() targets whatever tile is in front of
        # the player along aim_dx/aim_dy (GameplayState._attempt_pickaxe()),
        # so dragging to aim picks which tile actually gets hit instead of
        # digging in a stale direction.
        pickaxe_btn_radius = 30
        joystick_edge = self.joystick.cx + self.joystick.radius * 1.4
        items_edge = item_cx0 - item_spacing - item_btn_radius
        pickaxe_cx = (joystick_edge + items_edge) / 2
        self.pickaxe_button = VirtualButton(pickaxe_cx, item_cy, pickaxe_btn_radius, "", Action.PICKAXE,
                                             icon=create_pickaxe_icon(), aimable=True)

        # Stage K24 follow-up: a discreet way into the F1 debug panel
        # (previously PC/keyboard-only) - deliberately small and unlabeled-
        # icon (just short text, same minimal style as pause_button's "II")
        # and tucked above the joystick, out of the main action cluster, so
        # it doesn't read as a real gameplay control to bump by accident.
        # Fires once on press like pause_button (not aimable - there's
        # nothing to aim).
        debug_btn_radius = 18
        debug_gap = 40
        self.debug_button = VirtualButton(
            self.joystick.cx, self.joystick.cy - self.joystick.radius - debug_gap - debug_btn_radius,
            debug_btn_radius, "DBG", Action.DEBUG_PANEL)

    def refresh_item_icons(self, player):
        """Stage K12: item_buttons are built once at InputManager
        construction (before any Player/save exists), defaulting to the
        first 3 ITEMS - health/mana/antidote, same order as Player's default
        hotbar_items. Once a save loads (or the player edits their hotbar
        selection in the Items overlay), the touch buttons' icons need to
        be repointed at whatever's actually in player.hotbar_items so
        tapping one fires (via Action.USE_n -> GameStateManager._use_hotbar_item)
        the item it visibly shows, not a stale default."""
        for i, btn in enumerate(self.item_buttons):
            if i < len(player.hotbar_items):
                btn.icon = create_potion_icon(player.hotbar_items[i])

    # ------------------------------------------------------------------ actions
    def _press_action(self, action):
        self._actions.add(action)

    def consume_action(self, action):
        if action in self._actions:
            self._actions.discard(action)
            return True
        return False

    def tapped_rect(self, rect):
        for i, (x, y) in enumerate(self._taps):
            if rect.collidepoint(x, y):
                del self._taps[i]
                return True
        return False

    def any_unconsumed_tap(self):
        """Stage J12: "click closes the menu" - callers check this AFTER
        letting a panel's own handle_tap() consume clicks on its buttons
        (tapped_rect() pops a tap the instant it matches a rect), so a tap
        still sitting here means it landed somewhere the panel didn't
        claim - the backdrop, effectively - and the menu should close.
        Doesn't consume anything itself; _taps already gets cleared once
        per frame by update() regardless."""
        return bool(self._taps)

    def mouse_pos(self):
        """Stage J13: last known corrected mouse position (screen-space,
        800x600 logical) - used for continuous PC mouse-aimed combat.
        Not meaningful once touch_active is set (no real mouse on mobile)."""
        return self._mouse_screen_pos

    # ---------------------------------------------------------------- movement
    def movement_vector(self):
        if self.joystick.active:
            return self.joystick.vector

        keys = pygame.key.get_pressed()
        dx, dy = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy = 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx = 1
        if dx != 0 and dy != 0:
            dx *= 0.707
            dy *= 0.707
        return dx, dy

    def is_action_held(self, action_name):
        """Stage K23: continuous "is this action's bound input physically
        down right now" poll - separate from consume_action()'s one-shot
        edge trigger, for the PC hold-to-fire attack/spell loop in
        GameplayState.update() (mirrors mobile's VirtualButton.active,
        which already auto-fires while held). Works for either binding
        shape game.keybinds.BINDINGS can hold: a pygame keycode int, or a
        "MOUSE1"/"MOUSE2"/"MOUSE3" string."""
        from game.keybinds import BINDINGS
        bound = BINDINGS.get(action_name)
        if bound is None:
            return False
        if isinstance(bound, str):
            button_i = int(bound[5:]) - 1
            pressed = pygame.mouse.get_pressed(num_buttons=3)
            return 0 <= button_i < len(pressed) and pressed[button_i]
        return pygame.key.get_pressed()[bound]

    # ------------------------------------------------------------- raw events
    def begin_key_capture(self, callback):
        """Stage K15: the Settings overlay calls this when the player
        starts rebinding an action - the very next KEYDOWN is swallowed
        here (never reaches the normal action dispatch below, so e.g.
        capturing a new Pickaxe key doesn't also fire Action.PICKAXE) and
        handed to `callback(key_code)` instead."""
        self._capture_callback = callback

    def feed(self, event):
        # Stage K22: capture used to only ever intercept KEYDOWN, so
        # rebinding an action to a mouse click in Settings silently did
        # nothing - the click fell through to the normal MOUSEBUTTONDOWN
        # handling below instead of reaching the capture callback. Any
        # mouse button now completes a capture too, encoded the same way
        # BINDINGS stores it (game.keybinds.key_name/MOUSE_LABELS): the
        # string "MOUSE1"/"MOUSE2"/"MOUSE3" rather than a pygame keycode.
        if self._capture_callback is not None:
            if event.type == pygame.KEYDOWN:
                cb = self._capture_callback
                self._capture_callback = None
                cb(event.key)
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                cb = self._capture_callback
                self._capture_callback = None
                cb(f"MOUSE{event.button}")
                return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_w, pygame.K_UP):
                self._press_action(Action.MENU_UP)
            if event.key in (pygame.K_s, pygame.K_DOWN):
                self._press_action(Action.MENU_DOWN)
            if event.key in (pygame.K_a, pygame.K_LEFT):
                self._press_action(Action.MENU_LEFT)
            if event.key in (pygame.K_d, pygame.K_RIGHT):
                self._press_action(Action.MENU_RIGHT)
            if event.key == pygame.K_TAB:
                self._press_action(Action.TAB_NEXT)
            if event.key == pygame.K_RETURN:
                self._press_action(Action.CONFIRM)
            # Stage K15: CONFIRM/RESTART/PAUSE stay hardcoded to their
            # physical keys - not in game/keybinds.py's REMAPPABLE list,
            # since every menu's keyboard-nav assumptions (and the
            # while-paused RESTART trick below) are built around them never
            # moving. ATTACK/CAST_3 default to these exact same physical
            # keys (SPACE/R) but are checked independently right below via
            # BINDINGS, so remapping one doesn't drag the other along.
            if event.key == pygame.K_SPACE:
                self._press_action(Action.CONFIRM)
                self._press_action(Action.SECRET)
            if event.key == pygame.K_ESCAPE:
                self._press_action(Action.PAUSE)
            if event.key == pygame.K_r:
                self._press_action(Action.RESTART)

            from game.keybinds import BINDINGS
            if event.key == BINDINGS["ATTACK"]:
                self._press_action(Action.ATTACK)
            if event.key == BINDINGS["CAST_1"]:
                self._press_action(Action.CAST_1)
            if event.key == BINDINGS["CAST_2"]:
                self._press_action(Action.CAST_2)
            if event.key == BINDINGS["CAST_3"]:
                # Unconsumed while paused (see RESTART above) - cleared
                # every frame (InputManager.update()), so this can't leak
                # into a stray heal cast on unpause.
                self._press_action(Action.CAST_3)
            if event.key == BINDINGS["DASH"]:
                self._press_action(Action.DASH)
            if event.key == BINDINGS["PICKAXE"]:
                self._press_action(Action.PICKAXE)
            if event.key == BINDINGS["PAPERDOLL"]:
                self._press_action(Action.PAPERDOLL)
            if event.key == BINDINGS["ITEMS"]:
                self._press_action(Action.ITEMS)
            if event.key == BINDINGS["LEADERBOARD"]:
                self._press_action(Action.LEADERBOARD)
            if event.key == BINDINGS["TOGGLE_HOTBAR"]:
                # Stage K12: only meaningful inside the Items overlay ("seus
                # itens" row -> toggle hotbar selection), consumed nowhere
                # else - safe to bind globally like every other menu action.
                self._press_action(Action.TOGGLE_HOTBAR)
            if event.key == pygame.K_1:
                self._press_action(Action.USE_1)
            if event.key == pygame.K_2:
                self._press_action(Action.USE_2)
            if event.key == pygame.K_3:
                self._press_action(Action.USE_3)
            if event.key == pygame.K_m:
                self._press_action(Action.DEV_NEXT_LEVEL)
            if event.key == pygame.K_n:
                self._press_action(Action.DEV_PREV_LEVEL)
            if event.key == pygame.K_F1:
                self._press_action(Action.DEBUG_PANEL)
            if event.key == pygame.K_F11:
                self._press_action(Action.FULLSCREEN)
            if event.key == pygame.K_F12:
                self._press_action(Action.MUTE)

        # Stage K24: `and not self.touch_active` on all 3 mouse branches
        # below - measured live with a real Playwright touchscreen tap
        # (not theorized): a genuine touch on a touchscreen ALSO fires a
        # synthetic/"ghost" MOUSEBUTTONDOWN (standard browser legacy-
        # compatibility behavior for pages that only listen for mouse
        # events), which this code used to process as if it were real
        # desktop mouse input. That's what "a mira vermelha nao coincide
        # com onde o usuario esta tocando" actually was: the red crosshair
        # (this branch's only job) was drawn at the *ghost* mouse event's
        # position, a separate/differently-timed event from the real touch
        # the player saw feedback for elsewhere - and since Dash defaults
        # to MOUSE1, every real tap anywhere on the touch HUD was also
        # silently firing a Dash attempt via the BINDINGS loop below
        # (confirmed: tapping the joystick's exact center produced an
        # "Investida bloqueada" toast, Dash's own failure message).
        # touch_active is one-way (set by the first real FINGERDOWN, never
        # cleared) - once a session is confirmed touch, mouse events for
        # the rest of it are always ghosts, never real input.
        elif event.type == pygame.MOUSEBUTTONDOWN and not self.touch_active:
            # Stage K22: any remappable action (Dash by default - see
            # game/keybinds.py's DEFAULT_BINDINGS) can now be bound to a
            # mouse button, checked the same way the KEYDOWN branch above
            # checks BINDINGS - "MOUSE{button}" against the live binding
            # string. Runs for every button (not just 1) so right/middle
            # click work as bindings too, independent of the button==1-only
            # UI-tap/crosshair logic below.
            from game.keybinds import BINDINGS
            mouse_code = f"MOUSE{event.button}"
            for action_name, bound in BINDINGS.items():
                if bound == mouse_code:
                    self._press_action(Action[action_name])

            if event.button == 1:
                pos = _corrected_mouse_pos(event.pos)
                self._mouse_screen_pos = pos
                self._crosshair_pos = pos
                self._crosshair_timer = self._CROSSHAIR_DURATION
                self._pointer_down("mouse", *pos)
        elif event.type == pygame.MOUSEMOTION and not self.touch_active:
            pos = _corrected_mouse_pos(event.pos)
            self._mouse_screen_pos = pos
            self._pointer_move("mouse", *pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and not self.touch_active:
            self._pointer_up("mouse")

        elif event.type == pygame.FINGERDOWN:
            self.touch_active = True
            x, y = event.x * self.screen_w, event.y * self.screen_h
            self._pointer_down(event.finger_id, x, y)
        elif event.type == pygame.FINGERMOTION:
            x, y = event.x * self.screen_w, event.y * self.screen_h
            self._pointer_move(event.finger_id, x, y)
        elif event.type == pygame.FINGERUP:
            self._pointer_up(event.finger_id)

    def _pointer_down(self, pid, x, y):
        claimed = None
        # Stage J12: these hit-tests are for the mobile-only virtual
        # controls, which are invisible on PC (touch_active is deliberately
        # never set by a mouse click - see MOUSEBUTTONDOWN above). Without
        # this guard, a plain desktop click anywhere near where the
        # joystick/attack/spell/item buttons WOULD be on mobile (e.g. the
        # joystick's generous radius*1.4 hit circle at the bottom-left) got
        # silently claimed and never became a tap - so "click outside a
        # panel closes it" could randomly eat clicks depending on screen
        # position, even though nothing was drawn there.
        if self.touch_active:
            if self.joystick.contains(x, y):
                self.joystick.press(pid, x, y)
                claimed = "joystick"
            elif self.attack_button.contains(x, y):
                self.attack_button.press(pid)
                # Stage J13: no immediate fire - aimable, drag to aim, then
                # GameplayState.update() polls active+has_aim to swing.
                claimed = "attack"
            elif self.pause_button.contains(x, y):
                self.pause_button.press(pid)
                self._press_action(Action.PAUSE)
                claimed = "pause"
            elif self.debug_button.contains(x, y):
                self.debug_button.press(pid)
                self._press_action(Action.DEBUG_PANEL)
                claimed = "debug"
            elif self.dash_button.contains(x, y):
                self.dash_button.press(pid)
                # Same "no immediate fire, drag to aim" shape as the attack
                # button above - GameplayState.update() polls active+has_aim.
                claimed = "dash"
            elif self.pickaxe_button.contains(x, y):
                self.pickaxe_button.press(pid)
                claimed = "pickaxe"
            else:
                for i, btn in enumerate(self.spell_buttons):
                    if btn.contains(x, y):
                        btn.press(pid)
                        if not btn.aimable:
                            self._press_action(btn.action)
                        claimed = ("spell", i)
                        break
                else:
                    for i, btn in enumerate(self.item_buttons):
                        if btn.contains(x, y):
                            btn.press(pid)
                            self._press_action(btn.action)
                            claimed = ("item", i)
                            break

        self._pointers[pid] = {
            "x": x, "y": y,
            "start_x": x, "start_y": y,
            "start_t": self._time,
            "claimed": claimed,
        }

    def _pointer_move(self, pid, x, y):
        p = self._pointers.get(pid)
        if p is None:
            return
        p["x"], p["y"] = x, y
        claimed = p["claimed"]
        if claimed == "joystick":
            self.joystick.drag(pid, x, y)
        elif claimed == "attack":
            self.attack_button.drag(pid, x, y)
        elif claimed == "dash":
            self.dash_button.drag(pid, x, y)
        elif claimed == "pickaxe":
            self.pickaxe_button.drag(pid, x, y)
        elif isinstance(claimed, tuple) and claimed[0] == "spell":
            self.spell_buttons[claimed[1]].drag(pid, x, y)

    def _pointer_up(self, pid):
        p = self._pointers.pop(pid, None)
        if p is None:
            return
        claimed = p["claimed"]
        if claimed == "joystick":
            self.joystick.release(pid)
        elif claimed == "attack":
            self.attack_button.release(pid)
        elif claimed == "dash":
            self.dash_button.release(pid)
        elif claimed == "pickaxe":
            self.pickaxe_button.release(pid)
        elif claimed == "pause":
            self.pause_button.release(pid)
        elif claimed == "debug":
            self.debug_button.release(pid)
        elif isinstance(claimed, tuple) and claimed[0] == "spell":
            self.spell_buttons[claimed[1]].release(pid)
        elif isinstance(claimed, tuple) and claimed[0] == "item":
            self.item_buttons[claimed[1]].release(pid)
        else:
            dist = math.hypot(p["x"] - p["start_x"], p["y"] - p["start_y"])
            duration = self._time - p["start_t"]
            if dist <= TAP_MAX_MOVEMENT and duration <= TAP_MAX_DURATION:
                self._taps.append((p["x"], p["y"]))

    # ------------------------------------------------------------- lifecycle
    def update(self, dt):
        self._time += dt
        if self._crosshair_timer > 0:
            self._crosshair_timer -= dt
        self.attack_button.update(dt)
        self.dash_button.update(dt)
        self.pickaxe_button.update(dt)
        self.pause_button.update(dt)
        self.debug_button.update(dt)
        for btn in self.spell_buttons:
            btn.update(dt)
        for btn in self.item_buttons:
            btn.update(dt)
        # Anything not consumed by a state this frame is stale - drop it so it
        # can't leak into a different screen after a state transition.
        self._actions.clear()
        self._taps.clear()

    def draw(self, surface, hide_controls=False, debug_panel_open=False):
        self._draw_crosshair(surface)
        if not self.touch_active:
            return
        # Stage K24: called with hide_controls=True while any menu/pause
        # overlay is open (GameplayState.draw()) - the joystick/attack/
        # spell/item buttons used to always draw last, on top of every
        # overlay, since this ran unconditionally after all of them. A
        # closed menu doesn't need this flag at all (touch_active alone
        # already gates everything below on desktop).
        if not hide_controls:
            self.joystick.draw(surface)
            self.attack_button.draw(surface)
            self.dash_button.draw(surface)
            self.pickaxe_button.draw(surface)
            self.pause_button.draw(surface)
            for btn in self.spell_buttons:
                btn.draw(surface)
            for btn in self.item_buttons:
                btn.draw(surface)
        # Stage K24 follow-up: debug_button is the one exception - when
        # IT'S the reason hide_controls is True (the debug panel itself is
        # open), it has to stay visible/tappable, or a mobile player who
        # opened the panel would have no way back out of it (unlike every
        # other overlay, which already closes via a tap outside/its own
        # close control - the debug panel is keyboard/F1-shortcut-driven
        # otherwise).
        if not hide_controls or debug_panel_open:
            self.debug_button.draw(surface)

    def _draw_crosshair(self, surface):
        """Stage J11: marks the (now _corrected_mouse_pos()-corrected)
        position of the last real mouse click, fading out over
        _CROSSHAIR_DURATION - drawn regardless of touch_active (mouse
        clicks happen on desktop, where the virtual touch controls above
        are never shown). Kept on permanently (not debug-only) per the
        user's request - upcoming mouse-aimed combat needs the same
        "where does the game think the pointer is" visibility, and it's
        exactly what originally measured the correction this now applies
        (see _corrected_mouse_pos's docstring)."""
        if self._crosshair_timer <= 0 or self._crosshair_pos is None:
            return
        alpha = int(255 * (self._crosshair_timer / self._CROSSHAIR_DURATION))
        x, y = self._crosshair_pos
        size = 14
        layer = pygame.Surface((size * 2 + 4, size * 2 + 4), pygame.SRCALPHA)
        cx, cy = layer.get_width() // 2, layer.get_height() // 2
        color = (255, 40, 40, alpha)
        pygame.draw.line(layer, color, (cx - size, cy), (cx + size, cy), 3)
        pygame.draw.line(layer, color, (cx, cy - size), (cx, cy + size), 3)
        pygame.draw.circle(layer, color, (cx, cy), size, 2)
        surface.blit(layer, (x - cx, y - cy))
