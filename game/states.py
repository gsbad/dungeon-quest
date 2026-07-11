import pygame
import math
import time
import random
from game.player import Player
from game.level import Level
from game.boss import Boss, CacodemonBoss
from game.camera import Camera
from game.assets import create_heart_sprite, create_logo_sprite, create_victory_hero_sprite
from game.input_system import Action
from game.audio import SoundButton

SW, SH = 800, 600

# ─── Fonts ────────────────────────────────────────────────────────────────────
def font(size, bold=False):
    f = pygame.font.Font(None, size)
    f.set_bold(bold)
    return f

def draw_text(surface, text, f, color, cx, y, shadow=True):
    if shadow:
        s = f.render(text, True, (0,0,0))
        surface.blit(s, (cx - s.get_width()//2 + 2, y+2))
    r = f.render(text, True, color)
    surface.blit(r, (cx - r.get_width()//2, y))
    return r.get_height()


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


class HeartPickup:
    def __init__(self, x, y, sprite):
        self.x = float(x)
        self.y = float(y)
        self.sprite = sprite
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
    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.stars = [Star() for _ in range(80)]
        self.t = 0
        self.selected = 0
        self.options = ["JOGAR", "SAIR"]
        self._option_rects = [None] * len(self.options)

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
        for i, rect in enumerate(self._option_rects):
            if rect and self.input.tapped_rect(rect):
                self.selected = i
                self.audio.play("menu_select")
                return self.options[i]
        return None

    def update(self, dt):
        self.t += dt
        for star in self.stars:
            star.update(dt)

    def draw(self):
        self.screen.fill((5, 5, 20))
        for star in self.stars:
            star.draw(self.screen)

        # Title glow
        glow_r = int(200 + 30 * math.sin(self.t * 2))
        glow_surf = pygame.Surface((500, 120), pygame.SRCALPHA)
        pygame.draw.ellipse(glow_surf, (80, 0, 120, 60), (0, 0, 500, 120))
        self.screen.blit(glow_surf, (150, 80))

        f_title = font(64, bold=True)
        draw_text(self.screen, "DUNGEON QUEST", f_title, (220, 160, 255), SW//2, 90)

        f_sub = font(20)
        draw_text(self.screen, "Criado por Gustavo Sa - RU 361193", f_sub, (180, 180, 220), SW//2, 175)

        # Controls box
        box = pygame.Surface((320, 160), pygame.SRCALPHA)
        box.fill((20, 10, 40, 180))
        pygame.draw.rect(box, (120, 80, 200), (0,0,320,160), 2)
        self.screen.blit(box, (SW//2-160, 220))

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
            k_surf = f_ctrl.render(key, True, (255, 220, 100))
            d_surf = f_ctrlv.render(desc, True, (200, 200, 220))
            self.screen.blit(k_surf, (SW//2 - 150, y))
            self.screen.blit(d_surf, (SW//2 - 10, y))

        # Menu options
        f_menu = font(32, bold=True)
        for i, opt in enumerate(self.options):
            pulse = 1.0 + 0.08 * math.sin(self.t * 4) if i == self.selected else 1.0
            color = (255, 220, 50) if i == self.selected else (160, 140, 200)
            prefix = "> " if i == self.selected else "  "
            label = prefix + opt
            y = 410 + i * 55
            draw_text(self.screen, label, f_menu, color, SW//2, y)
            w, h = f_menu.size(label)
            self._option_rects[i] = pygame.Rect(SW//2 - w//2 - 30, y - 15, w + 60, h + 30)

        # Version
        f_tiny = font(12)
        v = f_tiny.render("Linguagem de Programacao Aplicada - UNINTER 2026", True, (80,80,100))
        self.screen.blit(v, (SW//2 - v.get_width()//2, SH - 24))


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
        draw_text(self.screen, f"Nivel {self.next_level}", f, (220,180,255), SW//2, SH//2-20)
        from game.level import LEVEL_MAPS
        if self.next_level in LEVEL_MAPS:
            f2 = font(22)
            title = LEVEL_MAPS[self.next_level]["title"]
            draw_text(self.screen, title, f2, (180,180,220), SW//2, SH//2+24)
        if self.next_level == 4:
            f3 = font(18)
            draw_text(self.screen, "O BOSS FINAL AGUARDA...", f3, (255,100,100), SW//2, SH//2+60)


# ─── Gameplay State ────────────────────────────────────────────────────────────
class GameplayState:
    def __init__(self, screen, input_mgr, audio_mgr, level_num=1, player=None):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.level_num = level_num
        self.level = Level(level_num)
        self.camera = Camera(SW, SH, self.level.width, self.level.height)

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

        # Boss (level 4 and 5)
        self.boss = None
        self.hearts = []
        self.heart_sprite = create_heart_sprite(True)
        self.heart_spawn_timer = random.uniform(8.0, 14.0)
        if level_num == 4:
            self.boss = Boss(SW//2 - 48, 80)
        elif level_num == 5:
            self.boss = CacodemonBoss(SW//2 - 40, 100)

        self.paused = False
        self.next_state = None
        self._restart_rect = None

        # Level-entry message
        self.msg_timer = 2.5
        self.msg_text = f"Nivel {level_num}: {self.level.data['title']}"

        # Screen shake
        self.shake = 0

    def handle_event(self, event):
        if self.input.consume_action(Action.PAUSE):
            self.paused = not self.paused
        if self.paused:
            if self.input.consume_action(Action.RESTART):
                self.next_state = "restart"
            elif self._restart_rect and self.input.tapped_rect(self._restart_rect):
                self.next_state = "restart"
        elif self.input.consume_action(Action.ATTACK):
            self.player.try_attack()

    def update(self, dt):
        if self.paused:
            return

        self.camera.follow(self.player, dt)

        if self.msg_timer > 0:
            self.msg_timer -= dt

        self.player.update(dt, self.level.walls, self.input.movement_vector())

        if self.level_num == 4:
            self._update_heart_spawns(dt)
            self._check_heart_pickups()

        if self.boss:
            if self.player.attacking:
                atk_rect = self.player.get_attack_rect()
                self.boss.take_damage(1 if atk_rect.colliderect(self.boss.rect) else 0)
            self.boss.update(dt, self.player, self.level.walls)
            if not self.boss.alive:
                self.next_state = "secret_victory" if self.level_num == 5 else "victory"
        else:
            self.level.update(dt, self.player)
            if self.level.check_exit(self.player):
                self.next_state = f"next:{self.level_num+1}"

        # Check death
        if self.player.hp <= 0:
            self.next_state = "game_over"

    def draw(self):
        cx = int(self.camera.x)
        cy = int(self.camera.y)

        self.level.draw(self.screen, cx, cy, SW, SH)

        for heart in self.hearts:
            heart.draw(self.screen, cx, cy)

        if self.boss:
            self.boss.draw(self.screen, cx, cy)

        self.player.draw(self.screen, cx, cy)

        # HUD
        self.player.draw_hud(self.screen)
        self.level.draw_hud_info(self.screen)

        if self.boss and self.boss.alive:
            self.boss.draw_hud(self.screen, SW)

        # Entry message
        if self.msg_timer > 0:
            alpha = min(255, int(self.msg_timer * 255))
            f = font(28, bold=True)
            surf = f.render(self.msg_text, True, (255, 220, 100))
            surf.set_alpha(alpha)
            self.screen.blit(surf, (SW//2 - surf.get_width()//2, SH//2 - 20))

        # Pause overlay
        if self.paused:
            overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
            overlay.fill((0,0,0,140))
            self.screen.blit(overlay, (0,0))
            f = font(48, bold=True)
            draw_text(self.screen, "PAUSADO", f, (220,180,255), SW//2, SH//2-40)
            f2 = font(20)
            draw_text(self.screen, "ESC / toque no botao - Continuar", f2, (180,180,220), SW//2, SH//2+20)
            restart_label = "R / toque aqui - Reiniciar"
            draw_text(self.screen, restart_label, f2, (180,180,220), SW//2, SH//2+50)
            w, h = f2.size(restart_label)
            self._restart_rect = pygame.Rect(SW//2 - w//2 - 20, SH//2 + 50 - 14, w + 40, h + 28)
        else:
            self._restart_rect = None

        if self.input.touch_active:
            self.input.draw(self.screen)

    def _spawn_heart(self):
        attempts = 0
        while attempts < 50:
            attempts += 1
            margin = 48
            x = random.randint(margin, self.level.width - margin - self.heart_sprite.get_width())
            y = random.randint(margin, self.level.height - margin - self.heart_sprite.get_height())
            candidate = pygame.Rect(x, y, self.heart_sprite.get_width(), self.heart_sprite.get_height())
            if any(candidate.colliderect(w) for w in self.level.walls):
                continue
            if self.boss and candidate.colliderect(self.boss.rect):
                continue
            if candidate.colliderect(self.player.rect):
                continue
            self.hearts.append(HeartPickup(x, y, self.heart_sprite))
            return

    def _update_heart_spawns(self, dt):
        if self.boss and not self.boss.alive:
            return
        if self.hearts:
            for heart in self.hearts:
                heart.update(dt)
            return
        self.heart_spawn_timer -= dt
        if self.heart_spawn_timer <= 0:
            self.heart_spawn_timer = random.uniform(8.0, 14.0)
            self._spawn_heart()

    def _check_heart_pickups(self):
        for heart in self.hearts[:]:
            if self.player.rect.colliderect(heart.rect):
                self.player.hp = min(self.player.max_hp, self.player.hp + 1)
                self.hearts.remove(heart)
                self.audio.play("pickup")


# ─── Game Over ────────────────────────────────────────────────────────────────
class GameOverState:
    def __init__(self, screen, input_mgr, audio_mgr):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.stars = [Star() for _ in range(60)]
        self._menu_rect = None
        self._restart_rect = None

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "menu"
        if self.input.consume_action(Action.RESTART):
            self.audio.play("menu_select")
            return "restart"
        if self._menu_rect and self.input.tapped_rect(self._menu_rect):
            self.audio.play("menu_select")
            return "menu"
        if self._restart_rect and self.input.tapped_rect(self._restart_rect):
            self.audio.play("menu_select")
            return "restart"
        return None

    def update(self, dt):
        self.t += dt
        for s in self.stars:
            s.update(dt)

    def draw(self):
        self.screen.fill((20, 0, 0))
        for s in self.stars:
            s.draw(self.screen)

        f1 = font(72, bold=True)
        pulse = abs(math.sin(self.t * 2))
        r = int(180 + 75 * pulse)
        draw_text(self.screen, "FIM DE JOGO", f1, (r, 30, 30), SW//2, 160)

        f2 = font(22)
        draw_text(self.screen, "Voce foi derrotado nas trevas...", f2, (200,150,150), SW//2, 280)

        f3 = font(20, bold=True)
        menu_label = "[ ENTER ] - Menu Principal"
        restart_label = "[ R ] - Tentar Novamente"
        draw_text(self.screen, menu_label, f3, (220,180,180), SW//2, 360)
        draw_text(self.screen, restart_label, f3, (220,180,180), SW//2, 395)

        mw, mh = f3.size(menu_label)
        self._menu_rect = pygame.Rect(SW//2 - mw//2 - 20, 360 - 12, mw + 40, mh + 24)
        rw, rh = f3.size(restart_label)
        self._restart_rect = pygame.Rect(SW//2 - rw//2 - 20, 395 - 12, rw + 40, rh + 24)


# ─── Victory ──────────────────────────────────────────────────────────────────
class VictoryState:
    def __init__(self, screen, input_mgr, audio_mgr, elapsed_seconds=0.0):
        self.screen = screen
        self.input = input_mgr
        self.audio = audio_mgr
        self.t = 0
        self.particles = []
        self._spawn_timer = 0
        self.elapsed = float(elapsed_seconds)
        self._menu_rect = None
        self._secret_rect = None

    def handle_event(self, event):
        if self.input.consume_action(Action.SECRET):
            self.audio.play("menu_select")
            return "secret"
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "menu"
        if self._secret_rect and self.input.tapped_rect(self._secret_rect):
            self.audio.play("menu_select")
            return "secret"
        if self._menu_rect and self.input.tapped_rect(self._menu_rect):
            self.audio.play("menu_select")
            return "menu"
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
        self.screen.fill((5, 10, 30))
        for p in self.particles:
            p.draw(self.screen, 0, 0)

        f1 = font(64, bold=True)
        glow = int(200 + 55 * math.sin(self.t * 3))
        draw_text(self.screen, "VITORIA!", f1, (255, glow, 50), SW//2, 140)

        f2 = font(24)
        draw_text(self.screen, "O Rei das Sombras foi derrotado!", f2, (220,220,180), SW//2, 235)
        draw_text(self.screen, "A paz voltou as terras do reino.", f2, (200,200,160), SW//2, 268)

        f3 = font(18)
        draw_text(self.screen, "Parabens, heroi!", f3, (180,255,180), SW//2, 330)

        f4 = font(20, bold=True)
        menu_label = "[ ENTER ] - Menu Principal"
        draw_text(self.screen, menu_label, f4, (200,200,220), SW//2, 420)
        mw, mh = f4.size(menu_label)
        self._menu_rect = pygame.Rect(SW//2 - mw//2 - 20, 420 - 12, mw + 40, mh + 24)

        # Show total play time
        mins = int(self.elapsed // 60)
        secs = int(self.elapsed % 60)
        time_str = f"Tempo: {mins:02d}:{secs:02d}"
        ftime = font(18)
        draw_text(self.screen, time_str, ftime, (180,220,180), SW//2, 460)

        # Instructions
        f_ins = font(16)
        secret_label = "[ ESPACO ] - Nivel Secreto"
        draw_text(self.screen, secret_label, f_ins, (180,200,180), SW//2, 500)
        sw, sh = f_ins.size(secret_label)
        self._secret_rect = pygame.Rect(SW//2 - sw//2 - 20, 500 - 10, sw + 40, sh + 20)

        f5 = font(14)
        draw_text(self.screen, "Linguagem de Programacao Aplicada - UNINTER 2026",
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
        self._menu_rect = None

    def handle_event(self, event):
        if self.input.consume_action(Action.CONFIRM):
            self.audio.play("menu_select")
            return "menu"
        if self._menu_rect and self.input.tapped_rect(self._menu_rect):
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
        menu_label = "[ ENTER ] - Menu Principal"
        draw_text(self.screen, menu_label, f3, (255, 220, 180), SW//2, 340)
        mw, mh = f3.size(menu_label)
        self._menu_rect = pygame.Rect(SW//2 - mw//2 - 20, 340 - 12, mw + 40, mh + 24)

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
        self.sound_button = SoundButton(40, 40)
        self.state = MenuState(screen, input_mgr, audio_mgr)
        self.player = None
        self.play_time = 0.0

    def handle_event(self, event):
        result = self.state.handle_event(event)
        if result:
            self._transition(result)

    def update(self, dt):
        if self.input.tapped_rect(self.sound_button.rect):
            self.audio.toggle_mute()
            self.audio.play("menu_select")

        self.state.update(dt)

        # Track play time while in gameplay
        if isinstance(self.state, GameplayState):
            self.play_time += dt
            ns = self.state.next_state
            if ns:
                self.player = self.state.player
                self._transition(ns)

        if isinstance(self.state, TransitionState):
            if self.state.done:
                lvl = self.state.next_level
                self.state = GameplayState(self.screen, self.input, self.audio, lvl, self.player)

    def draw(self):
        self.state.draw()
        self.sound_button.draw(self.screen, self.audio.muted)

    def _transition(self, result):
        if result == "JOGAR":
            self.player = None
            self.state = TransitionState(self.screen, 1, None)
            self.play_time = 0.0
        elif result == "SAIR":
            import sys, pygame
            pygame.quit(); sys.exit()
        elif result == "menu":
            self.player = None
            self.state = MenuState(self.screen, self.input, self.audio)
        elif result == "restart":
            self.player = None
            self.state = TransitionState(self.screen, 1, None)
            self.play_time = 0.0
        elif result == "game_over":
            self.audio.play("game_over")
            self.state = GameOverState(self.screen, self.input, self.audio)
        elif result == "victory":
            self.audio.play("victory")
            self.state = VictoryState(self.screen, self.input, self.audio, elapsed_seconds=self.play_time)
        elif result == "secret":
            self.player = None
            self.state = TransitionState(self.screen, 5, None)
            self.play_time = 0.0
        elif result == "secret_victory":
            self.audio.play("victory")
            self.state = SecretVictoryState(self.screen, self.input, self.audio)
        elif result and result.startswith("next:"):
            next_lvl = int(result.split(":")[1])
            self.state = TransitionState(self.screen, next_lvl, self.player)
