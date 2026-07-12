import pygame
from game.theme import (
    GREEN, DARK_GREEN, BROWN, DARK_BROWN, SAND, STONE, DARK_STONE, GOLD,
    RED, DARK_RED, BLUE, CYAN, PURPLE, DARK_PURPLE, WHITE, BLACK, ORANGE,
    PINK, LIGHT_BLUE, GRAY,
)

def make_surface(w, h, color):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill(color)
    return s

def draw_pixel_art(surface, pixels, scale=1):
    """pixels: list of (x, y, color) tuples"""
    for (x, y, color) in pixels:
        pygame.draw.rect(surface, color, (x*scale, y*scale, scale, scale))


def create_player_sprite(direction="down", attacking=False):
    SC = 3
    s = pygame.Surface((16*SC, 16*SC), pygame.SRCALPHA)
    # Body (tunic - green)
    body = [
        (5,6),(6,6),(7,6),(8,6),(9,6),(10,6),
        (4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7),(11,7),
        (4,8),(5,8),(6,8),(7,8),(8,8),(9,8),(10,8),(11,8),
        (4,9),(5,9),(6,9),(7,9),(8,9),(9,9),(10,9),(11,9),
        (5,10),(6,10),(7,10),(8,10),(9,10),(10,10),
    ]
    for (x,y) in body:
        pygame.draw.rect(s, (34,160,34), (x*SC,y*SC,SC,SC))
    # Head
    head = [(5,2),(6,2),(7,2),(8,2),(9,2),(10,2),
            (4,3),(5,3),(6,3),(7,3),(8,3),(9,3),(10,3),(11,3),
            (4,4),(5,4),(6,4),(7,4),(8,4),(9,4),(10,4),(11,4),
            (4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5),(11,5)]
    for (x,y) in head:
        pygame.draw.rect(s, (220,170,110), (x*SC,y*SC,SC,SC))
    # Hat
    hat = [(5,0),(6,0),(7,0),(8,0),(9,0),(10,0),
           (4,1),(5,1),(6,1),(7,1),(8,1),(9,1),(10,1),(11,1),
           (3,2),(12,2)]
    for (x,y) in hat:
        pygame.draw.rect(s, (34,120,34), (x*SC,y*SC,SC,SC))
    # Eyes
    if direction == "down":
        pygame.draw.rect(s, BLACK, (6*SC,4*SC,SC,SC))
        pygame.draw.rect(s, BLACK, (9*SC,4*SC,SC,SC))
    elif direction == "up":
        pass  # back of head
    else:
        pygame.draw.rect(s, BLACK, (8*SC,4*SC,SC,SC))
    # Legs
    legs = [(5,11),(6,11),(9,11),(10,11),
            (5,12),(6,12),(9,12),(10,12),
            (5,13),(6,13),(9,13),(10,13)]
    for (x,y) in legs:
        pygame.draw.rect(s, (80,40,10), (x*SC,y*SC,SC,SC))
    # Sword (attacking)
    if attacking:
        sword = [(12,5),(13,4),(14,3),(15,2)]
        for (x,y) in sword:
            pygame.draw.rect(s, (200,200,220), (x*SC,y*SC,SC,SC))
        pygame.draw.rect(s, GOLD, (11*SC,6*SC,SC,SC))
    else:
        # Shield on side
        pygame.draw.rect(s, BLUE, (3*SC,7*SC,SC*2,SC*3))
        pygame.draw.rect(s, GOLD, (3*SC,8*SC,SC*2,SC))
    return s


# Per-etype palette + which of the 3 hand-drawn rigs to paint it with
# (Stage D6) - same "one dict of per-id data, N painter functions" idea as
# BOSS_SPRITES/_BOSS_RIG_PAINTERS below, applied to common enemies. A new
# mob's look is one entry here, never new drawing code.
ENEMY_SPRITES = {
    "skeleton":     {"rig": "skeleton",    "body": (230, 230, 230), "eye": (200, 0, 0)},
    "goblin":       {"rig": "goblin",      "body": (80, 180, 80),   "eye": (255, 200, 0)},
    "dark_knight":  {"rig": "dark_knight", "body": (40, 40, 60),    "accent": (160, 0, 0)},

    # Individualization pass (levels 5/6/7/9/10/11) - each new archetype
    # gets its own rig (spider/serpent/treant/brute/imp/quadruped/robed/
    # golem/reptile/chimera, all new below) or reuses skeleton/dark_knight
    # recolored where the silhouette already fits (dark_skeleton/zumbi,
    # death_knight) - same "one dict entry, never new drawing code unless
    # the shape truly differs" rule as the original 3 rigs.

    # Level 5 - Pantano Sombrio
    "aranha":   {"rig": "spider",  "body": (55, 35, 65),  "eye": (255, 40, 40)},
    "serpente": {"rig": "serpent", "body": (60, 130, 60), "eye": (255, 220, 60)},
    "treant":   {"rig": "treant",  "body": (70, 50, 30),  "eye": (90, 170, 70)},

    # Level 6 - Torre Amaldicoada
    "troll":        {"rig": "brute",       "body": (95, 115, 75), "accent": (210, 210, 200)},
    "death_knight": {"rig": "dark_knight", "body": (25, 25, 30),   "accent": (230, 230, 220)},

    # Level 7 - Cripta Perdida
    "zumbi": {"rig": "skeleton", "body": (110, 130, 90), "eye": (40, 40, 30)},
    "verme": {"rig": "serpent",  "body": (140, 110, 70), "eye": (60, 40, 20)},
    "imp":   {"rig": "imp",      "body": (150, 40, 40),  "accent": (60, 10, 10)},

    # Level 9 - Salao dos Ecos
    "dark_horse": {"rig": "quadruped", "body": (25, 20, 35),  "accent": (150, 60, 200)},
    "acolito":    {"rig": "robed",     "body": (110, 90, 60), "accent": (200, 190, 160)},
    "feiticeira": {"rig": "robed",     "body": (55, 45, 100), "accent": (150, 210, 255)},

    # Level 10 - Abismo de Cinzas
    "fire_hound":      {"rig": "quadruped", "body": (150, 60, 20), "accent": (255, 170, 40)},
    "ogro":            {"rig": "brute",     "body": (110, 80, 40), "accent": (230, 210, 170)},
    "elemental_pedra": {"rig": "golem",     "body": (100, 90, 85), "accent": (255, 170, 60)},

    # Level 11 - Corredor Final
    "chimera":       {"rig": "chimera", "body": (140, 100, 40), "accent": (230, 210, 60)},
    "lyzardman":     {"rig": "reptile", "body": (40, 110, 70),  "accent": (220, 230, 80)},
    "dark_skeleton": {"rig": "skeleton", "body": (70, 70, 80),  "eye": (170, 60, 255)},
}


