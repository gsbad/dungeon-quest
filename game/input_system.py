import math
import pygame
from enum import Enum, auto
from game.theme import font
from game.assets import create_spell_icon, create_sword_icon, create_potion_icon
from game.items import ITEMS

TAP_MAX_DURATION = 0.35
TAP_MAX_MOVEMENT = 18
JOYSTICK_DEADZONE = 0.15


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
    USE_1 = auto()
    USE_2 = auto()
    USE_3 = auto()
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
HELP_ENTRIES = [
    ("WASD / Setas", "Mover o personagem"),
    ("ESPACO", "Atacar corpo a corpo"),
    ("F", "Conjurar Bola de Fogo"),
    ("Q", "Conjurar Nova de Gelo"),
    ("R", "Conjurar Luz Curativa / Reiniciar (na tela de pausa ou de morte)"),
    ("4 / 5 / 6", "Usar item (slots do hotbar)"),
    ("C", "Abrir/fechar o menu Personagem"),
    ("I", "Abrir/fechar o menu Itens"),
    ("L", "Abrir/fechar o Ranking (requer login Google)"),
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
    falls back to rendering `label` as text. `action` is fired once on press."""

    def __init__(self, cx, cy, radius, label, action, icon=None):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.label = label
        self.action = action
        self.icon = icon
        self.pointer_id = None
        self.press_flash = 0.0
        self._font = None

    def contains(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.radius ** 2

    def press(self, pointer_id):
        self.pointer_id = pointer_id
        self.press_flash = 1.0

    def release(self, pointer_id):
        if pointer_id == self.pointer_id:
            self.pointer_id = None

    @property
    def active(self):
        return self.pointer_id is not None

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

        if self.icon is not None:
            size = int(self.radius * 1.4)
            scaled = pygame.transform.scale(self.icon, (size, size))
            surface.blit(scaled, (self.cx - size // 2, self.cy - size // 2))
            return

        if self._font is None:
            self._font = font(20)
        txt = self._font.render(self.label, True, (35, 25, 10))
        surface.blit(txt, (self.cx - txt.get_width() // 2, self.cy - txt.get_height() // 2))


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

        self.joystick = VirtualJoystick(100, screen_h - 120, radius=70, knob_radius=32)
        self.attack_button = VirtualButton(screen_w - 90, screen_h - 100, 48, "ATK", Action.ATTACK,
                                            icon=create_sword_icon())
        self.pause_button = VirtualButton(screen_w - 40, 40, 26, "II", Action.PAUSE)
        # Stage H3: the corner PaperdollButton/ItemsButton (states.py) already
        # cover "C"/"I" on both mobile and desktop, so the touch-only "C"/"I"
        # VirtualButtons that used to sit between the joystick and ATK were
        # pure duplicates - removed to free up that space for the spell arc.
        #
        # 3 buttons in an arc around the attack button (one per spell, same
        # radius the old single "MAG" button had) instead of a single
        # cast-whatever's-selected button - each one fires its spell's own
        # Action.CAST_n directly, same binding as the F/Q/R keyboard keys.
        atk = self.attack_button
        spell_btn_radius = 36
        arc_distance = atk.radius + 14 + spell_btn_radius
        arc_angles_deg = [180, 135, 90]  # left, up-left, up (y-down screen coords)
        cast_actions = [Action.CAST_1, Action.CAST_2, Action.CAST_3]
        from game.spells import ORDER as SPELL_ORDER
        self.spell_buttons = []
        for angle_deg, action, spell_id in zip(arc_angles_deg, cast_actions, SPELL_ORDER):
            rad = math.radians(angle_deg)
            bx = atk.cx + math.cos(rad) * arc_distance
            by = atk.cy - math.sin(rad) * arc_distance
            btn = VirtualButton(bx, by, spell_btn_radius, "", action,
                                 icon=create_spell_icon(spell_id))
            self.spell_buttons.append(btn)

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

    # ------------------------------------------------------------- raw events
    def feed(self, event):
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
            if event.key == pygame.K_SPACE:
                self._press_action(Action.CONFIRM)
                self._press_action(Action.ATTACK)
                self._press_action(Action.SECRET)
            if event.key == pygame.K_ESCAPE:
                self._press_action(Action.PAUSE)
            if event.key == pygame.K_r:
                self._press_action(Action.RESTART)
                # Same physical key also casts Luz Curativa (SPELL_ORDER[2])
                # during gameplay - no collision with RESTART above, since
                # that's only consumed while paused (game/states.py) and
                # CAST_3 only while not paused; unconsumed actions are
                # cleared every frame (InputManager.update()), so pressing R
                # while paused can't leak into a stray heal cast on unpause.
                self._press_action(Action.CAST_3)
            if event.key == pygame.K_c:
                self._press_action(Action.PAPERDOLL)
            if event.key == pygame.K_i:
                self._press_action(Action.ITEMS)
            if event.key == pygame.K_l:
                self._press_action(Action.LEADERBOARD)
            if event.key == pygame.K_f:
                self._press_action(Action.CAST_1)
            if event.key == pygame.K_q:
                self._press_action(Action.CAST_2)
            if event.key == pygame.K_4:
                self._press_action(Action.USE_1)
            if event.key == pygame.K_5:
                self._press_action(Action.USE_2)
            if event.key == pygame.K_6:
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

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Deliberately doesn't set touch_active - a PC mouse click still
            # needs to register taps (menu buttons, paperdoll +/-), but it
            # shouldn't make the mobile-only joystick/attack/pause/paperdoll
            # overlay pop up on desktop. Real touchscreens send FINGERDOWN
            # separately (see below), so this doesn't affect mobile.
            self.debug_last_raw = event.pos
            self.debug_last_scaled = event.pos
            self._pointer_down("mouse", *event.pos)
        elif event.type == pygame.MOUSEMOTION:
            self._pointer_move("mouse", *event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
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
        if self.joystick.contains(x, y):
            self.joystick.press(pid, x, y)
            claimed = "joystick"
        elif self.attack_button.contains(x, y):
            self.attack_button.press(pid)
            self._press_action(Action.ATTACK)
            claimed = "attack"
        elif self.pause_button.contains(x, y):
            self.pause_button.press(pid)
            self._press_action(Action.PAUSE)
            claimed = "pause"
        else:
            for i, btn in enumerate(self.spell_buttons):
                if btn.contains(x, y):
                    btn.press(pid)
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
        if p["claimed"] == "joystick":
            self.joystick.drag(pid, x, y)

    def _pointer_up(self, pid):
        p = self._pointers.pop(pid, None)
        if p is None:
            return
        claimed = p["claimed"]
        if claimed == "joystick":
            self.joystick.release(pid)
        elif claimed == "attack":
            self.attack_button.release(pid)
        elif claimed == "pause":
            self.pause_button.release(pid)
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
        self.attack_button.update(dt)
        self.pause_button.update(dt)
        for btn in self.spell_buttons:
            btn.update(dt)
        for btn in self.item_buttons:
            btn.update(dt)
        # Anything not consumed by a state this frame is stale - drop it so it
        # can't leak into a different screen after a state transition.
        self._actions.clear()
        self._taps.clear()

    def draw(self, surface):
        if not self.touch_active:
            return
        self.joystick.draw(surface)
        self.attack_button.draw(surface)
        self.pause_button.draw(surface)
        for btn in self.spell_buttons:
            btn.draw(surface)
        for btn in self.item_buttons:
            btn.draw(surface)
