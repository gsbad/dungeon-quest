import asyncio
import pygame
import sys
from game.states import GameStateManager
from game.input_system import InputManager
from game.audio import AudioManager
from game.theme import SW, SH

async def main():
    pygame.init()
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
    except pygame.error:
        pass  # Sem dispositivo de áudio (WSL/headless/navegador) – continua sem som

    screen = pygame.display.set_mode((SW, SH), pygame.SCALED)
    pygame.display.set_caption("Dungeon Quest")
    clock = pygame.time.Clock()

    input_mgr = InputManager(SW, SH)
    audio_mgr = AudioManager()
    manager = GameStateManager(screen, input_mgr, audio_mgr)

    while True:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            input_mgr.feed(event)
            manager.handle_event(event)

        manager.update(dt)
        input_mgr.update(dt)
        manager.draw()
        pygame.display.flip()
        await asyncio.sleep(0)  # devolve o controle ao event loop do navegador (exigido pelo Pygbag)

asyncio.run(main())
