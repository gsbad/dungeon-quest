"""
Stage L4 (docs/coop-implementation-plan.md): overlay pra criar/entrar numa
room coop, mesmo padrão Panel/TextButton de game/merchant.py e
game/settings_overlay.py. As chamadas de rede (game/net_coop.py's
create_room()/connect()) são coroutines - GameplayState.update() não é
async (chamado direto do loop de main.py) - então esse overlay dispara
elas com asyncio.ensure_future() e guarda a Task numa referência forte
(self._task), o mesmo cuidado contra coleta prematura que game/net.py's
_track() já documenta (sem isso a Task pode nunca chegar a rodar).

Decisão #3 do plano (backend gera o código da room) já define o que esse
overlay pede: "Criar Room" não pede nada, só mostra o código que volta do
servidor; "Entrar" pede o código de 4 caracteres de outro jogador, digitado
com o mesmo estilo de captura de KEYDOWN cru que NameEntryState
(game/states.py) já usa pro nome do personagem - sem widget de teclado
virtual dedicado (esse é só o L13, pro chat).
"""
import asyncio
import pygame

from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, TextButton, draw_text
import game.net_coop as net_coop

_PANEL_W = 360
_PANEL_H = 300
_CODE_LEN = 4


class CoopOverlay:
    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = SH // 2 - _PANEL_H // 2
        self.panel = Panel(_PANEL_W, _PANEL_H, PANEL_FILL, PANEL_BORDER, border_width=2)

        # "menu" | "join_code" | "busy" | "connected" | "error"
        self.mode = "menu"
        self.error_text = ""
        self.code_input = ""
        self.room_id = None
        self.roster = {}  # player_id -> name
        self.host_player_id = None  # Stage L5 - quem no roster é o host
        self._match_ended_reason = None  # Stage L5 - consumido por GameplayState (ver consume_match_ended())
        self._task = None
        self._t = 0.0  # cursor piscando, mesmo ritmo de NameEntryState

        cx = SW // 2
        self._create_button = TextButton("Criar Room", cx, self.py + 100)
        self._join_button = TextButton("Entrar em Room", cx, self.py + 150)
        self._connect_button = TextButton("Conectar", cx, self.py + 165)
        self._back_button = TextButton("Voltar", cx, self.py + 220)
        self._leave_button = TextButton("Sair da Room", cx, self.py + _PANEL_H - 40)

    # ---- network plumbing -------------------------------------------------

    def _launch(self, coro):
        self._task = asyncio.ensure_future(coro)

    async def _do_create(self, name):
        try:
            room_id = await net_coop.create_room()
            await net_coop.connect(room_id, name)
            self.room_id = room_id
            self.roster = {}
            self.mode = "connected"
        except Exception as e:
            self.error_text = str(e)
            self.mode = "error"

    async def _do_join(self, code, name):
        try:
            await net_coop.connect(code, name)
            self.room_id = code
            self.roster = {}
            self.mode = "connected"
        except Exception as e:
            self.error_text = str(e)
            self.mode = "error"

    def _start_create(self, player):
        self.mode = "busy"
        self._launch(self._do_create(player.name if player and player.name else "?"))

    def _start_join(self, player):
        if len(self.code_input) != _CODE_LEN:
            return
        self.mode = "busy"
        self._launch(self._do_join(self.code_input, player.name if player and player.name else "?"))

    def _leave(self):
        net_coop.disconnect()
        self.room_id = None
        self.roster = {}
        self.host_player_id = None
        self.mode = "menu"

    def consume_match_ended(self):
        """Stage L5: pop-once, mesmo padrão de consume_difficulty_dirty()
        (game/debug_panel.py) - None enquanto nada aconteceu, uma string
        (o motivo) na primeira sondagem depois do host sumir. GameplayState
        lê isso todo frame (não só quando o painel está aberto) pra saber
        quando precisa jogar TODO o estado de volta pro menu principal -
        decisão #4 do plano: sem migração de host, os demais não continuam
        sozinhos."""
        reason = self._match_ended_reason
        self._match_ended_reason = None
        return reason

    # ---- frame-driven state ------------------------------------------------

    def update(self, dt):
        """Stage L6: o drain de `net_coop.poll_messages()` passou pra
        GameplayState (um dono só pra fila inteira - com posição de
        jogador/inimigo/boss chegando no mesmo canal a partir desta fase,
        duas partes do jogo lendo a fila cada uma por conta própria
        roubariam mensagem uma da outra). Este método só cuida do que não
        depende de mensagem nenhuma: o timer do cursor piscando e detectar
        que a conexão caiu sozinha (sem nenhuma mensagem "leave" chegando -
        rede oscilou, processo do host morreu sem fechar o socket direito,
        etc)."""
        self._t += dt
        if self.mode != "connected":
            return
        if not net_coop.is_connected():
            if net_coop.is_host():
                # O próprio host perdeu a conexão (rede oscilou) - a
                # sessão coop acaba, mas ele continua jogando sozinho, não
                # precisa ser expulso da própria partida por isso.
                self.error_text = net_coop.get_last_error() or "conexao perdida"
                self.mode = "error"
            else:
                self._match_ended_reason = net_coop.get_last_error() or "conexao com o host perdida."
                self._leave()

    def process_message(self, msg):
        """Chamado por GameplayState pra cada mensagem "roster"/"join"/
        "leave" que tira da fila central (ver update() acima) - as únicas
        que este overlay entende; "pos"/"enemies"/"boss"/etc (Stage L6+)
        vão pra outros lugares."""
        if self.mode != "connected":
            return
        was_host = net_coop.is_host()
        t = msg.get("type")
        if t == "roster":
            self.roster = {p["player_id"]: p["name"] for p in msg["players"]}
            for p in msg["players"]:
                if p.get("is_host"):
                    self.host_player_id = p["player_id"]
        elif t == "join":
            self.roster[msg["player_id"]] = msg.get("name", "?")
            if msg.get("is_host"):
                self.host_player_id = msg["player_id"]
        elif t == "leave":
            pid = msg.get("player_id")
            self.roster.pop(pid, None)
            if not was_host and pid is not None and pid == self.host_player_id:
                # O host saiu - sem migração de host na v1, a partida
                # acaba pros demais (decisão #4), não só reseta este
                # painel. Quem É o host nunca cai nesse branch (perder
                # a própria conexão não deveria expulsá-lo da própria
                # partida - ver o ramo `is_connected()` de update()).
                self._match_ended_reason = "O host saiu da partida."
                self._leave()

    def handle_event(self, event, player=None):
        """Captura de KEYDOWN cru pro campo de codigo - so importa no modo
        join_code. Mesmo padrao de NameEntryState (game/states.py)."""
        if self.mode != "join_code" or event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_RETURN:
            self._start_join(player)
        elif event.key == pygame.K_BACKSPACE:
            self.code_input = self.code_input[:-1]
        elif event.unicode and event.unicode.isalnum() and len(self.code_input) < _CODE_LEN:
            self.code_input += event.unicode.upper()

    def handle_tap(self, input_mgr, player=None, save_state=None):
        if self.mode == "menu":
            if input_mgr.tapped_rect(self._create_button.rect):
                self._start_create(player)
            elif input_mgr.tapped_rect(self._join_button.rect):
                self.mode = "join_code"
                self.code_input = ""
        elif self.mode == "join_code":
            if input_mgr.tapped_rect(self._connect_button.rect):
                self._start_join(player)
            elif input_mgr.tapped_rect(self._back_button.rect):
                self.mode = "menu"
        elif self.mode == "connected":
            if input_mgr.tapped_rect(self._leave_button.rect):
                self._leave()
        elif self.mode == "error":
            if input_mgr.tapped_rect(self._back_button.rect):
                self.error_text = ""
                self.mode = "menu"
        # "busy": nenhum botao ativo - so aguardando a Task terminar.

    # ---- draw ---------------------------------------------------------------

    def draw(self, surface, player=None):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))
        cx = self.px + _PANEL_W // 2

        f_title = font(24, bold=True)
        draw_text(surface, "COOP", f_title, ACCENT_GOLD, cx, self.py + 24)

        f = font(16)
        f_hint = font(13)

        if self.mode == "menu":
            self._create_button.draw(surface, f, SUBTEXT)
            self._join_button.draw(surface, f, SUBTEXT)
            draw_text(surface, "ESC - Fechar", f_hint, SUBTEXT, cx, self.py + _PANEL_H - 20)

        elif self.mode == "join_code":
            draw_text(surface, "Codigo da room:", f, SUBTEXT, cx, self.py + 90)
            cursor = "_" if int(self._t * 2) % 2 == 0 else " "
            shown = (self.code_input + cursor).ljust(_CODE_LEN, "-")
            f_code = font(32, bold=True)
            draw_text(surface, shown, f_code, ACCENT_GOLD, cx, self.py + 120)
            connect_color = SUBTEXT if len(self.code_input) == _CODE_LEN else (110, 110, 120)
            self._connect_button.draw(surface, f, connect_color)
            self._back_button.draw(surface, f, SUBTEXT)
            draw_text(surface, "Enter - Conectar | ESC - Voltar", f_hint, SUBTEXT, cx, self.py + _PANEL_H - 20)

        elif self.mode == "busy":
            draw_text(surface, "Conectando...", f, SUBTEXT, cx, self.py + 130)

        elif self.mode == "connected":
            draw_text(surface, f"Room: {self.room_id}", font(20, bold=True), ACCENT_GOLD, cx, self.py + 60)
            draw_text(surface, "Diga esse codigo pros outros jogadores", f_hint, SUBTEXT, cx, self.py + 84)

            my_name = player.name if player and player.name else "Voce"
            names = [(my_name, net_coop.is_host())]
            names += [(name, pid == self.host_player_id) for pid, name in self.roster.items()]
            f_row = font(15)
            y = self.py + 116
            for name, is_host in names:
                label = f"{name} (host)" if is_host else name
                draw_text(surface, label, f_row, (225, 225, 235), cx, y, shadow=False)
                y += 24
            if not self.roster:
                draw_text(surface, "Esperando outros jogadores entrarem...", f_hint, SUBTEXT, cx, y + 6)

            self._leave_button.draw(surface, f, SUBTEXT)
            draw_text(surface, "ESC - Fechar (continua conectado)", f_hint, SUBTEXT, cx, self.py + _PANEL_H - 20)

        elif self.mode == "error":
            f_err = font(15)
            draw_text(surface, "Falha na conexao:", f, (255, 140, 140), cx, self.py + 100)
            draw_text(surface, self.error_text, f_err, (255, 170, 170), cx, self.py + 130)
            self._back_button.draw(surface, f, SUBTEXT)
