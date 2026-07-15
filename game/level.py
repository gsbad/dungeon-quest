import pygame
import random
import math
from game.assets import create_tile, create_chest_sprite, create_cracked_wall_overlay, create_dig_marker
from game.enemy import Enemy, BASE_XP, GOLD_DROPS, GoldDrop, Particle
from game.stats import xp_for_kill, gold_for_kill
from game.affixes import PARAGON_REWARD_MULT, CHAMPION_REWARD_MULT
from game.theme import font, ACCENT_GOLD
import game.net_coop as net_coop

TILE = 48

# Map layouts: '#'=wall, '.'=floor/grass, 'W'=water, 'E'=enemy spawn, 'P'=player, 'X'=exit
LEVEL_MAPS = {
    1: {
        "type": "combat",
        "boss": None,
        "next": 2,
        "victory": None,
        "monster_level": 1,
        "weather": "fog",
        "tileset": "grass",
        "floor": "grass",
        "bg": (20, 80, 20),
        "title": "Floresta Encantada",
        "description": "Uma floresta densa envolta em neblina - o primeiro territorio disputado com esqueletos e goblins.",
        "enemies": ["skeleton", "goblin"],
        "layout": [
            "####################",
            "#..................#",
            "#.....##...##......#",
            "#.....##...##..E...#",
            "#..................#",
            "#...E..........E...#",
            "#.....####.........#",
            "#.....####.........#",
            "#.......E..........#",
            "#..................#",
            "#..E...............#",
            "#.......##.##......#",
            "#.......##.##...E..#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    2: {
        "type": "combat",
        "boss": None,
        "next": 3,
        "victory": None,
        "speed_multiplier": 1.2,
        "hazards": {"puddles": True},
        "monster_level": 4,
        "weather": "sandstorm",
        "tileset": "sand",
        "floor": "sand",
        "bg": (160, 130, 60),
        "title": "Ruinas do Deserto",
        "description": "Ruinas soterradas por uma tempestade de areia constante, com poças acidas deixadas por goblins.",
        "enemies": ["skeleton", "goblin", "goblin"],
        "layout": [
            "####################",
            "#..................#",
            "#.E....###.......E.#",
            "#......#.#.........#",
            "#......###...E.....#",
            "#..................#",
            "#...E..........E...#",
            "##.##..........##.##",
            "#..................#",
            "#....E.....E.......#",
            "#.....####.........#",
            "#.....#..#...E.....#",
            "#..E..####.........#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    3: {
        "type": "combat",
        "boss": None,
        "next": 4,
        "victory": None,
        "speed_multiplier": 1.2,
        "hazards": {"puddles": True},
        "monster_level": 8,
        # No weather key - an indoor dungeon has no sky; snow made no sense
        # here (Stage D5 biome-fit pass). get("weather") returns None,
        # which WeatherSystem already treats as a no-op.
        "tileset": "floor",
        "floor": "floor",
        "bg": (30, 20, 50),
        "title": "Masmorra das Sombras",
        "description": "Corredores de pedra sem luz do sol, onde um Cavaleiro Negro comanda uma horda de esqueletos e goblins.",
        "enemies": ["dark_knight", "skeleton", "goblin", "goblin", "goblin"],
        "layout": [
            "####################",
            "#..................#",
            "#.E..####....####.E#",
            "#....#..#....#..#..#",
            "#....####....####..#",
            "#.E................#",
            "#......####........#",
            "#......#..#..E.....#",
            "#......####........#",
            "#.E............E...#",
            "#....####...####...#",
            "#....#..#...#..#...#",
            "#..E.####...####.E.#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    4: {  # Boss level - Act 1 finale
        "type": "boss",
        "boss": "orc_warlord",
        "next": 5,
        "victory": None,
        "weather": "storm",
        "tileset": "war_camp",
        "floor": "war_camp",
        "bg": (35, 20, 10),
        "title": "Acampamento de Guerra",
        "description": "O acampamento fortificado do Senhor da Guerra Orc, sob uma tempestade constante - final do Ato 1.",
        "enemies": [],
        # Palisade posts ringing the battleground (Stage B4b) - perimeter
        # obstacles only, center kept open for the orc's charge attack.
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#..#............#..#",
            "#..................#",
            "#..................#",
            "#.#..............#.#",
            "#..................#",
            "#..................#",
            "#..#............#..#",
            "#..................#",
            "#.#..............#.#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (9, 12),
        "exit": None,
    },
    5: {
        "type": "combat",
        "boss": None,
        "next": 6,
        "victory": None,
        "monster_level": 12,
        "weather": "rain",
        "tileset": "swamp",
        "floor": "swamp",
        "bg": (25, 40, 25),
        "title": "Pantano Sombrio",
        "description": "Um pantano encharcado pela chuva, lar de aranhas venenosas, serpentes e treants guardioes que se escondem entre as arvores retorcidas.",
        "enemies": ["aranha", "serpente", "treant"],
        # Stage individualization pass: 2 extra root-cluster obstacles
        # (row6/row9) - a small nod to "treants lurking among the trees"
        # without touching the water hazards or existing E spawn rows.
        "layout": [
            "####################",
            "#..................#",
            "#..WW....##....WW..#",
            "#..WW....##....WW..#",
            "#........##........#",
            "#.E..............E.#",
            "#....#........#....#",
            "#....WW......WW....#",
            "#....WW......WW....#",
            "#........#.........#",
            "#.E....##....##..E.#",
            "#.......##..##.....#",
            "#..................#",
            "#..E....E......E...#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    6: {
        "type": "combat",
        "boss": None,
        "next": 7,
        "victory": None,
        "monster_level": 16,
        "weather": "storm",
        "tileset": "cursed_floor",
        "floor": "cursed_floor",
        "bg": (25, 15, 40),
        "title": "Torre Amaldicoada",
        "description": "Uma torre castigada por tempestades, guardada por um cavaleiro da morte, um troll amaldicoado e esqueletos remanescentes.",
        "enemies": ["skeleton", "troll", "death_knight"],
        "layout": [
            "####################",
            "#..................#",
            "#..####......####..#",
            "#..#..#..E...#..#..#",
            "#..#..#......#..#..#",
            "#..####......####..#",
            "#..................#",
            "#........E.........#",
            "#..................#",
            "#..####......####..#",
            "#..#..#......#..#..#",
            "#..#..#..E...#..#..#",
            "#..####......####..#",
            "#.E................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    7: {
        "type": "combat",
        "boss": None,
        "next": 8,
        "victory": None,
        "monster_level": 20,
        "weather": "gloom",
        "tileset": "crypt_floor",
        "floor": "crypt_floor",
        "bg": (20, 20, 30),
        "title": "Cripta Perdida",
        "description": "Uma cripta esquecida na escuridao, infestada de zumbis, vermes cadavericos e pequenos imps que se alimentam dos restos.",
        "enemies": ["zumbi", "verme", "imp"],
        "layout": [
            "####################",
            "#..................#",
            "#.E..##.....##....E#",
            "#....##.....##.....#",
            "#..................#",
            "#......######......#",
            "#......#....#......#",
            "#..E....#..#....E..#",
            "#......#....#......#",
            "#......######......#",
            "#..................#",
            "#....##.....##.....#",
            "#.E..##.....##....E#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    8: {  # Boss level - Act 2 finale
        "type": "boss",
        "boss": "necromancer",
        "next": 9,
        "victory": None,
        "weather": "gloom",
        "tileset": "crypt_floor",
        "floor": "crypt_floor",
        "bg": (10, 30, 20),
        "title": "Cripta do Necromante",
        "description": "O santuario sombrio do Necromante, que invoca mortos-vivos sob uma escuridao permanente - final do Ato 2.",
        "enemies": [],
        # Tomb-column colonnade (Stage B4b) - two rows of isolated pillars
        # flanking an open central hall, open enough for the summon/curse
        # patterns' sightlines.
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (9, 12),
        "exit": None,
    },
    9: {
        "type": "combat",
        "boss": None,
        "next": 10,
        "victory": None,
        "monster_level": 24,
        "weather": "snow",
        "tileset": "ritual_floor",
        "floor": "ritual_floor",
        "bg": (30, 30, 45),
        "title": "Salao dos Ecos",
        "description": "Um salao gelado onde a neve cai sem parar, palco de um ritual profano guardado por um corcel sombrio, um acolito e uma feiticeira.",
        "enemies": ["dark_horse", "acolito", "feiticeira"],
        "layout": [
            "####################",
            "#..................#",
            "#....E........E....#",
            "#..................#",
            "#.####.......####..#",
            "#.#..#........#..#.#",
            "#.#..#..E..E..#..#.#",
            "#.#..#........#..#.#",
            "#.####.......####..#",
            "#..................#",
            "#....E........E....#",
            "#..................#",
            "#..................#",
            "#.E...........E....#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    10: {
        "type": "combat",
        "boss": None,
        "next": 11,
        "victory": None,
        "monster_level": 28,
        "weather": "ashfall",
        "tileset": "lava",
        "floor": "lava",
        "bg": (90, 35, 15),
        "title": "Abismo de Cinzas",
        "description": "Um abismo vulcanico sob chuva de cinzas, onde caes de fogo, ogros brutais e elementais de pedra guardam as fendas incandescentes.",
        "enemies": ["fire_hound", "ogro", "elemental_pedra"],
        "layout": [
            "####################",
            "#..................#",
            "#..E....E....E....E#",
            "#..................#",
            "###.############.###",
            "#..................#",
            "#..E....E....E....E#",
            "#..................#",
            "###.############.###",
            "#..................#",
            "#..E....E....E....E#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    11: {
        "type": "combat",
        "boss": None,
        "next": 12,
        "victory": None,
        "monster_level": 32,
        "weather": "fog",
        "tileset": "boss_floor",
        "floor": "boss_floor",
        "bg": (20, 10, 25),
        "title": "Corredor Final",
        "description": "O ultimo corredor antes do trono, guardado por uma quimera, lyzardmen ageis e esqueletos negros sob uma neblina densa.",
        "enemies": ["chimera", "lyzardman", "dark_skeleton"],
        "layout": [
            "####################",
            "#..................#",
            "#.E................#",
            "#..................#",
            "#....##########....#",
            "#....#........#....#",
            "#.E..#.E..E..E#..E.#",
            "#....#........#....#",
            "#....##########....#",
            "#..................#",
            "#................E.#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (2, 2),
        "exit": (17, 13),
    },
    12: {  # Boss level - Act 3 finale
        "type": "boss",
        "boss": "shadow_king",
        "next": None,
        "victory": "victory",
        "weather": "storm",
        "tileset": "throne_floor",
        "floor": "throne_floor",
        "bg": (15, 5, 30),
        "title": "Trono das Trevas",
        "description": "O trono do Rei das Sombras, envolto em tempestade eterna - o confronto final do Ato 3.",
        "enemies": [],
        # Throne dais backdrop + a sparse pillared hall (Stage B4b) - kept
        # more open than the other 2 arenas since Shadow King's whole
        # pattern pool is ranged and wants long sightlines.
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#...###......###...#",
            "#..................#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#..................#",
            "#....#........#....#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (9, 12),
        "exit": None,
    },
    13: {  # Secret Hell level
        "type": "boss",
        "boss": "cacodemon",
        "next": None,
        "victory": "secret_victory",
        "weather": "ashfall",
        # Stage B4b rework: the old "lava" tileset read as bright, "screaming"
        # magma - swapped for a darker obsidian-abyss look that still fits
        # an other-worldly demon arena without the loud orange floor.
        "tileset": "abyss_floor",
        "floor": "abyss_floor",
        "bg": (25, 10, 18),
        "title": "Fase Secreta: INFERNO",
        "description": "Um santuario de obsidiana escondido num abismo entre mundos, guardado por um Cacodemonio.",
        "enemies": [],
        # Scattered, asymmetric broken-pillar rubble - chaotic "other world"
        # feel instead of a tidy arena, single isolated tiles only so
        # CacodemonBoss's direct player-chase never gets trapped.
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#..................#",
            "#.....#............#",
            "#..............#...#",
            "#..................#",
            "#........#.........#",
            "#..................#",
            "#............#.....#",
            "#....#.............#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (9, 12),
        "exit": None,
    },
}


class Level:
    def __init__(self, level_num, extra_speed_mult=1.0, ml_bonus=0, audio_mgr=None, network_follower=False):
        self.level_num = level_num
        # Stage H7: forwarded to every spawned Enemy so mob attacks can play
        # their own sound (see game/audio.py's attack_{etype} sounds).
        self.audio = audio_mgr
        self.data = LEVEL_MAPS[level_num]
        # Stage K14: a per-instance mutable copy - LEVEL_MAPS' "layout" list
        # is a module-level constant shared by every Level built for this
        # level_num (every difficulty tier, every replay), so breaking a
        # block or revealing the key tile in place on the original list
        # would corrupt it for every future playthrough in this process.
        self.layout = [list(row) for row in self.data["layout"]]
        self.rows = len(self.layout)
        self.cols = len(self.layout[0])
        self.width = self.cols * TILE
        self.height = self.rows * TILE

        self.walls = []
        self.enemies = []
        self.exit_rect = None
        self.exit_open = False

        # Stage L6 (docs/coop-implementation-plan.md): id estável por
        # inimigo, sobrevive a self.enemies encolher/reordenar quando um
        # morre (índice na lista não é estável o bastante pra um broadcast
        # de rede identificar "qual inimigo é esse"). network_follower vira
        # True só num guest conectado (nunca no host nem em single-player) -
        # precisa vir por parâmetro do construtor, não setado depois: _build()
        # (mais abaixo, ainda dentro deste __init__) já cria os primeiros
        # Enemy da fase, então setar isso só depois de Level(...) retornar
        # deixaria esses primeiros com o valor errado.
        self._next_net_id = 0
        self.network_follower = network_follower
        # Stage L8 (docs/coop-implementation-plan.md): quantos jogadores
        # estão na room agora - setado por GameplayState.update() a cada
        # frame (ver a chamada de self.level.update(...) abaixo), 1 fora
        # de coop. credit_kill() usa isso pra dividir XP igualmente
        # (decisão #2: split igual, não proporcional a dano causado).
        self._room_size = 1

        self.player_start_tile = self.data["player_start"]
        self._used_enemy_tiles = set()
        self._enemy_spawn_min_dist = 3
        self.puddles = []
        self.gold_drops = []
        # Stage K14: pending_drops entries are (kind, x, y) for "heart"/
        # "mana"/"potion" - GameplayState (which already owns the Pickup
        # class and inventory) drains this each frame and turns each one
        # into the real thing; gold stays self-contained here since
        # GoldDrop doesn't need anything states.py owns.
        self.pending_drops = []
        # Destructible interior walls (K14): {(col,row): hits}, 2 hits to
        # break; border walls (the level's outer rectangle) are never in
        # here - see _is_border(). Presence in this dict alone means
        # "cracked" (1 hit) since a 2nd hit removes the entry immediately.
        self._block_hits = {}
        self._key_tile = None
        self._key_found = False
        self.dig_particles = []
        # Stage K23: every floor (col,row) the player has ever swung the
        # pickaxe at, regardless of whether it turned out to be the key -
        # drawn every frame in draw() as a persistent "already checked here"
        # patch. NOT a reveal: the key tile looks exactly like any other
        # floor tile (dug or not) before it's actually dug - only presence
        # in this set (which only grows through a real swing) marks it,
        # same reasoning that removed the old always-on key-tile marker
        # below (see draw()'s comment).
        self._dug_tiles = set()
        # Gradual post-clear respawn (K14) - captured once in _build() from
        # the original 'E' spawns, so a respawned mob matches this level's
        # own roster/difficulty instead of a hardcoded fallback.
        self._original_enemy_specs = []
        self._respawns_remaining = 0
        self._respawn_timer = 0.0
        self._respawn_interval = 6.0
        self._speed_mul = 1.0
        self._monster_level = 1

        # Difficulty-tier hooks (Stage B5) - Level itself stays unaware
        # difficulty exists, same separation already used for Paragon/
        # weather; GameplayState just hands in two numbers.
        self.extra_speed_mult = extra_speed_mult
        self.ml_bonus = ml_bonus

        self._tile_cache = {}
        self._build()

    def _get_tile(self, ttype):
        if ttype not in self._tile_cache:
            self._tile_cache[ttype] = create_tile(ttype)
        return self._tile_cache[ttype]

    def _is_safe_enemy_tile(self, col, row):
        start_col, start_row = self.player_start_tile
        dx = col - start_col
        dy = row - start_row
        if dx * dx + dy * dy < self._enemy_spawn_min_dist * self._enemy_spawn_min_dist:
            return False
        if self.layout[row][col] == '#':
            return False
        return True

    def _find_enemy_spawn(self, orig_col, orig_row):
        if self._is_safe_enemy_tile(orig_col, orig_row) and (orig_col, orig_row) not in self._used_enemy_tiles:
            return orig_col, orig_row

        best = None
        best_score = None
        for row in range(self.rows):
            for col in range(self.cols):
                if (col, row) in self._used_enemy_tiles:
                    continue
                if not self._is_safe_enemy_tile(col, row):
                    continue
                score = abs(col - orig_col) + abs(row - orig_row)
                if best is None or score < best_score:
                    best = (col, row)
                    best_score = score
        return best if best is not None else (orig_col, orig_row)

    def _tag_enemy(self, enemy):
        """Stage L6: chamado em todo Enemy(...) recém-criado desta fase,
        nos 3 lugares que constroem um (_build() logo abaixo, o trickle de
        respawn no update(), e a invocação do necromante em
        GameplayState.update())."""
        enemy.net_id = self._next_net_id
        self._next_net_id += 1
        enemy.network_follower = self.network_follower
        return enemy

    def _build(self):
        floor_type = self.data["floor"]
        wall_type  = "wall"
        enemy_types = self.data["enemies"]
        ei = 0

        speed_mul = self.data.get("speed_multiplier", 1.0) * self.extra_speed_mult
        monster_level = self.data.get("monster_level", 1) + self.ml_bonus
        self._speed_mul = speed_mul
        self._monster_level = monster_level

        for row_i, row in enumerate(self.layout):
            for col_i, ch in enumerate(row):
                x = col_i * TILE
                y = row_i * TILE
                if ch == '#':
                    self.walls.append(pygame.Rect(x, y, TILE, TILE))
                elif ch == 'E':
                    etype = enemy_types[ei % len(enemy_types)] if enemy_types else "skeleton"
                    ei += 1
                    spawn_col, spawn_row = self._find_enemy_spawn(col_i, row_i)
                    spawn_x = spawn_col * TILE
                    spawn_y = spawn_row * TILE
                    self.enemies.append(self._tag_enemy(Enemy(spawn_x + 8, spawn_y + 8, etype, speed_multiplier=speed_mul,
                                               ml=monster_level, level_num=self.level_num, audio_mgr=self.audio)))
                    self._used_enemy_tiles.add((spawn_col, spawn_row))
                    # Stage K14: remembered so the post-clear respawn trickle
                    # can bring back the same etype roster at the same spots,
                    # not an arbitrary fallback mob.
                    self._original_enemy_specs.append((etype, spawn_x + 8, spawn_y + 8))

        # Stage K14: one extra full wave, trickled in slowly - see update()'s
        # respawn block. Capped (not infinite) so a player still hunting for
        # the key doesn't face an ever-growing mob count.
        self._respawns_remaining = len(self._original_enemy_specs)
        self._respawn_timer = self._respawn_interval

        if self.data["exit"]:
            ex_col, ex_row = self.data["exit"]
            self.exit_rect = pygame.Rect(ex_col * TILE, ex_row * TILE, TILE, TILE)

        self._pick_key_tile()

    def _is_border(self, col, row):
        """Every LEVEL_MAPS layout's outer rectangle (row/col 0 and the
        last row/col) is a solid '#' wall by convention (confirmed across
        all 13 layouts) - border walls stay indestructible, only interior
        '#' tiles can be cracked/broken by the picareta."""
        return row == 0 or row == self.rows - 1 or col == 0 or col == self.cols - 1

    def _pick_key_tile(self):
        """Stage K14: the hidden key is buried under a floor tile (never
        under a '#' block, per the user's spec), picked far enough from the
        player's own start tile that it can't be dug up trivially on
        arrival. Boss levels (data["type"] != "combat") never get a key -
        they already transition on boss death, no exit_rect/chest at all."""
        if self.data["type"] != "combat":
            return
        start_col, start_row = self.player_start_tile
        exit_tile = self.data["exit"]
        candidates = []
        for row in range(1, self.rows - 1):
            for col in range(1, self.cols - 1):
                if self.layout[row][col] != '.':
                    continue
                if (col, row) in self._used_enemy_tiles:
                    continue
                if exit_tile and (col, row) == tuple(exit_tile):
                    continue
                dx, dy = col - start_col, row - start_row
                if dx * dx + dy * dy < 25:
                    continue
                candidates.append((col, row))
        if candidates:
            self._key_tile = random.choice(candidates)

    def get_player_start(self):
        col, row = self.data["player_start"]
        return (col * TILE + 8, row * TILE + 8)

    def update(self, dt, player, audio_mgr=None, room_size=1):
        self._room_size = room_size
        # Only enable puddles behavior on levels that declare the hazard
        puddles_arg = self.puddles if self.data.get("hazards", {}).get("puddles") else None
        for enemy in self.enemies:
            enemy.update(dt, player, self.walls, self.width, self.height, puddles_arg)
        # Playtest freeze bug: dead enemies used to stay in this list
        # forever (only ever filtered OUT for counting via the `living =`
        # line below, never actually removed) - with Stage K14's post-
        # clear respawn trickle also appending new ones on top, a long
        # session in one level accumulates dead objects that still get
        # iterated every frame for no reason. Kept alive one extra frame
        # after death exactly as long as it still has floating damage
        # numbers on screen (the killing blow's number needs to finish
        # drifting/fading), pruned right after.
        self.enemies = [e for e in self.enemies if e.alive or e.floating_numbers]

        # Update puddles and damage player on contact - each puddle has its
        # own lifetime now (Puddle.LIFETIME, Stage K23), so this also prunes
        # the expired ones instead of them persisting forever.
        for p in self.puddles:
            p.update(dt)
            if p.rect.colliderect(player.rect):
                if p.can_damage():
                    # Same ~1/6-of-old-max_hp chip as before, rescaled to the
                    # bigger hp range from game/stats.py (Stage A3). Typed
                    # magic, not physical - it's the goblin's poison spell
                    # effect landing on the floor, not a contact hit.
                    player.take_damage(round(player.max_hp / 6), dtype="magic")
                    if random.random() < 0.20:
                        player.try_apply_debuff("poison")
        self.puddles = [p for p in self.puddles if p.alive]

        # Update gold drops - expire the unclaimed ones, collect the rest
        for g in self.gold_drops:
            g.update(dt)
            if g.alive and g.rect.colliderect(player.rect):
                player.credit_gold(g.amount)
                g.alive = False
                if audio_mgr:
                    audio_mgr.play("pickup")
        self.gold_drops = [g for g in self.gold_drops if g.alive]

        # Stage K14: the exit no longer opens on a kill-count - it opens
        # only when the hidden key is dug up (try_break_tile below sets
        # exit_open directly). Once every original enemy is dead, trickle
        # a capped extra wave back in instead (gives the player something
        # to fight while still searching), one every _respawn_interval.
        # Stage L6: gerar uma nova onda é uma decisão de simulação (rolagem
        # aleatória de etype) - só o host faz isso. Um guest só vê a onda
        # aparecer quando o próprio broadcast do host incluir os novos ids.
        living = [e for e in self.enemies if e.alive]
        if not self.network_follower and not living and self.data["type"] == "combat" and self._respawns_remaining > 0:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self._respawn_timer = self._respawn_interval
                self._respawns_remaining -= 1
                etype, sx, sy = random.choice(self._original_enemy_specs)
                self.enemies.append(self._tag_enemy(Enemy(sx, sy, etype, speed_multiplier=self._speed_mul,
                                           ml=self._monster_level, level_num=self.level_num, audio_mgr=self.audio)))

        for particle in self.dig_particles:
            particle.update(dt)
        self.dig_particles = [p for p in self.dig_particles if p.life > 0]

        # Check player attack vs enemies - Stage L6: só o host resolve isso.
        # Um guest atacando um Enemy follower não pode chamar take_damage()
        # local (o HP real mora no host; aplicar dano aqui divergiria do
        # próximo snapshot e "voltaria" visualmente). Dano de guest contra
        # inimigo do host fica pra um incremento futuro (repassar o golpe
        # pro host resolver) - não coberto por este L6.
        if not self.network_follower and player.attacking:
            atk_rect = player.get_attack_rect()
            for enemy in self.enemies:
                if not (enemy.alive and atk_rect.colliderect(enemy.rect)):
                    continue
                if enemy.affix == "warded" and random.random() < 0.25:
                    continue  # blocked - Paragon affix
                dmg, is_crit = player.roll_physical()
                enemy.take_damage(dmg, dtype="physical", crit=is_crit,
                                   knockback_from=(player.x + player.width / 2, player.y + player.height / 2))
                if not enemy.alive:
                    self.credit_kill(player, enemy)

    def credit_kill(self, player, enemy):
        """XP/gold/kill-tracking for a just-died regular enemy - shared by
        the melee path above and game/states.py's Fireball collision, so a
        kill is rewarded identically no matter which weapon landed it.

        Stage L8 (docs/coop-implementation-plan.md): só XP é compartilhado
        em coop, não o ouro - o ouro de inimigo comum já é um GoldDrop
        físico (pickup andando por cima), o mesmo "quem chega primeiro
        pega" que já vale em single-player; duplicar/sincronizar esse
        pickup pra cada cliente é um problema de sync bem maior, fora do
        escopo desta fase. XP não tem esse problema (crédito instantâneo
        já hoje), então é o que a decisão #2 (split igual, não
        proporcional a dano) realmente cobre aqui - quem matou E o resto
        da room recebem 1/N do XP cada, não o total cada um."""
        if enemy.is_paragon:
            reward_mult = PARAGON_REWARD_MULT
        elif enemy.is_champion:
            reward_mult = CHAMPION_REWARD_MULT
        else:
            reward_mult = 1
        self._credit_xp_shared(player, xp_for_kill(BASE_XP[enemy.etype], enemy.ml, player.level) * reward_mult)
        # Stage K14: independent rolls instead of unconditional gold - the
        # user's explicit complaint was "hoje e 100% ouro"; gold stays the
        # common case (medio/alto chance) while heart/mana/potion are rarer
        # bonus rolls, all independent so more than one can land on the
        # same kill.
        cx, cy = enemy.x + enemy.width / 2, enemy.y + enemy.height / 2
        if random.random() < 0.75:
            self.gold_drops.append(GoldDrop(
                cx, cy, gold_for_kill(GOLD_DROPS[enemy.etype], enemy.ml) * reward_mult
            ))
        drop_roll = random.random()
        if drop_roll < 0.10:
            self.pending_drops.append(("heart", cx, cy))
        elif drop_roll < 0.16:
            self.pending_drops.append(("mana", cx, cy))
        if random.random() < 0.06:
            self.pending_drops.append(("potion", cx, cy))
        player.kills[enemy.etype] = player.kills.get(enemy.etype, 0) + 1
        if enemy.affix == "volatile":
            ex, ey = enemy.x + enemy.width / 2, enemy.y + enemy.height / 2
            px, py = player.x + player.width / 2, player.y + player.height / 2
            if math.hypot(px - ex, py - ey) <= 70:
                player.take_damage(15, dtype="magic", knockback_from=(ex, ey))

    def _credit_xp_shared(self, player, amount):
        """Stage L8: fora de coop (self._room_size == 1, o padrão) aplica
        o total normalmente - comportamento de sempre, nenhum call site
        precisou mudar. Conectado, divide pelo número de jogadores na room
        (quem matou incluso, decisão #2) - credita a própria fração aqui e
        avisa a room pra cada guest aplicar a fração dele no próprio
        Player local (cada cliente só pode mexer no seu próprio XP, não
        existe um "Player compartilhado")."""
        if self._room_size > 1 and net_coop.is_connected():
            share = amount / self._room_size
            player.gain_xp(share)
            net_coop.send({"type": "credit_xp", "amount": share})
        else:
            player.gain_xp(amount)

    def try_break_tile(self, col, row, player, audio_mgr=None):
        """Stage K14: the picareta's actual effect on whatever tile is
        directly in front of the player (GameplayState computes col/row
        from player.aim_dx/aim_dy, mirroring get_attack_rect()'s split -
        Player only owns the cooldown/state, Level owns what's in the
        world). Returns True if the swing landed on anything at all - a
        wall, the secret key tile, or (Stage K22) ordinary floor, which
        gets a small dirt-puff/sound of its own now so digging never goes
        completely silent. Only a swing aimed out of bounds or at an
        indestructible border wall (see _is_border) whiffs entirely."""
        if self.data["type"] != "combat":
            return False
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            return False
        ch = self.layout[row][col]
        if ch == '#':
            if self._is_border(col, row):
                return False
            hits = self._block_hits.get((col, row), 0) + 1
            if hits >= 2:
                self._break_block(col, row)
            else:
                self._block_hits[(col, row)] = hits
            for _ in range(6):
                self.dig_particles.append(Particle(col * TILE + TILE / 2, row * TILE + TILE / 2, (150, 130, 110)))
            if audio_mgr:
                audio_mgr.play("attack")
            return True
        elif ch == '.' and not self._key_found and (col, row) == self._key_tile:
            self._key_found = True
            self.exit_open = True
            self._dug_tiles.add((col, row))
            for _ in range(10):
                self.dig_particles.append(Particle(col * TILE + TILE / 2, row * TILE + TILE / 2, ACCENT_GOLD))
            if audio_mgr:
                audio_mgr.play("pickup")
            return True
        elif ch == '.':
            # Stage K22: an ordinary floor tile used to be a total no-op -
            # no particle, no sound, indistinguishable from a whiff into
            # open air out of pickaxe range. That silence read as "the
            # pickaxe doesn't do anything" during normal play, since almost
            # every tile a player digs while hunting for the secret key
            # isn't the one exact key tile. A small dirt puff + the same
            # swing sound as a wall hit confirms every swing landed on
            # *something*, without granting a drop or revealing anything -
            # the key tile above stays the only tile that matters.
            #
            # Stage K23: also joins _dug_tiles - draw() paints a persistent
            # patch on every tile in there (see its comment), so a player
            # can see at a glance which floor tiles they've already tried
            # instead of losing track across a whole level. Deliberately
            # the exact same marker/logic for a miss as for the real key
            # tile above - the two must be visually indistinguishable
            # beforehand, or this would just be a slower way to reveal it.
            self._dug_tiles.add((col, row))
            for _ in range(3):
                self.dig_particles.append(Particle(col * TILE + TILE / 2, row * TILE + TILE / 2, (110, 90, 70)))
            if audio_mgr:
                audio_mgr.play("attack")
            return True
        return False

    def _break_block(self, col, row):
        self.layout[row][col] = '.'
        rect = pygame.Rect(col * TILE, row * TILE, TILE, TILE)
        self.walls = [w for w in self.walls if w.topleft != rect.topleft]
        del self._block_hits[(col, row)]
        self._roll_block_drop(col, row)

    def _roll_block_drop(self, col, row):
        # Stage K14: "pot/coracao/mana, chance baixa/media" per the user's
        # spec - most broken blocks are just rubble, no drop at all.
        x, y = col * TILE + TILE / 2, row * TILE + TILE / 2
        roll = random.random()
        if roll < 0.12:
            self.pending_drops.append(("heart", x, y))
        elif roll < 0.20:
            self.pending_drops.append(("mana", x, y))
        elif roll < 0.24:
            self.pending_drops.append(("potion", x, y))

    def check_exit(self, player):
        if self.exit_open and self.exit_rect:
            return player.rect.colliderect(self.exit_rect)
        return False

    def draw(self, surface, cam_x, cam_y, screen_w, screen_h):
        bg = self.data["bg"]
        surface.fill(bg)

        floor_tile = self._get_tile(self.data["floor"])
        wall_tile  = self._get_tile("wall")

        # Only draw tiles in view
        start_col = max(0, int(cam_x // TILE))
        end_col   = min(self.cols, int((cam_x + screen_w) // TILE) + 2)
        start_row = max(0, int(cam_y // TILE))
        end_row   = min(self.rows, int((cam_y + screen_h) // TILE) + 2)

        for row_i in range(start_row, end_row):
            for col_i in range(start_col, end_col):
                x = col_i * TILE - cam_x
                y = row_i * TILE - cam_y
                ch = self.layout[row_i][col_i]
                if ch == '#':
                    surface.blit(wall_tile, (x, y))
                    # Stage K14: presence in _block_hits means "cracked"
                    # (1 hit landed, not yet broken) - see try_break_tile().
                    if (col_i, row_i) in self._block_hits:
                        surface.blit(create_cracked_wall_overlay(), (x, y))
                else:
                    surface.blit(floor_tile, (x, y))
                    # Stage K23: used to always show on the key's own tile
                    # BEFORE it was ever dug - a permanent "something's off
                    # underfoot" hint that, on reflection, is exactly a
                    # location reveal (a careful player could just look for
                    # the one different-looking floor tile instead of
                    # searching). Now it means the opposite: presence in
                    # _dug_tiles requires an actual pickaxe swing having
                    # already landed here (try_break_tile), so the key tile
                    # looks like every other undug tile until it's the
                    # player's own dig history marking it - same for a real
                    # find as for a miss.
                    if (col_i, row_i) in self._dug_tiles:
                        surface.blit(create_dig_marker(), (x, y))

        if self.data["floor"] == "lava":
            import math, time
            pulse = int(8 + 5 * math.sin(time.time() * 2.5))
            for wave_id in range(start_row, end_row, 2):
                wy = wave_id * TILE - cam_y + pulse
                color = (150, 60, 20) if wave_id % 4 == 0 else (190, 90, 35)
                pygame.draw.line(surface, color, (0, wy), (screen_w, wy), 2)

        # Stage K14: "saida vira bau" - always visible (closed, locked)
        # once the level exists, not summoned from nothing the moment it
        # opens like the old kill-triggered portal was. Opens (sprite swap
        # + a glow) once the hidden key is found.
        if self.exit_rect:
            ex = self.exit_rect.x - cam_x
            ey = self.exit_rect.y - cam_y
            if self.exit_open:
                import math, time
                pulse = int(60 + 40 * math.sin(time.time() * 4))
                glow = pygame.Surface((TILE + 20, TILE + 20), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 215, 80, pulse), (0, 0, TILE + 20, TILE + 20))
                surface.blit(glow, (ex - 10, ey - 10))
            surface.blit(create_chest_sprite(open=self.exit_open), (ex, ey))
            if not self.exit_open:
                f = font(12, bold=True)
                txt = f.render("TRANCADO", True, (200, 180, 140))
                surface.blit(txt, (ex + TILE // 2 - txt.get_width() // 2, ey + TILE + 2))

        for particle in self.dig_particles:
            particle.draw(surface, cam_x, cam_y)

        # Draw puddles/gold first (so enemies/players appear above)
        if hasattr(self, 'puddles'):
            for p in self.puddles:
                p.draw(surface, cam_x, cam_y)

        for g in self.gold_drops:
            g.draw(surface, cam_x, cam_y)

        for enemy in self.enemies:
            enemy.draw(surface, cam_x, cam_y)

    def draw_hud_info(self, surface):
        """Level name and enemy count"""
        f = font(16, bold=True)
        title = f.render(f"Fase {self.level_num}: {self.data['title']}", True, ACCENT_GOLD)
        surface.blit(title, (surface.get_width()//2 - title.get_width()//2, surface.get_height()-30))

        # Top-center, clear of the HP/mana/XP dock (top-left) and the
        # sound/fullscreen/pause buttons (top-right).
        # Stage K7: the "Inimigos: N" kill counter is gone - that top-center
        # spot is now the hotbar's (moved up from _HOTBAR_Y=34 to make room
        # for it here originally; now freed up again).
        # Stage K14: kill count stopped being the win condition entirely -
        # the exit (now a chest) opens only once the hidden key is dug up.
        if self.exit_open:
            # Stage H4: same tofu-box glyph bug as boss.py's ENRAIVECIDO -
            # pygame's default font has no U+2B06 glyph.
            txt = f.render("Chave encontrada! Va ate o bau!", True, (100, 255, 180))
            surface.blit(txt, (surface.get_width()//2 - txt.get_width()//2, 12))
        elif self.data["type"] == "combat" and self._key_tile is not None:
            txt = f.render("Cave com a picareta (E) em busca da chave", True, (200, 180, 140))
            surface.blit(txt, (surface.get_width()//2 - txt.get_width()//2, 12))