def _shade(color, factor):
    """A lighter (factor>1) or darker (factor<1) variant of `color` - used
    for a rig's secondary details (goblin legs, dark_knight shoulder pads)
    so recoloring one archetype recolors its whole sprite consistently
    instead of leaving those bits stuck on the original hardcoded shade."""
    return tuple(max(0, min(255, round(c * factor))) for c in color)


def _paint_skeleton(s, SC, body, eye):
    body_pixels = [(5,6),(6,6),(7,6),(8,6),(9,6),(10,6),
            (4,7),(5,7),(10,7),(11,7),
            (4,8),(5,8),(7,8),(8,8),(10,8),(11,8),
            (4,9),(5,9),(10,9),(11,9),
            (5,10),(6,10),(7,10),(8,10),(9,10),(10,10)]
    for (x,y) in body_pixels:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(5,2),(6,2),(7,2),(8,2),(9,2),(10,2),
            (4,3),(11,3),(4,4),(11,4),(4,5),(11,5),
            (5,5),(6,5),(7,5),(8,5),(9,5),(10,5)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, eye, (6*SC,3*SC,SC,SC))
    pygame.draw.rect(s, eye, (9*SC,3*SC,SC,SC))
    for x in [5,7,9]:
        pygame.draw.rect(s, WHITE, (x*SC,5*SC,SC,SC))
    for (x,y) in [(5,11),(6,11),(9,11),(10,11),(5,12),(9,12),(5,13),(9,13)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))


def _paint_goblin(s, SC, body, eye):
    for (x,y) in [(5,6),(6,6),(7,6),(8,6),(9,6),(10,6),
                  (4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7),(11,7),
                  (4,8),(11,8),(4,9),(11,9),
                  (5,10),(6,10),(7,10),(8,10),(9,10),(10,10)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for (x,y) in [(4,2),(5,2),(6,2),(7,2),(8,2),(9,2),(10,2),(11,2),
                  (3,3),(12,3),(3,4),(12,4),(3,5),(12,5),
                  (4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5),(11,5)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, eye, (5*SC,3*SC,SC*2,SC))
    pygame.draw.rect(s, eye, (9*SC,3*SC,SC*2,SC))
    pygame.draw.rect(s, BLACK, (6*SC,3*SC,SC,SC))
    pygame.draw.rect(s, BLACK, (10*SC,3*SC,SC,SC))
    pygame.draw.rect(s, body, (2*SC,2*SC,SC,SC*2))
    pygame.draw.rect(s, body, (13*SC,2*SC,SC,SC*2))
    darker = _shade(body, 0.75)
    for (x,y) in [(5,11),(6,11),(9,11),(10,11),(5,12),(9,12),(5,13),(9,13)]:
        pygame.draw.rect(s, darker, (x*SC,y*SC,SC,SC))


def _paint_dark_knight(s, SC, body, accent):
    for (x,y) in [(4,6),(5,6),(6,6),(7,6),(8,6),(9,6),(10,6),(11,6),
                  (3,7),(12,7),(3,8),(12,8),(3,9),(12,9),
                  (4,10),(5,10),(6,10),(7,10),(8,10),(9,10),(10,10),(11,10)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for (x,y) in [(4,1),(5,1),(6,1),(7,1),(8,1),(9,1),(10,1),(11,1),
                  (3,2),(12,2),(3,3),(12,3),(3,4),(12,4),(3,5),(12,5),
                  (4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5),(11,5)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, accent, (5*SC,3*SC,SC*6,SC))
    lighter = _shade(body, 1.75)
    for y in [6,7]:
        pygame.draw.rect(s, lighter, (2*SC,y*SC,SC*2,SC))
        pygame.draw.rect(s, lighter, (12*SC,y*SC,SC*2,SC))
    for (x,y) in [(4,11),(5,11),(10,11),(11,11),(4,12),(5,12),(10,12),(11,12),
                  (4,13),(5,13),(10,13),(11,13)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))


def _paint_spider(s, SC, body, eye):
    # Low round body (abdomen+cephalothorax), 8 legs radiating as lines -
    # the one rig here that isn't upright-humanoid, matches aranha's
    # low-profile ambush-predator silhouette.
    body_pixels = [(7,6),(8,6),
                   (6,7),(7,7),(8,7),(9,7),
                   (5,8),(6,8),(7,8),(8,8),(9,8),(10,8),
                   (6,9),(7,9),(8,9),(9,9),
                   (7,10),(8,10)]
    for (x,y) in body_pixels:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, eye, (6*SC,7*SC,SC,SC))
    pygame.draw.rect(s, eye, (9*SC,7*SC,SC,SC))
    legs = [
        ((6,8),(1,5)), ((5,9),(0,9)), ((5,10),(1,13)), ((6,11),(3,14)),
        ((10,8),(15,5)), ((11,9),(16,9)), ((11,10),(15,13)), ((10,11),(13,14)),
    ]
    for (x1,y1),(x2,y2) in legs:
        pygame.draw.line(s, body, (x1*SC,y1*SC), (x2*SC,y2*SC), max(1, SC-1))


def _paint_serpent(s, SC, body, eye):
    # Long S-curve body of overlapping circles, no legs at all - shared by
    # serpente (snake) and verme (worm), differentiated purely by palette.
    segments = [(3,13,2.2),(4,11,2.3),(6,9.5,2.5),(8,8.5,2.6),(10,7.5,2.4),(12,6.5,2.1)]
    for (cx,cy,r) in segments:
        pygame.draw.circle(s, body, (int(cx*SC), int(cy*SC)), int(r*SC))
    pygame.draw.circle(s, eye, (int(12.5*SC), int(6*SC)), max(1, SC-2))


def _paint_treant(s, SC, body, eye):
    # Tree-humanoid: trunk widening into root feet, branch arms, a leafy
    # canopy (eye slot doubles as leaf/glow color) instead of a face.
    trunk = [(7,7),(8,7),(6,8),(7,8),(8,8),(9,8),(6,9),(7,9),(8,9),(9,9),
             (6,10),(7,10),(8,10),(9,10)]
    for (x,y) in trunk:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    roots = [(4,11),(5,11),(6,11),(9,11),(10,11),(11,11),
             (3,12),(4,12),(11,12),(12,12)]
    for (x,y) in roots:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.line(s, body, (7*SC,7*SC), (2*SC,4*SC), max(1, SC-1))
    pygame.draw.line(s, body, (9*SC,7*SC), (13*SC,4*SC), max(1, SC-1))
    pygame.draw.circle(s, eye, (8*SC, 4*SC), 3*SC)
    darker = _shade(body, 0.7)
    pygame.draw.circle(s, darker, (8*SC, 4*SC), 3*SC, 1)


