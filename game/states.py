import pygame
import sys
import math
import time
import random
from game.player import Player, hotbar_slots
from game.items import ITEMS, use_item
from game.level import Level, LEVEL_MAPS
from game.boss import Boss, CacodemonBoss, Projectile
from game.enemy import Particle, Enemy
from game.camera import Camera
from game.paperdoll import Paperdoll
from game.merchant import ItemsOverlay
from game.debug_panel import DebugPanel
from game.leaderboard import LeaderboardOverlay
from game.weather import WeatherSystem
from game.assets import (
    create_heart_sprite, create_mana_orb_sprite, create_logo_sprite,
    create_victory_hero_sprite, create_player_sprite,
)
from game.input_system import Action, FullscreenButton, PaperdollButton, ItemsButton, LeaderboardButton
from game.audio import SoundButton
from game.stats import POINTS_PER_LEVEL, MAX_LEVEL
from game.spells import SPELLS, ORDER as SPELL_ORDER, missing_requirements, requirement_text
from game.difficulty import DIFFICULTIES, ORDER as DIFFICULTY_ORDER, next_difficulty, is_unlocked
from game.affixes import AFFIXES
from game.theme import (
    SW, SH, font, BG_MENU, BG_GAME_OVER, BG_VICTORY, TITLE_MENU, TITLE_PAUSE,
    ACCENT_GOLD, SELECTED, UNSELECTED, SUBTEXT, PANEL_FILL, PANEL_BORDER,
)
from game.ui import draw_text, TextButton, Panel, ProgressBar

# Maps a level's "boss" key (LEVEL_MAPS) to (BossClass, spawn_dx_from_center, spawn_y).
# Data-driven so new levels/bosses only need a registry entry + LEVEL_MAPS metadata,
# not new level_num==N literals scattered across this file.
# Value is a (factory, spawn_dx, spawn_y) tuple - factory takes (x, y) and
# returns the boss instance. Orc Warlord/Necromancer/Shadow King all share
# the exact same Boss class (Stage B4's "one rig, several bosses"), just
# with a different boss_id selecting stats/name/palette from
# game/stats.py's BOSS_ARCHETYPES - only CacodemonBoss is its own class.
# Factories take (x, y, enrage_frac) so difficulty tiers (Stage B5) can
# move Boss's phase-2 threshold without either Boss subclass needing a
# special case - CacodemonBoss has no phase concept, so its factory just
# ignores the argument.
BOSS_REGISTRY = {
    "orc_warlord": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="orc_warlord", enrage_frac=ef, audio_mgr=am), 48, 80),
    "necromancer": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="necromancer", enrage_frac=ef, audio_mgr=am), 48, 80),
    "shadow_king": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="shadow_king", enrage_frac=ef, audio_mgr=am), 48, 80),
    "cacodemon": (lambda x, y, ef=0.5, am=None: CacodemonBoss(x, y, audio_mgr=am), 40, 100),
}


# ─── Particle star for menus ──────────────────────────────────────────────────
class Star:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = random.randint(0, SW)
        self.y = random.randint(0, SH)
        self.speed = random.uniform(20, 80)
        self.size  = random.randint(1, 3)
        self.alpha = random.randint(80, 255)

    def update(self, dt):
        self.y += self.speed * dt
        if self.y > SH:
            self.reset()
            self.y = 0

    def draw(self, surface):
        s = pygame.Surface((self.size*2, self.size*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255,255,255,self.alpha), (self.size,self.size), self.size)
        surface.blit(s, (int(self.x), int(self.y)))


class Pickup:
    """A heart or mana-orb dropped on the ground (Stage F8 generalized the
    old heart-only HeartPickup to also cover mana, same bob-animation and
    lifecycle for both - only `kind` differs, read by
    GameplayState._check_pickup_pickups() to decide what it heals)."""

    def __init__(self, x, y, sprite, kind):
        self.x = float(x)
        self.y = float(y)
        self.sprite = sprite
        self.kind = kind
        self.rect = pygame.Rect(self.x, self.y, sprite.get_width(), sprite.get_height())
        self._bob = random.uniform(0, math.pi * 2)
        self.offset = 0

    def update(self, dt):
        self._bob += dt * 3.0
        self.offset = math.sin(self._bob) * 3
        self.rect.topleft = (int(self.x), int(self.y))

    def draw(self, surface, cam_x, cam_y):
        surface.blit(self.sprite, (int(self.x - cam_x), int(self.y - cam_y + self.offset)))


