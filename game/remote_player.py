"""
Stage L3 (docs/coop-implementation-plan.md): entidade leve, só-visual, pra
representar outros jogadores na mesma room coop. Ao contrário de
game/player.py's Player (que carrega input local, física, hotbar), esta só
guarda o que precisa pra desenhar e interpolar: posição, direção, ataque,
HP, nome, profissão. Nunca simula nada - o estado inteiro vem de fora via
apply_snapshot(), alimentado pelas mensagens de rede do L2 a partir da
Fase 2 - o mesmo "recebe snapshot, só desenha" que o plano já descreve pro
host-autoritativo de Enemy/Boss (L6).

Interpolação é obrigatória mesmo mirando só rede local (LAN) - sem ela, um
RemotePlayer "pisca" pra nova posição a cada broadcast em vez de deslizar
(ver docs/coop-feasibility.md, risco #6). Usa a mesma suavização
exponencial que Camera.follow() já usa (game/camera.py) - não existe um
lerp() genérico em game/ hoje, essa é a convenção mais próxima a seguir em
vez de inventar uma nova.
"""
import pygame

from game.assets import create_player_sprite
from game.theme import font, SUBTEXT, GREEN
from game.ui import ProgressBar
from game.player import CHAT_BUBBLE_DURATION

_INTERP_SPEED = 10.0  # 1/s - mesma ordem de grandeza da Camera.follow() (8.0)
_HP_BAR = ProgressBar(28, 4, (40, 10, 10), (10, 5, 5))
# Stage L14: abaixo do hotbar + chips de status do HUD (que desenham por
# cima de qualquer coisa no mundo) - mesmo valor computado que
# game/player.py's _draw_chat_bubble() usa (_HOTBAR_Y + _HOTBAR_SLOT + 6 +
# 34 + 8 = 90), duplicado aqui em vez de importar constantes com "_" de
# outro módulo.
_HUD_CLEAR_Y = 90


