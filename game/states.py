import pygame
import sys
import math
import time
import random
from game.player import Player, hotbar_slots, DASH_DEX_REQ
from game.items import use_item
from game.level import Level, LEVEL_MAPS, TILE
from game.boss import Boss, CacodemonBoss, Projectile
from game.enemy import Particle, Enemy
from game.camera import Camera
from game.paperdoll import Paperdoll
from game.merchant import ItemsOverlay
from game.debug_panel import DebugPanel
from game.leaderboard import LeaderboardOverlay
from game.settings_overlay import SettingsOverlay
from game.coop_overlay import CoopOverlay
from game.remote_player import RemotePlayer
from game.chat_widget import ChatWidget
import game.net_coop as net_coop
from game.weather import WeatherSystem
from game.assets import (
    create_heart_sprite, create_mana_orb_sprite, create_logo_sprite,
    create_player_sprite,
)
from game.input_system import (
    Action, FullscreenButton, PaperdollButton, ItemsButton, LeaderboardButton, SettingsButton,
    CoopButton,
)
from game.audio import SoundButton
from game.stats import POINTS_PER_LEVEL, MAX_LEVEL, difficulty_tier_index
from game.spells import SPELLS
from game.class_kits import basic_attack_for
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
    # Stage Q2: Atos 4-6 + boss secreto - todos reusam a mesma Boss class
    # (so cacodemon tem chassi bespoke), so precisam de 1 linha cada aqui.
    "ursa_ancestral": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="ursa_ancestral", enrage_frac=ef, audio_mgr=am), 48, 80),
    "imperatriz_aranha": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="imperatriz_aranha", enrage_frac=ef, audio_mgr=am), 48, 80),
    "barao_sanguinario": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="barao_sanguinario", enrage_frac=ef, audio_mgr=am), 48, 80),
    "colosso_runico": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="colosso_runico", enrage_frac=ef, audio_mgr=am), 48, 80),
    "arquibruxa": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="arquibruxa", enrage_frac=ef, audio_mgr=am), 48, 80),
    "senhor_da_alcateia": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="senhor_da_alcateia", enrage_frac=ef, audio_mgr=am), 48, 80),
    "dragao_primordial": (lambda x, y, ef=0.5, am=None: Boss(x, y, boss_id="dragao_primordial", enrage_frac=ef, audio_mgr=am), 48, 80),
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
        # Extended-session freeze fix (same class of bug as font()'s cache
        # in this file's imports, audio.SoundButton, etc.) - size/alpha
        # are fixed until the next reset(), so render the dot once here
        # instead of allocating a new Surface every single draw() call for
        # as long as the menu (with ~60 of these) stays open.
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, self.alpha), (self.size, self.size), self.size)
        self._surf = s

    def update(self, dt):
        self.y += self.speed * dt
        if self.y > SH:
            self.reset()
            self.y = 0

    def draw(self, surface):
        surface.blit(self._surf, (int(self.x), int(self.y)))


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
        self._title_glow = None  # extended-session freeze fix, see draw()
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

        # Title glow - extended-session freeze fix (same class of bug as
        # font()'s own cache): this surface's content never actually
        # varies frame to frame (the ellipse rect below is fixed, doesn't
        # read self.t), so a fresh Surface here every frame the menu sits
        # open was pure waste. Built once, lazily, reused forever.
        if self._title_glow is None:
            glow_surf = pygame.Surface((500, 120), pygame.SRCALPHA)
            pygame.draw.ellipse(glow_surf, (80, 0, 120, 60), (0, 0, 500, 120))
            self._title_glow = glow_surf
        self.screen.blit(self._title_glow, (150, 80))

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
    selected - unlocking is sequential, cleared by reaching level 25's
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
                 xp_gained, gold_gained, player, coop=None, remote_players=None,
                 kills_gained=0, key_finder_id=None):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.level_num = level_num
        self.next_level = next_level
        self.xp_gained = xp_gained
        self.gold_gained = gold_gained
        self.player = player
        # Stage L6: só repassado adiante pro TransitionState quando "Continuar"
        # for confirmado (ver _transition's "next:" branch) - mesma razão
        # de TransitionState carregar isso agora, ver o comentário lá.
        self.coop = coop
        self.remote_players = remote_players
        self.continue_button = TextButton("[ ENTER ] - Continuar", SW // 2, SH - 90)
        self._xp_bar = ProgressBar(320, 14, (40, 40, 40), (140, 140, 140), border_width=2)
        # Stage K23: was create_victory_hero_sprite() - a generic green-
        # tunic hero raising a sword, same regardless of who's actually
        # playing. Replaced with the player's real Paperdoll look (same
        # create_player_sprite(..., profession) call game/paperdoll.py's
        # _portrait_for() uses for the character panel) so this screen
        # shows the hero the player actually built, not a placeholder.
        self._hero_portrait = pygame.transform.scale(
            create_player_sprite("down", False, self.player.profession), (120, 120))

        # Bugfix round (2a leva): coop score screen - kills_gained/
        # key_finder_id are already local (computed by GameStateManager
        # before constructing this), but a REMOTE player's kills/gold/xp
        # for THIS level only exist on their own machine - each side
        # self-reports once here (same "each client authoritative for its
        # own Player" shape as pos/chat/credit_xp), and remote_stats fills
        # in as those "level_complete_stats" messages arrive. GameplayState
        # is the only place net_coop.poll_messages() got drained before -
        # this screen has to do its own polling now (see update()) or a
        # message sent while it's on screen would just queue unread until
        # the NEXT GameplayState.update() (too late to show it here).
        self.kills_gained = kills_gained
        self.key_finder_id = key_finder_id
        self.remote_stats = {}
        if self.coop and net_coop.is_connected():
            net_coop.send({
                "type": "level_complete_stats", "player_id": net_coop.get_player_id(),
                "kills": kills_gained, "gold": gold_gained, "xp": xp_gained,
                "level": player.level, "xp_frac": player.xp_frac,
            })

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return f"next:{self.next_level}"
        if self.input.tapped_rect(self.continue_button.rect):
            self.audio.play("menu_select")
            return f"next:{self.next_level}"
        return None

    def update(self, dt):
        if self.coop and net_coop.is_connected():
            for msg in net_coop.poll_messages():
                if msg.get("type") == "level_complete_stats":
                    self.remote_stats[msg.get("player_id")] = msg

    def draw(self):
        self.screen.fill((10, 12, 22))

        f1 = font(40, bold=True)
        draw_text(self.screen, f"Fase {self.level_num} concluida!", f1, ACCENT_GOLD, SW // 2, 110)

        if self.coop and self.remote_players:
            self._draw_coop_scoreboard()
        else:
            self._draw_solo_summary()

        f4 = font(18, bold=True)
        self.continue_button.draw(self.screen, f4, (220, 220, 235))

    def _draw_solo_summary(self):
        f2 = font(20)
        draw_text(self.screen, f"+{self.xp_gained} XP", f2, (200, 220, 255), SW // 2, 200)
        draw_text(self.screen, f"+{self.gold_gained} ouro", f2, (230, 200, 80), SW // 2, 232)

        bar_x = SW // 2 - self._xp_bar.w // 2
        self._xp_bar.draw(self.screen, bar_x, 280, self.player.xp_frac, ACCENT_GOLD)
        f3 = font(15)
        lvl_label = "Nivel maximo!" if self.player.level >= MAX_LEVEL else f"Nivel {self.player.level}"
        draw_text(self.screen, lvl_label, f3, SUBTEXT, SW // 2, 302)

        portrait_x = SW // 2 - self._hero_portrait.get_width() // 2
        self.screen.blit(self._hero_portrait, (portrait_x, 330))

    def _draw_coop_scoreboard(self):
        """Bugfix round (2a leva): uma coluna por jogador (local + cada
        RemotePlayer), portrait/nome/kills/ouro/XP individual, e um
        destaque pra quem achou a chave - pedido explicito do usuário
        depois de notar que a tela de vitoria coop era identica a solo."""
        columns = [{
            "name": self.player.name, "profession": self.player.profession,
            "kills": self.kills_gained, "gold": self.gold_gained, "xp": self.xp_gained,
            "level": self.player.level, "xp_frac": self.player.xp_frac,
            "is_key_finder": self.key_finder_id is not None and self.key_finder_id == net_coop.get_player_id(),
        }]
        for rp in self.remote_players.values():
            stat = self.remote_stats.get(rp.player_id)
            columns.append({
                "name": rp.name, "profession": rp.profession,
                "kills": stat.get("kills") if stat else None,
                "gold": stat.get("gold") if stat else None,
                "xp": stat.get("xp") if stat else None,
                "level": stat.get("level") if stat else None,
                "xp_frac": stat.get("xp_frac", 0.0) if stat else 0.0,
                "is_key_finder": self.key_finder_id is not None and self.key_finder_id == rp.player_id,
            })

        n = len(columns)
        col_w = min(220, (SW - 40) // n)
        total_w = col_w * n
        start_x = (SW - total_w) // 2
        f_name = font(18, bold=True)
        f_stat = font(15)
        f_badge = font(13, bold=True)
        col_bar = ProgressBar(min(160, col_w - 30), 10, (40, 40, 40), (140, 140, 140), border_width=1)

        for i, col in enumerate(columns):
            cx = start_x + i * col_w + col_w // 2
            portrait = pygame.transform.scale(
                create_player_sprite("down", False, col["profession"]), (72, 72))
            self.screen.blit(portrait, (cx - 36, 175))

            draw_text(self.screen, col["name"], f_name, (220, 220, 235), cx, 260)
            if col["is_key_finder"]:
                draw_text(self.screen, f"CHAVE ENCONTRADA (+{self._key_bonus_label()} XP)",
                          f_badge, ACCENT_GOLD, cx, 280)

            def _fmt(v, suffix=""):
                return f"+{v}{suffix}" if v is not None else "..."

            draw_text(self.screen, f"Kills: {_fmt(col['kills'])}", f_stat, (220, 160, 160), cx, 305)
            draw_text(self.screen, f"Ouro: {_fmt(col['gold'])}", f_stat, (230, 200, 80), cx, 326)
            draw_text(self.screen, f"XP: {_fmt(col['xp'])}", f_stat, (200, 220, 255), cx, 347)

            bar_x = cx - col_bar.w // 2
            col_bar.draw(self.screen, bar_x, 368, col["xp_frac"] or 0.0, ACCENT_GOLD)
            lvl_txt = f"Nivel {col['level']}" if col["level"] is not None else "..."
            draw_text(self.screen, lvl_txt, font(12), SUBTEXT, cx, 388)

    def _key_bonus_label(self):
        import game.stats as stats
        return stats.KEY_FINDER_XP_BONUS


# ─── Transition ───────────────────────────────────────────────────────────────
class TransitionState:
    def __init__(self, screen, next_level, player, coop=None, remote_players=None):
        self.screen = screen
        self.next_level = next_level
        self.player = player
        # Stage L6 (docs/coop-implementation-plan.md): uma sessão coop
        # ativa precisa sobreviver a uma troca de fase - sem repassar isso,
        # a próxima GameplayState nasceria com um CoopOverlay novo em
        # folha (mode="menu", sem roster/host_player_id), mesmo com
        # net_coop ainda conectado por baixo (é module-level, não morre
        # sozinho) - o sintoma real foi "host cai não derruba mais o
        # guest depois de QUALQUER transição de fase", achado testando
        # coop_sync com tools/coop_harness.py. None (o padrão) mantém o
        # comportamento de sempre pra toda transição sem coop.
        self.coop = coop
        self.remote_players = remote_players
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
    def __init__(self, screen, input_mgr, audio_mgr, level_num=1, player=None, save_state=None,
                 coop=None, remote_players=None):
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

        # Stage L6 (docs/coop-implementation-plan.md): decidido uma vez na
        # entrada da fase, não sondado dinamicamente depois - entrar numa
        # room coop NO MEIO de uma fase já em andamento só passa a valer
        # na PRÓXIMA fase (ver docs/coop-implementation-plan.md's nota
        # sobre esse limite de v1). O host nunca é follower (só guests).
        self.net_follower = net_coop.is_connected() and not net_coop.is_host()
        # Estagio O: qual tier de cada familia (game/stats.py's
        # MONSTER_FAMILIES) spawna nesta fase - derivado da MESMA
        # dificuldade que ja determina ml_bonus/champion_chance acima, nao
        # um dial novo. Determinístico e já sincronizado em coop (host/
        # guest concordam em self.difficulty via level_sync/coop_sync),
        # então não introduz nenhum risco de divergência novo.
        tier_index = difficulty_tier_index(self.difficulty["order"])
        self.level = Level(level_num, extra_speed_mult=hastened_mult, ml_bonus=self.difficulty["ml_bonus"],
                           audio_mgr=audio_mgr, network_follower=self.net_follower, tier_index=tier_index)
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
        # Stage K12: touch item-buttons are built before any Player exists
        # (InputManager construction) - repoint their icons at whichever 3
        # items this player actually has selected.
        self.input.refresh_item_icons(self.player)
        # Estagio M1: mesma razao - o arco de magias moveis foi construido
        # com o DEFAULT_KIT antes de qualquer Player existir. Estagio
        # M-correcao: repoe pra self.player.hotbar_spells (selecao manual
        # do jogador), nao mais derivado da profissao.
        self.input.refresh_spell_buttons(self.player.hotbar_spells)

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
            self.boss.network_follower = self.net_follower
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
        self.settings = SettingsOverlay()
        self.settings_open = False
        # Stage L6: reusa a MESMA CoopOverlay/remote_players de uma
        # GameplayState anterior quando fornecida (toda troca de fase, via
        # TransitionState/StageCompleteState) - uma sessão coop ativa é
        # module-level em net_coop, não morre numa troca de fase, então o
        # UI/roster que a acompanha (mode, host_player_id, os avatares dos
        # outros jogadores) também não pode. Só um single-player comum
        # (coop=None, o padrão) nasce com um painel novo em folha.
        self.coop = coop if coop is not None else CoopOverlay()
        self.coop_open = False
        # Stage L6 (docs/coop-implementation-plan.md): outros jogadores na
        # mesma room, keyed por player_id - RemotePlayer (Stage L3) só
        # desenha/interpola o que chega via mensagens "pos", nunca simula.
        self.remote_players = remote_players if remote_players is not None else {}
        self._coop_pos_send_timer = 0.0
        self._coop_level_sync_timer = 0.0
        # Stage L13/L14 (docs/coop-implementation-plan.md): ao contrário de
        # coop/remote_players acima, NÃO é repassado através de transições
        # de fase - um rascunho de mensagem não confirmado é efêmero e de
        # baixo risco de perder (diferente da conexão coop em si), não vale
        # a complexidade extra de enfiar isso em TransitionState/
        # StageCompleteState também.
        self.chat = ChatWidget()

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
        # Bugfix round (2a leva): same delta-snapshot shape, for the coop
        # victory screen's per-player kill count (StageCompleteState).
        self._kills_at_level_start = sum(self.player.kills.values())

    def handle_event(self, event):
        if self.chat.active:
            # Stage L13: mesma exclusividade do campo de código de room
            # (L4) acima - digitar "M" numa mensagem de chat não pode
            # disparar DEV_NEXT_LEVEL. handle_event() só retorna uma
            # mensagem não-vazia ao confirmar com Enter.
            msg = self.chat.handle_event(event)
            if msg:
                # Stage L14: eu mesmo não recebo minha própria mensagem de
                # volta (o backend exclui o remetente do broadcast, ver
                # backend/app/main.py's _coop_broadcast(..., exclude=
                # player_id)) - preciso mostrar meu próprio balão local na
                # hora, sem esperar a rede.
                self.player.say(msg)
                if net_coop.is_connected():
                    net_coop.send({"type": "chat", "text": msg})
            return
        if self.coop_open and self.coop.mode == "join_code":
            # Stage L4: a free-text field takes exclusive keyboard focus
            # while capturing, same as any real text input - discovered
            # live building tools/coop_harness.py (Stage L1.5): the room
            # code alphabet includes M/N, and DEV_NEXT_LEVEL/PREV_LEVEL
            # below are letter-bound and deliberately fire "even with an
            # overlay open" - typing a code containing one used to jump
            # the local player a level forward/back mid-keystroke. Return
            # here, before any Action (dev shortcuts included) gets a
            # chance to consume the same keydown. ESC is the one exception
            # - still backs out to the overlay's menu mode, matching the
            # "ESC - Voltar" hint CoopOverlay.draw() shows in this mode.
            if self.input.consume_action(Action.PAUSE):
                self.coop.mode = "menu"
                return
            self.coop.handle_event(event, self.player)
            return

        # Dev/test shortcuts (Stage B4 follow-up): jump forward/back one
        # level directly, bypassing bosses/exits - lets every one of the 13
        # layouts be reached and re-checked without playing the whole
        # campaign each time. Always active, even mid-boss-fight or with an
        # overlay open (outside of coop's text-entry mode above) - it's a
        # debug tool, not a gameplay control.
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
            if (not self.paused and not self.paperdoll_open and not self.items_open
                    and not self.leaderboard_open and not self.settings_open and not self.coop_open):
                self.debug_panel_open = not self.debug_panel_open
                if not self.debug_panel_open and self.debug_panel.consume_difficulty_dirty():
                    self._dev_jump(0)
        if self.coop_open:
            # Modos que não capturam texto (menu/busy/connected/error) -
            # ainda passam pelo handle_event pra nada em especial hoje, mas
            # mantém o overlay recebendo eventos crus se algum modo futuro
            # precisar (ex: colar um código).
            self.coop.handle_event(event, self.player)
        if (self.paperdoll_open or self.items_open or self.debug_panel_open
                or self.leaderboard_open or self.settings_open or self.coop_open):
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
                elif self.settings_open:
                    self.toggle_settings()
                elif self.coop_open:
                    self.toggle_coop()
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
        elif (event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN
                and net_coop.is_connected()):
            # Stage L13/L14: Enter abre o campo de chat - mesma convenção
            # de tecla-crua-não-remapeável que Enter/Backspace/Esc já têm
            # em todo campo de texto do jogo (NameEntryState, o código de
            # room do CoopOverlay), não uma Action nova no keybind system.
            # Só faz sentido com uma room coop ativa (não há pra quem
            # mandar mensagem sozinho).
            self.chat.open()
        elif self.input.consume_action(Action.DASH):
            self._attempt_dash()
        elif self.input.consume_action(Action.PICKAXE):
            self._attempt_pickaxe()
        elif self.input.consume_action(Action.CAST_SELECTED):
            self._attempt_cast(self.player.selected_spell)
        elif self.input.consume_action(Action.USE_1):
            self._use_hotbar_item(0)
        elif self.input.consume_action(Action.USE_2):
            self._use_hotbar_item(1)
        elif self.input.consume_action(Action.USE_3):
            self._use_hotbar_item(2)

    def _use_hotbar_item(self, slot):
        # Stage K12: keys 1/2/3 use whichever item is in that hotbar slot
        # (player.hotbar_items), not a fixed ITEMS-dict-order index anymore -
        # ITEMS grew to ~25 entries, so "the first 3" stopped meaning
        # "whatever's shown in the hotbar" the moment selection became
        # player-editable.
        if slot < len(self.player.hotbar_items):
            use_item(self.player, self.player.hotbar_items[slot])

    def _handle_hotbar_taps(self):
        for kind, key, rect in hotbar_slots(self.player):
            # Neither slot kind is drawn on touch (see Player._draw_hotbar) -
            # the spell_buttons/item_buttons rows handle that input instead,
            # so skip the now-invisible tap targets to match.
            if self.input.touch_active:
                continue
            if not self.input.tapped_rect(rect):
                continue
            if kind == "spell":
                self._attempt_cast(key)
            elif kind == "item":
                use_item(self.player, key)
            elif kind == "attack":
                self.player.try_attack()
            elif kind == "dash":
                self._attempt_dash()
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
        elif (not self.paused and not self.items_open and not self.debug_panel_open
                and not self.leaderboard_open and not self.settings_open and not self.coop_open):
            self.paperdoll_open = True

    def toggle_items(self):
        """Shared by the I keypress and Stage G5's ItemsButton tap."""
        if self.items_open:
            self.items_open = False
        elif (not self.paused and not self.paperdoll_open and not self.debug_panel_open
                and not self.leaderboard_open and not self.settings_open and not self.coop_open):
            self.items_open = True

    def toggle_leaderboard(self):
        """Shared by the L keypress and Stage J8's LeaderboardButton tap -
        same "only one overlay at a time" guard as toggle_paperdoll/
        toggle_items."""
        if self.leaderboard_open:
            self.leaderboard_open = False
        elif (not self.paused and not self.paperdoll_open and not self.items_open
                and not self.debug_panel_open and not self.settings_open and not self.coop_open):
            self.leaderboard_open = True
            self.leaderboard.open()

    def toggle_settings(self):
        """Stage K15 - click/tap-only (no dedicated key, per the plan's
        "novo botao" framing), same "only one overlay at a time" guard as
        the others."""
        if self.settings_open:
            self.settings_open = False
        elif (not self.paused and not self.paperdoll_open and not self.items_open
                and not self.debug_panel_open and not self.leaderboard_open and not self.coop_open):
            self.settings_open = True

    def toggle_coop(self):
        """Stage L4 (docs/coop-implementation-plan.md) - click/tap-only,
        same guard as toggle_settings. Unlike the others, closing this one
        does NOT tear down an active connection - net_coop's session lives
        at module level, independent of whether this panel is showing, the
        same way closing Settings doesn't reset keybinds. Only the
        overlay's own "Sair da room" button calls net_coop.disconnect()."""
        if self.coop_open:
            self.coop_open = False
        elif (not self.paused and not self.paperdoll_open and not self.items_open
                and not self.debug_panel_open and not self.leaderboard_open and not self.settings_open):
            self.coop_open = True

    def _apply_remote_pos(self, msg):
        """Stage L6: mensagem "pos" de outro jogador na room - cria o
        RemotePlayer na primeira vez que esse player_id aparece (o nome
        vem do roster que o CoopOverlay já rastreia, não da própria
        mensagem "pos" - ela só carrega o que muda todo frame)."""
        pid = msg.get("player_id")
        if pid is None:
            return
        rp = self.remote_players.get(pid)
        if rp is None:
            rp = RemotePlayer(pid, name=self.coop.roster.get(pid, "?"))
            self.remote_players[pid] = rp
        rp.apply_snapshot(
            msg.get("x", 0), msg.get("y", 0),
            direction=msg.get("direction", "down"),
            attacking=msg.get("attacking", False),
            hp=msg.get("hp"), max_hp=msg.get("max_hp"),
            downed=msg.get("downed", False), downed_timer=msg.get("downed_timer", 0.0),
        )

    def _boss_snapshot_dict(self):
        """Stage L6: chamado só pelo host, montando o que vai na mensagem
        "enemies". None quando não há boss nesta fase - o guest então nem
        toca em self.boss (que também será None lá, pela mesma
        LEVEL_MAPS[level_num]["boss"] que o level_sync já garantiu bater
        dos dois lados)."""
        if self.boss is None:
            return None
        return {
            "x": self.boss.x, "y": self.boss.y,
            "hp": self.boss.hp, "max_hp": self.boss.max_hp,
            "alive": self.boss.alive,
            "phase": getattr(self.boss, "phase", 1),
            "charge_state": getattr(self.boss, "charge_state", None),
        }

    def _apply_remote_enemies(self, msg):
        """Stage L6: snapshot de inimigos/boss do host. Cria um Enemy
        "fantoche" pra qualquer net_id novo (a onda de respawn do host,
        por exemplo) - o roster INICIAL da fase já nasce com os mesmos ids
        dos dois lados, já que Level._build() varre o layout na mesma
        ordem determinística tanto no host quanto no guest (mesmo
        level_num, mesmo layout, zero aleatoriedade na posição/etype - ver
        docs/coop-implementation-plan.md), então normalmente isto só
        aplica apply_snapshot() num Enemy que o próprio guest já tinha."""
        by_id = {e.net_id: e for e in self.level.enemies}
        for data in msg.get("enemies", []):
            eid = data.get("id")
            enemy = by_id.get(eid)
            if enemy is None:
                enemy = Enemy(data["x"], data["y"], data.get("etype", "skeleton"),
                              level_num=self.level_num, audio_mgr=self.audio)
                enemy.net_id = eid
                enemy.network_follower = True
                self.level.enemies.append(enemy)
                by_id[eid] = enemy
            enemy.apply_snapshot(
                data["x"], data["y"], data.get("flip", False),
                data["hp"], data["max_hp"], data.get("alive", True),
                is_paragon=data.get("is_paragon", False),
                is_champion=data.get("is_champion", False),
                affix=data.get("affix"),
            )

        boss_data = msg.get("boss")
        if boss_data and self.boss is not None:
            self.boss.network_follower = True
            if isinstance(self.boss, CacodemonBoss):
                self.boss.apply_snapshot(boss_data["x"], boss_data["y"],
                                          boss_data["hp"], boss_data["max_hp"], boss_data.get("alive", True))
            else:
                self.boss.apply_snapshot(boss_data["x"], boss_data["y"], boss_data.get("phase", 1),
                                          boss_data["hp"], boss_data["max_hp"], boss_data.get("alive", True),
                                          charge_state=boss_data.get("charge_state"))

    def _handle_pvp_attacks(self):
        """Stage L7 (docs/coop-implementation-plan.md): dano jogador-contra-
        jogador do zero. Cada cliente é autoritativo só pro PRÓPRIO Player
        (rola o próprio dano igual combate PvE de sempre, contra o
        RemotePlayer.rect do alvo em vez de um Enemy.rect) - roda em
        QUALQUER cliente, host ou guest, sem checar net_coop.is_host():
        diferente do modo rede host-autoritativo de Enemy/Boss (L6), PvP é
        simétrico - cada Player só existe de verdade no cliente de quem
        joga com ele.

        Stage L10 (docs/coop-implementation-plan.md): "Traicoeiro" pune
        quem ACERTA um aliado - aplicado direto aqui, no momento do golpe,
        porque quem ataca já sabe sozinho que acabou de acertar um aliado
        (não precisa de confirmação da rede, ao contrário de "Homicida"
        abaixo, que só o ALVO sabe se o golpe foi letal ou não)."""
        if not net_coop.is_connected() or not self.player.attacking:
            return
        atk_rect = self.player.get_attack_rect()
        for rp in self.remote_players.values():
            if rp.x is None:
                continue
            if atk_rect.colliderect(rp.rect):
                dmg, is_crit = self.player.roll_physical()
                # Stage L11 (docs/coop-implementation-plan.md): plumbing de
                # bônus dirigido - se este alvo especificamente me acertou/
                # derrubou antes (Reação Justa/Acerto de Contas, L12), o
                # dano contra ELE (só ele, não a room inteira) sai mais
                # forte. multiplier_against() volta 1.0 (no-op) se não há
                # bônus ativo contra rp.player_id.
                dmg = round(dmg * self.player.vengeance.multiplier_against(rp.player_id))
                net_coop.send({
                    "type": "player_hit",
                    "target_player_id": rp.player_id,
                    "damage": dmg, "dtype": "physical", "crit": is_crit,
                    "attacker_x": self.player.x, "attacker_y": self.player.y,
                })
                self.player.status.apply("traicoeiro")

    def _attempt_cast(self, spell_id, silent=False):
        self.player.selected_spell = spell_id
        if not self.player.try_cast(spell_id):
            # A failed cast used to be completely silent - pressing the key
            # while locked/on cooldown/out of mana looked identical to the
            # key doing nothing at all. Same msg_timer/msg_text toast the
            # level-up/profession-change messages already use.
            # Stage J13: `silent` is for the mobile hold-to-aim auto-fire
            # polling below, which retries every frame while a spell button
            # is held - without it, holding through a cooldown would reset
            # the toast every single frame instead of showing it once.
            if not silent:
                self._cast_fail_message(spell_id)
            return
        spell = SPELLS[spell_id]
        self.audio.play("attack")
        # Estagio M1: dispatch dinamico em vez de um if/elif por magia - os
        # 16 metodos _cast_<spell_id> (3 originais + 13 novos) seguem essa
        # convencao de nome a risca, então getattr() já resolve certo sem
        # precisar crescer esta cadeia a cada magia nova.
        getattr(self, f"_cast_{spell_id}")(spell)

    def _cast_fail_message(self, spell_id):
        # Estagio M1: sem mais o caso "bloqueada: requer X" - ter a
        # profissao com essa magia no kit ja e o unico requisito agora
        # (game/class_kits.py), so cooldown/mana podem bloquear um cast.
        spell = SPELLS[spell_id]
        if self.player.spell_cooldowns.get(spell_id, 0) > 0:
            text = f"{spell['name']} em recarga"
        elif self.player.mana < spell["mana_cost"]:
            text = f"Mana insuficiente para {spell['name']}"
        else:
            return
        self.msg_timer, self.msg_text = 1.6, text

    def _attempt_dash(self):
        if self.player.try_dash():
            return
        # Same "don't fail silently" reasoning as _cast_fail_message above.
        if self.player.stats.dexterity < DASH_DEX_REQ:
            text = f"Investida bloqueada: requer DES {DASH_DEX_REQ}"
        elif self.player.dash_cooldown > 0:
            text = "Investida em recarga"
        else:
            return
        self.msg_timer, self.msg_text = 1.6, text

    def _attempt_pickaxe(self):
        # Stage K14: Player only owns the cooldown gate (try_pickaxe);
        # the target tile is computed here (same aim_dx/aim_dy vector
        # get_attack_rect() already uses) and resolved by Level, which
        # owns the world (blocks/key/exit) - same split as melee attack.
        if not self.player.try_pickaxe():
            return
        cx = self.player.x + self.player.width / 2 + self.player.aim_dx * TILE
        cy = self.player.y + self.player.height / 2 + self.player.aim_dy * TILE
        col, row = int(cx // TILE), int(cy // TILE)
        was_found = self.level._key_found
        self.level.try_break_tile(col, row, self.player, self.audio)
        # Stage K23: fires exactly on the swing that flips _key_found (not
        # on every dig, and not on a swing that lands after it's already
        # been found) - try_break_tile()'s own "pickup" sound stays for the
        # small immediate cue, this adds the bigger pose+fanfare on top.
        if self.level._key_found and not was_found:
            self.player.trigger_key_found_pose()
            self.audio.play("victory")

    def _separate_from_player(self, other):
        """Stage K9: standard AABB de-penetration, split 50/50 - pushes
        along whichever axis has the smaller overlap (the "shallow" axis),
        same shape any 2D physics engine's simplest resolver uses. Doesn't
        re-check walls afterward (a rare corner-case double-overlap could
        in theory nudge something a few px into a wall) - acceptable given
        how small these pushes are compared to a wall tile."""
        p, o = self.player.rect, other.rect
        if not p.colliderect(o):
            return
        overlap_x = min(p.right, o.right) - max(p.left, o.left)
        overlap_y = min(p.bottom, o.bottom) - max(p.top, o.top)
        if overlap_x < overlap_y:
            push = overlap_x / 2 + 0.5
            if p.centerx < o.centerx:
                self.player.x -= push
                other.x += push
            else:
                self.player.x += push
                other.x -= push
        else:
            push = overlap_y / 2 + 0.5
            if p.centery < o.centery:
                self.player.y -= push
                other.y += push
            else:
                self.player.y += push
                other.y -= push

    def _cast_fireball(self, spell):
        # Stage J13: fires along the continuous aim_dx/aim_dy vector (mouse
        # angle on PC, drag-aim on mobile) instead of snapping to one of the
        # 4 cardinal directions - Projectile itself already takes a plain
        # (vx, vy), so this is the only spot that needed to change.
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        speed = 320
        dmg = self.player.magic_damage(spell["spell_base"])
        self.player_projectiles.append(
            Projectile(px, py, self.player.aim_dx * speed, self.player.aim_dy * speed, dmg, (255, 120, 20))
        )

    def _cast_frost_nova(self, spell, radius=110):
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        dmg = self.player.magic_damage(spell["spell_base"])
        targets = list(self.level.enemies)
        if self.boss:
            targets.append(self.boss)
        for target in targets:
            if not getattr(target, "alive", True):
                continue
            tx = target.x + target.width / 2
            ty = target.y + target.height / 2
            if math.hypot(tx - px, ty - py) <= radius:
                # Bugfix round: Frost Nova was the one damage source never
                # migrated to the hit_request pipeline melee/dash/Fireball's
                # projectile loop already use (see cast_targets further
                # down) - a guest casting it against a host-owned Enemy/Boss
                # applied damage only locally, reverting on the next
                # "enemies" snapshot (silent no-op, same bug class already
                # fixed elsewhere, just missed here).
                if getattr(target, "network_follower", False):
                    target_id = "boss" if target is self.boss else target.net_id
                    net_coop.send({"type": "hit_request", "enemy_id": target_id,
                                   "damage": dmg, "dtype": "magic",
                                   "kbx": px, "kby": py, "player_id": net_coop.get_player_id()})
                else:
                    target.take_damage(dmg, dtype="magic", knockback_from=(px, py))
                    if hasattr(target, "status"):
                        target.status.apply("slow")
                    # Also missing before: a Frost Nova kill never called
                    # credit_kill (melee/dash/Fireball all do), so XP/gold
                    # never dropped for anything it killed, coop or not.
                    if not target.alive and hasattr(target, "etype"):
                        self.level.credit_kill(self.player, target)
        # PvP: unlike melee (_handle_pvp_attacks, checked every frame) and
        # Fireball (checked in the projectile loop below), Frost Nova never
        # tested self.remote_players at all - a caster standing next to
        # another player's avatar dealt them zero damage. Same "player_hit"
        # shape _handle_pvp_attacks already sends, applied to every remote
        # player caught in the burst (an AoE can hit more than one, unlike
        # a single-target projectile).
        if net_coop.is_connected():
            for rp in self.remote_players.values():
                if rp.x is None:
                    continue
                rx, ry = rp.x + rp.width / 2, rp.y + rp.height / 2
                if math.hypot(rx - px, ry - py) <= radius:
                    net_coop.send({
                        "type": "player_hit",
                        "target_player_id": rp.player_id,
                        "damage": round(dmg), "dtype": "magic",
                        "attacker_x": self.player.x, "attacker_y": self.player.y,
                    })
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

    # ------------------------------------------------------------------
    # Estagio M1 (leva de conteudo - kits de classe): 13 magias novas.
    # ------------------------------------------------------------------

    def _aoe_around_player(self, dmg, radius, dtype="physical", status_to_enemy=None, hit_players=True):
        """Nucleo compartilhado por toda magia de area centrada no PROPRIO
        jogador (Investida Brutal, Terremoto, Veneno Mortal, Laminas
        Giratorias, Impacto Sismico, Danca das Laminas) - mesmo pipeline
        coop-aware (hit_request/credit_kill/PvP) que _cast_frost_nova já
        tinha, generalizado pra nao repetir 6 vezes quase identico.
        status_to_enemy só se aplica no alvo LOCAL (não-follower) - mesma
        limitação que a Nova de Gelo já tinha antes desta leva (o protocolo
        "hit_request" hoje só carrega dano, nao status; consistente, nao
        um bug novo). Retorna (px, py) pro chamador desenhar suas próprias
        particulas."""
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        targets = list(self.level.enemies)
        if self.boss:
            targets.append(self.boss)
        for target in targets:
            if not getattr(target, "alive", True):
                continue
            tx, ty = target.x + target.width / 2, target.y + target.height / 2
            if math.hypot(tx - px, ty - py) > radius:
                continue
            if getattr(target, "network_follower", False):
                target_id = "boss" if target is self.boss else target.net_id
                net_coop.send({"type": "hit_request", "enemy_id": target_id,
                               "damage": dmg, "dtype": dtype,
                               "kbx": px, "kby": py, "player_id": net_coop.get_player_id()})
            else:
                target.take_damage(dmg, dtype=dtype, knockback_from=(px, py))
                if status_to_enemy and hasattr(target, "status"):
                    target.status.apply(status_to_enemy)
                if not target.alive and hasattr(target, "etype"):
                    self.level.credit_kill(self.player, target)
        if hit_players and net_coop.is_connected():
            for rp in self.remote_players.values():
                if rp.x is None:
                    continue
                rx, ry = rp.x + rp.width / 2, rp.y + rp.height / 2
                if math.hypot(rx - px, ry - py) <= radius:
                    net_coop.send({
                        "type": "player_hit", "target_player_id": rp.player_id,
                        "damage": round(dmg), "dtype": dtype,
                        "attacker_x": self.player.x, "attacker_y": self.player.y,
                    })
        return px, py

    def _status_around_player(self, radius, status_id):
        """Nucleo pras magias que so aplicam status (sem dano) num raio ao
        redor do jogador - Provocacao (taunt) e Raizes Prendentes (root).
        Sem HP envolvido, aplicado direto no proprio objeto local de cada
        cliente (host ou guest) - nao precisa do protocolo hit_request
        (esse existe pra resolver HP de forma autoritativa, nao pra
        cosmetica/comportamento que nao gera conflito real)."""
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        targets = list(self.level.enemies)
        if self.boss:
            targets.append(self.boss)
        hit_any = False
        for target in targets:
            if not getattr(target, "alive", True):
                continue
            tx, ty = target.x + target.width / 2, target.y + target.height / 2
            if math.hypot(tx - px, ty - py) <= radius and hasattr(target, "status"):
                target.status.apply(status_id)
                hit_any = True
        return px, py, hit_any

    def _cast_investida_brutal(self, spell):
        # Guerreiro (ofensiva): area curta a frente do proprio jogador, mais
        # forte que o ataque basico, cooldown baixo - reusa o mesmo nucleo
        # de AoE da Nova de Gelo em vez de um "avanco" fisico novo (ver
        # Player.try_teleport() abaixo pra uma primitiva de movimento real,
        # usada por Passo Sombrio - aqui o efeito e so dano, sem deslocar).
        dmg = self.player.magic_damage(spell["spell_base"])
        px, py = self._aoe_around_player(dmg, 70, dtype="physical")
        for _ in range(10):
            self.level_up_particles.append(Particle(px, py, (230, 90, 60)))

    def _cast_grito_de_guerra(self, spell):
        # Guerreiro (utilitaria): +25% dano fisico por 10s - buff temporario
        # puro, mesmo StatusEffectCarrier.apply() que qualquer pocao usa.
        self.player.status.apply("grito_de_guerra")
        for _ in range(14):
            self.level_up_particles.append(
                Particle(self.player.x + self.player.width / 2,
                         self.player.y + self.player.height / 2, (255, 160, 60))
            )

    def _cast_terremoto(self, spell):
        # Guerreiro (ultimate): area grande, dano pesado.
        dmg = self.player.magic_damage(spell["spell_base"])
        px, py = self._aoe_around_player(dmg, 140, dtype="physical")
        ring_count = 24
        for i in range(ring_count):
            angle = (2 * math.pi / ring_count) * i
            rx = px + math.cos(angle) * 140
            ry = py + math.sin(angle) * 140
            self.level_up_particles.append(Particle(rx, ry, (150, 110, 60)))

    def _cast_veneno_mortal(self, spell):
        # Assassino (ofensiva): dano curto + envenena tudo ao redor.
        dmg = self.player.magic_damage(spell["spell_base"])
        px, py = self._aoe_around_player(dmg, 65, dtype="physical", status_to_enemy="poison")
        for _ in range(10):
            self.level_up_particles.append(Particle(px, py, (110, 200, 90)))

    def _cast_passo_sombrio(self, spell):
        # Assassino (utilitaria): TELEPORTE - primitiva nova (Player.
        # try_teleport()), nao existia nenhuma forma de atravessar geometria
        # sem colidir antes desta leva.
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        for _ in range(8):
            self.level_up_particles.append(Particle(px, py, (150, 90, 200)))
        self.player.try_teleport(spell["teleport_dist"], self.level.walls)
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        for _ in range(8):
            self.level_up_particles.append(Particle(px, py, (190, 140, 230)))

    def _cast_laminas_giratorias(self, spell):
        # Assassino (ultimate): rodopio, area grande.
        dmg = self.player.magic_damage(spell["spell_base"])
        px, py = self._aoe_around_player(dmg, 120, dtype="physical")
        for i in range(3):
            angle = (2 * math.pi / 3) * i
            for r in (40, 80, 120):
                rx = px + math.cos(angle) * r
                ry = py + math.sin(angle) * r
                self.level_up_particles.append(Particle(rx, ry, (215, 218, 225)))

    def _cast_provocacao(self, spell):
        # Cavaleiro: TAUNT - primitiva nova. Inimigos proximos ficam mais
        # agressivos (status "provoked", speed_mult>1.0 - o unico status
        # "positivo" pro alvo que o jogo aplica de proposito, ver game/
        # status_effects.py). Sem alvo real de ameaca multi-jogador ainda
        # (Enemy.update() so enxerga um Player por vez hoje) - prova de
        # conceito de UM sistema, kit completo de Cavaleiro fica pro
        # Estagio M2+.
        px, py, hit_any = self._status_around_player(130, "provoked")
        for _ in range(12):
            self.level_up_particles.append(Particle(px, py, (220, 60, 60)))

    def _cast_impacto_sismico(self, spell):
        # Campeao: STUN - primitiva nova (Enemy.status.has("stun"), ver
        # game/enemy.py's update()). Dano + atordoamento numa area grande.
        dmg = self.player.magic_damage(spell["spell_base"])
        px, py = self._aoe_around_player(dmg, 110, dtype="physical", status_to_enemy="stun")
        for _ in range(16):
            self.level_up_particles.append(Particle(px, py, (160, 120, 60)))

    def _cast_raizes_prendentes(self, spell):
        # Druida: ROOT - reusa o eixo speed_mult existente (sem eixo novo),
        # so o id "root" (duracao/força diferente de "slow").
        px, py, hit_any = self._status_around_player(120, "root")
        for _ in range(12):
            self.level_up_particles.append(Particle(px, py, (90, 150, 70)))

    def _cast_totem_curativo(self, spell):
        # Xama: TOTEM - primitiva nova (game/level.py's HealTotem), a
        # primeira entidade persistente "do lado do jogador" no jogo.
        from game.level import HealTotem
        px = self.player.x + self.player.width / 2
        py = self.player.y + self.player.height / 2
        self.level.player_totems.append(HealTotem(px, py, spell["heal_frac"]))
        for _ in range(10):
            self.level_up_particles.append(Particle(px, py, (110, 220, 130)))

    def _cast_armadilha(self, spell):
        # Ranger: ARMADILHA - primitiva nova (game/level.py's Trap),
        # plantada aos pes do jogador.
        from game.level import Trap
        dmg = self.player.magic_damage(spell["spell_base"])
        px = self.player.x + self.player.width / 2
        py = self.player.y + self.player.height / 2
        self.level.player_traps.append(Trap(px, py, dmg))
        for _ in range(8):
            self.level_up_particles.append(Particle(px, py, (170, 170, 178)))

    def _cast_julgamento(self, spell):
        # Paladino: EXECUCAO - primitiva nova (bonus de dano proporcional a
        # vida FALTANTE do alvo). Acha o inimigo vivo mais proximo num raio
        # curto (sem mira - "o mais proximo", nao um projetil).
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        targets = [t for t in list(self.level.enemies) + ([self.boss] if self.boss else [])
                   if getattr(t, "alive", True)]
        if not targets:
            return
        def _dist(t):
            return math.hypot(t.x + t.width / 2 - px, t.y + t.height / 2 - py)
        target = min((t for t in targets if _dist(t) <= 130), key=_dist, default=None)
        if target is None:
            return
        base = self.player.magic_damage(spell["spell_base"])
        missing_frac = 1.0 - (target.hp / target.max_hp if target.max_hp else 0)
        dmg = round(base * (1 + missing_frac * 1.5))  # ate +150% contra um alvo quase morto
        if getattr(target, "network_follower", False):
            target_id = "boss" if target is self.boss else target.net_id
            net_coop.send({"type": "hit_request", "enemy_id": target_id,
                           "damage": dmg, "dtype": "magic",
                           "kbx": px, "kby": py, "player_id": net_coop.get_player_id()})
        else:
            target.take_damage(dmg, dtype="magic", knockback_from=(px, py))
            if not target.alive and hasattr(target, "etype"):
                self.level.credit_kill(self.player, target)
        tx, ty = target.x + target.width / 2, target.y + target.height / 2
        for _ in range(10):
            self.level_up_particles.append(Particle(tx, ty, (255, 220, 120)))

    def _cast_danca_das_laminas(self, spell):
        # Duelista: COMBO reinterpretado como 3 golpes rapidos NUM cast so
        # (em vez de um contador persistente entre ataques normais, que
        # exigiria instrumentar todo golpe do jogo - fora do escopo desta
        # leva) - ainda assim 3 pulsos reais de dano, nao um so multiplicado.
        dmg = self.player.magic_damage(spell["spell_base"])
        for _ in range(3):
            px, py = self._aoe_around_player(dmg, 90, dtype="physical")
            for _ in range(6):
                self.level_up_particles.append(Particle(px, py, (215, 218, 225)))

    # ------------------------------------------------------------------
    # Estagio M2 (leva de conteudo - kits de classe): 31 magias novas pras
    # 13 profissoes restantes. Todas encaixam num dos 4 "shapes" ja
    # estabelecidos no Estagio M1 (projetil/AoE-ao-redor/buff-proprio/
    # cura) - em vez de repetir o corpo inteiro 31 vezes, cada magia so
    # tem um metodo `_cast_<id>` de 1 linha delegando pro genérico certo
    # (getattr(self, f"_cast_{spell_id}") em _attempt_cast continua
    # funcionando sem mudar - o NOME do metodo é o que importa pro
    # dispatch, nao o corpo).
    # ------------------------------------------------------------------

    def _cast_generic_projectile(self, spell):
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        speed = 320
        dmg = self.player.magic_damage(spell["spell_base"])
        self.player_projectiles.append(
            Projectile(px, py, self.player.aim_dx * speed, self.player.aim_dy * speed, dmg,
                       spell.get("color", (255, 255, 255)),
                       status_effect=spell.get("status_effect"),
                       status_chance=spell.get("status_chance", 0.0),
                       dtype=spell.get("dtype", "magic"))
        )

    def _cast_generic_aoe(self, spell):
        dmg = self.player.magic_damage(spell["spell_base"])
        radius = spell.get("radius", 100)
        px, py = self._aoe_around_player(dmg, radius, dtype=spell.get("dtype", "physical"),
                                          status_to_enemy=spell.get("status_to_enemy"))
        for _ in range(10):
            self.level_up_particles.append(Particle(px, py, spell.get("color", (200, 200, 200))))

    def _cast_generic_buff(self, spell):
        self.player.status.apply(spell["buff_id"])
        px, py = self.player.x + self.player.width / 2, self.player.y + self.player.height / 2
        for _ in range(12):
            self.level_up_particles.append(Particle(px, py, spell.get("color", (255, 220, 150))))

    def _cast_generic_heal(self, spell):
        heal_frac = spell["heal_frac"] * self.player.stats.healing_power
        self.player.hp = min(self.player.max_hp, self.player.hp + self.player.max_hp * heal_frac)
        for _ in range(14):
            self.level_up_particles.append(
                Particle(self.player.x + self.player.width / 2,
                         self.player.y + self.player.height / 2, (255, 240, 200))
            )

    # --- Mago ---
    def _cast_raio_de_gelo(self, spell): self._cast_generic_projectile(spell)
    def _cast_explosao_arcana(self, spell): self._cast_generic_aoe(spell)

    # --- Feiticeiro ---
    def _cast_correntes_malditas(self, spell): self._cast_generic_projectile(spell)
    def _cast_chama_negra(self, spell): self._cast_generic_projectile(spell)
    def _cast_tempestade_sombria(self, spell): self._cast_generic_aoe(spell)

    # --- Cavaleiro ---
    def _cast_investida_do_guardiao(self, spell): self._cast_generic_aoe(spell)
    def _cast_escudo_de_ferro(self, spell): self._cast_generic_buff(spell)

    # --- Duelista ---
    def _cast_corte_cruzado(self, spell): self._cast_generic_aoe(spell)
    def _cast_ripostar(self, spell): self._cast_generic_buff(spell)

    # --- Cavaleiro Arcano ---
    def _cast_lamina_arcana(self, spell): self._cast_generic_aoe(spell)
    def _cast_escudo_arcano(self, spell): self._cast_generic_buff(spell)
    def _cast_explosao_runica(self, spell): self._cast_generic_aoe(spell)

    # --- Paladino ---
    def _cast_aura_sagrada(self, spell): self._cast_generic_buff(spell)
    def _cast_cura_divina(self, spell): self._cast_generic_heal(spell)

    # --- Campeao ---
    def _cast_furia_do_campeao(self, spell): self._cast_generic_buff(spell)
    def _cast_resistencia_inabalavel(self, spell): self._cast_generic_buff(spell)

    # --- Monge ---
    def _cast_palma_espiritual(self, spell): self._cast_generic_aoe(spell)
    def _cast_meditacao(self, spell): self._cast_generic_buff(spell)
    def _cast_chute_giratorio(self, spell): self._cast_generic_aoe(spell)

    # --- Xama ---
    def _cast_raio_da_natureza(self, spell): self._cast_generic_projectile(spell)
    def _cast_espirito_do_lobo(self, spell): self._cast_generic_buff(spell)

    # --- Ranger ---
    def _cast_disparo_perfurante(self, spell): self._cast_generic_projectile(spell)
    def _cast_chuva_de_flechas(self, spell): self._cast_generic_aoe(spell)

    # --- Arcanista ---
    def _cast_prisma_arcano(self, spell): self._cast_generic_projectile(spell)
    def _cast_tempestade_astral(self, spell): self._cast_generic_aoe(spell)
    def _cast_meteoro(self, spell): self._cast_generic_aoe(spell)

    # --- Druida ---
    def _cast_regeneracao_natural(self, spell): self._cast_generic_buff(spell)
    def _cast_furia_da_natureza(self, spell): self._cast_generic_aoe(spell)

    # --- Templario ---
    def _cast_luz_purificadora(self, spell): self._cast_generic_heal(spell)
    def _cast_escudo_divino(self, spell): self._cast_generic_buff(spell)
    def _cast_sentenca_celestial(self, spell): self._cast_generic_aoe(spell)

    def update(self, dt):
        # Stage L5/L6 (docs/coop-implementation-plan.md): processa
        # mensagens de rede coop TODO frame, não só enquanto o painel está
        # aberto - de propósito antes de qualquer early-return de overlay/
        # pausa abaixo (detectar "o host caiu" não pode depender de o
        # jogador estar com o painel de coop aberto no momento certo).
        # Handle_tap continua só rodando com o painel aberto, lá embaixo.
        self.coop.update(dt)
        self.chat.update(dt)

        # Captured before the message loop (not at its old spot right
        # before the local boss-melee block below) - a guest's "hit_request"
        # can now kill the boss from inside this same loop, and the one-shot
        # "just died this frame" guard further down needs boss_was_alive to
        # reflect the state from before ANY of this frame's combat (message-
        # driven or local), not just local melee.
        boss_was_alive = self.boss.alive if self.boss else False

        if net_coop.is_connected():
            for msg in net_coop.poll_messages():
                t = msg.get("type")
                if t in ("roster", "join", "leave"):
                    # CoopOverlay é o dono do roster/quem-é-host - só ele
                    # entende esses 3 tipos. Um "leave" também derruba o
                    # RemotePlayer correspondente aqui, já que ele mora em
                    # GameplayState, não no overlay.
                    self.coop.process_message(msg)
                    if t == "leave":
                        self.remote_players.pop(msg.get("player_id"), None)
                elif t == "pos":
                    self._apply_remote_pos(msg)
                elif t == "level_sync" and not net_coop.is_host():
                    # Stage L6: só o host manda isso (ver o timer mais
                    # abaixo) - um guest cuja fase/dificuldade diverge da
                    # que o host acabou de anunciar se realinha. Também
                    # força a re-transição quando os VALORES já batem mas
                    # self.net_follower ainda é False - acontece sempre que
                    # se entra numa room coop no MEIO de uma fase já
                    # carregada (o único jeito que a UI de L4 permite):
                    # net_follower foi calculado uma vez, na construção
                    # desta GameplayState, antes da conexão existir, e não
                    # se atualiza sozinho depois. Sem isso o Level desta
                    # fase nunca liga o modo rede, mesmo já conectado.
                    lvl, diff = msg.get("level_num"), msg.get("difficulty_id")
                    if lvl is not None and diff is not None and ((lvl, diff) != (self.level_num, self.difficulty_id) or not self.net_follower):
                        self.next_state = f"coop_sync:{lvl}:{diff}"
                        return
                elif t == "enemies" and not net_coop.is_host():
                    self._apply_remote_enemies(msg)
                elif t == "hit_request" and net_coop.is_host():
                    # A guest's melee/dash/projectile against an Enemy or
                    # Boss follower can't call take_damage() locally (real
                    # HP lives on the host - see the network_follower checks
                    # below in this same update()), so it forwards the
                    # already-rolled damage/crit here instead of silently
                    # doing nothing. Host applies it exactly like its own
                    # local attacks would, then the existing "enemies"
                    # broadcast (12Hz, further down) carries the result back
                    # out to every guest automatically - no new outbound
                    # message needed.
                    target_id = msg.get("enemy_id")
                    dmg = msg.get("damage", 0)
                    dtype = msg.get("dtype", "physical")
                    crit = msg.get("crit", False)
                    kb = (msg.get("kbx", 0), msg.get("kby", 0))
                    if target_id == "boss":
                        if self.boss is not None and self.boss.alive:
                            self.boss.take_damage(dmg, dtype=dtype, crit=crit, knockback_from=kb)
                    else:
                        enemy = next((e for e in self.level.enemies
                                      if e.net_id == target_id and e.alive), None)
                        if enemy is not None:
                            enemy.take_damage(dmg, dtype=dtype, crit=crit, knockback_from=kb)
                            if not enemy.alive:
                                # Bugfix round (2a leva): before this,
                                # EVERY hit_request-resolved kill got
                                # credited to the HOST's own player.kills
                                # (self.player here), never the guest who
                                # actually landed it - see credit_kill()'s
                                # killer_id param and the new "kill_credit"
                                # broadcast it sends when killer_id isn't
                                # the resolver's own id.
                                self.level.credit_kill(self.player, enemy, killer_id=msg.get("player_id"))
                elif t == "block_broken":
                    # Symmetric, not host-gated - whichever side (host or
                    # guest) actually broke the block locally sent this;
                    # roll_drop=False so the peer doesn't re-roll a second
                    # independent heart/mana/potion drop for the same break.
                    self.level._break_block(msg.get("col"), msg.get("row"), roll_drop=False)
                elif t == "key_found":
                    # Symmetric too, same reasoning as "block_broken" -
                    # idempotent (setting True twice is harmless).
                    self.level._key_found = True
                    self.level.exit_open = True
                    # Bugfix round (2a leva): quem achou, pro bonus de XP
                    # na tela de vitoria coop - só aceita a primeira vez
                    # (key_finder_id ainda None), a mesma idempotencia do
                    # resto deste handler.
                    if self.level.key_finder_id is None:
                        self.level.key_finder_id = msg.get("player_id")
                elif t == "credit_xp" and not net_coop.is_host():
                    # Stage L8: só o host manda isso (quem realmente
                    # resolve a morte) - decisão #2, a fração já vem
                    # calculada (split igual entre quem estava na room no
                    # momento do kill), este cliente só aplica no próprio
                    # Player.
                    self.player.gain_xp(msg.get("amount", 0))
                elif t == "credit_gold" and not net_coop.is_host():
                    self.player.credit_gold(msg.get("amount", 0))
                elif t == "kill_credit" and msg.get("player_id") == net_coop.get_player_id():
                    # Bugfix round (2a leva): Level.credit_kill() sends this
                    # (host-side, resolving a hit_request) when the actual
                    # killer isn't the resolver itself - same self-filtering
                    # shape as "player_hit" above, since only the rightful
                    # killer's own kills counter should move.
                    et = msg.get("etype")
                    self.player.kills[et] = self.player.kills.get(et, 0) + 1
                elif t == "player_hit" and msg.get("target_player_id") == net_coop.get_player_id():
                    # Stage L7: quem manda essa mensagem já rolou o próprio
                    # dano (mesma lógica de sempre, contra um RemotePlayer
                    # em vez de um Enemy) - este cliente só aplica no seu
                    # próprio Player, autoritativo pra si mesmo. player_id
                    # é carimbado pelo servidor (nunca confiar num campo
                    # que o próprio remetente pudesse forjar), então é a
                    # fonte confiável de "quem me atingiu" pra L11/L12.
                    hp_before_pvp = self.player.hp
                    self.player.take_damage(
                        msg.get("damage", 0), dtype=msg.get("dtype", "physical"),
                        knockback_from=(msg.get("attacker_x", self.player.x), msg.get("attacker_y", self.player.y)),
                        source="player", attacker_player_id=msg.get("player_id"),
                    )
                    # Stage L12 (docs/coop-implementation-plan.md): "Reação
                    # Justa" - só concede se o golpe REALMENTE tirou HP
                    # (hp caiu de verdade), não se take_damage() foi um
                    # no-op (invencibilidade/dodge/já caído) - comparar
                    # antes/depois em vez de confiar em last_attacker_*
                    # (que só é atualizado quando o golpe passa, mas fica
                    # com o valor do golpe anterior se este for bloqueado,
                    # não dá pra usar como sinal de "este golpe passou").
                    if self.player.hp < hp_before_pvp:
                        self.player.vengeance.grant(msg.get("player_id"), 1.15, 10.0)
                elif t == "friendly_kill" and msg.get("attacker_player_id") == net_coop.get_player_id():
                    # Stage L10: mandado pela VÍTIMA no momento em que ela
                    # cai (ver a checagem de morte mais abaixo) - só quem
                    # bateu o golpe letal (identificado pelo player_id que
                    # o SERVIDOR carimbou no "player_hit" original, não um
                    # campo que a vítima poderia forjar) se pune sozinho.
                    self.player.status.apply("homicida")
                elif t == "chat":
                    # Stage L14: quem mandou (player_id carimbado pelo
                    # servidor) já tem um RemotePlayer aqui - a mensagem
                    # "pos" mais recente já o criou (ver _apply_remote_pos()
                    # acima), então não há necessidade de criar um novo só
                    # pra isso. Uma mensagem de chat de alguém que ainda
                    # não mandou nenhum "pos" (impossível na prática, dado
                    # que os dois broadcasts correm juntos) simplesmente
                    # some sem avatar pra mostrar o balão - aceitável.
                    rp = self.remote_players.get(msg.get("player_id"))
                    if rp is not None:
                        rp.say(msg.get("text", ""))
        elif self.remote_players:
            # A sessão coop acabou (saiu, host caiu, rede oscilou) - os
            # avatares dos outros jogadores não continuam parados no mundo.
            self.remote_players.clear()

        match_ended = self.coop.consume_match_ended()
        if match_ended:
            # Decisão #4 do plano: sem migração de host, quem não é host
            # volta pro menu principal - não continua sozinho na cópia
            # local do Level (ver GameStateManager.update()'s tratamento
            # especial de next_state == "menu", que pula o bookkeeping de
            # fim-de-fase normal).
            self.next_state = "menu"
            return

        if net_coop.is_connected():
            # ~12x/s, não todo frame (60fps) - mesma cadência (~10-15Hz)
            # que a feasibility study já apontava pra posição/estado.
            self._coop_pos_send_timer += dt
            if self._coop_pos_send_timer >= 1.0 / 12:
                self._coop_pos_send_timer = 0.0
                net_coop.send({
                    "type": "pos",
                    "x": self.player.x, "y": self.player.y,
                    "direction": self.player.direction, "attacking": self.player.attacking,
                    "hp": self.player.hp, "max_hp": self.player.max_hp,
                    # Stage L9 - pra "todos caídos" e o desenho do RemotePlayer
                    # (downed_timer só pro countdown ficar exato pros outros
                    # também, não só localmente).
                    "downed": self.player.downed, "downed_timer": self.player.downed_timer,
                })
            if net_coop.is_host():
                # Stage L6: 1x/s basta (é só 2 valores) - anuncia em que
                # fase/dificuldade o host está, pra qualquer guest que
                # divergir (acabou de entrar, ou entrou no meio de uma fase
                # antiga) se realinhar via next_state = "coop_sync:...".
                # Sem isso, os snapshots de inimigo/boss (broadcast
                # separado, mais abaixo) cairiam no Level errado do guest.
                self._coop_level_sync_timer += dt
                if self._coop_level_sync_timer >= 1.0:
                    self._coop_level_sync_timer = 0.0
                    net_coop.send({
                        "type": "level_sync",
                        "level_num": self.level_num, "difficulty_id": self.difficulty_id,
                    })
                # Stage L6: mesmo timer/cadência do broadcast de posição -
                # o core do modo rede. Manda a lista inteira toda vez (sem
                # delta-compression) - simples de acertar primeiro, mesmo
                # não sendo o mínimo de bytes possível; LAN e uma dúzia de
                # inimigos não é onde otimizar banda importa nesta v1.
                if self._coop_pos_send_timer == 0.0:  # acabou de mandar "pos" acima
                    net_coop.send({
                        "type": "enemies",
                        "enemies": [
                            {
                                "id": e.net_id, "etype": e.etype, "x": e.x, "y": e.y,
                                "flip": e.flip, "hp": e.hp, "max_hp": e.max_hp, "alive": e.alive,
                                "is_paragon": e.is_paragon, "is_champion": e.is_champion, "affix": e.affix,
                            }
                            for e in self.level.enemies
                        ],
                        "boss": self._boss_snapshot_dict(),
                    })
        for rp in self.remote_players.values():
            rp.update(dt)

        self.weather.update(dt)  # ambient - keeps animating through pause/overlays

        title_key = (self.player.name, self.player.level)
        if title_key != self._last_title_key:
            self._last_title_key = title_key
            import game.save as save
            save.update_browser_title(self.player)

        # Stage J12: a click that lands outside whatever the panel's own
        # handle_tap() just claimed (backdrop, not one of its buttons)
        # closes the menu - same "same shortcut, ESC, or click" trio the
        # user asked for, alongside the key that opened it and ESC (both
        # already handled above in handle_event()).
        if self.paperdoll_open:
            self.paperdoll.handle_tap(self.input, self.player, self.save_state)
            if self.input.any_unconsumed_tap():
                self.toggle_paperdoll()
                return
            self.paperdoll.handle_keys(self.input, self.player, self.save_state)
            return
        if self.items_open:
            self.items.handle_tap(self.input, self.player, self.save_state)
            if self.input.any_unconsumed_tap():
                self.toggle_items()
                return
            self.items.handle_keys(self.input, self.player, self.save_state)
            return
        if self.debug_panel_open:
            self.debug_panel.handle_tap(self.input)
            if self.input.any_unconsumed_tap():
                self.debug_panel_open = False
                if self.debug_panel.consume_difficulty_dirty():
                    self._dev_jump(0)
                return
            self.debug_panel.handle_keys(self.input, self)
            return
        if self.leaderboard_open:
            self.leaderboard.update()
            self.leaderboard.handle_tap(self.input)
            if self.input.any_unconsumed_tap():
                self.toggle_leaderboard()
                return
            self.leaderboard.handle_keys(self.input)
            return
        if self.settings_open:
            self.settings.handle_tap(self.input, self.player, self.save_state)
            if self.input.any_unconsumed_tap():
                self.toggle_settings()
                return
            self.settings.handle_keys(self.input, self.player, self.save_state)
            return
        if self.coop_open:
            self.coop.handle_tap(self.input, self.player, self.save_state)
            if self.input.any_unconsumed_tap():
                self.toggle_coop()
                return
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
                self.player.try_apply_debuff("poison")

        if self._weather_debuff_effect is not None:
            self._weather_debuff_timer -= dt
            if self._weather_debuff_timer <= 0:
                weather_debuff = self.weather.defn["debuff"]
                self._weather_debuff_timer = weather_debuff[1]
                self.player.try_apply_debuff(self._weather_debuff_effect)

        # Storm lightning (Choque) - synced to the visible flash so the hit
        # reads as caused by the strike, not an invisible separate timer.
        if self.weather.consume_lightning() and random.random() < 0.40:
            self.player.try_apply_debuff("shock")

        hp_before = self.player.hp
        self.player.update(dt, self.level.walls, self.input.movement_vector(),
                           level_width=self.level.width, level_height=self.level.height)

        # Stage J13: mouse-aimed combat (PC) - continuous facing towards the
        # cursor's world position, independent of movement, feeding
        # get_attack_rect()/_cast_fireball(). Mobile has no hover concept,
        # so it aims by holding+dragging the attack/spell buttons instead
        # (VirtualButton.aim_dx/dy, set by InputManager._pointer_move) -
        # each is also polled here to auto-fire while held+aimed, respecting
        # its own cooldown (try_attack()/try_cast() already no-op otherwise).
        # Healing Light has no button here (game/input_system.py only marks
        # fireball/frost_nova as aimable) since it doesn't need a direction.
        if not self.input.touch_active:
            mx, my = self.input.mouse_pos()
            world_x, world_y = mx + self.camera.render_x, my + self.camera.render_y
            pcx = self.player.x + self.player.width / 2
            pcy = self.player.y + self.player.height / 2
            self.player.set_aim(world_x - pcx, world_y - pcy)
            # Stage K23: hold-to-fire for PC - attack/spell keys used to
            # only register on the exact KEYDOWN event (handle_event's old
            # consume_action(ATTACK/CAST_1/2/3) branches), so holding one
            # down past the first swing did nothing until released and
            # pressed again. Polled every frame here instead, same "auto-
            # fire while held" shape mobile's VirtualButton already had -
            # try_attack()/try_cast() already no-op on cooldown, so this is
            # safe to call every frame regardless of hold duration.
            # Stage K24: keys/mouse fetched once here and passed to all 4
            # is_action_held() calls below, instead of each one fetching
            # its own fresh pygame.key.get_pressed()/get_pressed() copy -
            # up to 8 of those a frame collapsed to 2. Same class of
            # per-frame-allocation cost as the font()/Puddle-surface bugs
            # already found and fixed for the extended-session freeze, just
            # on the desktop-only hold-to-fire path added after that fix,
            # which the earlier soak test predates and never exercised.
            keys = pygame.key.get_pressed()
            mouse = pygame.mouse.get_pressed(num_buttons=3)
            player_spells = self.player.hotbar_spells
            if self.input.is_action_held("ATTACK", keys, mouse):
                self.player.try_attack()
            if self.input.is_action_held("CAST_1", keys, mouse):
                self._attempt_cast(player_spells[0], silent=True)
            if self.input.is_action_held("CAST_2", keys, mouse):
                self._attempt_cast(player_spells[1], silent=True)
            if self.input.is_action_held("CAST_3", keys, mouse):
                self._attempt_cast(player_spells[2], silent=True)
        else:
            atk_btn = self.input.attack_button
            if atk_btn.active and atk_btn.has_aim:
                self.player.set_aim(atk_btn.aim_dx, atk_btn.aim_dy)
                self.player.try_attack()
            player_spells = self.player.hotbar_spells
            for i, btn in enumerate(self.input.spell_buttons):
                if btn.active and btn.has_aim:
                    self.player.set_aim(btn.aim_dx, btn.aim_dy)
                    self._attempt_cast(player_spells[i], silent=True)
            # Stage K24: same "touch+drag to aim, auto-fires while held"
            # shape as atk_btn above - try_dash() directly (not
            # _attempt_dash(), which also flashes a "bloqueada"/"em
            # recarga" toast on failure - fine for a single keyboard press,
            # but held every frame here it would just re-flash that same
            # toast continuously while on cooldown instead of once).
            dash_btn = self.input.dash_button
            if dash_btn.active and dash_btn.has_aim:
                self.player.set_aim(dash_btn.aim_dx, dash_btn.aim_dy)
                self.player.try_dash()
            # Stage K24 follow-up: same shape again - _attempt_pickaxe()
            # (unlike _attempt_dash()) has no failure-toast side effect to
            # worry about spamming, so it's safe to call directly here
            # instead of needing a silent-mode split.
            pickaxe_btn = self.input.pickaxe_button
            if pickaxe_btn.active and pickaxe_btn.has_aim:
                self.player.set_aim(pickaxe_btn.aim_dx, pickaxe_btn.aim_dy)
                self._attempt_pickaxe()

        self._update_pickup_spawns(dt)
        self._check_pickup_pickups()

        # Stage L8: quantos jogadores estão na room agora - 1 fora de
        # coop. self.coop.roster já exclui o próprio jogador local, então
        # +1 é o total certo.
        room_size = (1 + len(self.coop.roster)) if net_coop.is_connected() else 1

        if self.boss:
            # Stage L6/L8: a guest's damage against a boss follower can't be
            # applied locally (real HP lives on the host) - it now forwards
            # a "hit_request" instead of silently doing nothing (see the
            # message-loop handler above), so this branch runs for both
            # host and guest; only which of the two paths at the bottom
            # fires differs.
            if self.player.attacking:
                atk_rect = self.player.get_attack_rect()
                # take_damage() used to be called unconditionally here (with
                # dmg=0 on a miss) - Boss/CacodemonBoss.take_damage() always
                # sets hit_flash + spawns particles regardless of amount, so
                # every swing flashed the boss even from across the map,
                # never actually connecting. Only call it on an actual hit.
                if atk_rect.colliderect(self.boss.rect):
                    dmg, is_crit = self.player.roll_physical()
                    kb = (self.player.x + self.player.width / 2, self.player.y + self.player.height / 2)
                    if self.boss.network_follower:
                        net_coop.send({"type": "hit_request", "enemy_id": "boss",
                                       "damage": dmg, "dtype": "physical", "crit": is_crit,
                                       "kbx": kb[0], "kby": kb[1], "player_id": net_coop.get_player_id()})
                    else:
                        self.boss.take_damage(dmg, dtype="physical", crit=is_crit, knockback_from=kb)
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
                    self.level.enemies.append(self.level._tag_enemy(summon))
                    self.boss_summons.append(summon)
                self.boss.pending_summons = []

            # Summoned adds need the same chase/melee/credit-kill handling
            # as any other mob - boss fights never ran Level.update() before
            # Stage D6 (self.level.enemies was always empty on boss levels
            # until now), so this is a no-op for orc_warlord/shadow_king.
            self.level.update(dt, self.player, self.audio, room_size=room_size)
        else:
            self.level.update(dt, self.player, self.audio, room_size=room_size)
            if self.level.check_exit(self.player):
                self.next_state = f"next:{self.level.data['next']}"

        self._handle_pvp_attacks()
        self._drain_level_drops()

        # Fireball projectiles - checked against whichever targets this
        # level actually has (regular enemies, a boss, or none). Handled
        # after the melee/boss branch above so a boss (or enemy) killed by
        # Fireball is credited exactly the same as one killed by melee -
        # this used to only grant xp/gold on the melee path.
        cast_targets = list(self.level.enemies) + ([self.boss] if self.boss else [])

        # Stage K9: the hero and a monster/boss should never occupy the same
        # space - skipped while dashing, since Dash's whole point is
        # passing *through* a target to land contact damage (see the block
        # right below); solid-body separation would fight that by shoving
        # them apart before the overlap check below ever sees them touch.
        if not self.player.dashing:
            for target in cast_targets:
                if getattr(target, "alive", True):
                    self._separate_from_player(target)

        # Stage J14: Dash contact damage - checked every frame the dash is
        # moving (not just on activation) since it travels DASH_SPEED*dt per
        # frame and could overlap an enemy mid-dash rather than exactly on
        # press. player._dash_hit_ids (cleared once per dash in try_dash())
        # caps it to one hit per enemy per activation, same idea as a melee
        # swing not re-hitting every frame it's held "attacking".
        if self.player.dashing:
            for target in cast_targets:
                if not getattr(target, "alive", True) or id(target) in self.player._dash_hit_ids:
                    continue
                if self.player.rect.colliderect(target.rect):
                    self.player._dash_hit_ids.add(id(target))
                    dmg, is_crit = self.player.roll_physical()
                    kb = (self.player.x + self.player.width / 2, self.player.y + self.player.height / 2)
                    if getattr(target, "network_follower", False):
                        # Stage L6/L8 follow-up: a guest's dash contact
                        # against a follower target (Enemy OR Boss) used to
                        # just no-op here - now forwarded the same way the
                        # boss-melee block above does.
                        target_id = "boss" if target is self.boss else target.net_id
                        net_coop.send({"type": "hit_request", "enemy_id": target_id,
                                       "damage": dmg, "dtype": "physical", "crit": is_crit,
                                       "kbx": kb[0], "kby": kb[1], "player_id": net_coop.get_player_id()})
                    else:
                        target.take_damage(dmg, dtype="physical", crit=is_crit, knockback_from=kb)
                        if not target.alive and hasattr(target, "etype"):
                            self.level.credit_kill(self.player, target)

        for proj in self.player_projectiles:
            proj.update(dt, self.level.walls)
            if not proj.alive:
                continue
            # PvP: this loop only ever tested cast_targets (enemies/boss) -
            # a Fireball flying through another player's avatar passed
            # straight through with zero effect. Checked before the enemy
            # loop below and consumes the projectile the same way a hit on
            # an enemy would (one target per projectile).
            if net_coop.is_connected():
                hit_player = False
                for rp in self.remote_players.values():
                    if rp.x is None:
                        continue
                    if proj.rect.colliderect(rp.rect):
                        net_coop.send({
                            "type": "player_hit",
                            "target_player_id": rp.player_id,
                            "damage": round(proj.damage), "dtype": proj.dtype,
                            "attacker_x": self.player.x, "attacker_y": self.player.y,
                        })
                        proj.alive = False
                        hit_player = True
                        break
                if hit_player:
                    continue
            for target in cast_targets:
                if not (getattr(target, "alive", True) and proj.rect.colliderect(target.rect)):
                    continue
                if getattr(target, "network_follower", False):
                    target_id = "boss" if target is self.boss else target.net_id
                    net_coop.send({"type": "hit_request", "enemy_id": target_id,
                                   "damage": proj.damage, "dtype": proj.dtype,
                                   "kbx": proj.x, "kby": proj.y, "player_id": net_coop.get_player_id()})
                else:
                    target.take_damage(proj.damage, dtype=proj.dtype, knockback_from=(proj.x, proj.y))
                    # Estagio M2 (kits de classe): projeteis do jogador
                    # carregavam status_effect/status_chance (game/boss.py's
                    # Projectile, mesmo campo que projeteis de boss/inimigo
                    # ja usam) mas este loop nunca aplicava - Raio de Gelo/
                    # Correntes Malditas (magias novas) precisam disso pra
                    # aplicar Lentidao/Fraqueza no impacto.
                    if proj.status_effect and target.alive and hasattr(target, "status") and random.random() < proj.status_chance:
                        target.status.apply(proj.status_effect)
                    if not target.alive and hasattr(target, "etype"):
                        self.level.credit_kill(self.player, target)
                proj.alive = False
                break
        self.player_projectiles = [p for p in self.player_projectiles if p.alive]

        if self.boss and boss_was_alive and not self.boss.alive:
            # Stage L8: ao contrário do ouro de inimigo comum (GoldDrop
            # físico, não compartilhado - ver Level.credit_kill()), a
            # recompensa do boss já é crédito instantâneo pros dois lados
            # (xp E ouro) - dá pra compartilhar os dois igualmente, sem
            # nenhum problema de sync de pickup físico envolvido.
            if room_size > 1 and net_coop.is_connected():
                xp_share = self.boss.xp_reward / room_size
                gold_share = self.boss.gold_reward / room_size
                self.player.gain_xp(xp_share)
                self.player.credit_gold(gold_share)
                net_coop.send({"type": "credit_xp", "amount": xp_share})
                net_coop.send({"type": "credit_gold", "amount": gold_share})
            else:
                self.player.gain_xp(self.boss.xp_reward)
                self.player.credit_gold(self.boss.gold_reward)
            # Instant credit, not a walk-over pickup like regular enemies -
            # the level ends immediately (victory screen), so there's no
            # gameplay window to walk over a dropped coin. Particle burst
            # instead, for the visual payoff.
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
            self.settings_open = False
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
            # Estagio M-correcao: um respec NAO troca mais o kit de magias
            # (self.player.hotbar_spells e escolha manual do jogador na aba
            # Magias, nunca automatica) - so o ataque basico/postura mudam
            # com a profissao agora, o arco movel de magias fica como está.
            self.player.pending_profession_change = None

        # Check death - Stage L9 (docs/coop-implementation-plan.md): em
        # coop, hp <= 0 vira "caído" (revive automático em 5s, decisão #1),
        # não o game_over normal de single-player, que reinicia a fase
        # inteira. `not self.player.downed` evita rechamar trigger_downed()
        # todo frame enquanto o hp continua <= 0 (fica assim até o timer
        # zerar e o próprio Player se revivar).
        if self.player.hp <= 0:
            if net_coop.is_connected():
                if not self.player.downed:
                    # Stage L10: "Homicida" pune quem DERRUBA um aliado -
                    # só a VÍTIMA sabe se o golpe que a derrubou foi
                    # letal (last_attacker_source/_player_id já vem do
                    # take_damage() do "player_hit" - ver _handle_pvp_
                    # attacks() e o poll_messages() de L7), então é ela
                    # quem avisa o agressor pela rede pra ele se punir -
                    # capturado ANTES de trigger_downed() por segurança,
                    # mesmo que ele não mexa nesses campos hoje.
                    was_player_kill = (self.player.last_attacker_source == "player"
                                        and self.player.last_attacker_player_id is not None)
                    attacker_id = self.player.last_attacker_player_id
                    self.player.trigger_downed()
                    if was_player_kill:
                        net_coop.send({"type": "friendly_kill", "attacker_player_id": attacker_id})
                        # Stage L12: "Acerto de Contas" - versão mais forte
                        # (35% vs. 15%) e mais longa (2min vs. 10s) de
                        # "Reação Justa" acima, só quando o golpe foi
                        # letal. grant() substitui em vez de empilhar (a
                        # mesma semântica de "refresca o clock" que
                        # StatusEffectCarrier.apply() já usa) - não faz
                        # sentido acumular os dois contra o mesmo alvo.
                        self.player.vengeance.grant(attacker_id, 1.35, 120.0)
            else:
                self.next_state = "game_over"

        # "Todos caídos ao mesmo tempo" encerra a partida (decisão #1) -
        # só considera jogadores dos quais já se ouviu falar (rp.x is not
        # None); uma room recém-criada sem mais ninguém confirmado ainda
        # não deve contar como "todo mundo caiu" por causa de uma lista
        # vazia (all([]) é True em Python - guard explícito abaixo evita
        # essa pegadinha).
        if net_coop.is_connected() and self.player.downed:
            others_downed = [rp.downed for rp in self.remote_players.values() if rp.x is not None]
            if others_downed and all(others_downed):
                self.next_state = "menu"

    def draw(self):
        cx = int(self.camera.render_x)
        cy = int(self.camera.render_y)

        self.level.draw(self.screen, cx, cy, SW, SH)

        for pickup in self.pickups:
            pickup.draw(self.screen, cx, cy)

        if self.boss:
            self.boss.draw(self.screen, cx, cy)

        self.player.draw(self.screen, cx, cy)

        for rp in self.remote_players.values():
            rp.draw(self.screen, cx, cy)

        for proj in self.player_projectiles:
            proj.draw(self.screen, cx, cy)

        for p in self.level_up_particles:
            p.draw(self.screen, cx, cy)

        self.camera.apply_zoom(self.screen)

        # Weather - screen-space, drawn after the zoom post-effect so fog/
        # rain/snow don't visually warp during a zoom_pulse hit effect.
        self.weather.draw(self.screen)

        # HUD
        # Stage K8: mouse_pos powers hover tooltips - meaningless on touch
        # (no persistent hover there), but harmless to pass either way since
        # draw_tooltip() only ever draws when a rect actually contains it.
        self.player.draw_hud(self.screen, self.save_state, touch_active=self.input.touch_active,
                              mouse_pos=self.input.mouse_pos())
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
            self.paperdoll.draw(self.screen, self.player, self.save_state, forced=self.level_up_forced,
                                 mouse_pos=self.input.mouse_pos())

        # Itens overlay
        if self.items_open:
            self.items.draw(self.screen, self.player, mouse_pos=self.input.mouse_pos())

        # Debug panel overlay (Stage B5 follow-up - F1, PC only)
        if self.debug_panel_open:
            self.debug_panel.draw(self.screen, self)

        # Leaderboard overlay (Stage J8-J10)
        if self.leaderboard_open:
            self.leaderboard.draw(self.screen)

        # Settings overlay (Stage K15)
        if self.settings_open:
            self.settings.draw(self.screen, self.save_state)

        # Coop room overlay (Stage L4)
        if self.coop_open:
            self.coop.draw(self.screen, self.player)

        # Chat input (Stage L13) - não é "outro painel" no sentido de
        # toggle_coop()/toggle_settings() etc. (não bloqueia o resto da
        # tela nem pausa o jogo, só a caixa de texto no rodapé), então
        # desenha por cima de tudo isso, sempre que ativo.
        self.chat.draw(self.screen)

        # Stage J11: always called now, not just when touch_active - the
        # mouse-click crosshair (InputManager._draw_crosshair) needs to
        # render on desktop too, where touch_active is deliberately never
        # set. InputManager.draw() already re-checks touch_active itself
        # before drawing the virtual joystick/buttons, so this doesn't
        # change anything about when THOSE show up.
        # Stage K24: hide_controls=True while any overlay above is showing -
        # the joystick/attack/spell/item buttons used to draw on top of
        # every one of them (this call happens after all the overlay draws
        # above), covering menu buttons on mobile and looking wrong under
        # the pause dim too.
        menu_open = (self.paused or self.paperdoll_open or self.items_open
                     or self.debug_panel_open or self.leaderboard_open or self.settings_open)
        # Stage K24 follow-up: debug_panel_open passed separately so
        # InputManager.draw() can keep just the debug button itself up as
        # an exception - the only overlay a mobile player has no other way
        # to close (every other one already closes via a tap outside it).
        self.input.draw(self.screen, hide_controls=menu_open, debug_panel_open=self.debug_panel_open)

    def _spawn_pickup(self, kind, at=None):
        sprite = self._pickup_sprites[kind]
        if at is not None:
            # Stage K14: monster/block drops want an exact position (where
            # the kill/break happened), unlike the timer-driven random
            # placement below - skip the collision-avoidance search since
            # the position is already valid ground the kill/dig happened on.
            x, y = at[0] - sprite.get_width() / 2, at[1] - sprite.get_height() / 2
            self.pickups.append(Pickup(x, y, sprite, kind))
            return
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

    def _drain_level_drops(self):
        """Stage K14: game/level.py reports "something dropped here" as a
        plain (kind, x, y) descriptor (pending_drops) rather than
        instantiating Pickup itself - Pickup/inventory/toast all belong to
        this class already (the timer-driven heart/mana spawn above), and
        importing them into level.py would reach back into states.py
        (which already imports FROM level.py), a circular import."""
        for kind, x, y in self.level.pending_drops:
            if kind == "potion":
                self.player.inventory["health_potion"] = self.player.inventory.get("health_potion", 0) + 1
                self.msg_timer, self.msg_text = 1.6, "Pocao de Vida encontrada!"
            else:
                self._spawn_pickup(kind, at=(x, y))
        self.level.pending_drops = []

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
        # Stage Q2: um segundo nivel secreto (Dragao Primordial, fase 26) -
        # mesmo gate de desbloqueio que o primeiro (Cacodemonio), so
        # clicavel/tocavel (sem tecla dedicada propria, ao contrario do
        # primeiro que usa Action.SECRET) pra nao precisar de um Action novo
        # no keybind system so pra isso.
        secret2_label = "Nivel Secreto: Furia do Dragao" if secret_unlocked else "Nivel Secreto 2 - vença o Inferno para desbloquear"
        self.secret2_button = TextButton(secret2_label, SW//2, 534, pad_y=8)

    def handle_event(self, event):
        if self.secret_unlocked:
            if self.input.consume_action(Action.SECRET):
                self.audio.play("menu_select")
                return "secret"
            if self.input.tapped_rect(self.secret_button.rect):
                self.audio.play("menu_select")
                return "secret"
            if self.input.tapped_rect(self.secret2_button.rect):
                self.audio.play("menu_select")
                return "secret2"
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
        # Stage Q2: generico de proposito - o boss final da campanha deixou
        # de ser sempre o Rei das Sombras (Ato 3) quando os Atos 4-6 foram
        # encadeados depois dele; nomear um boss especifico aqui exigiria
        # passar o boss_id ate este draw(), que nenhum outro dado de
        # VictoryState hoje precisa.
        draw_text(self.screen, "O ultimo tirano foi derrotado!", f2, (220,220,180), SW//2, 235)
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
        self.secret2_button.draw(self.screen, f_ins, secret_color)

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
        self.settings_button = SettingsButton(SW - 40, 262)
        self.coop_button = CoopButton(SW - 40, 316)

        import game.save as save
        self.save_state = save.load() or save.new_game_state()
        self.audio.muted = self.save_state["settings"]["muted"]
        # Stage K15: applies any remapped keys before InputManager ever
        # reads game.keybinds.BINDINGS - an empty dict here is a no-op
        # (BINDINGS already starts as a copy of DEFAULT_BINDINGS).
        import game.keybinds as keybinds
        keybinds.apply_saved_bindings(self.save_state["settings"]["keybinds"])

        # Stage I4: fire-and-forget, no JWT needed (/balance is public) -
        # patches ITEMS/DIFFICULTIES/SPELLS/game.stats in place whenever it
        # resolves, if ever; the code's own defaults already make the game
        # fully playable before/without this.
        import game.net as net
        net.trigger_balance_fetch()
        net.trigger_appearance_fetch()

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
        if highest >= 25:
            # This tier's final boss is already cleared - move on to the
            # next difficulty (already unlocked, since clearing tier N is
            # exactly what unlocks tier N+1) instead of re-fighting the
            # same final boss forever.
            nd = next_difficulty(diff_id)
            if nd:
                self.save_state["progression"]["current_difficulty"] = nd
                return 1
            return 25  # Inferno has no next tier - keep replaying its final boss
        return min(highest + 1, 25)

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
            if self.input.tapped_rect(self.settings_button.rect):
                self.state.toggle_settings()
                self.audio.play("menu_select")
            if self.input.tapped_rect(self.coop_button.rect):
                self.state.toggle_coop()
                self.audio.play("menu_select")

        self.state.update(dt)

        # Track play time while in gameplay
        if isinstance(self.state, GameplayState):
            self.play_time += dt
            self.save_state["counters"]["playtime_s"] += dt
            ns = self.state.next_state
            if ns == "menu":
                # Stage L5: o host caiu em coop (decisão #4) - não é fim de
                # fase nenhum, então pula inteiramente o bookkeeping abaixo
                # (deaths/highest_level_cleared/cleared_difficulties/sync) -
                # a partida foi interrompida, não terminou. self.player
                # continua o mesmo (não some, só a GameplayState acaba).
                self._transition(ns)
            elif ns and ns.startswith("coop_sync:"):
                # Stage L6: guest entrando numa room cuja fase/dificuldade
                # do host diverge da sua - pula o bookkeeping de fim-de-fase
                # (não foi uma fase concluída, é reposicionamento pra bater
                # com o host antes do modo rede de Enemy/Boss fazer
                # sentido nenhum).
                self._transition(ns)
            elif ns:
                self.player = self.state.player
                import game.save as save
                if ns == "game_over":
                    self.save_state["counters"]["deaths"] = self.save_state["counters"].get("deaths", 0) + 1
                    self._just_cleared_difficulty = None
                    # Stage K3: death no longer touches highest_level_cleared
                    # - "Continuar" resumes at the deepest level already
                    # cleared (_continue_level() below reads exactly that),
                    # same as the original pre-Stage-D4 behavior. A death
                    # only costs the in-progress run, never the checkpoint.
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
            # Stage L6/L7: TransitionState.handle_event() é um no-op - uma
            # tecla apertada durante os ~1.5s da transição nunca é
            # consumida por ninguém e ficaria esperando a PRÓXIMA
            # GameplayState pra ser lida, sendo mal-interpretada lá (uma
            # troca de fase é sempre um contexto novo). Defensivo, mesmo
            # raciocínio de _transition()'s próprio clear_actions() -
            # limpar a cada frame que a transição existir garante que nada
            # sobra pra vazar, não importa quando o evento chegou durante
            # a janela.
            self.input.clear_actions()
            if self.state.done:
                lvl = self.state.next_level
                self.state = GameplayState(self.screen, self.input, self.audio, lvl, self.player,
                                            save_state=self.save_state,
                                            coop=self.state.coop, remote_players=self.state.remote_players)

    def draw(self):
        self.state.draw()
        self.sound_button.draw(self.screen, self.audio.muted)
        self.fullscreen_button.draw(self.screen, self._is_fullscreen())
        if isinstance(self.state, GameplayState):
            self.paperdoll_button.draw(self.screen)
            self.items_button.draw(self.screen)
            self.leaderboard_button.draw(self.screen)
            self.settings_button.draw(self.screen)
            self.coop_button.draw(self.screen)

    def _has_progress(self):
        # A character who dies before ever clearing level 1 anywhere would
        # otherwise make this false and silently orphan their name/gold/
        # attributes behind "Novo Jogo" - a non-empty name or level>1 means
        # a character exists, dungeon progress or not.
        highest = self.save_state["progression"]["highest_level_cleared"]
        return (any(v > 0 for v in highest.values())
                or self.save_state["character"]["level"] > 1
                or bool(self.save_state["character"]["name"]))

    def _transition(self, result):
        # Stage L6/L7: uma Action ainda não consumida no frame em que a
        # troca de estado acontece não devia vazar pro estado novo - um
        # ESC pressionado bem no instante em que uma transição dispara
        # (inclusive as automáticas de coop, como coop_sync, que agora
        # podem acontecer sem nenhuma ação do jogador) podia sobreviver
        # até a GameplayState seguinte e ser mal-interpretado lá (uma
        # troca de fase é sempre um contexto novo - nenhuma Action de
        # antes devia atravessar). Defensivo: o bug real investigado com
        # tools/coop_harness.py acabou sendo outra coisa (o teste fechava
        # o painel coop tarde demais, depois do coop_sync automático já
        # ter reconstruído a GameplayState) - ver InputManager.clear_actions().
        self.input.clear_actions()
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
        elif result.startswith("coop_sync:"):
            # Stage L6: guest recebeu a fase/dificuldade atual do host
            # (mensagem "level_sync") e diverge da sua - vai direto pra lá
            # via o mesmo TransitionState que "next:" usa, mas SEM passar
            # pelo StageCompleteState/tally de xp-ganho daquele branch (não
            # é uma fase concluída, é só se realinhar com o host antes do
            # modo rede de Enemy/Boss fazer sentido).
            _, level_num_s, difficulty_id = result.split(":", 2)
            self.save_state["progression"]["current_difficulty"] = difficulty_id
            self.state = TransitionState(self.screen, int(level_num_s), self.player,
                                          coop=self.state.coop, remote_players=self.state.remote_players)
            self.play_time = 0.0
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
            start_level = min(highest + 1, 25)
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
            # Stage L6: getattr, não self.state.coop direto - ao contrário
            # dos outros sites, não há garantia forte de que self.state
            # ainda é a GameplayState aqui (caminho raro/pouco testado).
            coop = getattr(self.state, "coop", None)
            remote_players = getattr(self.state, "remote_players", None)
            self.player = self._player_from_save()
            self.state = TransitionState(self.screen, 13, self.player, coop=coop, remote_players=remote_players)
            self.play_time = 0.0
        elif result == "secret2":
            # Stage Q2: mesma logica do "secret" acima, so que pra fase 26
            # (Dragao Primordial) em vez da 13 (Cacodemonio).
            coop = getattr(self.state, "coop", None)
            remote_players = getattr(self.state, "remote_players", None)
            self.player = self._player_from_save()
            self.state = TransitionState(self.screen, 26, self.player, coop=coop, remote_players=remote_players)
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
                kills_gained = sum(self.player.kills.values()) - finished._kills_at_level_start
                # Bugfix round (2a leva): key_finder_id is None outside coop
                # (Level.__init__'s default) and never equals a real
                # net_coop.get_player_id(), so this bonus can't fire in
                # single-player - qualified import (not a top-level
                # `from game.stats import KEY_FINDER_XP_BONUS`) since
                # balance_config.py overrides it via `setattr(stats, ...)`
                # on the module object, which a name-binding import would
                # freeze at whatever value existed at first import.
                import game.stats as stats
                key_finder_id = finished.level.key_finder_id
                local_pid = net_coop.get_player_id() if net_coop.is_connected() else None
                if key_finder_id is not None and key_finder_id == local_pid:
                    self.player.gain_xp(stats.KEY_FINDER_XP_BONUS)
                xp_gained = self.player.xp_earned_total - finished._xp_at_level_start
                gold_gained = self.player.gold - finished._gold_at_level_start
                self.state = StageCompleteState(self.screen, self.input, self.audio,
                                                 finished.level_num, next_lvl,
                                                 xp_gained, gold_gained, self.player,
                                                 coop=finished.coop, remote_players=finished.remote_players,
                                                 kills_gained=kills_gained, key_finder_id=key_finder_id)
            else:
                # self.state aqui é a StageCompleteState que acabou de
                # confirmar "Continuar" (ver docstring da classe) - Stage
                # L6 repassa coop/remote_players dela pro TransitionState
                # final, completando a corrente iniciada acima.
                self.state = TransitionState(self.screen, next_lvl, self.player,
                                              coop=self.state.coop, remote_players=self.state.remote_players)