def _paint_brute(s, SC, body, accent):
    # Big, broad humanoid (troll/ogro) - wider torso and thicker limbs than
    # skeleton/goblin, a single jutting tusk instead of a face detail.
    torso = [(x,y) for y in range(5,11) for x in range(4,12)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(2,5) for x in range(6,10)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, accent, (7*SC,4*SC,SC,SC*2))
    for y in range(6,10):
        pygame.draw.rect(s, body, (1*SC,y*SC,SC*2,SC))
        pygame.draw.rect(s, body, (13*SC,y*SC,SC*2,SC))
    darker = _shade(body, 0.8)
    for (x,y) in [(5,11),(6,11),(9,11),(10,11),(5,12),(6,12),(9,12),(10,12),(5,13),(9,13)]:
        pygame.draw.rect(s, darker, (x*SC,y*SC,SC,SC))


def _paint_imp(s, SC, body, accent):
    # Small mischievous demon - narrow torso, bat wings, tiny horns/tail -
    # the smallest silhouette of the new rigs, matches imp's fast/erratic role.
    torso = [(x,y) for y in range(7,11) for x in range(6,10)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(4,7) for x in range(6,10)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.polygon(s, accent, [(5*SC,4*SC),(6*SC,1*SC),(7*SC,4*SC)])
    pygame.draw.polygon(s, accent, [(9*SC,4*SC),(10*SC,1*SC),(11*SC,4*SC)])
    pygame.draw.polygon(s, accent, [(6*SC,7*SC),(2*SC,5*SC),(4*SC,9*SC)])
    pygame.draw.polygon(s, accent, [(10*SC,7*SC),(14*SC,5*SC),(12*SC,9*SC)])
    pygame.draw.rect(s, WHITE, (6*SC,5*SC,SC,SC))
    pygame.draw.rect(s, WHITE, (9*SC,5*SC,SC,SC))
    for (x,y) in [(7,11),(8,11),(7,12),(8,12)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.line(s, body, (8*SC,13*SC), (11*SC,15*SC), max(1, SC-1))


def _paint_quadruped(s, SC, body, accent):
    # Generic 4-legged beast (dark_horse/fire_hound) - horizontal body,
    # head to one side, 4 thin legs, accent used for mane/flame details.
    torso = [(x,y) for y in range(7,10) for x in range(3,12)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(5,8) for x in range(11,15)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for (x,y) in [(2,6),(1,7),(2,8)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for x in [4,6,9,11]:
        for y in range(10,14):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for (x,y) in [(11,5),(12,5),(13,4)]:
        pygame.draw.rect(s, accent, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, WHITE, (13*SC,6*SC,SC,SC))


def _paint_robed(s, SC, body, accent):
    # Simple hooded robe (acolito/feiticeira) - trapezoid gown widening to
    # the ground, hooded head, two small glowing eyes (no visible face).
    for y in range(6,14):
        half = (y - 6) // 2 + 2
        for x in range(8-half, 8+half):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(2,6) for x in range(6,10)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, accent, (6*SC,5*SC,SC*4,SC))
    pygame.draw.rect(s, accent, (6*SC,4*SC,SC,SC))
    pygame.draw.rect(s, accent, (9*SC,4*SC,SC,SC))


def _paint_golem(s, SC, body, accent):
    # Blocky rock humanoid (elemental_pedra) - chunkier than every other
    # rig, cracked accent lines, a glowing core instead of a face.
    torso = [(x,y) for y in range(5,13) for x in range(3,12)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(2,5) for x in range(6,10)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for y in range(6,10):
        pygame.draw.rect(s, body, (1*SC,y*SC,SC*2,SC))
        pygame.draw.rect(s, body, (12*SC,y*SC,SC*2,SC))
    for (x,y) in [(5,13),(6,13),(9,13),(10,13)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC*2,SC))
    darker = _shade(body, 0.7)
    for (x,y) in [(5,6),(9,8),(6,10),(10,6)]:
        pygame.draw.rect(s, darker, (x*SC,y*SC,SC,SC))
    pygame.draw.circle(s, accent, (8*SC, 8*SC), SC)


def _paint_reptile(s, SC, body, accent):
    # Reptilian humanoid (lyzardman) - skeleton-shaped torso, elongated
    # snout, a tail dragging behind, scale-fleck texture via _shade.
    torso = [(x,y) for y in range(6,11) for x in range(5,11)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(3,6) for x in range(6,10)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, body, (10*SC,4*SC,SC*2,SC))
    pygame.draw.rect(s, accent, (7*SC,4*SC,SC,SC))
    for (x,y) in [(5,11),(6,11),(9,11),(10,11),(5,12),(9,12)]:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.line(s, body, (5*SC,11*SC), (1*SC,14*SC), max(1, SC-1))
    lighter = _shade(body, 1.3)
    for (x,y) in [(6,7),(9,9),(7,10)]:
        pygame.draw.rect(s, lighter, (x*SC,y*SC,SC,SC))


def _paint_chimera(s, SC, body, accent):
    # Most bespoke rig - lion-ish quadruped body, goat-horned head, a
    # snake-headed tail (accent used for horns/mane/tail eye).
    torso = [(x,y) for y in range(7,11) for x in range(3,11)]
    for (x,y) in torso:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    head = [(x,y) for y in range(4,8) for x in range(10,14)]
    for (x,y) in head:
        pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.polygon(s, accent, [(10*SC,4*SC),(9*SC,1*SC),(11*SC,4*SC)])
    pygame.draw.polygon(s, accent, [(13*SC,4*SC),(14*SC,1*SC),(14*SC,4*SC)])
    pygame.draw.rect(s, accent, (9*SC,4*SC,SC*4,SC))
    pygame.draw.rect(s, WHITE, (13*SC,6*SC,SC,SC))
    for x in [4,6,8,10]:
        for y in range(11,14):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    pygame.draw.line(s, body, (3*SC,9*SC), (0*SC,6*SC), max(1, SC-1))
    pygame.draw.circle(s, accent, (0, 6*SC), max(1, SC-2))


_RIG_PAINTERS = {
    "skeleton": _paint_skeleton,
    "goblin": _paint_goblin,
    "dark_knight": _paint_dark_knight,
    "spider": _paint_spider,
    "serpent": _paint_serpent,
    "treant": _paint_treant,
    "brute": _paint_brute,
    "imp": _paint_imp,
    "quadruped": _paint_quadruped,
    "robed": _paint_robed,
    "golem": _paint_golem,
    "reptile": _paint_reptile,
    "chimera": _paint_chimera,
}


def create_enemy_sprite(etype="skeleton"):
    SC = 3
    s = pygame.Surface((16*SC, 16*SC), pygame.SRCALPHA)
    defn = ENEMY_SPRITES[etype]
    body = defn["body"]
    # "eye" (skeleton/goblin) and "accent" (dark_knight) are the same slot -
    # whichever secondary color the rig's paint function expects.
    secondary = defn.get("eye") or defn.get("accent")
    _RIG_PAINTERS[defn["rig"]](s, SC, body, secondary)
    return s


# Per-boss rig (Stage B4 individualization pass) - each of the 4 campaign
# bosses now has its own hand-drawn silhouette instead of sharing one
# crowned-demon-king rig recolored via body_colors/eye_colors. Same
# "one dict of per-id data, N painter functions" convention as
# ENEMY_SPRITES/_RIG_PAINTERS above, just for bosses. body/accent are
# ((phase1), (phase2)) color pairs - phase2 always exists even for bosses
# whose visual barely changes, so _BOSS_RIG_PAINTERS never has to special-
# case a missing phase.
BOSS_SPRITES = {
    "orc_warlord": {"rig": "orc_warlord",
                    "body": ((50,120,40), (90,150,50)),
                    "accent": ((90,60,20), (110,70,25))},
    "necromancer": {"rig": "necromancer",
                    "body": ((18,16,22), (35,14,18))},
    "shadow_king": {"rig": "shadow_king",
                    "body": ((8,8,10), (18,6,10)),
                    "accent": ((240,240,245), (255,210,200))},
    "cacodemon":   {"rig": "cacodemon",
                    "body": ((140,35,10), (140,35,10))},
}


def _shade_lerp_row(y, y0, y1, x0_lo, x0_hi, x1_lo, x1_hi):
    """Linear-interpolated (left, right) x-bounds for row y between y0..y1 -
    used to build the necromancer's flared trapezoid cloak one row at a
    time instead of hand-listing every row's pixel span."""
    t = (y - y0) / max(1, (y1 - y0))
    x0 = round(x0_lo + (x0_hi - x0_lo) * t)
    x1 = round(x1_lo + (x1_hi - x1_lo) * t)
    return x0, x1


def _boss_arms(s, SC, color, y0=9, y1=16):
    for y in range(y0, y1):
        pygame.draw.rect(s, color, (1*SC, y*SC, SC*3, SC))
        pygame.draw.rect(s, color, (20*SC, y*SC, SC*3, SC))


def _boss_claws(s, SC, y=15, color=(200,200,220)):
    for x in [0,1,2]:
        pygame.draw.rect(s, color, (x*SC, y*SC, SC, SC*2))
    for x in [20,21,22]:
        pygame.draw.rect(s, color, (x*SC, y*SC, SC, SC*2))


def _boss_legs(s, SC, color):
    for x in [6,7,8,9]:
        for y in range(18,22):
            pygame.draw.rect(s, color, (x*SC,y*SC,SC,SC))
    for x in [14,15,16,17]:
        for y in range(18,22):
            pygame.draw.rect(s, color, (x*SC,y*SC,SC,SC))


def _boss_edge_aura(s, SC, color):
    """Phase-2 tell (top/bottom edge dashes) - factored out of the old
    single create_boss_sprite so orc_warlord/necromancer/shadow_king can
    each tint it to match their own palette (rage red / sickly green /
    ghost white) instead of every boss sharing the same fire-orange."""
    for i in range(0,24,2):
        pygame.draw.rect(s, (*color, 120), (i*SC,0,SC,SC))
        pygame.draw.rect(s, (*color, 120), (i*SC,23*SC,SC,SC))


def _paint_orc_warlord(s, SC, phase, body, accent):
    # Torso + head (broad, brutish)
    for y in range(8,18):
        for x in range(4,20):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for y in range(2,9):
        for x in range(6,18):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    # Furrowed angry brow ("olhos de mau") - dark red bar above each eye
    brow = (90,10,10)
    pygame.draw.rect(s, brow, (7*SC,3*SC,SC*3,SC))
    pygame.draw.rect(s, brow, (14*SC,3*SC,SC*3,SC))
    # Eyes - yellow/orange, angry
    eye_color = (255,180,40) if phase == 1 else (255,90,30)
    for x in [8,9,13,14]:
        pygame.draw.rect(s, eye_color, (x*SC,4*SC,SC,SC*2))
    pygame.draw.rect(s, BLACK, (9*SC,4*SC,SC,SC))
    pygame.draw.rect(s, BLACK, (14*SC,4*SC,SC,SC))
    # Mouth + tusks (jutting up, not fangs pointing down)
    for x in range(7,17):
        pygame.draw.rect(s, (20,60,15), (x*SC,7*SC,SC,SC))
    pygame.draw.rect(s, WHITE, (8*SC,6*SC,SC,SC*2))
    pygame.draw.rect(s, WHITE, (15*SC,6*SC,SC,SC*2))
    # Arms + claws
    _boss_arms(s, SC, body)
    _boss_claws(s, SC)
    # Tacape (club) gripped in the right hand - the one asymmetric prop
    handle = accent
    for (x,y) in [(21,9),(22,8),(22,7),(23,6),(23,5)]:
        pygame.draw.rect(s, handle, (x*SC,y*SC,SC,SC))
    head_blob = [(21,2),(22,2),(23,2),(21,3),(22,3),(23,3),(22,4),(23,4)]
    for (x,y) in head_blob:
        pygame.draw.rect(s, (130,120,110), (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, (90,80,75), (22*SC,3*SC,SC,SC))
    # Legs
    _boss_legs(s, SC, body)
    if phase == 2:
        _boss_edge_aura(s, SC, (200,20,10))


def _paint_necromancer(s, SC, phase, body, accent=None):
    # Flared trapezoid cloak (narrow at the shoulders, wide at the ground)
    # instead of a blocky torso - reads as a loose robe, not armor.
    for y in range(8,18):
        x0, x1 = _shade_lerp_row(y, 8, 17, 9, 0, 15, 24)
        x0, x1 = max(0,x0), min(24,x1)
        for x in range(x0, x1):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    # Hood
    for y in range(2,9):
        for x in range(8,16):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    # Skull face inside the hood
    bone = (225,220,205)
    for y in range(4,8):
        for x in range(9,15):
            pygame.draw.rect(s, bone, (x*SC,y*SC,SC,SC))
    pygame.draw.rect(s, BLACK, (10*SC,5*SC,SC,SC))
    pygame.draw.rect(s, BLACK, (13*SC,5*SC,SC,SC))
    pygame.draw.rect(s, (140,130,110), (11*SC,6*SC,SC*2,SC))  # nasal cavity
    glow = (120,255,140) if phase == 1 else (180,255,120)
    pygame.draw.rect(s, glow, (10*SC,5*SC,SC,SC//2))
    pygame.draw.rect(s, glow, (13*SC,5*SC,SC,SC//2))
    for x in range(9,15,2):
        pygame.draw.rect(s, BLACK, (x*SC,7*SC,SC,SC//2))  # teeth gaps
    # Sleeves, flared at the wrist, no weapon
    _boss_arms(s, SC, body)
    for x in [0,1,2,3]:
        pygame.draw.rect(s, body, (x*SC,14*SC,SC,SC))
    for x in [20,21,22,23]:
        pygame.draw.rect(s, body, (x*SC,14*SC,SC,SC))
    bone_hands = (200,195,180)
    pygame.draw.rect(s, bone_hands, (1*SC,15*SC,SC*2,SC))
    pygame.draw.rect(s, bone_hands, (20*SC,15*SC,SC*2,SC))
    if phase == 2:
        _boss_edge_aura(s, SC, (40,200,90))


def _paint_shadow_king(s, SC, phase, body, accent):
    # Solid black specter silhouette - torso/head with no crown, no face
    # detail, ragged smoke-tendril hem instead of clean legs.
    for y in range(8,16):
        for x in range(4,20):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for y in range(2,9):
        for x in range(6,18):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    tendril_len = {4:2, 6:4, 9:1, 11:3, 14:1, 17:4, 19:2}
    for x in range(4,20):
        extra = tendril_len.get(x, 0)
        for y in range(16, 16+extra):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    # Glowing white eyes - no pupils, no mouth, nothing else on the face.
    # `accent` is already the phase-correct color (BOSS_SPRITES pairs it by
    # phase before calling in), so no second phase check needed here.
    for x in [8,9,13,14]:
        pygame.draw.rect(s, accent, (x*SC,4*SC,SC,SC*2))
    # Wispy tapered arms (no claws) - triangular hand tips
    _boss_arms(s, SC, body, y0=9, y1=14)
    pygame.draw.polygon(s, body, [(1*SC,14*SC),(4*SC,14*SC),(2*SC,17*SC)])
    pygame.draw.polygon(s, body, [(20*SC,14*SC),(23*SC,14*SC),(21*SC,17*SC)])
    if phase == 2:
        _boss_edge_aura(s, SC, (230,230,235))


def _paint_cacodemon(s, SC, phase, body, accent=None):
    # Humanoid demon (replaces the old floating-sphere sprite) - one big
    # central eye, horns, small bat wings, clawed limbs.
    for y in range(8,18):
        for x in range(4,20):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    for y in range(2,9):
        for x in range(6,18):
            pygame.draw.rect(s, body, (x*SC,y*SC,SC,SC))
    # Wings (behind the torso)
    wing = (110,30,10)
    pygame.draw.polygon(s, wing, [(4*SC,10*SC),(0,7*SC),(2*SC,15*SC),(4*SC,13*SC)])
    pygame.draw.polygon(s, wing, [(20*SC,10*SC),(24*SC,7*SC),(22*SC,15*SC),(20*SC,13*SC)])
    # Horns
    horn = (60,15,5)
    pygame.draw.polygon(s, horn, [(7*SC,2*SC),(6*SC,0),(9*SC,2*SC)])
    pygame.draw.polygon(s, horn, [(17*SC,2*SC),(18*SC,0),(15*SC,2*SC)])
    # One big central eye
    cx, cy = 12*SC, 5*SC
    pygame.draw.circle(s, (255,120,20), (cx,cy), 3*SC)
    pygame.draw.circle(s, (255,220,120), (cx,cy), int(1.6*SC))
    pygame.draw.circle(s, BLACK, (cx,cy), SC)
    # Fanged mouth
    for x in range(7,17):
        pygame.draw.rect(s, (60,5,0), (x*SC,8*SC,SC,SC))
    for x in [7,8,11,12,15,16]:
        pygame.draw.rect(s, WHITE, (x*SC,9*SC,SC,SC*2))
    # Arms + claws
    _boss_arms(s, SC, body)
    _boss_claws(s, SC)
    # Legs
    _boss_legs(s, SC, body)


_BOSS_RIG_PAINTERS = {
    "orc_warlord": _paint_orc_warlord,
    "necromancer": _paint_necromancer,
    "shadow_king": _paint_shadow_king,
    "cacodemon": _paint_cacodemon,
}


def create_boss_sprite(boss_id, phase=1):
    """One rig per boss_id (Stage B4 individualization) - see BOSS_SPRITES/
    _BOSS_RIG_PAINTERS above. Cacodemon has no phase-2 concept (see
    CacodemonBoss in game/boss.py) but still accepts `phase` for a uniform
    call signature with the other 3 bosses."""
    SC = 4
    s = pygame.Surface((24*SC, 24*SC), pygame.SRCALPHA)
    defn = BOSS_SPRITES[boss_id]
    body = defn["body"][phase - 1]
    accent = defn.get("accent", (None, None))[phase - 1]
    _BOSS_RIG_PAINTERS[defn["rig"]](s, SC, phase, body, accent)
    return s


def create_logo_sprite(scale=4):
    # Simple sword over shield pixel art
    SC = scale
    w, h = 40, 20
    s = pygame.Surface((w*SC, h*SC), pygame.SRCALPHA)
    # Shield base (green-ish)
    pygame.draw.ellipse(s, (30,160,80), (6*SC,4*SC,28*SC,12*SC))
    pygame.draw.ellipse(s, (20,100,50), (8*SC,6*SC,24*SC,8*SC), 2)
    # Sword center
    # blade
    pygame.draw.rect(s, (200,200,220), (18*SC,0*SC,4*SC,12*SC))
    # tip
    pygame.draw.polygon(s, (220,220,220), [(18*SC,0),(22*SC,0),(20*SC,3*SC)])
    # hilt
    pygame.draw.rect(s, (150,100,40), (14*SC,8*SC,12*SC,2*SC))
    pygame.draw.rect(s, (180,140,60), (17*SC,10*SC,6*SC,2*SC))
    return s


def create_victory_hero_sprite(scale=4):
    SC = scale
    s = pygame.Surface((16*SC, 20*SC), pygame.SRCALPHA)
    # reuse small player colors: tunic green
    # torso
    for (x,y) in [(5,6),(6,6),(7,6),(8,6),(9,6),(10,6),(4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7),(11,7)]:
        pygame.draw.rect(s, (34,160,34), (x*SC,y*SC,SC,SC))
    # head
    for (x,y) in [(6,2),(7,2),(8,2),(9,2),(5,3),(6,3),(7,3),(8,3),(9,3),(10,3)]:
        pygame.draw.rect(s, (220,170,110), (x*SC,y*SC,SC,SC))
    # raised sword (hero holding up)
    pygame.draw.rect(s, (200,200,220), (12*SC,0*SC,2*SC,10*SC))
    pygame.draw.rect(s, (180,140,60), (10*SC,8*SC,6*SC,2*SC))
    # shield at side
    pygame.draw.rect(s, (50,100,200), (2*SC,7*SC,4*SC,6*SC))
    pygame.draw.rect(s, (220,180,80), (3*SC,9*SC,2*SC,2*SC))
    return s


def create_tile(tile_type):
    s = pygame.Surface((48, 48))
    if tile_type == "grass":
        s.fill((34,120,34))
        # Texture dots
        for pos in [(8,8),(24,16),(40,8),(16,32),(36,28),(12,40),(30,36)]:
            pygame.draw.circle(s, (20,100,20), pos, 2)
    elif tile_type == "wall":
        s.fill((80,80,90))
        # Brick pattern
        pygame.draw.rect(s, (60,60,70), (0,0,48,4))
        pygame.draw.rect(s, (60,60,70), (0,16,48,4))
        pygame.draw.rect(s, (60,60,70), (0,32,48,4))
        pygame.draw.rect(s, (60,60,70), (0,44,48,4))
        for y in [0,2]:
            offset = 0 if y % 2 == 0 else 24
            for x in range(0,48,24):
                pygame.draw.rect(s, (60,60,70), (x+offset,0,2,48))
    elif tile_type == "floor":
        s.fill((100,80,60))
        pygame.draw.rect(s, (80,60,40), (0,0,48,2))
        pygame.draw.rect(s, (80,60,40), (0,0,2,48))
    elif tile_type == "water":
        s.fill((30,80,180))
        for pos in [(8,16),(24,8),(38,20),(14,34),(32,38)]:
            pygame.draw.circle(s, (60,120,220), pos, 4)
    elif tile_type == "boss_floor":
        s.fill((40,10,60))
        for pos in [(8,8),(24,24),(40,8),(16,40),(36,16)]:
            pygame.draw.circle(s, (80,0,120), pos, 3)
    elif tile_type == "sand":
        s.fill((210,180,100))
        for pos in [(6,10),(20,20),(38,12),(14,36),(30,30),(10,44)]:
            pygame.draw.circle(s, (190,160,80), pos, 2)
    elif tile_type == "lava":
        s.fill((150, 60, 15))
        # Lava effect with glowing spots
        for pos in [(12,12),(36,24),(20,36),(8,28)]:
            pygame.draw.circle(s, (230, 120, 30), pos, 6)
        for pos in [(12,12),(36,24),(20,36),(8,28)]:
            pygame.draw.circle(s, (255, 170, 50), pos, 3)
    elif tile_type == "swamp":
        s.fill((40, 55, 30))
        for pos in [(10,14),(30,10),(20,30),(38,36),(6,40)]:
            pygame.draw.circle(s, (60, 80, 40), pos, 5)
        for pos in [(10,14),(30,10),(20,30),(38,36),(6,40)]:
            pygame.draw.circle(s, (30, 90, 60), pos, 2)
    # Per-boss-arena floors (Stage B4b individualization) - one distinct
    # tile per boss theme instead of 3 bosses sharing "boss_floor" and the
    # 4th using bright "lava" (the "magma gritante" look the user asked to
    # rework for the Cacodemon arena specifically).
    elif tile_type == "war_camp":
        s.fill((70, 55, 25))
        for pos in [(10,10),(34,14),(20,34),(38,38)]:
            pygame.draw.ellipse(s, (50, 40, 18), (pos[0]-8, pos[1]-4, 16, 8))
        for pos in [(6,30),(30,6),(40,26),(14,42)]:
            pygame.draw.rect(s, (90, 60, 20), (pos[0], pos[1], 6, 4))
    elif tile_type == "crypt_floor":
        s.fill((25, 25, 30))
        for x in range(0, 48, 24):
            pygame.draw.line(s, (45, 45, 55), (x, 0), (x, 48), 1)
        for y in range(0, 48, 24):
            pygame.draw.line(s, (45, 45, 55), (0, y), (48, y), 1)
        for pos in [(12,12),(36,30)]:
            pygame.draw.circle(s, (90, 220, 130), pos, 2)
    elif tile_type == "throne_floor":
        s.fill((18, 10, 28))
        for pos in [(8,10),(24,22),(40,10),(16,36),(36,38)]:
            pygame.draw.circle(s, (150, 130, 200), pos, 1)
        pygame.draw.line(s, (60, 40, 90), (0, 24), (48, 24), 1)
    elif tile_type == "abyss_floor":
        s.fill((22, 10, 16))
        for pos in [(10,10),(34,18),(18,34),(38,38)]:
            pygame.draw.circle(s, (90, 20, 25), pos, 2)
        pygame.draw.line(s, (60, 15, 20), (4, 40), (20, 26), 1)
        pygame.draw.line(s, (60, 15, 20), (28, 12), (44, 30), 1)
    # Common-mob individualization pass (levels 6/9) - cursed_floor (Torre
    # Amaldicoada) and ritual_floor (Salao dos Ecos) round out the per-level
    # floor set; level 7 reuses crypt_floor (already exists, built for the
    # Necromante boss room) and levels 5/10/11 keep swamp/lava/boss_floor
    # (already fit the new roster), so no new tile needed for those.
    elif tile_type == "cursed_floor":
        s.fill((30, 20, 40))
        for pos in [(10,10),(38,14),(24,24),(12,38),(36,36)]:
            pygame.draw.circle(s, (90, 40, 130), pos, 1)
        pygame.draw.line(s, (110, 60, 160), (16, 6), (24, 18), 1)
        pygame.draw.line(s, (110, 60, 160), (32, 30), (24, 18), 1)
        pygame.draw.line(s, (110, 60, 160), (16, 30), (24, 18), 1)
    elif tile_type == "ritual_floor":
        s.fill((45, 48, 60))
        pygame.draw.circle(s, (150, 170, 210), (24, 24), 14, 1)
        pygame.draw.circle(s, (150, 170, 210), (24, 24), 3)
        for pos in [(8,8),(40,8),(8,40),(40,40)]:
            pygame.draw.circle(s, (180, 200, 230), pos, 1)
    return s


def create_heart_sprite(full=True):
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    color = (220, 40, 40) if full else (80, 80, 80)
    pixels = [
        (3,1),(4,1),(8,1),(9,1),
        (2,2),(3,2),(4,2),(5,2),(7,2),(8,2),(9,2),(10,2),
        (1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(7,3),(8,3),(9,3),(10,3),(11,3),
        (1,4),(2,4),(3,4),(4,4),(5,4),(6,4),(7,4),(8,4),(9,4),(10,4),(11,4),
        (2,5),(3,5),(4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5),
        (3,6),(4,6),(5,6),(6,6),(7,6),(8,6),(9,6),
        (4,7),(5,7),(6,7),(7,7),(8,7),
        (5,8),(6,8),(7,8),
        (6,9),
    ]
    SC = 2
    for (x,y) in pixels:
        pygame.draw.rect(s, color, (x*SC, y*SC, SC, SC))
    return s


def create_mana_orb_sprite():
    """Floating mana pickup (Stage F8) - same 24x24 canvas and bob-animation
    contract as create_heart_sprite, just a blue orb instead of a heart, so
    game/states.py's Pickup class can treat both interchangeably."""
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    pygame.draw.circle(s, (40, 90, 210), (12, 12), 9)
    pygame.draw.circle(s, (110, 160, 255), (12, 12), 9, 2)
    pygame.draw.circle(s, (180, 210, 255), (9, 9), 3)
    return s


def create_projectile_sprite(ptype="fireball"):
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    if ptype == "fireball":
        for (x,y,c) in [(3,7,(255,200,0)),(4,6,(255,200,0)),(5,5,(255,150,0)),
                        (6,4,(255,100,0)),(7,3,(255,50,0)),(8,4,(255,100,0)),
                        (9,5,(255,150,0)),(10,6,(255,200,0)),(11,7,(255,200,0)),
                        (4,8,(255,150,0)),(5,9,(255,100,0)),(6,10,(200,50,0)),
                        (7,8,(255,255,0)),(8,9,(255,200,0)),(9,8,(255,150,0))]:
            pygame.draw.rect(s, c, (x,y,2,2))
    elif ptype == "slash":
        for i in range(8):
            pygame.draw.rect(s, (200,220,255), (i,i,3,3))
    return s


def create_item_sprite(itype="key"):
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    if itype == "key":
        # Key head
        pygame.draw.circle(s, GOLD, (7,6), 4)
        pygame.draw.circle(s, (40,30,0), (7,6), 2)
        # Key shaft
        pygame.draw.rect(s, GOLD, (6,10,2,5))
        pygame.draw.rect(s, GOLD, (8,12,3,1))
        pygame.draw.rect(s, GOLD, (8,14,3,1))
    elif itype == "potion":
        pygame.draw.rect(s, (180,100,200), (5,2,6,2))
        pygame.draw.rect(s, (180,100,200), (4,4,8,9))
        pygame.draw.rect(s, (220,150,255), (5,5,3,5))
    elif itype == "gold":
        pygame.draw.circle(s, GOLD, (8, 8), 6)
        pygame.draw.circle(s, (170, 130, 0), (8, 8), 6, 1)
        pygame.draw.circle(s, (255, 240, 160), (6, 6), 2)
    return s


_LEVEL_THUMB_CACHE = {}


def create_level_thumbnail(floor, bg):
    """A small swatch for the Atlas tab (Stage F3) - the level's floor tile
    pattern over its background color, since there's no per-level image
    asset to show. Takes primitive values (not a LEVEL_MAPS dict) so
    game/assets.py doesn't need to import game/level.py, which already
    imports this module (would be circular)."""
    key = (floor, bg)
    if key in _LEVEL_THUMB_CACHE:
        return _LEVEL_THUMB_CACHE[key]
    s = pygame.Surface((48, 36), pygame.SRCALPHA)
    s.fill(bg)
    tile = create_tile(floor)
    scaled = pygame.transform.scale(tile, (24, 24))
    for x in (0, 24):
        s.blit(scaled, (x, 6))
    pygame.draw.rect(s, tuple(min(255, c + 40) for c in bg), (0, 0, 48, 36), 1)
    _LEVEL_THUMB_CACHE[key] = s
    return s


def create_particle(color, size=4):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill(color)
    return s


# ─── Stage F1 icons ─────────────────────────────────────────────────────────
# Hotbar/items/attributes/debuffs used to be flat-color boxes + a 2-3 letter
# abbreviation (see game/player.py's old _SPELL_ABBR/_ITEM_ABBR). These are
# small (14-16px) pixel-art icons instead, same draw_pixel_art/manual-rect
# style as the rest of this file. Each create_* function memoizes into its
# own module-level cache - called every frame from HUD/menu draw code, and
# none of these depend on any live game state, so building once and reusing
# the Surface is free correctness, not premature optimization.

_SPELL_ICON_CACHE = {}
_POTION_ICON_CACHE = {}
_ATTR_ICON_CACHE = {}
_DEBUFF_ICON_CACHE = {}


def create_spell_icon(spell_id):
    if spell_id in _SPELL_ICON_CACHE:
        return _SPELL_ICON_CACHE[spell_id]
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    if spell_id == "fireball":
        for (x, y, c) in [(3,7,(255,200,0)),(4,6,(255,200,0)),(5,5,(255,150,0)),
                          (6,4,(255,100,0)),(7,3,(255,50,0)),(8,4,(255,100,0)),
                          (9,5,(255,150,0)),(10,6,(255,200,0)),(11,7,(255,200,0)),
                          (4,8,(255,150,0)),(5,9,(255,100,0)),(6,10,(200,50,0)),
                          (7,8,(255,255,0)),(8,9,(255,200,0)),(9,8,(255,150,0))]:
            pygame.draw.rect(s, c, (x, y, 2, 2))
    elif spell_id == "frost_nova":
        cx, cy = 8, 8
        tip = (200, 235, 255)
        core = (140, 210, 255)
        pygame.draw.circle(s, core, (cx, cy), 3)
        for dx, dy in [(0,-6),(0,6),(-6,0),(6,0),(-4,-4),(4,-4),(-4,4),(4,4)]:
            pygame.draw.line(s, tip, (cx, cy), (cx + dx, cy + dy), 1)
            pygame.draw.circle(s, tip, (cx + dx, cy + dy), 1)
    elif spell_id == "healing_light":
        gold = (255, 225, 120)
        bright = (255, 250, 210)
        pygame.draw.rect(s, gold, (7, 1, 2, 14))
        pygame.draw.rect(s, gold, (1, 7, 14, 2))
        pygame.draw.line(s, gold, (3, 3), (13, 13), 1)
        pygame.draw.line(s, gold, (13, 3), (3, 13), 1)
        pygame.draw.circle(s, bright, (8, 8), 2)
    _SPELL_ICON_CACHE[spell_id] = s
    return s


_POTION_COLORS = {
    "health_potion": ((200, 40, 40), (255, 110, 110)),
    "mana_potion": ((40, 90, 210), (110, 160, 255)),
    "antidote": ((50, 160, 80), (140, 230, 150)),
}


def create_potion_icon(item_id):
    if item_id in _POTION_ICON_CACHE:
        return _POTION_ICON_CACHE[item_id]
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    dark, light = _POTION_COLORS.get(item_id, ((150, 150, 150), (210, 210, 210)))
    pygame.draw.rect(s, (140, 130, 120), (6, 1, 4, 3))
    pygame.draw.rect(s, dark, (4, 4, 8, 10), border_radius=2)
    pygame.draw.rect(s, light, (5, 6, 3, 6))
    _POTION_ICON_CACHE[item_id] = s
    return s


def create_attribute_icon(attr):
    if attr in _ATTR_ICON_CACHE:
        return _ATTR_ICON_CACHE[attr]
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    if attr == "strength":  # arm with muscle
        skin = (220, 170, 110)
        pygame.draw.rect(s, skin, (2, 10, 5, 4))
        pygame.draw.circle(s, skin, (9, 8), 5)
        pygame.draw.circle(s, (190, 140, 90), (9, 8), 5, 1)
    elif attr == "dexterity":  # boot
        leather = (120, 80, 40)
        pygame.draw.rect(s, leather, (5, 2, 4, 8))
        pygame.draw.rect(s, leather, (5, 9, 9, 4))
        pygame.draw.rect(s, (60, 40, 20), (5, 12, 9, 2))
    elif attr == "intelligence":  # brain
        pink = (230, 150, 180)
        pygame.draw.ellipse(s, pink, (2, 3, 12, 10))
        pygame.draw.line(s, (180, 100, 130), (8, 4), (8, 12), 1)
        pygame.draw.arc(s, (180, 100, 130), (2, 3, 7, 10), 1.0, 3.0, 1)
        pygame.draw.arc(s, (180, 100, 130), (7, 3, 7, 10), 0.1, 2.1, 1)
    elif attr == "wisdom":  # wizard hat
        purple = (130, 80, 200)
        pygame.draw.polygon(s, purple, [(8, 0), (12, 12), (4, 12)])
        pygame.draw.rect(s, purple, (2, 12, 12, 2))
        pygame.draw.circle(s, (255, 220, 100), (8, 5), 1)
    elif attr == "vigor":  # armor chestplate
        steel = (150, 160, 175)
        pygame.draw.polygon(s, steel, [(8, 2), (13, 5), (12, 13), (4, 13), (3, 5)])
        pygame.draw.line(s, (100, 110, 125), (8, 3), (8, 12), 1)
    elif attr == "luck":  # four-leaf clover
        green = (60, 170, 80)
        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3)]:
            pygame.draw.circle(s, green, (8 + dx, 8 + dy), 3)
        pygame.draw.rect(s, (90, 60, 20), (7, 8, 2, 6))
    _ATTR_ICON_CACHE[attr] = s
    return s


def create_debuff_icon(effect_id):
    if effect_id in _DEBUFF_ICON_CACHE:
        return _DEBUFF_ICON_CACHE[effect_id]
    s = pygame.Surface((14, 14), pygame.SRCALPHA)
    if effect_id == "poison":
        c = (140, 220, 90)
        pygame.draw.polygon(s, c, [(7, 1), (11, 8), (7, 13), (3, 8)])
    elif effect_id == "slow":
        c = (120, 170, 230)
        pygame.draw.arc(s, c, (1, 1, 12, 12), 0.3, 5.5, 2)
        pygame.draw.circle(s, c, (7, 2), 1)
    elif effect_id == "weakness":
        c = (200, 120, 200)
        pygame.draw.circle(s, c, (7, 5), 4, 1)
        pygame.draw.line(s, c, (5, 3), (6, 4), 1)
        pygame.draw.line(s, c, (9, 3), (8, 4), 1)
        pygame.draw.line(s, c, (7, 9), (7, 13), 2)
    elif effect_id == "burn":
        c = (255, 130, 40)
        pygame.draw.polygon(s, c, [(7, 1), (10, 7), (8, 7), (10, 13), (4, 8), (6, 8)])
    elif effect_id == "chill":
        c = (150, 200, 255)
        for dx, dy in [(0, -6), (0, 6), (-6, 0), (6, 0), (-4, -4), (4, -4), (-4, 4), (4, 4)]:
            pygame.draw.line(s, c, (7, 7), (7 + dx, 7 + dy), 1)
    elif effect_id == "heat":
        c = (255, 180, 80)
        pygame.draw.circle(s, c, (7, 7), 3)
        for dx, dy in [(0,-6),(0,6),(-6,0),(6,0),(-4,-4),(4,-4),(-4,4),(4,4)]:
            pygame.draw.line(s, c, (7 + dx * 0.5, 7 + dy * 0.5), (7 + dx, 7 + dy), 1)
    elif effect_id == "shock":
        c = (255, 255, 120)
        pygame.draw.polygon(s, c, [(8, 1), (4, 8), (7, 8), (6, 13), (11, 6), (8, 6)])
    else:
        c = (200, 200, 200)
        pygame.draw.circle(s, c, (7, 7), 4)
    _DEBUFF_ICON_CACHE[effect_id] = s
    return s
