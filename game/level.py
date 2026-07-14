import pygame
import random
import math
from game.assets import create_tile
from game.enemy import Enemy, BASE_XP, GOLD_DROPS, GoldDrop
from game.stats import xp_for_kill, gold_for_kill
from game.affixes import PARAGON_REWARD_MULT, CHAMPION_REWARD_MULT
from game.theme import font, ACCENT_GOLD

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
    def __init__(self, level_num, extra_speed_mult=1.0, ml_bonus=0, audio_mgr=None):
        self.level_num = level_num
        # Stage H7: forwarded to every spawned Enemy so mob attacks can play
        # their own sound (see game/audio.py's attack_{etype} sounds).
        self.audio = audio_mgr
        self.data = LEVEL_MAPS[level_num]
        self.layout = self.data["layout"]
        self.rows = len(self.layout)
        self.cols = len(self.layout[0])
        self.width = self.cols * TILE
        self.height = self.rows * TILE

        self.walls = []
        self.enemies = []
        self.exit_rect = None
        self.exit_open = False

        self.player_start_tile = self.data["player_start"]
        self._used_enemy_tiles = set()
        self._enemy_spawn_min_dist = 3
        self.puddles = []
        self.gold_drops = []

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

    def _build(self):
        floor_type = self.data["floor"]
        wall_type  = "wall"
        enemy_types = self.data["enemies"]
        ei = 0

        speed_mul = self.data.get("speed_multiplier", 1.0) * self.extra_speed_mult
        monster_level = self.data.get("monster_level", 1) + self.ml_bonus

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
                    self.enemies.append(Enemy(spawn_x + 8, spawn_y + 8, etype, speed_multiplier=speed_mul,
                                               ml=monster_level, level_num=self.level_num, audio_mgr=self.audio))
                    self._used_enemy_tiles.add((spawn_col, spawn_row))

        if self.data["exit"]:
            ex_col, ex_row = self.data["exit"]
            self.exit_rect = pygame.Rect(ex_col * TILE, ex_row * TILE, TILE, TILE)

    def get_player_start(self):
        col, row = self.data["player_start"]
        return (col * TILE + 8, row * TILE + 8)

    def update(self, dt, player, audio_mgr=None):
        # Only enable puddles behavior on levels that declare the hazard
        puddles_arg = self.puddles if self.data.get("hazards", {}).get("puddles") else None
        for enemy in self.enemies:
            enemy.update(dt, player, self.walls, self.width, self.height, puddles_arg)

        # Update puddles and damage player on contact (puddles persist)
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

        # Update gold drops - expire the unclaimed ones, collect the rest
        for g in self.gold_drops:
            g.update(dt)
            if g.alive and g.rect.colliderect(player.rect):
                player.gold += g.amount
                g.alive = False
                if audio_mgr:
                    audio_mgr.play("pickup")
        self.gold_drops = [g for g in self.gold_drops if g.alive]

        # Open exit when all enemies are dead
        living = [e for e in self.enemies if e.alive]
        if not living and self.exit_rect and self.data["type"] == "combat":
            self.exit_open = True

        # Check player attack vs enemies
        if player.attacking:
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
        kill is rewarded identically no matter which weapon landed it."""
        if enemy.is_paragon:
            reward_mult = PARAGON_REWARD_MULT
        elif enemy.is_champion:
            reward_mult = CHAMPION_REWARD_MULT
        else:
            reward_mult = 1
        player.gain_xp(xp_for_kill(BASE_XP[enemy.etype], enemy.ml, player.level) * reward_mult)
        self.gold_drops.append(GoldDrop(
            enemy.x + enemy.width / 2, enemy.y + enemy.height / 2,
            gold_for_kill(GOLD_DROPS[enemy.etype], enemy.ml) * reward_mult
        ))
        player.kills[enemy.etype] = player.kills.get(enemy.etype, 0) + 1
        if enemy.affix == "volatile":
            ex, ey = enemy.x + enemy.width / 2, enemy.y + enemy.height / 2
            px, py = player.x + player.width / 2, player.y + player.height / 2
            if math.hypot(px - ex, py - ey) <= 70:
                player.take_damage(15, dtype="magic", knockback_from=(ex, ey))

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
                else:
                    surface.blit(floor_tile, (x, y))

        if self.data["floor"] == "lava":
            import math, time
            pulse = int(8 + 5 * math.sin(time.time() * 2.5))
            for wave_id in range(start_row, end_row, 2):
                wy = wave_id * TILE - cam_y + pulse
                color = (150, 60, 20) if wave_id % 4 == 0 else (190, 90, 35)
                pygame.draw.line(surface, color, (0, wy), (screen_w, wy), 2)

        # Draw exit portal
        if self.exit_rect and self.exit_open:
            import math, time
            ex = self.exit_rect.x - cam_x
            ey = self.exit_rect.y - cam_y
            t = time.time()
            pulse = int(30 + 20 * math.sin(t * 4))
            portal_surf = pygame.Surface((TILE + 20, TILE + 20), pygame.SRCALPHA)
            pygame.draw.ellipse(portal_surf, (0, 100, 255, 150), (2, 2, TILE + 16, TILE + 16))
            pygame.draw.ellipse(portal_surf, (100, 180, 255, 200), (6, 6, TILE + 8, TILE + 8), 4)
            surface.blit(portal_surf, (ex - 10, ey - 10))
            f = font(14, bold=True)
            txt = f.render("SAIDA", True, (100, 180, 255))
            surface.blit(txt, (ex + 6, ey + 10))

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
        # for it here originally; now freed up again). Stage K14's dig-for-
        # a-key exit will make "kill count" not even the win condition
        # anymore, so this wasn't just cosmetic to drop.
        if self.exit_open:
            # Stage H4: same tofu-box glyph bug as boss.py's ENRAIVECIDO -
            # pygame's default font has no U+2B06 glyph.
            txt = f.render("Encontre a Saida!", True, (100, 255, 180))
            surface.blit(txt, (surface.get_width()//2 - txt.get_width()//2, 12))
