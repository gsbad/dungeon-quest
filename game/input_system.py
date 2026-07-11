import math
import pygame
from enum import Enum, auto
from game.theme import font

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
    SECRET = auto()
    PAPERDOLL = auto()
    ITEMS = auto()
    CAST_1 = auto()
    CAST_2 = auto()
    CAST_3 = auto()
    CAST_SELECTED = auto()


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
    """Round tap button. `label` is drawn centered; `action` is fired once on press."""

    def __init__(self, cx, cy, radius, label, action):
        self.cx = cx
        self.cy = cy
        self.radius = radius
        self.label = label
        self.action = action
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
        self.attack_button = VirtualButton(screen_w - 90, screen_h - 100, 48, "ATK", Action.ATTACK)
        self.pause_button = VirtualButton(screen_w - 40, 40, 26, "II", Action.PAUSE)
        self.paperdoll_button = VirtualButton(screen_w // 2, screen_h - 110, 30, "C", Action.PAPERDOLL)
        self.items_button = VirtualButton(screen_w - 200, screen_h - 110, 28, "I", Action.ITEMS)
        # Selecting *which* spell happens on the paperdoll's spell tab
        # (Stage B2) - this button just fires whatever's currently selected,
        # same split as the plan's "1 botao conjurar" for mobile.
        self.cast_button = VirtualButton(screen_w - 90, screen_h - 230, 36, "MAG", Action.CAST_SELECTED)

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
            if event.key == pygame.K_c:
                self._press_action(Action.PAPERDOLL)
            if event.key == pygame.K_i:
                self._press_action(Action.ITEMS)
            if event.key == pygame.K_1:
                self._press_action(Action.CAST_1)
            if event.key == pygame.K_2:
                self._press_action(Action.CAST_2)
            if event.key == pygame.K_3:
                self._press_action(Action.CAST_3)

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
        elif self.paperdoll_button.contains(x, y):
            self.paperdoll_button.press(pid)
            self._press_action(Action.PAPERDOLL)
            claimed = "paperdoll"
        elif self.items_button.contains(x, y):
            self.items_button.press(pid)
            self._press_action(Action.ITEMS)
            claimed = "items"
        elif self.cast_button.contains(x, y):
            self.cast_button.press(pid)
            self._press_action(Action.CAST_SELECTED)
            claimed = "cast"

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
        if p["claimed"] == "joystick":
            self.joystick.release(pid)
        elif p["claimed"] == "attack":
            self.attack_button.release(pid)
        elif p["claimed"] == "pause":
            self.pause_button.release(pid)
        elif p["claimed"] == "paperdoll":
            self.paperdoll_button.release(pid)
        elif p["claimed"] == "items":
            self.items_button.release(pid)
        elif p["claimed"] == "cast":
            self.cast_button.release(pid)
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
        self.paperdoll_button.update(dt)
        self.items_button.update(dt)
        self.cast_button.update(dt)
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
        self.paperdoll_button.draw(surface)
        self.items_button.draw(surface)
        self.cast_button.draw(surface)