class RemotePlayer:
    def __init__(self, player_id, name="?", profession=None):
        self.player_id = player_id
        self.name = name
        self.profession = profession

        # None até a primeira apply_snapshot() - sentinela pra não desenhar
        # nem interpolar a partir de um (0, 0) fantasma antes do primeiro
        # pacote de posição chegar.
        self.x = None
        self.y = None
        self.target_x = 0.0
        self.target_y = 0.0
        self.width = 32
        self.height = 36

        self.direction = "down"
        self.attacking = False
        self.hp = 1
        self.max_hp = 1
        # Stage L9 (docs/coop-implementation-plan.md) - "caído"/revive,
        # espelhando Player.downed/downed_timer via a mesma mensagem "pos".
        self.downed = False
        self.downed_timer = 0.0
        # Stage L14 - balão de fala, alimentado por say() quando uma
        # mensagem "chat" chega (evento avulso, não parte do snapshot
        # contínuo de "pos" - ver GameplayState's poll_messages()).
        self.chat_text = ""
        self.chat_timer = 0.0

        self._sprite_cache = {}

    @property
    def rect(self):
        """Stage L7 (docs/coop-implementation-plan.md): mesma forma de
        Enemy.rect/Boss.rect - o attack_rect de um Player local colide
        contra isto pra detectar PvP."""
        return pygame.Rect(self.x, self.y, self.width, self.height)

    def apply_snapshot(self, x, y, direction="down", attacking=False, hp=None, max_hp=None,
                        downed=False, downed_timer=0.0):
        """Chamado quando uma mensagem de posição chega pela rede - nunca
        teleporta self.x/self.y direto, só move o alvo que update()
        persegue a cada frame (exceto na primeiríssima snapshot, onde
        aparecer já no lugar certo é melhor que deslizar da origem)."""
        self.target_x = x
        self.target_y = y
        if self.x is None:
            self.x, self.y = x, y
        self.direction = direction
        self.attacking = attacking
        if hp is not None:
            self.hp = hp
        if max_hp is not None:
            self.max_hp = max_hp
        self.downed = downed
        self.downed_timer = downed_timer

    def say(self, text):
        """Stage L14: mesmo método/shape de Player.say() - chamado quando
        uma mensagem "chat" chega pela rede pra este player_id."""
        self.chat_text = text
        self.chat_timer = CHAT_BUBBLE_DURATION

    def update(self, dt):
        if self.chat_timer > 0:
            self.chat_timer -= dt
        if self.x is None:
            return
        self.x += (self.target_x - self.x) * _INTERP_SPEED * dt
        self.y += (self.target_y - self.y) * _INTERP_SPEED * dt

    def _get_sprite(self, key):
        # Sem god_mode/debug_invincible no cache key (diferente do
        # Player._get_sprite real) - um RemotePlayer nunca entra em god
        # mode, esse estado é local a quem está jogando, não trafega.
        cache_key = (key, self.profession)
        cached = self._sprite_cache.get(cache_key)
        if cached is None:
            attacking = key.endswith("_atk")
            direction = key[:-4] if attacking else key
            cached = create_player_sprite(direction, attacking, self.profession)
            self._sprite_cache[cache_key] = cached
        return cached

    def draw(self, surface, cam_x, cam_y):
        if self.x is None:
            return

        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)

        if self.downed:
            # Stage L9: mesmo truque de Player._draw_downed() - gira o
            # sprite parado em vez de uma pose nova por profissão.
            sprite = self._get_sprite(self.direction)
            fallen = pygame.transform.rotate(sprite, 90 if self.direction != "left" else -90)
            fx = sx - 8 + (sprite.get_width() - fallen.get_width()) // 2
            fy = sy - 12 + (sprite.get_height() - fallen.get_height()) // 2
            surface.blit(fallen, (fx, fy))
            f = font(13, bold=True)
            secs = max(0, int(self.downed_timer) + 1)
            txt = f.render(f"{self.name} caido - {secs}s", True, SUBTEXT)
            surface.blit(txt, (sx + self.width // 2 - txt.get_width() // 2, sy - 26))
            return

        key = self.direction
        if self.attacking:
            key = self.direction + "_atk"

        sprite = self._get_sprite(key)
        if self.direction == "left":
            sprite = pygame.transform.flip(
                self._get_sprite("right_atk" if self.attacking else "right"), True, False
            )

        surface.blit(sprite, (sx - 8, sy - 12))

        bx = sx
        by = sy - 20
        frac = max(0, self.hp / self.max_hp)
        _HP_BAR.draw(surface, bx, by, frac, GREEN)

        f_name = font(12, bold=True)
        txt = f_name.render(self.name, True, SUBTEXT)
        surface.blit(txt, (bx + _HP_BAR.w // 2 - txt.get_width() // 2, by - 16))

        if self.chat_timer > 0:
            self._draw_chat_bubble(surface, sx, sy)

    def _draw_chat_bubble(self, surface, sx, sy):
        """Stage L14: mesmo desenho de Player._draw_chat_bubble() (balão +
        rabicho), só que acima do nameplate/barra de HP que só RemotePlayer
        tem (Player não desenha nameplate acima de si mesmo)."""
        f = font(13, bold=True)
        txt = f.render(self.chat_text, True, (20, 20, 24))
        pad_x, pad_y = 8, 5
        bw, bh = txt.get_width() + pad_x * 2, txt.get_height() + pad_y * 2
        bx = sx + self.width // 2 - bw // 2
        # Stage L14: mesmo clamp de Player._draw_chat_bubble() - um
        # RemotePlayer perto do topo da TELA (não do mapa dele, da câmera
        # de QUEM está olhando) teria o balão desenhado por baixo do
        # hotbar/chips de status do jogador local, que desenham por cima.
        by = max(sy - 40 - bh, _HUD_CLEAR_Y)
        bubble = pygame.Surface((bw, bh + 6), pygame.SRCALPHA)
        pygame.draw.rect(bubble, (240, 240, 235), (0, 0, bw, bh), border_radius=6)
        pygame.draw.polygon(bubble, (240, 240, 235),
                             [(bw // 2 - 5, bh), (bw // 2 + 5, bh), (bw // 2, bh + 6)])
        surface.blit(bubble, (bx, by))
        surface.blit(txt, (bx + pad_x, by + pad_y))
