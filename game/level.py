import pygame
import random
from game.assets import create_tile
from game.enemy import Enemy, BASE_XP, GOLD_DROPS, GoldDrop
from game.stats import xp_for_kill, gold_for_kill
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
        "weather": "rain",
        "tileset": "sand",
        "floor": "sand",
        "bg": (160, 130, 60),
        "title": "Ruinas do Deserto",
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
        "weather": "snow",
        "tileset": "floor",
        "floor": "floor",
        "bg": (30, 20, 50),
        "title": "Masmorra das Sombras",
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
    4: {  # Boss level
        "type": "boss",
        "boss": "shadow_king",
        "next": None,
        "victory": "victory",
        "heart_spawns": True,
        "weather": "storm",
        "tileset": "boss_floor",
        "floor": "boss_floor",
        "bg": (15, 5, 30),
        "title": "Trono das Trevas",
        "enemies": [],
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "####################",
        ],
        "player_start": (9, 12),
        "exit": None,
    },
    5: {  # Secret Hell level
        "type": "boss",
        "boss": "cacodemon",
        "next": None,
        "victory": "secret_victory",
        "tileset": "lava",
        "floor": "lava",
        "bg": (120, 40, 10),
        "title": "Fase Secreta: INFERNO",
        "enemies": [],
        "layout": [
            "####################",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
            "#..................#",
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
    def __init__(self, level_num):
        self.level_num = level_num
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

        speed_mul = self.data.get("speed_multiplier", 1.0)
        monster_level = self.data.get("monster_level", 1)

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
                    self.enemies.append(Enemy(spawn_x + 8, spawn_y + 8, etype, speed_multiplier=speed_mul, ml=monster_level))
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
                    # bigger hp range from game/stats.py (Stage A3).
                    player.take_damage(round(player.max_hp / 6))
                    if random.random() < 0.20:
                        player.status.apply("poison")

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
                if enemy.alive and atk_rect.colliderect(enemy.rect):
                    enemy.take_damage(player.attack_damage)
                    if not enemy.alive:
                        player.gain_xp(xp_for_kill(BASE_XP[enemy.etype], enemy.ml, player.level))
                        self.gold_drops.append(GoldDrop(
                            enemy.x + enemy.width / 2, enemy.y + enemy.height / 2,
                            gold_for_kill(GOLD_DROPS[enemy.etype], enemy.ml)
                        ))
                        player.kills[enemy.etype] = player.kills.get(enemy.etype, 0) + 1

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
        living = [e for e in self.enemies if e.alive]
        if living and self.data["type"] == "combat":
            txt = f.render(f"Inimigos: {len(living)}", True, (255,100,100))
            surface.blit(txt, (surface.get_width()//2 - txt.get_width()//2, 12))
        elif self.exit_open:
            txt = f.render("⬆ Encontre a Saida!", True, (100, 255, 180))
            surface.blit(txt, (surface.get_width()//2 - txt.get_width()//2, 12))
