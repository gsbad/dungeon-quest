import asyncio
import pygame
import sys
from game.states import GameStateManager
from game.input_system import InputManager

async def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass  # Sem dispositivo de áudio (WSL/headless/navegador) – continua sem som

    SCREEN_W, SCREEN_H = 800, 600
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Dungeon Quest")
    clock = pygame.time.Clock()

    input_mgr = InputManager(SCREEN_W, SCREEN_H)
    manager = GameStateManager(screen, input_mgr)

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
