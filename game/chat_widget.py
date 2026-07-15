"""
Stage L13 (docs/coop-implementation-plan.md): campo de texto livre pra
chat coop - Enter abre, digita, Enter confirma/Esc cancela. Sem precedente
reaproveitável no código hoje (confirmado lendo NameEntryState e o campo
de código de room do CoopOverlay - nenhum dos dois desenha um cursor
piscando de verdade nem aceita texto arbitrário: NameEntryState restringe
a alfanumerico+espaco pro nome do personagem, o campo de room do
CoopOverlay força maiusculas/alfanumerico com tamanho fixo pro código),
então este é um componente novo, pequeno e autocontido - mesmo "arquivo
por responsabilidade" de game/remote_player.py e game/coop_overlay.py.

PC-only por decisão deliberada (ver docs/coop-feasibility.md) - sem
teclado virtual nem fluxo de "abrir teclado do celular" hoje, chat em
mobile fica pra uma rodada futura.
"""
import pygame

from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT

MAX_LEN = 80
_BOX_W, _BOX_H = 420, 40


class ChatWidget:
    def __init__(self):
        self.active = False
        self.text = ""
        self._t = 0.0

    def open(self):
        self.active = True
        self.text = ""

    def handle_event(self, event):
        """Só deve ser chamado enquanto self.active (GameplayState.
        handle_event() já garante isso, mesma exclusividade que o campo
        de código do CoopOverlay já usa - ver Stage L4's lição sobre
        vazamento de tecla pros atalhos de dev). Retorna a mensagem
        confirmada (str não-vazia) ao apertar Enter, None caso contrário
        (inclusive Esc/Enter com campo vazio, que só fecham o campo)."""
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            self.active = False
            self.text = ""
        elif event.key == pygame.K_RETURN:
            self.active = False
            msg = self.text.strip()
            self.text = ""
            if msg:
                return msg
        elif event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.text) < MAX_LEN:
            self.text += event.unicode
        return None

    def update(self, dt):
        self._t += dt

    def draw(self, surface):
        if not self.active:
            return
        box_x = SW // 2 - _BOX_W // 2
        box_y = SH - 90
        box = pygame.Surface((_BOX_W, _BOX_H), pygame.SRCALPHA)
        box.fill((15, 15, 20, 220))
        pygame.draw.rect(box, ACCENT_GOLD, (0, 0, _BOX_W, _BOX_H), 2, border_radius=6)
        surface.blit(box, (box_x, box_y))

        cursor = "|" if int(self._t * 2) % 2 == 0 else " "
        f = font(16)
        txt = f.render(self.text + cursor, True, (235, 235, 245))
        surface.blit(txt, (box_x + 12, box_y + (_BOX_H - txt.get_height()) // 2))

        f_hint = font(11)
        hint = f_hint.render("Enter - Enviar | ESC - Cancelar", True, SUBTEXT)
        surface.blit(hint, (SW // 2 - hint.get_width() // 2, box_y + _BOX_H + 4))
