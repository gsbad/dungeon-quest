"""
Fast, no-browser regression tests for two bugs the playtest-report round
after Stage Q2 (M-Q content wave) surfaced, both pure game-logic (not
coop-network) issues that don't need Playwright/pygbag at all - a real
pygame.init() with SDL_VIDEODRIVER=dummy is enough to exercise the actual
Level/Player code directly and assert on the resulting state.

Bug A ("chave nunca aparece embaixo de nenhum dos 10 X"): game/level.py's
_pick_key_tile() used to roll the hidden key's tile completely
independently of _spawn_treasure_marks()'s 10 decorative "X" positions -
two unrelated random.choice() calls, so the key had no guaranteed relation
to any mark at all. Fixed by folding key selection into
_spawn_treasure_marks() itself, picked from the same candidate list the
marks come from - see game/level.py's updated docstring there.

Bug B ("PvP joga o jogador pra fora do mapa"): Player.update()'s safety-net
clamp (for knockback/dash tunneling clean through a 1-tile-wide border
wall in a single large-dt frame) used to clamp to the raw [0, level_width]
rectangle, which includes the solid border wall tile itself - a tunneled
player got pinned AT x=0 (or the mirrored bound on the other 3 edges),
inside/behind the wall graphic instead of back on the floor. Fixed by
clamping one full TILE in from each edge instead. See game/player.py's
updated comment.

Usage:
    python tools/logic_tests.py
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402


class _DummyAudio:
    def play(self, *a, **k):
        pass


def _log(msg):
    print(f"[logic_tests] {msg}", flush=True)


def test_key_always_under_a_treasure_mark(trials=25):
    """Clears the original enemy wave on a fresh Level(1) `trials` times
    (fresh instance each time, since _spawn_treasure_marks() only ever
    fires once per Level via _first_wave_map_shown) and asserts the key
    tile it picks is always one of that same run's 10 X marks."""
    from game.level import Level, TILE
    from game.player import Player

    for i in range(trials):
        lvl = Level(1)
        assert lvl._key_tile is None, (
            "key_tile should stay undecided until the treasure marks spawn, "
            f"got {lvl._key_tile} right after Level.__init__ (trial {i})"
        )
        player = Player(*lvl.get_player_start(), audio_mgr=_DummyAudio())
        for e in lvl.enemies:
            e.alive = False
            e.hp = 0
        lvl.update(1 / 60, player, audio_mgr=None)

        assert lvl.treasure_marks, f"no treasure marks spawned (trial {i})"
        assert lvl._key_tile is not None, f"key_tile still None after marks spawned (trial {i})"
        mark_tiles = {(int(mx // TILE), int(my // TILE)) for mx, my in lvl.treasure_marks}
        assert lvl._key_tile in mark_tiles, (
            f"key_tile {lvl._key_tile} is not among this run's treasure marks {mark_tiles} (trial {i})"
        )
    _log(f"OK - key tile matched one of the 10 X marks in all {trials} trials.")


def test_knockback_never_strands_player_in_border_wall(trials=8):
    """Places the player right against each of the 4 level edges and fires
    a PvP-style knockback (take_damage(knockback_from=...)) pointed
    straight at that edge, then updates with a large single-frame dt (the
    stutter/GC-pause scenario the safety-net clamp exists for) big enough
    for the old code to tunnel clean through the 1-tile border. Asserts
    the player ends up on the floor side - not overlapping a wall, and
    fully inside [0, level_width] x [0, level_height]."""
    from game.level import Level, TILE
    from game.player import Player

    edges = [
        ("left",   lambda w, h, pw, ph: (TILE + 2, h / 2),                     (1, 0)),
        ("right",  lambda w, h, pw, ph: (w - TILE - pw - 2, h / 2),            (-1, 0)),
        ("top",    lambda w, h, pw, ph: (w / 2, TILE + 2),                     (0, 1)),
        ("bottom", lambda w, h, pw, ph: (w / 2, h - TILE - ph - 2),            (0, -1)),
    ]

    for name, start_fn, away_dir in edges:
        for i in range(trials):
            lvl = Level(1)
            px, py = start_fn(lvl.width, lvl.height, 32, 36)
            player = Player(px, py, audio_mgr=_DummyAudio())
            player.x, player.y = float(px), float(py)

            attacker_x = player.x - away_dir[0] * 300
            attacker_y = player.y - away_dir[1] * 300
            player.take_damage(10, knockback_from=(attacker_x, attacker_y))
            assert player.knockback_timer > 0, f"[{name}] hit didn't trigger knockback (trial {i})"

            player.update(0.5, lvl.walls, (0, 0), level_width=lvl.width, level_height=lvl.height)

            rect = player.rect
            in_bounds = 0 <= rect.left and rect.right <= lvl.width and 0 <= rect.top and rect.bottom <= lvl.height
            overlaps_wall = any(rect.colliderect(w) for w in lvl.walls)
            assert in_bounds, f"[{name}] player rect {rect} left the level bounds (trial {i})"
            assert not overlaps_wall, (
                f"[{name}] player rect {rect} landed inside/behind a wall tile after knockback tunnel (trial {i})"
            )
    _log(f"OK - knockback tunnel never stranded the player in a border wall, all 4 edges x {trials} trials.")


def main():
    pygame.init()
    pygame.display.set_mode((800, 600))
    try:
        test_key_always_under_a_treasure_mark()
        test_knockback_never_strands_player_in_border_wall()
    except AssertionError as e:
        _log(f"RESULTADO: FALHOU - {e}")
        sys.exit(1)
    _log("RESULTADO: OK - todos os testes de logica passaram.")


if __name__ == "__main__":
    main()