# ─── Menu State ───────────────────────────────────────────────────────────────
class MenuState:
    def __init__(self, screen, input_mgr, audio_mgr, has_save=False):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.stars = [Star() for _ in range(80)]
        self.t = 0
        self.selected = 0
        self.options = (["CONTINUAR", "DIFICULDADE", "RESETAR CHAR"] if has_save else ["NOVO JOGO"]) + ["SAIR"]
        # 4 options (has_save) need tighter spacing to clear the controls
        # panel above (bottom edge ~y380) and stay on-screen (SH=600).
        base_y, step = (385, 46) if len(self.options) >= 4 else (410, 55)
        self.option_buttons = [
            TextButton(opt, SW//2, base_y + i*step, pad_x=30, pad_y=15)
            for i, opt in enumerate(self.options)
        ]
        self.controls_panel = Panel(320, 160, PANEL_FILL, PANEL_BORDER)

        # Stage H5/H6 - a row of profession portraits where the old credits
        # line used to be. Same create_player_sprite(...)+transform.scale
        # pattern as game/paperdoll.py's _portrait_for() (kept separate,
        # not shared, since Paperdoll's cache is keyed to a Paperdoll
        # instance's lifetime, MenuState's to its own).
        self._portrait_professions = [
            "Guerreiro", "Mago", "Paladino", "Campeao",
            "Cavaleiro Arcano", "Assassino", "Templario",
        ]
        self._portraits = [
            pygame.transform.scale(create_player_sprite("down", False, prof), (48, 48))
            for prof in self._portrait_professions
        ]

    def handle_event(self, event):
        if self.input.consume_action(Action.MENU_UP):
            self.selected = (self.selected - 1) % len(self.options)
            self.audio.play("menu_move")
        if self.input.consume_action(Action.MENU_DOWN):
            self.selected = (self.selected + 1) % len(self.options)
            self.audio.play("menu_move")
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return self.options[self.selected]
        for i, btn in enumerate(self.option_buttons):
            if self.input.tapped_rect(btn.rect):
                self.selected = i
                self.audio.play("menu_select")
                return self.options[i]
        return None

    def update(self, dt):
        self.t += dt
        for star in self.stars:
            star.update(dt)

    def draw(self):
        self.screen.fill(BG_MENU)
        for star in self.stars:
            star.draw(self.screen)

        # Title glow
        glow_r = int(200 + 30 * math.sin(self.t * 2))
        glow_surf = pygame.Surface((500, 120), pygame.SRCALPHA)
        pygame.draw.ellipse(glow_surf, (80, 0, 120, 60), (0, 0, 500, 120))
        self.screen.blit(glow_surf, (150, 80))

        f_title = font(64, bold=True)
        draw_text(self.screen, "DUNGEON QUEST", f_title, TITLE_MENU, SW//2, 90)

        # Stage H5/H6 - profession portrait row where the credits line used
        # to be, same open vertical gap between the title and the controls
        # panel.
        gap = 10
        row_w = len(self._portraits) * 48 + (len(self._portraits) - 1) * gap
        x0 = SW // 2 - row_w // 2
        for i, portrait in enumerate(self._portraits):
            self.screen.blit(portrait, (x0 + i * (48 + gap), 155))

        # Controls box
        self.controls_panel.draw(self.screen, (SW//2-160, 220))

        f_ctrl = font(16, bold=True)
        f_ctrlv = font(16)
        ctrl_title = f_ctrl.render("CONTROLES", True, (200, 150, 255))
        self.screen.blit(ctrl_title, (SW//2 - ctrl_title.get_width()//2, 228))

        controls = [
            ("W / A / S / D",     "Mover personagem"),
            ("^ v < >",           "Mover (alternativo)"),
            ("ESPACO",            "Atacar"),
            ("ESC",               "Menu / Pausar"),
        ]
        for i, (key, desc) in enumerate(controls):
            y = 255 + i * 28
            k_surf = f_ctrl.render(key, True, ACCENT_GOLD)
            d_surf = f_ctrlv.render(desc, True, (200, 200, 220))
            self.screen.blit(k_surf, (SW//2 - 150, y))
            self.screen.blit(d_surf, (SW//2 - 10, y))

        # Menu options
        f_menu = font(32, bold=True)
        for i, opt in enumerate(self.options):
            color = SELECTED if i == self.selected else UNSELECTED
            prefix = "> " if i == self.selected else "  "
            self.option_buttons[i].label = prefix + opt
            self.option_buttons[i].draw(self.screen, f_menu, color)

        # Version
        f_tiny = font(12)
        v = f_tiny.render("Criado por Gustavo Sa", True, (80,80,100))
        self.screen.blit(v, (SW//2 - v.get_width()//2, SH - 24))


# ─── Confirm Character Reset ───────────────────────────────────────────────────
class ConfirmResetState:
    """Safety confirmation before "RESETAR CHAR" actually wipes the save
    (Stage D4) - modeled on GameOverState's shape (stars background, two
    TextButtons, same Action.MENU_UP/DOWN/CONFIRM handling), since it's the
    same "two-choice decision screen" shape. Defaults to NAO so an
    accidental Enter/tap on the menu option itself can't cascade into a
    wipe without a second deliberate confirm."""

    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.stars = [Star() for _ in range(60)]
        self.selected = 0
        self.options = [("NAO - VOLTAR", "menu"), ("SIM - APAGAR TUDO", "reset_confirmed")]
        self.option_buttons = [
            TextButton(label, SW//2, 380 + i*55, pad_x=24, pad_y=14)
            for i, (label, _) in enumerate(self.options)
        ]

    def handle_event(self, event):
        if self.input.consume_action(Action.MENU_UP) or self.input.consume_action(Action.MENU_DOWN):
            self.selected = 1 - self.selected
            self.audio.play("menu_move")
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return self.options[self.selected][1]
        for i, btn in enumerate(self.option_buttons):
            if self.input.tapped_rect(btn.rect):
                self.audio.play("menu_select")
                return self.options[i][1]
        return None

    def update(self, dt):
        self.t += dt
        for s in self.stars:
            s.update(dt)

    def draw(self):
        self.screen.fill(BG_GAME_OVER)
        for s in self.stars:
            s.draw(self.screen)

        f1 = font(48, bold=True)
        pulse = abs(math.sin(self.t * 2))
        r = int(180 + 75 * pulse)
        draw_text(self.screen, "RESETAR PERSONAGEM", f1, (r, 30, 30), SW//2, 160)

        f2 = font(18)
        draw_text(self.screen, "Tem certeza? Nome, nivel, atributos, ouro e progresso",
                  f2, (200,150,150), SW//2, 250)
        draw_text(self.screen, "da masmorra serao apagados. Essa acao nao pode ser desfeita.",
                  f2, (200,150,150), SW//2, 278)

        f3 = font(20, bold=True)
        for i, (label, _) in enumerate(self.options):
            color = SELECTED if i == self.selected else UNSELECTED
            prefix = "> " if i == self.selected else "  "
            self.option_buttons[i].label = prefix + label
            self.option_buttons[i].draw(self.screen, f3, color)


# ─── Difficulty Select ─────────────────────────────────────────────────────────
class DifficultySelectState:
    """Map-select screen (Stage B5): pick which of the 5 tiers to play.
    Locked tiers (per game.difficulty.is_unlocked) show but can't be
    selected - unlocking is sequential, cleared by reaching level 12's
    "victory" at the tier below."""

    def __init__(self, screen, input_mgr, audio_mgr, cleared_difficulties):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.cleared = cleared_difficulties
        self.selected = 0
        self.t = 0
        self.stars = [Star() for _ in range(60)]
        self.option_buttons = [
            TextButton(DIFFICULTIES[d]["name"], SW // 2, 220 + i * 56, pad_x=30, pad_y=13)
            for i, d in enumerate(DIFFICULTY_ORDER)
        ]
        self.back_button = TextButton("[ ESC ] - Voltar", SW // 2, 220 + len(DIFFICULTY_ORDER) * 56 + 20)

    def _unlocked(self, i):
        return is_unlocked(DIFFICULTY_ORDER[i], self.cleared)

    def handle_event(self, event):
        if self.input.consume_action(Action.MENU_UP):
            self.selected = (self.selected - 1) % len(DIFFICULTY_ORDER)
            self.audio.play("menu_move")
        if self.input.consume_action(Action.MENU_DOWN):
            self.selected = (self.selected + 1) % len(DIFFICULTY_ORDER)
            self.audio.play("menu_move")
        if self.input.consume_action(Action.CONFIRM):
            if self._unlocked(self.selected):
                self.audio.play("menu_select")
                return f"difficulty:{DIFFICULTY_ORDER[self.selected]}"
            return None
        if self.input.consume_action(Action.PAUSE):
            return "menu"
        for i, btn in enumerate(self.option_buttons):
            if self.input.tapped_rect(btn.rect):
                if self._unlocked(i):
                    self.audio.play("menu_select")
                    return f"difficulty:{DIFFICULTY_ORDER[i]}"
                return None
        if self.input.tapped_rect(self.back_button.rect):
            self.audio.play("menu_select")
            return "menu"
        return None

    def update(self, dt):
        self.t += dt
        for star in self.stars:
            star.update(dt)

    def draw(self):
        self.screen.fill(BG_MENU)
        for star in self.stars:
            star.draw(self.screen)

        f_title = font(38, bold=True)
        draw_text(self.screen, "SELECIONAR DIFICULDADE", f_title, TITLE_MENU, SW // 2, 90)
        f_hint = font(15)
        draw_text(self.screen, "ESC - Voltar", f_hint, SUBTEXT, SW // 2, 150)

        f_opt = font(24, bold=True)
        for i, d in enumerate(DIFFICULTY_ORDER):
            unlocked = self._unlocked(i)
            if not unlocked:
                color = (90, 90, 100)
                label = f"{DIFFICULTIES[d]['name']} (bloqueado)"
            else:
                color = SELECTED if i == self.selected else UNSELECTED
                label = DIFFICULTIES[d]["name"]
            prefix = "> " if (i == self.selected and unlocked) else "  "
            self.option_buttons[i].label = prefix + label
            self.option_buttons[i].draw(self.screen, f_opt, color)

        self.back_button.draw(self.screen, font(17), SUBTEXT)


# ─── Name Entry ───────────────────────────────────────────────────────────────
class NameEntryState:
    """Shown once when starting "NOVO JOGO", before the character exists.
    Same handle_event/update/draw shape as MenuState. PC types on the
    physical keyboard directly (handle_event already gets the raw pygame
    event); mobile taps an on-screen keyboard grid via input.tapped_rect() -
    the same touch mechanism every other menu/overlay in this game already
    uses, so there's no new browser-API risk (unlike, say, focusing a
    hidden HTML text input to summon the OS keyboard - deliberately not
    used here)."""

    MAX_LEN = 12
    ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    KEY_W, KEY_H, GAP = 52, 48, 6

    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.name = ""
        self.t = 0
        self.stars = [Star() for _ in range(60)]
        self.key_rects = {}
        start_y = 260
        for r, row in enumerate(self.ROWS):
            row_w = len(row) * (self.KEY_W + self.GAP) - self.GAP
            start_x = SW // 2 - row_w // 2
            for i, ch in enumerate(row):
                x = start_x + i * (self.KEY_W + self.GAP)
                y = start_y + r * (self.KEY_H + self.GAP)
                self.key_rects[ch] = pygame.Rect(x, y, self.KEY_W, self.KEY_H)
        action_y = start_y + len(self.ROWS) * (self.KEY_H + self.GAP) + 14
        self.backspace_rect = pygame.Rect(SW // 2 - 160, action_y, 150, 44)
        self.confirm_rect = pygame.Rect(SW // 2 + 10, action_y, 150, 44)

    def _is_allowed_char(self, ch):
        return ch.isalnum() or ch == " "

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.audio.play("menu_select")
                return "name_confirmed"
            elif event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
            elif event.unicode and self._is_allowed_char(event.unicode) and len(self.name) < self.MAX_LEN:
                self.name += event.unicode

        for ch, rect in self.key_rects.items():
            if self.input.tapped_rect(rect):
                if len(self.name) < self.MAX_LEN:
                    self.name += ch
                self.audio.play("menu_move")
                return None
        if self.input.tapped_rect(self.backspace_rect):
            self.name = self.name[:-1]
            self.audio.play("menu_move")
            return None
        if self.input.tapped_rect(self.confirm_rect):
            self.audio.play("menu_select")
            return "name_confirmed"
        return None

    def update(self, dt):
        self.t += dt
        for star in self.stars:
            star.update(dt)

    def draw(self):
        self.screen.fill(BG_MENU)
        for star in self.stars:
            star.draw(self.screen)

        f_title = font(34, bold=True)
        draw_text(self.screen, "COMO SE CHAMA O HEROI?", f_title, TITLE_MENU, SW // 2, 80)

        f_sub = font(16)
        draw_text(self.screen, "Digite no teclado ou toque nas letras", f_sub, SUBTEXT, SW // 2, 130)

        # Name field with a blinking cursor
        cursor = "|" if int(self.t * 2) % 2 == 0 else ""
        f_name = font(28, bold=True)
        draw_text(self.screen, self.name + cursor, f_name, ACCENT_GOLD, SW // 2, 175)

        f_key = font(20, bold=True)
        for ch, rect in self.key_rects.items():
            pygame.draw.rect(self.screen, (40, 30, 70), rect, border_radius=8)
            pygame.draw.rect(self.screen, (160, 140, 210), rect, 1, border_radius=8)
            draw_text(self.screen, ch, f_key, (225, 225, 235), rect.centerx, rect.y + 12, shadow=False)

        f_action = font(17, bold=True)
        pygame.draw.rect(self.screen, (110, 30, 30), self.backspace_rect, border_radius=8)
        pygame.draw.rect(self.screen, (200, 200, 210), self.backspace_rect, 1, border_radius=8)
        draw_text(self.screen, "APAGAR", f_action, (240, 220, 220), self.backspace_rect.centerx,
                  self.backspace_rect.y + 13, shadow=False)

        can_confirm = True  # empty name just falls back to "Heroi"
        pygame.draw.rect(self.screen, (25, 130, 70), self.confirm_rect, border_radius=8)
        pygame.draw.rect(self.screen, (200, 200, 210), self.confirm_rect, 1, border_radius=8)
        draw_text(self.screen, "CONFIRMAR", f_action, (225, 245, 230), self.confirm_rect.centerx,
                  self.confirm_rect.y + 13, shadow=False)

        f_hint = font(14)
        draw_text(self.screen, "ENTER / toque em Confirmar", f_hint, SUBTEXT, SW // 2, SH - 30)


# ─── Stage Complete ─────────────────────────────────────────────────────────
class StageCompleteState:
    """Stage F9: shown once a regular (non-final-boss) level's exit fires,
    before the existing level-name TransitionState - "next:N" on confirm
    re-enters GameStateManager._transition exactly like the old direct
    TransitionState path did, so no other transition logic needs to change."""

    def __init__(self, screen, input_mgr, audio_mgr, level_num, next_level,
                 xp_gained, gold_gained, player):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.level_num = level_num
        self.next_level = next_level
        self.xp_gained = xp_gained
        self.gold_gained = gold_gained
        self.player = player
        self.continue_button = TextButton("[ ENTER ] - Continuar", SW // 2, SH - 90)
        self._xp_bar = ProgressBar(320, 14, (40, 40, 40), (140, 140, 140), border_width=2)

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return f"next:{self.next_level}"
        if self.input.tapped_rect(self.continue_button.rect):
            self.audio.play("menu_select")
            return f"next:{self.next_level}"
        return None

    def update(self, dt):
        pass

    def draw(self):
        self.screen.fill((10, 12, 22))

        f1 = font(40, bold=True)
        draw_text(self.screen, f"Fase {self.level_num} concluida!", f1, ACCENT_GOLD, SW // 2, 110)

        f2 = font(20)
        draw_text(self.screen, f"+{self.xp_gained} XP", f2, (200, 220, 255), SW // 2, 200)
        draw_text(self.screen, f"+{self.gold_gained} ouro", f2, (230, 200, 80), SW // 2, 232)

        bar_x = SW // 2 - self._xp_bar.w // 2
        self._xp_bar.draw(self.screen, bar_x, 280, self.player.xp_frac, ACCENT_GOLD)
        f3 = font(15)
        lvl_label = "Nivel maximo!" if self.player.level >= MAX_LEVEL else f"Nivel {self.player.level}"
        draw_text(self.screen, lvl_label, f3, SUBTEXT, SW // 2, 302)

        f4 = font(18, bold=True)
        self.continue_button.draw(self.screen, f4, (220, 220, 235))


# ─── Transition ───────────────────────────────────────────────────────────────
class TransitionState:
    def __init__(self, screen, next_level, player):
        self.screen = screen
        self.next_level = next_level
        self.player = player
        self.timer = 0
        self.duration = 1.5
        self.done = False

    def handle_event(self, event): pass

    def update(self, dt):
        self.timer += dt
        if self.timer >= self.duration:
            self.done = True

    def draw(self):
        self.screen.fill((0, 0, 0))
        progress = self.timer / self.duration
        alpha = int(255 * (1 - abs(progress - 0.5) * 2))
        f = font(36, bold=True)
        draw_text(self.screen, f"Nivel {self.next_level}", f, TITLE_PAUSE, SW//2, SH//2-20)
        from game.level import LEVEL_MAPS
        next_data = LEVEL_MAPS.get(self.next_level)
        if next_data:
            f2 = font(22)
            draw_text(self.screen, next_data["title"], f2, SUBTEXT, SW//2, SH//2+24)
        if next_data and next_data.get("boss"):
            f3 = font(18)
            draw_text(self.screen, "O BOSS FINAL AGUARDA...", f3, (255,100,100), SW//2, SH//2+60)


# ─── Gameplay State ────────────────────────────────────────────────────────────
class GameplayState:
    def __init__(self, screen, input_mgr, audio_mgr, level_num=1, player=None, save_state=None):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.save_state = save_state
        self.level_num = level_num

        # Difficulty tier (Stage B5) - drives the monster-level bonus, extra
        # enemy speed, level affixes, boss enrage threshold, and champion
        # spawn chance below. Falls back to normal if constructed without a
        # save (shouldn't happen - GameStateManager always passes one - but
        # keeps this class constructible standalone, e.g. for tests).
        self.difficulty_id = save_state["progression"]["current_difficulty"] if save_state else "normal"
        self.difficulty = DIFFICULTIES[self.difficulty_id]
        hastened_mult = 1.25 if "hastened" in self.difficulty["level_affixes"] else 1.0

        self.level = Level(level_num, extra_speed_mult=hastened_mult, ml_bonus=self.difficulty["ml_bonus"],
                           audio_mgr=audio_mgr)
        self.camera = Camera(SW, SH, self.level.width, self.level.height)

        # Stage F3 (Atlas tab): record this level as seen, permanently -
        # separate from highest_level_cleared, which regresses on death.
        if save_state is not None and level_num not in save_state["progression"]["levels_seen"]:
            save_state["progression"]["levels_seen"].append(level_num)

        if player is None:
            sx, sy = self.level.get_player_start()
            self.player = Player(sx, sy, audio_mgr)
        else:
            sx, sy = self.level.get_player_start()
            self.player = player
            self.player.x, self.player.y = sx, sy
            self.player.attacking = False
            self.player.attack_timer = 0

        self.camera.x = self.player.x - SW//2
        self.camera.y = self.player.y - SH//2

        # Paragon rolls (Stage B3) - upgrades some already-spawned enemies
        # in place; Level itself stays unaware Paragon exists at all. Then
        # Champion rolls (Stage B5) do the same for whichever enemies
        # Paragon didn't already claim, at a rate set by the difficulty tier.
        from game.affixes import apply_paragon_rolls, apply_champion_rolls
        apply_paragon_rolls(self.level.enemies, self.player)
        apply_champion_rolls(self.level.enemies, self.difficulty["champion_chance"])

        # Boss, driven by the level's metadata (LEVEL_MAPS[level_num]["boss"])
        self.boss = None
        # Stage F8: hearts used to be boss-level-only (gated by
        # LEVEL_MAPS' now-removed "heart_spawns" flag); a mana orb (rarer)
        # was added alongside it, and both now spawn on every combat level.
        self.pickups = []
        self._pickup_sprites = {"heart": create_heart_sprite(True), "mana": create_mana_orb_sprite()}
        self.pickup_spawn_timer = random.uniform(8.0, 14.0)
        boss_key = self.level.data.get("boss")
        if boss_key:
            boss_factory, spawn_dx, spawn_y = BOSS_REGISTRY[boss_key]
            self.boss = boss_factory(SW//2 - spawn_dx, spawn_y, self.difficulty["boss_enrage_frac"], audio_mgr)
        # Enemies spawned by a boss's "summon" pattern (necromancer, Stage
        # D6) - tracked separately from self.level.enemies just to cap how
        # many of THIS boss's adds can be alive at once; the enemies
        # themselves live in self.level.enemies like any other mob once
        # spawned, so game/level.py's normal update handles them.
        self.boss_summons = []

        self.paused = False
        self.next_state = None
        self._restart_button = TextButton(
            "R / toque aqui - Reiniciar", SW//2, SH//2+50, pad_x=20, pad_y=14
        )

        # Level-entry message
        self.msg_timer = 2.5
        diff_suffix = f" [{self.difficulty['name']}]" if self.difficulty_id != "normal" else ""
        self.msg_text = f"Nivel {level_num}: {self.level.data['title']}{diff_suffix}"

        # Screen shake
        self.shake = 0

        self.level_up_particles = []

        self.paperdoll = Paperdoll()
        self.paperdoll_open = False
        # Stage F2: level-up opens the Paperdoll's stats tab automatically
        # and, while this is True, ESC/C can't close it until every point is
        # spent - otherwise the toast was too easy to miss and points sat
        # unspent for the rest of the run.
        self.level_up_forced = False
        self.items = ItemsOverlay()
        self.items_open = False
        self.debug_panel = DebugPanel()
        self.debug_panel_open = False
        self.leaderboard = LeaderboardOverlay()
        self.leaderboard_open = False

        # "Penumbra" level affix (Stage B5) forces a darker fog than the
        # level's own weather flavor, combat levels only - boss arenas are
        # already an intense enough test on their own.
        weather_id = self.level.data.get("weather")
        if "dimming" in self.difficulty["level_affixes"] and self.level.data["type"] == "combat":
            weather_id = "dimming_fog"
        self.weather = WeatherSystem(weather_id)

        # Weather's speed_mult/visibility_mult (Stage D5) - a fresh
        # GameplayState per level means this naturally resets on the next
        # level instead of needing explicit cleanup. Enemy aggro range
        # shrinks in fog/gloom - this is what finally gives
        # visibility_mult a gameplay effect instead of just informing how
        # heavy the overlay looks.
        self.player.weather_speed_mult = self.weather.speed_multiplier
        for enemy in self.level.enemies:
            enemy.aggro_range *= self.weather.visibility_multiplier

        # Periodic weather debuff (e.g. Calor while sandstorm/ashfall is
        # active) - same shape as the cursed_ground timer below, but driven
        # by the level's weather instead of a difficulty-tier affix, so it
        # runs on boss levels too (weather is part of a level's identity,
        # not an optional harder-difficulty extra).
        weather_debuff = self.weather.defn.get("debuff") if self.weather.defn else None
        self._weather_debuff_effect = weather_debuff[0] if weather_debuff else None
        self._weather_debuff_timer = weather_debuff[1] if weather_debuff else None

        # "Chao Amaldicoado" level affix (Stage B5) - periodic Poison while
        # exploring a combat level, independent of taking any hit. None
        # disables it entirely (cheaper than checking membership every tick).
        self._cursed_ground_timer = (
            8.0 if "cursed_ground" in self.difficulty["level_affixes"]
            and self.level.data["type"] == "combat" else None
        )

        # Fireball projectiles - a separate list from Enemy's/Boss's own
        # projectiles since these belong to the player and can hit either
        # regular enemies or a boss depending on which fight this level is.
        self.player_projectiles = []

        # Stage F6 - only re-touch the browser tab title (and only import
        # `js`) when name/level actually changed, not every frame.
        self._last_title_key = None

        # Stage F9 - snapshot for the stage-complete screen's "XP ganho" /
        # "+N ouro" figures, diffed against the player's running totals when
        # this level's exit fires (see GameStateManager._transition's
        # "next:" branch).
        self._xp_at_level_start = self.player.xp_earned_total
        self._gold_at_level_start = self.player.gold

    def handle_event(self, event):
        # Dev/test shortcuts (Stage B4 follow-up): jump forward/back one
        # level directly, bypassing bosses/exits - lets every one of the 13
        # layouts be reached and re-checked without playing the whole
        # campaign each time. Always active, even mid-boss-fight or with an
        # overlay open - it's a debug tool, not a gameplay control.
        if self.input.consume_action(Action.DEV_NEXT_LEVEL):
            self._dev_jump(1)
        if self.input.consume_action(Action.DEV_PREV_LEVEL):
            self._dev_jump(-1)

        if self.input.consume_action(Action.PAPERDOLL):
            self.toggle_paperdoll()
        if self.input.consume_action(Action.ITEMS):
            self.toggle_items()
        if self.input.consume_action(Action.LEADERBOARD):
            self.toggle_leaderboard()
        if self.input.consume_action(Action.DEBUG_PANEL):
            if not self.paused and not self.paperdoll_open and not self.items_open and not self.leaderboard_open:
                self.debug_panel_open = not self.debug_panel_open
                if not self.debug_panel_open and self.debug_panel.consume_difficulty_dirty():
                    self._dev_jump(0)
        if self.paperdoll_open or self.items_open or self.debug_panel_open or self.leaderboard_open:
            # Stage F2: ESC also closes whichever menu is open, same as
            # pressing the key that opened it, instead of only pausing.
            # Stage J12 fixed a longstanding gap here: debug_panel_open had
            # no ESC branch at all (only F1 closed it) - it does now, same
            # as every other overlay.
            if self.input.consume_action(Action.PAUSE):
                if self.paperdoll_open:
                    self.toggle_paperdoll()
                elif self.items_open:
                    self.toggle_items()
                elif self.leaderboard_open:
                    self.toggle_leaderboard()
                elif self.debug_panel_open:
                    self.debug_panel_open = False
                    if self.debug_panel.consume_difficulty_dirty():
                        self._dev_jump(0)
            return
        if self.input.consume_action(Action.PAUSE):
            self.paused = not self.paused
        if self.paused:
            if self.input.consume_action(Action.RESTART):
                self.next_state = "restart"
            elif self.input.tapped_rect(self._restart_button.rect):
                self.next_state = "restart"
        elif self.input.consume_action(Action.ATTACK):
            self.player.try_attack()
        elif self.input.consume_action(Action.CAST_1):
            self._attempt_cast(SPELL_ORDER[0])
        elif self.input.consume_action(Action.CAST_2):
            self._attempt_cast(SPELL_ORDER[1])
        elif self.input.consume_action(Action.CAST_3):
            self._attempt_cast(SPELL_ORDER[2])
        elif self.input.consume_action(Action.CAST_SELECTED):
            self._attempt_cast(self.player.selected_spell)
        elif self.input.consume_action(Action.USE_1):
            use_item(self.player, list(ITEMS)[0])
        elif self.input.consume_action(Action.USE_2):
            use_item(self.player, list(ITEMS)[1])
        elif self.input.consume_action(Action.USE_3):
            use_item(self.player, list(ITEMS)[2])

    def _handle_hotbar_taps(self):
        for kind, key, rect in hotbar_slots():
            # Neither slot kind is drawn on touch (see Player._draw_hotbar) -
            # the spell_buttons/item_buttons rows handle that input instead,
            # so skip the now-invisible tap targets to match.
            if self.input.touch_active:
                continue
            if not self.input.tapped_rect(rect):
                continue
            if kind == "spell":
                self._attempt_cast(key)
            else:
                use_item(self.player, key)
            return

    def _dev_jump(self, delta):
        target = self.level_num + delta
        if target in LEVEL_MAPS:
            self.next_state = f"next:{target}"

    def toggle_paperdoll(self):
        """Shared by the C keypress (handle_event) and Stage G5's
        PaperdollButton tap (GameStateManager.update()) - one place owning
        the "only one overlay at a time" guard, instead of duplicating it
        per input source. Stage J2: a level-up still auto-opens this panel
        on the stats tab (see update()'s pending_level_up branch), but no
        longer LOCKS it - closing with points unspent is allowed, the
        points just wait in player.unspent_points until the player comes
        back."""
        if self.paperdoll_open:
            self.paperdoll_open = False
            self.level_up_forced = False
        elif not self.paused and not self.items_open and not self.debug_panel_open and not self.leaderboard_open:
            self.paperdoll_open = True

    def toggle_items(self):
        """Shared by the I keypress and Stage G5's ItemsButton tap."""
        if self.items_open:
            self.items_open = False
        elif not self.paused and not self.paperdoll_open and not self.debug_panel_open and not self.leaderboard_open:
            self.items_open = True

    def toggle_leaderboard(self):
        """Shared by the L keypress and Stage J8's LeaderboardButton tap -
        same "only one overlay at a time" guard as toggle_paperdoll/
        toggle_items."""
        if self.leaderboard_open:
            self.leaderboard_open = False
        elif not self.paused and not self.paperdoll_open and not self.items_open and not self.debug_panel_open:
            self.leaderboard_open = True
            self.leaderboard.open()

    def _attempt_cast(self, spell_id):
        self.player.selected_spell = spell_id
        if not self.player.try_cast(spell_id):
            # A failed cast used to be completely silent - pressing the key
            # while locked/on cooldown/out of mana looked identical to the
            # key doing nothing at all. Same msg_timer/msg_text toast the
            # level-up/profession-change messages already use.
            self._cast_fail_message(spell_id)
            return
        spell = SPELLS[spell_id]
        self.audio.play("attack")
        if spell_id == "fireball":
            self._cast_fireball(spell)
        elif spell_id == "frost_nova":
            self._cast_frost_nova(spell)
        elif spell_id == "healing_light":
            self._cast_healing_light(spell)

    def _cast_fail_message(self, spell_id):
        spell = SPELLS[spell_id]
        if missing_requirements(self.player.stats, spell_id):
            text = f"{spell['name']} bloqueada: requer {requirement_text(spell_id)}"
        elif self.player.spell_cooldowns.get(spell_id, 0) > 0:
            text = f"{spell['name']} em recarga"
        elif self.player.mana < spell["mana_cost"]:
            text = f"Mana insuficiente para {spell['name']}"
        else:
            return
        self.msg_timer, self.msg_text = 1.6, text

    def _cast_fireball(self, spell):
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        direction = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[self.player.direction]
        speed = 320
        dmg = self.player.stats.magic_damage(spell["spell_base"])
        self.player_projectiles.append(
            Projectile(px, py, direction[0] * speed, direction[1] * speed, dmg, (255, 120, 20))
        )

    def _cast_frost_nova(self, spell, radius=110):
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        dmg = self.player.stats.magic_damage(spell["spell_base"])
        targets = list(self.level.enemies)
        if self.boss:
            targets.append(self.boss)
        for target in targets:
            if not getattr(target, "alive", True):
                continue
            tx = target.x + target.width / 2
            ty = target.y + target.height / 2
            if math.hypot(tx - px, ty - py) <= radius:
                target.take_damage(dmg, dtype="magic")
                if hasattr(target, "status"):
                    target.status.apply("slow")
        # Ring burst - particles placed AROUND the circumference of the real
        # hit radius (not scattered randomly from the player), so the
        # nova's actual reach flashes into view instead of reading as a
        # faint poof at the caster's own feet with nothing showing where it
        # actually hit.
        ring_count = 32
        for i in range(ring_count):
            angle = (2 * math.pi / ring_count) * i
            rx = px + math.cos(angle) * radius
            ry = py + math.sin(angle) * radius
            self.level_up_particles.append(Particle(rx, ry, (140, 220, 255)))
        for _ in range(12):
            self.level_up_particles.append(Particle(px, py, (210, 240, 255)))

    def _cast_healing_light(self, spell):
        heal_frac = spell["heal_frac"] * self.player.stats.healing_power
        self.player.hp = min(self.player.max_hp, self.player.hp + self.player.max_hp * heal_frac)
        for _ in range(16):
            self.level_up_particles.append(
                Particle(self.player.x + self.player.width/2,
                         self.player.y + self.player.height/2, (255, 240, 200))
            )

    def update(self, dt):
        self.weather.update(dt)  # ambient - keeps animating through pause/overlays

        title_key = (self.player.name, self.player.level)
        if title_key != self._last_title_key:
            self._last_title_key = title_key
            import game.save as save
            save.update_browser_title(self.player)

        if self.paperdoll_open:
            self.paperdoll.handle_tap(self.input, self.player, self.save_state)
            self.paperdoll.handle_keys(self.input, self.player, self.save_state)
            return
        if self.items_open:
            self.items.handle_tap(self.input, self.player, self.save_state)
            self.items.handle_keys(self.input, self.player, self.save_state)
            return
        if self.debug_panel_open:
            self.debug_panel.handle_tap(self.input)
            self.debug_panel.handle_keys(self.input, self)
            return
        if self.leaderboard_open:
            self.leaderboard.update()
            self.leaderboard.handle_tap(self.input)
            self.leaderboard.handle_keys(self.input)
            return
        if self.paused:
            return

        self._handle_hotbar_taps()

        self.camera.follow(self.player, dt)

        if self.msg_timer > 0:
            self.msg_timer -= dt

        if self._cursed_ground_timer is not None:
            self._cursed_ground_timer -= dt
            if self._cursed_ground_timer <= 0:
                self._cursed_ground_timer = 8.0
                self.player.status.apply("poison")

        if self._weather_debuff_effect is not None:
            self._weather_debuff_timer -= dt
            if self._weather_debuff_timer <= 0:
                weather_debuff = self.weather.defn["debuff"]
                self._weather_debuff_timer = weather_debuff[1]
                self.player.status.apply(self._weather_debuff_effect)

        # Storm lightning (Choque) - synced to the visible flash so the hit
        # reads as caused by the strike, not an invisible separate timer.
        if self.weather.consume_lightning() and random.random() < 0.40:
            self.player.status.apply("shock")

        hp_before = self.player.hp
        self.player.update(dt, self.level.walls, self.input.movement_vector())

        self._update_pickup_spawns(dt)
        self._check_pickup_pickups()

        boss_was_alive = self.boss.alive if self.boss else False

        if self.boss:
            if self.player.attacking:
                atk_rect = self.player.get_attack_rect()
                # take_damage() used to be called unconditionally here (with
                # dmg=0 on a miss) - Boss/CacodemonBoss.take_damage() always
                # sets hit_flash + spawns particles regardless of amount, so
                # every swing flashed the boss even from across the map,
                # never actually connecting. Only call it on an actual hit.
                if atk_rect.colliderect(self.boss.rect):
                    dmg, is_crit = self.player.stats.roll_physical()
                    self.boss.take_damage(dmg, dtype="physical", crit=is_crit)
                    self.camera.shake(5, 0.12)
                    self.camera.zoom_pulse(0.05, 0.15)
            self.boss.update(dt, self.player, self.level.walls)

            # Drain necromancer's summon requests into real Enemy instances,
            # capped at 3 alive from this boss at once (per the design doc -
            # the cap lives here, not on Boss, since only GameplayState
            # knows which of its summons are still alive).
            if self.boss.pending_summons:
                self.boss_summons = [e for e in self.boss_summons if e.alive]
                free_slots = max(0, 3 - len(self.boss_summons))
                for sx, sy in self.boss.pending_summons[:free_slots]:
                    summon = Enemy(sx, sy, "skeleton", ml=20 + self.difficulty["ml_bonus"],
                                    level_num=self.level_num, audio_mgr=self.audio)
                    summon.aggro_range *= self.weather.visibility_multiplier
                    self.level.enemies.append(summon)
                    self.boss_summons.append(summon)
                self.boss.pending_summons = []

            # Summoned adds need the same chase/melee/credit-kill handling
            # as any other mob - boss fights never ran Level.update() before
            # Stage D6 (self.level.enemies was always empty on boss levels
            # until now), so this is a no-op for orc_warlord/shadow_king.
            self.level.update(dt, self.player, self.audio)
        else:
            self.level.update(dt, self.player, self.audio)
            if self.level.check_exit(self.player):
                self.next_state = f"next:{self.level.data['next']}"

        # Fireball projectiles - checked against whichever targets this
        # level actually has (regular enemies, a boss, or none). Handled
        # after the melee/boss branch above so a boss (or enemy) killed by
        # Fireball is credited exactly the same as one killed by melee -
        # this used to only grant xp/gold on the melee path.
        cast_targets = list(self.level.enemies) + ([self.boss] if self.boss else [])
        for proj in self.player_projectiles:
            proj.update(dt, self.level.walls)
            if not proj.alive:
                continue
            for target in cast_targets:
                if getattr(target, "alive", True) and proj.rect.colliderect(target.rect):
                    target.take_damage(proj.damage, dtype=proj.dtype)
                    proj.alive = False
                    if not target.alive and hasattr(target, "etype"):
                        self.level.credit_kill(self.player, target)
                    break
        self.player_projectiles = [p for p in self.player_projectiles if p.alive]

        if self.boss and boss_was_alive and not self.boss.alive:
            self.player.gain_xp(self.boss.xp_reward)
            # Instant credit, not a walk-over pickup like regular enemies -
            # the level ends immediately (victory screen), so there's no
            # gameplay window to walk over a dropped coin. Particle burst
            # instead, for the visual payoff.
            self.player.gold += self.boss.gold_reward
            for _ in range(15):
                self.level_up_particles.append(
                    Particle(self.boss.x + self.boss.width/2,
                             self.boss.y + self.boss.height/2, ACCENT_GOLD)
                )
            boss_key = self.level.data.get("boss")
            self.player.boss_kills[boss_key] = self.player.boss_kills.get(boss_key, 0) + 1

            # Stage H1 fix: this used to be `if self.boss and not self.boss.alive:`
            # with no one-shot guard, re-running every single frame after the
            # boss died. That (a) permanently clobbered next_state back to
            # None on levels 4/8 (which use "next", not "victory" - only the
            # campaign-final levels 12/13 have a real "victory" value) and
            # (b) stomped any other source of next_state (e.g. the M/N dev
            # skip keys) set later in the same frame, since GameplayState's
            # own update() always runs after handle_event(). Reusing the
            # boss_was_alive guard above makes this fire exactly once, on
            # the death frame, like the xp/gold credit right above it.
            victory_result = self.level.data.get("victory")
            next_lvl = self.level.data.get("next")
            if victory_result:
                self.next_state = victory_result
            elif next_lvl is not None:
                self.next_state = f"next:{next_lvl}"

        # Screen shake feedback when the player takes damage (from boss or
        # regular enemies alike - both paths run above, so a simple hp diff
        # catches either source without touching combat logic itself).
        if self.player.hp < hp_before:
            self.camera.shake(8, 0.2)

        # Level-up fanfare - reuses the level-entry toast + the same
        # particle language as boss hits, just gold-colored. No zoom_pulse -
        # it read as screen shake and got in the way of seeing the particles.
        if self.player.pending_level_up > 0 and self.save_state is not None:
            # Persisted immediately (not just at level-exit) so a level
            # gained mid-run survives a closed tab/browser crash.
            import game.save as save
            import game.net as net
            save.sync_character(self.save_state, self.player)
            save.sync_economy(self.save_state, self.player)
            save.save(self.save_state)
            net.trigger_sync(self.save_state)
        if self.player.pending_level_up > 0:
            # Stage F2: open the stats tab immediately and lock it until the
            # new points are spent, instead of relying on the toast alone.
            self.paperdoll_open = True
            self.paperdoll.active_tab = "stats"
            self.level_up_forced = True
            self.items_open = False
            self.debug_panel_open = False
            self.leaderboard_open = False
        while self.player.pending_level_up > 0:
            self.player.pending_level_up -= 1
            self.msg_timer = 2.5
            self.msg_text = f"Nivel {self.player.level}! +{POINTS_PER_LEVEL} pontos"
            self.audio.play("victory")
            for _ in range(20):
                self.level_up_particles.append(
                    Particle(self.player.x + self.player.width/2,
                             self.player.y + self.player.height/2, ACCENT_GOLD)
                )

        self.level_up_particles = [p for p in self.level_up_particles if p.life > 0]
        for p in self.level_up_particles:
            p.update(dt)

        # Profession-change toast - profession is derived from spent points
        # (game/professions.py), so this fires whenever the paperdoll's
        # spend/respec buttons push the build across a threshold.
        if self.player.pending_profession_change:
            self.msg_timer = 2.5
            self.msg_text = f"Profissao alterada: {self.player.pending_profession_change}!"
            self.audio.play("menu_select")
            self.player.pending_profession_change = None

        # Check death
        if self.player.hp <= 0:
            self.next_state = "game_over"

    def draw(self):
        cx = int(self.camera.render_x)
        cy = int(self.camera.render_y)

        self.level.draw(self.screen, cx, cy, SW, SH)

        for pickup in self.pickups:
            pickup.draw(self.screen, cx, cy)

        if self.boss:
            self.boss.draw(self.screen, cx, cy)

        self.player.draw(self.screen, cx, cy)

        for proj in self.player_projectiles:
            proj.draw(self.screen, cx, cy)

        for p in self.level_up_particles:
            p.draw(self.screen, cx, cy)

        self.camera.apply_zoom(self.screen)

        # Weather - screen-space, drawn after the zoom post-effect so fog/
        # rain/snow don't visually warp during a zoom_pulse hit effect.
        self.weather.draw(self.screen)

        # HUD
        self.player.draw_hud(self.screen, self.save_state, touch_active=self.input.touch_active)
        self.level.draw_hud_info(self.screen)

        # Difficulty tag + active level affixes (Stage B5) - just above the
        # "Fase N: Titulo" line level.draw_hud_info() already draws.
        if self.difficulty_id != "normal":
            f_diff = font(14, bold=True)
            label = self.difficulty["name"].upper()
            if self.level.data["type"] == "combat" and self.difficulty["level_affixes"]:
                names = ", ".join(AFFIXES[a]["name"] for a in self.difficulty["level_affixes"])
                label += f" - {names}"
            diff_txt = f_diff.render(label, True, (255, 120, 120))
            self.screen.blit(diff_txt, (SW // 2 - diff_txt.get_width() // 2, SH - 50))

        if self.boss and self.boss.alive:
            self.boss.draw_hud(self.screen, SW)

        # Entry message
        if self.msg_timer > 0:
            alpha = min(255, int(self.msg_timer * 255))
            f = font(28, bold=True)
            surf = f.render(self.msg_text, True, ACCENT_GOLD)
            surf.set_alpha(alpha)
            self.screen.blit(surf, (SW//2 - surf.get_width()//2, SH//2 - 20))

        # Pause overlay
        if self.paused:
            overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
            overlay.fill((0,0,0,140))
            self.screen.blit(overlay, (0,0))
            f = font(48, bold=True)
            draw_text(self.screen, "PAUSADO", f, TITLE_PAUSE, SW//2, SH//2-40)
            f2 = font(20)
            draw_text(self.screen, "ESC / toque no botao - Continuar", f2, SUBTEXT, SW//2, SH//2+20)
            self._restart_button.draw(self.screen, f2, SUBTEXT)

        # Paperdoll overlay
        if self.paperdoll_open:
            self.paperdoll.draw(self.screen, self.player, self.save_state, forced=self.level_up_forced)

        # Itens overlay
        if self.items_open:
            self.items.draw(self.screen, self.player)

        # Debug panel overlay (Stage B5 follow-up - F1, PC only)
        if self.debug_panel_open:
            self.debug_panel.draw(self.screen, self)

        # Leaderboard overlay (Stage J8-J10)
        if self.leaderboard_open:
            self.leaderboard.draw(self.screen)

        # Stage J11: always called now, not just when touch_active - the
        # mouse-click crosshair (InputManager._draw_crosshair) needs to
        # render on desktop too, where touch_active is deliberately never
        # set. InputManager.draw() already re-checks touch_active itself
        # before drawing the virtual joystick/buttons, so this doesn't
        # change anything about when THOSE show up.
        self.input.draw(self.screen)

    def _spawn_pickup(self, kind):
        sprite = self._pickup_sprites[kind]
        attempts = 0
        while attempts < 50:
            attempts += 1
            margin = 48
            x = random.randint(margin, self.level.width - margin - sprite.get_width())
            y = random.randint(margin, self.level.height - margin - sprite.get_height())
            candidate = pygame.Rect(x, y, sprite.get_width(), sprite.get_height())
            if any(candidate.colliderect(w) for w in self.level.walls):
                continue
            if self.boss and candidate.colliderect(self.boss.rect):
                continue
            if candidate.colliderect(self.player.rect):
                continue
            self.pickups.append(Pickup(x, y, sprite, kind))
            return

    def _update_pickup_spawns(self, dt):
        if self.boss and not self.boss.alive:
            return
        if self.pickups:
            for pickup in self.pickups:
                pickup.update(dt)
            return
        self.pickup_spawn_timer -= dt
        if self.pickup_spawn_timer <= 0:
            self.pickup_spawn_timer = random.uniform(8.0, 14.0)
            # Mana is rarer than hearts (Stage F8) - a single weighted roll
            # per spawn, same "only one pickup on the ground at a time"
            # rule as before, just now covering both kinds together.
            kind = "mana" if random.random() < 0.3 else "heart"
            self._spawn_pickup(kind)

    def _check_pickup_pickups(self):
        for pickup in self.pickups[:]:
            if self.player.rect.colliderect(pickup.rect):
                if pickup.kind == "heart":
                    # Same ~1/6-of-max_hp heal as before, rescaled to the
                    # bigger hp range from game/stats.py (Stage A3).
                    heal = round(self.player.max_hp / 6)
                    self.player.hp = min(self.player.max_hp, self.player.hp + heal)
                else:
                    # Smaller fraction than mana_potion's 0.6 (game/items.py)
                    # since this one is free and drops on a timer.
                    mana = round(self.player.max_mana * 0.25)
                    self.player.mana = min(self.player.max_mana, self.player.mana + mana)
                self.pickups.remove(pickup)
                self.audio.play("pickup")


# ─── Game Over ────────────────────────────────────────────────────────────────
class GameOverState:
    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.stars = [Star() for _ in range(60)]
        self.menu_button = TextButton("[ ENTER ] - Menu Principal", SW//2, 360)
        self.restart_button = TextButton("[ R ] - Tentar Novamente", SW//2, 395)

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "menu"
        if self.input.consume_action(Action.RESTART):
            self.audio.play("menu_select")
            return "restart"
        if self.input.tapped_rect(self.menu_button.rect):
            self.audio.play("menu_select")
            return "menu"
        if self.input.tapped_rect(self.restart_button.rect):
            self.audio.play("menu_select")
            return "restart"
        return None

    def update(self, dt):
        self.t += dt
        for s in self.stars:
            s.update(dt)

    def draw(self):
        self.screen.fill(BG_GAME_OVER)
        for s in self.stars:
            s.draw(self.screen)

        f1 = font(72, bold=True)
        pulse = abs(math.sin(self.t * 2))
        r = int(180 + 75 * pulse)
        draw_text(self.screen, "FIM DE JOGO", f1, (r, 30, 30), SW//2, 160)

        f2 = font(22)
        draw_text(self.screen, "Voce foi derrotado nas trevas...", f2, (200,150,150), SW//2, 280)

        f3 = font(20, bold=True)
        self.menu_button.draw(self.screen, f3, (220,180,180))
        self.restart_button.draw(self.screen, f3, (220,180,180))


# ─── Victory ──────────────────────────────────────────────────────────────────
class VictoryState:
    def __init__(self, screen, input_mgr, audio_mgr, elapsed_seconds=0.0,
                 secret_unlocked=False, unlocked_next=None):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.particles = []
        self._spawn_timer = 0
        self.elapsed = float(elapsed_seconds)
        # Stage B5: the secret level is gated behind clearing Inferno -
        # locked, the button still shows (so it's discoverable) but does
        # nothing. unlocked_next names a difficulty tier this exact clear
        # just unlocked (first clear of this tier only, not on replays).
        self.secret_unlocked = secret_unlocked
        self.unlocked_next = unlocked_next
        # The primary action always drives straight into level 1 of whatever
        # tier is now current (next tier if one was just unlocked, same tier
        # otherwise) via GameStateManager's existing "CONTINUAR" branch/
        # _continue_level() - no extra trip through the main menu.
        self.continue_button = TextButton("[ ENTER ] - Continuar", SW//2, 420)
        secret_label = "[ ESPACO ] - Nivel Secreto" if secret_unlocked else "Nivel Secreto - vença o Inferno para desbloquear"
        self.secret_button = TextButton(secret_label, SW//2, 500, pad_y=10)

    def handle_event(self, event):
        if self.secret_unlocked:
            if self.input.consume_action(Action.SECRET):
                self.audio.play("menu_select")
                return "secret"
            if self.input.tapped_rect(self.secret_button.rect):
                self.audio.play("menu_select")
                return "secret"
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "CONTINUAR"
        if self.input.tapped_rect(self.continue_button.rect):
            self.audio.play("menu_select")
            return "CONTINUAR"
        return None

    def update(self, dt):
        self.t += dt
        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            self._spawn_timer = 0.05
            import random
            from game.enemy import Particle
            colors = [(255,215,0),(255,150,0),(200,255,100),(100,200,255),(220,100,255)]
            self.particles.append(
                Particle(random.randint(50, SW-50), random.randint(50, SH-100),
                         random.choice(colors))
            )
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

    def draw(self):
        self.screen.fill(BG_VICTORY)
        for p in self.particles:
            p.draw(self.screen, 0, 0)

        f1 = font(64, bold=True)
        glow = int(200 + 55 * math.sin(self.t * 3))
        draw_text(self.screen, "VITORIA!", f1, (255, glow, 50), SW//2, 140)

        f2 = font(24)
        draw_text(self.screen, "O Rei das Sombras foi derrotado!", f2, (220,220,180), SW//2, 235)
        draw_text(self.screen, "A paz voltou as terras do reino.", f2, (200,200,160), SW//2, 268)

        f3 = font(18, bold=True) if self.unlocked_next else font(18)
        if self.unlocked_next:
            draw_text(self.screen, f"Parabens, voce desbloqueou o modo {self.unlocked_next}!",
                      f3, ACCENT_GOLD, SW//2, 330)
        else:
            draw_text(self.screen, "Parabens, heroi!", f3, (180,255,180), SW//2, 330)

        f4 = font(20, bold=True)
        self.continue_button.draw(self.screen, f4, (200,200,220))

        # Show total play time
        mins = int(self.elapsed // 60)
        secs = int(self.elapsed % 60)
        time_str = f"Tempo: {mins:02d}:{secs:02d}"
        ftime = font(18)
        draw_text(self.screen, time_str, ftime, (180,220,180), SW//2, 460)

        # Instructions
        f_ins = font(16)
        secret_color = (180,200,180) if self.secret_unlocked else (110,100,100)
        self.secret_button.draw(self.screen, f_ins, secret_color)

        f5 = font(14)
        draw_text(self.screen, "Criado por Gustavo Sa",
                  f5, (80,80,120), SW//2, SH-24)


# ─── Secret Level (Mock) ───────────────────────────────────────────────────────
class SecretVictoryState:
    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.particles = []
        self._spawn_timer = 0
        self.menu_button = TextButton("[ ENTER ] - Menu Principal", SW//2, 340)

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "menu"
        if self.input.tapped_rect(self.menu_button.rect):
            self.audio.play("menu_select")
            return "menu"
        return None

    def update(self, dt):
        self.t += dt
        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            self._spawn_timer = 0.08
            import random
            from game.enemy import Particle
            self.particles.append(
                Particle(random.randint(80, SW-80), random.randint(120, SH-120),
                         random.choice([(255,140,0),(255,180,50),(255,80,0)]))
            )
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update(dt)

    def draw(self):
        self.screen.fill((25, 10, 5))

        # Lava glow background
        pulse = int(80 + 40 * math.sin(self.t * 2.5))
        glow = pygame.Surface((SW, SH), pygame.SRCALPHA)
        glow.fill((pulse, 40, 0, 30))
        self.screen.blit(glow, (0, 0))

        for p in self.particles:
            p.draw(self.screen, 0, 0)

        f1 = font(54, bold=True)
        draw_text(self.screen, "PARABENS!", f1, (255, 190, 80), SW//2, 120)

        f2 = font(26)
        draw_text(self.screen, "Parabens por vencer o desafio secreto do game!", f2, (235, 180, 120), SW//2, 200)
        draw_text(self.screen, "Você platinou o game!", f2, (235, 180, 120), SW//2, 240)

        f3 = font(20, bold=True)
        self.menu_button.draw(self.screen, f3, (255, 220, 180))

        # Infernal floor pulse
        for i in range(6):
            y = 420 + i * 18 + 6 * math.sin(self.t * 2 + i * 0.7)
            color = (170, 70, 25) if i % 2 == 0 else (210, 110, 40)
            pygame.draw.line(self.screen, color, (120, y), (680, y), 3)


# ─── State Manager ────────────────────────────────────────────────────────────
class GameStateManager:
    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        # Right side, next to the (mobile-only) pause button at SW-40 - keeps
        # the top-left free for the HP/mana/XP dock.
        self.sound_button = SoundButton(SW - 148, 40)
        self.fullscreen_button = FullscreenButton(SW - 94, 40)
        self._fullscreen_fallback = False  # só usado se pygame.display.is_fullscreen() não existir

        # Stage G5: stacked below the sound/fullscreen row, same right
        # edge (SW-40) as the mobile-only virtual pause button (which sits
        # higher, at y=40) - only meaningful (and only drawn) during
        # GameplayState, since paperdoll_open/items_open live there.
        self.paperdoll_button = PaperdollButton(SW - 40, 100)
        self.items_button = ItemsButton(SW - 40, 154)
        self.leaderboard_button = LeaderboardButton(SW - 40, 208)

        import game.save as save
        self.save_state = save.load() or save.new_game_state()
        self.audio.muted = self.save_state["settings"]["muted"]

        # Stage I4: fire-and-forget, no JWT needed (/balance is public) -
        # patches ITEMS/DIFFICULTIES/SPELLS/game.stats in place whenever it
        # resolves, if ever; the code's own defaults already make the game
        # fully playable before/without this.
        import game.net as net
        net.trigger_balance_fetch()

        self.state = MenuState(screen, input_mgr, audio_mgr, has_save=self._has_progress())
        self.player = None
        self.play_time = 0.0
        # Stage H7 - tracks whether the title theme is the thing currently
        # looping, so update() can start/stop it exactly on the transition
        # edge (MenuState<->anything else) instead of needing every single
        # _transition() branch that leaves/enters the menu to remember to
        # call play_music/stop_music itself.
        self._menu_music_playing = False
        # Set right before a "victory" transition if that clear was the
        # *first* clear of the active tier (Stage B5) - lets VictoryState
        # show "dificuldade desbloqueada" only once, not on every replay.
        self._just_cleared_difficulty = None

    def _persist(self):
        import game.save as save
        save.save(self.save_state)

    def _player_from_save(self):
        import game.save as save
        return save.character_from_state(self.save_state, 0, 0, self.audio)

    def _continue_level(self):
        diff_id = self.save_state["progression"]["current_difficulty"]
        highest = self.save_state["progression"]["highest_level_cleared"].get(diff_id, 0)
        if highest >= 12:
            # This tier's final boss is already cleared - move on to the
            # next difficulty (already unlocked, since clearing tier N is
            # exactly what unlocks tier N+1) instead of re-fighting the
            # same final boss forever.
            nd = next_difficulty(diff_id)
            if nd:
                self.save_state["progression"]["current_difficulty"] = nd
                return 1
            return 12  # Inferno has no next tier - keep replaying its final boss
        return min(highest + 1, 12)

    def _is_fullscreen(self):
        # Stage G6: on the web build, the real source of truth is the
        # browser's own Fullscreen API, not pygame's SDL2-emscripten state
        # (which is what didn't reflect reality in the first place - see
        # [[project_fullscreen_bug]]).
        if sys.platform == "emscripten":
            import js
            return bool(js.document.fullscreenElement)
        if hasattr(pygame.display, "is_fullscreen"):
            return pygame.display.is_fullscreen()
        return self._fullscreen_fallback

    def _toggle_fullscreen(self):
        # Stage G6: pygame.display.toggle_fullscreen() is confirmed broken
        # in the pygbag/WASM build ([[project_fullscreen_bug]]) - tries the
        # browser's native Fullscreen API there instead, via the same
        # sys.platform=="emscripten" + `js` bridge game/save.py already uses
        # for localStorage/document.title. A keypress (F11) is as direct a
        # user gesture as a click, which the API requires. Desktop keeps
        # the original pygame call unchanged.
        if sys.platform == "emscripten":
            import js
            if js.document.fullscreenElement:
                js.document.exitFullscreen()
            else:
                js.document.documentElement.requestFullscreen()
            return
        try:
            pygame.display.toggle_fullscreen()
            self._fullscreen_fallback = not self._fullscreen_fallback
        except pygame.error:
            pass

    def _ensure_fullscreen(self):
        """Stage J1: entering a run (Novo Jogo/Continuar/difficulty pick)
        auto-enters fullscreen, as if the resize button had been clicked.
        Guarded because _toggle_fullscreen() is bidirectional - starting a
        second run while already fullscreen must not kick the player OUT of
        it. Safe to call from _transition(): it runs synchronously inside
        the keydown/click event that produced the menu choice, so the
        browser still counts it as a user gesture (which requestFullscreen
        requires)."""
        if not self._is_fullscreen():
            self._toggle_fullscreen()

    def handle_event(self, event):
        result = self.state.handle_event(event)
        if result:
            self._transition(result)

    def update(self, dt):
        # Stage H7: title theme plays exactly while MenuState is current,
        # nothing else needs to know about it.
        on_menu = isinstance(self.state, MenuState)
        if on_menu and not self._menu_music_playing:
            self.audio.play_music("title_theme")
            self._menu_music_playing = True
        elif not on_menu and self._menu_music_playing:
            self.audio.stop_music()
            self._menu_music_playing = False

        if self.input.tapped_rect(self.sound_button.rect) or self.input.consume_action(Action.MUTE):
            self.audio.toggle_mute()
            self.audio.play("menu_select")
            self.save_state["settings"]["muted"] = self.audio.muted
            self._persist()

        if self.input.tapped_rect(self.fullscreen_button.rect) or self.input.consume_action(Action.FULLSCREEN):
            self._toggle_fullscreen()
            self.audio.play("menu_select")

        # Stage G5: only meaningful during actual gameplay - paperdoll_open/
        # items_open live on GameplayState, so these buttons are a no-op
        # (and hidden, see draw()) on every other screen.
        if isinstance(self.state, GameplayState):
            if self.input.tapped_rect(self.paperdoll_button.rect):
                self.state.toggle_paperdoll()
                self.audio.play("menu_select")
            if self.input.tapped_rect(self.items_button.rect):
                self.state.toggle_items()
                self.audio.play("menu_select")
            if self.input.tapped_rect(self.leaderboard_button.rect):
                self.state.toggle_leaderboard()
                self.audio.play("menu_select")

        self.state.update(dt)

        # Track play time while in gameplay
        if isinstance(self.state, GameplayState):
            self.play_time += dt
            self.save_state["counters"]["playtime_s"] += dt
            ns = self.state.next_state
            if ns:
                self.player = self.state.player
                import game.save as save
                if ns == "game_over":
                    self.save_state["counters"]["deaths"] = self.save_state["counters"].get("deaths", 0) + 1
                    self._just_cleared_difficulty = None
                    # Death sends the dungeon back to the start of the
                    # current tier - "Continuar" never resumes where the
                    # player died. The character itself (xp/level/
                    # attributes/gold/inventory, synced below) is never
                    # lost; only this tier's level checkpoint resets.
                    # cleared_difficulties (which tiers are unlocked) is
                    # untouched.
                    self.save_state["progression"]["highest_level_cleared"][self.state.difficulty_id] = 0
                else:
                    prog = self.save_state["progression"]
                    diff_id = self.state.difficulty_id
                    prog["highest_level_cleared"][diff_id] = max(
                        prog["highest_level_cleared"].get(diff_id, 0), self.state.level_num
                    )
                    if ns == "victory" and diff_id not in prog["cleared_difficulties"]:
                        prog["cleared_difficulties"].append(diff_id)
                        self._just_cleared_difficulty = diff_id
                    else:
                        self._just_cleared_difficulty = None
                save.sync_character(self.save_state, self.player)
                save.sync_counters(self.save_state, self.player)
                save.sync_economy(self.save_state, self.player)
                self._persist()
                import game.net as net
                net.trigger_sync(self.save_state)
                self._transition(ns)

        if isinstance(self.state, TransitionState):
            if self.state.done:
                lvl = self.state.next_level
                self.state = GameplayState(self.screen, self.input, self.audio, lvl, self.player,
                                            save_state=self.save_state)

    def draw(self):
        self.state.draw()
        self.sound_button.draw(self.screen, self.audio.muted)
        self.fullscreen_button.draw(self.screen, self._is_fullscreen())
        if isinstance(self.state, GameplayState):
            self.paperdoll_button.draw(self.screen)
            self.items_button.draw(self.screen)
            self.leaderboard_button.draw(self.screen)

    def _has_progress(self):
        # A death now zeroes the active tier's highest_level_cleared (see
        # the "game_over" branch above), so a character who dies before
        # clearing level 1 anywhere would otherwise make this false and
        # silently orphan their name/gold/attributes behind "Novo Jogo".
        # A non-empty name means a character exists, dungeon progress or not.
        highest = self.save_state["progression"]["highest_level_cleared"]
        return (any(v > 0 for v in highest.values())
                or self.save_state["character"]["level"] > 1
                or bool(self.save_state["character"]["name"]))

    def _transition(self, result):
        if result == "NOVO JOGO":
            self._ensure_fullscreen()
            self.state = NameEntryState(self.screen, self.input, self.audio)
        elif result == "name_confirmed":
            import game.save as save
            fresh = save.new_game_state()
            fresh["settings"]["muted"] = self.save_state["settings"]["muted"]
            fresh["character"]["name"] = (self.state.name.strip() or "Heroi")[:NameEntryState.MAX_LEN]
            self.save_state = fresh
            self.player = save.character_from_state(self.save_state, 0, 0, self.audio)
            self.state = TransitionState(self.screen, 1, self.player)
            self.play_time = 0.0
        elif result == "SAIR":
            import sys, pygame
            pygame.quit(); sys.exit()
        elif result == "menu":
            self.player = None
            self.state = MenuState(self.screen, self.input, self.audio, has_save=self._has_progress())
        elif result == "RESETAR CHAR":
            self.state = ConfirmResetState(self.screen, self.input, self.audio)
        elif result == "reset_confirmed":
            import game.save as save
            fresh = save.new_game_state()
            fresh["settings"]["muted"] = self.save_state["settings"]["muted"]
            self.save_state = fresh
            self._persist()  # wipe must survive an immediate quit
            # A deliberate reset needs to reach the cloud copy too, or the
            # next login on this account would silently resurrect the old
            # character via the very merge logic that's supposed to protect
            # progress from being lost.
            import game.net as net
            net.trigger_sync(self.save_state)
            self.player = None
            # has_progress() is now False -> menu shows "Novo Jogo" again,
            # same character-creation entry point as any other fresh save;
            # reset doesn't re-prompt for a name or start a run itself.
            self.state = MenuState(self.screen, self.input, self.audio, has_save=self._has_progress())
        elif result == "DIFICULDADE":
            self.state = DifficultySelectState(
                self.screen, self.input, self.audio,
                self.save_state["progression"]["cleared_difficulties"],
            )
        elif result and result.startswith("difficulty:"):
            self._ensure_fullscreen()
            diff_id = result.split(":", 1)[1]
            self.save_state["progression"]["current_difficulty"] = diff_id
            self.player = self._player_from_save()
            highest = self.save_state["progression"]["highest_level_cleared"].get(diff_id, 0)
            start_level = min(highest + 1, 12)
            self._persist()
            self.state = TransitionState(self.screen, start_level, self.player)
            self.play_time = 0.0
        elif result in ("CONTINUAR", "restart"):
            # Both resume the persisted character at its furthest cleared
            # level (within the currently active difficulty tier). The
            # character (xp/level/attributes/gold/inventory) is never lost -
            # only a death (see update()'s "game_over" branch) zeroes this
            # tier's furthest-cleared checkpoint, sending the dungeon itself
            # back to level 1 without touching the character underneath it.
            self._ensure_fullscreen()
            self.player = self._player_from_save()
            self.state = TransitionState(self.screen, self._continue_level(), self.player)
            self.play_time = 0.0
        elif result == "game_over":
            self.audio.play("game_over")
            self.state = GameOverState(self.screen, self.input, self.audio)
        elif result == "victory":
            self.audio.play("victory")
            prog = self.save_state["progression"]
            secret_unlocked = "inferno" in prog["cleared_difficulties"]
            unlocked_next = None
            if self._just_cleared_difficulty:
                nd = next_difficulty(self._just_cleared_difficulty)
                if nd:
                    unlocked_next = DIFFICULTIES[nd]["name"]
            self.state = VictoryState(self.screen, self.input, self.audio, elapsed_seconds=self.play_time,
                                       secret_unlocked=secret_unlocked, unlocked_next=unlocked_next)
        elif result == "secret":
            # Carries the real character over (not a fresh L1 player) -
            # otherwise leaving this level would sync a throwaway level-1
            # character back over the real save (see save_state sync in update()).
            self.player = self._player_from_save()
            self.state = TransitionState(self.screen, 13, self.player)
            self.play_time = 0.0
        elif result == "secret_victory":
            self.audio.play("victory")
            self.state = SecretVictoryState(self.screen, self.input, self.audio)
        elif result and result.startswith("next:"):
            next_lvl = int(result.split(":")[1])
            if isinstance(self.state, GameplayState):
                # Stage F9: a real level exit shows the stage-complete
                # summary first; its own "Continuar" re-enters this same
                # branch with self.state now being that StageCompleteState,
                # which falls through to the plain TransitionState below -
                # same one-screen-per-transition path dev level-skips
                # (M/N keys) also go through, unmodified.
                finished = self.state
                xp_gained = self.player.xp_earned_total - finished._xp_at_level_start
                gold_gained = self.player.gold - finished._gold_at_level_start
                self.state = StageCompleteState(self.screen, self.input, self.audio,
                                                 finished.level_num, next_lvl,
                                                 xp_gained, gold_gained, self.player)
            else:
                self.state = TransitionState(self.screen, next_lvl, self.player)
