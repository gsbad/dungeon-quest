"""
Developer/test overlay (F1) - lets attributes, level, gold, inventory,
difficulty tier, and a handful of "force this system to happen now" actions
be set directly, for exercising systems (Paragon/Champion rolls, difficulty
gating, boss one-hit testing, etc.) without grinding for them.

PC-keyboard-only, no mouse-tap path and no mobile button - same precedent
as the M/N dev-jump keys (game/states.py's GameplayState._dev_jump): this is
a testing tool, not a player-facing feature, so it doesn't need the touch
affordances every real overlay (Paperdoll, ItemsOverlay) has. Reuses their
exact keyboard idiom instead: W/S move a row cursor (pulsing glow highlight,
same look as Paperdoll._draw_glow), A/D adjust a value-row, Space fires a
trigger-row - see handle_keys().

Rows take the whole GameplayState (not just Player) because several of them
need level.enemies/boss/save_state/the existing msg_text toast - a tighter
coupling than Paperdoll/ItemsOverlay need, and a reasonable one for an
internal testing-only module (deliberately not generalized to match their
shape).
"""
import math
import random
import pygame
from game.theme import font, SW, SH, ACCENT_GOLD, SUBTEXT, PANEL_FILL, PANEL_BORDER
from game.ui import Panel, draw_text
from game.input_system import Action
from game.items import ITEMS
from game.difficulty import DIFFICULTIES, ORDER as DIFFICULTY_ORDER
from game.affixes import make_paragon, make_champion
from game.stats import MAX_LEVEL
import game.save as save

ATTR_STEP = 5
GOLD_STEP = 50
XP_CHUNK = 500

ATTR_ROWS = [
    ("strength", "FOR"), ("dexterity", "DES"), ("intelligence", "INT"),
    ("wisdom", "SAB"), ("vigor", "VIG"),
]

_PANEL_W = 460
_PY = 20
_TITLE_Y = 18
_ROWS_START_Y = 60
_ROW_H = 24


def _persist_character(gs):
    save.sync_character(gs.save_state, gs.player)
    save.save(gs.save_state)


def _persist_economy(gs):
    save.sync_economy(gs.save_state, gs.player)
    save.save(gs.save_state)


def _full_heal(gs):
    gs.player.hp = gs.player.max_hp
    gs.player.mana = gs.player.max_mana


class DebugPanel:
    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = _PY
        self.panel = None  # built lazily once _rows is known, for _PANEL_H
        self.cursor = 0
        self._difficulty_dirty = False
        self._rows = self._build_rows()
        panel_h = _ROWS_START_Y + len(self._rows) * _ROW_H + 40
        self.panel = Panel(_PANEL_W, panel_h, PANEL_FILL, PANEL_BORDER, border_width=2)
        self._panel_h = panel_h

    # ------------------------------------------------------------- rows
    def _build_rows(self):
        rows = []
        for attr, label in ATTR_ROWS:
            rows.append(self._attr_row(attr, label))
        rows.append(self._level_row())
        rows.append(self._points_row())
        rows.append(self._gold_row())
        rows.append(self._xp_trigger_row())
        for item_id in ITEMS:
            rows.append(self._item_row(item_id))
        rows.append(self._difficulty_row())
        rows.append(self._unlock_all_row())
        rows.append(self._force_row("Forcar Paragon", make_paragon))
        rows.append(self._force_row("Forcar Campeao", make_champion))
        rows.append(self._kill_all_row())
        rows.append(self._god_mode_row())
        rows.append(self._one_hit_boss_row())
        return rows

    def _attr_row(self, attr, label):
        def adjust(gs, d):
            current = getattr(gs.player.stats, attr)
            setattr(gs.player.stats, attr, max(1, current + d * ATTR_STEP))
            gs.player.refresh_profession()
            _full_heal(gs)
            _persist_character(gs)

        def text(gs):
            return str(int(getattr(gs.player.stats, attr)))

        return {"label": f"{label} (passo {ATTR_STEP})", "kind": "adjust", "adjust": adjust, "text": text}

    def _level_row(self):
        def adjust(gs, d):
            gs.player.level = max(1, min(MAX_LEVEL, gs.player.level + d))
            _persist_character(gs)

        def text(gs):
            return str(gs.player.level)

        return {"label": "Nivel (nao afeta combate)", "kind": "adjust", "adjust": adjust, "text": text}

    def _points_row(self):
        def adjust(gs, d):
            gs.player.unspent_points = max(0, gs.player.unspent_points + d)
            _persist_character(gs)

        def text(gs):
            return str(gs.player.unspent_points)

        return {"label": "Pontos Livres", "kind": "adjust", "adjust": adjust, "text": text}

    def _gold_row(self):
        def adjust(gs, d):
            gs.player.gold = max(0, gs.player.gold + d * GOLD_STEP)
            _persist_economy(gs)

        def text(gs):
            return f"{gs.player.gold}g"

        return {"label": f"Ouro (passo {GOLD_STEP})", "kind": "adjust", "adjust": adjust, "text": text}

    def _xp_trigger_row(self):
        def fire(gs):
            gs.player.gain_xp(XP_CHUNK)
            _persist_character(gs)
            gs.msg_timer, gs.msg_text = 2.0, f"+{XP_CHUNK} XP (debug)"

        return {"label": f"Adicionar {XP_CHUNK} XP", "kind": "trigger", "fire": fire}

    def _item_row(self, item_id):
        name = ITEMS[item_id]["name"]

        def adjust(gs, d):
            count = gs.player.inventory.get(item_id, 0)
            gs.player.inventory[item_id] = max(0, count + d)
            _persist_economy(gs)

        def text(gs):
            return f"x{gs.player.inventory.get(item_id, 0)}"

        return {"label": name, "kind": "adjust", "adjust": adjust, "text": text}

    def _difficulty_row(self):
        def adjust(gs, d):
            prog = gs.save_state["progression"]
            idx = DIFFICULTY_ORDER.index(prog["current_difficulty"])
            prog["current_difficulty"] = DIFFICULTY_ORDER[(idx + d) % len(DIFFICULTY_ORDER)]
            save.save(gs.save_state)
            self._difficulty_dirty = True

        def text(gs):
            diff_id = gs.save_state["progression"]["current_difficulty"]
            return DIFFICULTIES[diff_id]["name"]

        return {"label": "Dificuldade atual", "kind": "adjust", "adjust": adjust, "text": text}

    def _unlock_all_row(self):
        def fire(gs):
            gs.save_state["progression"]["cleared_difficulties"] = list(DIFFICULTY_ORDER)
            save.save(gs.save_state)
            gs.msg_timer, gs.msg_text = 2.0, "Todas as dificuldades desbloqueadas (debug)"

        return {"label": "Desbloquear todas dificuldades", "kind": "trigger", "fire": fire}

    def _force_row(self, label, apply_fn):
        def fire(gs):
            candidates = [e for e in gs.level.enemies if e.alive and not e.is_paragon and not e.is_champion]
            if not candidates:
                gs.msg_timer, gs.msg_text = 2.0, "Nenhum inimigo comum disponivel"
                return
            apply_fn(random.choice(candidates))
            gs.msg_timer, gs.msg_text = 2.0, f"{label} aplicado (debug)"

        return {"label": label, "kind": "trigger", "fire": fire}

    def _kill_all_row(self):
        def fire(gs):
            killed = 0
            for enemy in list(gs.level.enemies):
                if not enemy.alive:
                    continue
                # Deliberately bypasses the "warded" affix's block chance
                # (that check lives in Level.update()'s melee call site, not
                # inside Enemy.take_damage) - this is a forced debug kill,
                # not a simulated player attack, same reasoning as the
                # forced Paragon/Champion rows above.
                enemy.take_damage(10 ** 6)
                if not enemy.alive:
                    gs.level.credit_kill(gs.player, enemy)
                    killed += 1
            _persist_economy(gs)
            gs.msg_timer, gs.msg_text = 2.0, f"{killed} inimigos eliminados (debug)"

        return {"label": "Matar todos os inimigos da fase", "kind": "trigger", "fire": fire}

    def _god_mode_row(self):
        def fire(gs):
            gs.player.debug_invincible = not gs.player.debug_invincible

        def text(gs):
            return "ON" if gs.player.debug_invincible else "OFF"

        return {"label": "Modo Deus", "kind": "trigger", "fire": fire, "text": text}

    def _one_hit_boss_row(self):
        def fire(gs):
            if gs.boss is None:
                gs.msg_timer, gs.msg_text = 2.0, "Nenhum chefe ativo nesta fase"
            elif hasattr(gs.boss, "enable_one_hit"):
                gs.boss.enable_one_hit()
                gs.msg_timer, gs.msg_text = 2.0, "One-hit ativado no chefe (debug)"
            else:
                gs.msg_timer, gs.msg_text = 2.0, "Chefe atual nao suporta one-hit (Cacodemon)"

        return {"label": "One-hit no chefe atual", "kind": "trigger", "fire": fire}

    # ------------------------------------------------------------- state
    def consume_difficulty_dirty(self):
        dirty, self._difficulty_dirty = self._difficulty_dirty, False
        return dirty

    # ------------------------------------------------------------- input
    def handle_keys(self, input_mgr, game_state):
        n = len(self._rows)
        if input_mgr.consume_action(Action.MENU_UP):
            self.cursor = (self.cursor - 1) % n
        if input_mgr.consume_action(Action.MENU_DOWN):
            self.cursor = (self.cursor + 1) % n
        row = self._rows[self.cursor]
        if row["kind"] == "adjust":
            if input_mgr.consume_action(Action.MENU_LEFT):
                row["adjust"](game_state, -1)
            if input_mgr.consume_action(Action.MENU_RIGHT):
                row["adjust"](game_state, 1)
        elif row["kind"] == "trigger":
            if input_mgr.consume_action(Action.CONFIRM):
                row["fire"](game_state)

    # ------------------------------------------------------------- draw
    @staticmethod
    def _glow_alpha():
        return int(90 + 60 * abs(math.sin(pygame.time.get_ticks() / 1000.0 * 4)))

    def draw(self, surface, game_state):
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        self.panel.draw(surface, (self.px, self.py))

        f_title = font(20, bold=True)
        draw_text(surface, "PAINEL DE DEBUG (F1)", f_title, ACCENT_GOLD,
                  self.px + _PANEL_W // 2, self.py + _TITLE_Y)

        f_row = font(14)
        f_val = font(14, bold=True)
        for i, row in enumerate(self._rows):
            y = self.py + _ROWS_START_Y + i * _ROW_H
            if i == self.cursor:
                glow_rect = pygame.Rect(self.px + 10, y - 3, _PANEL_W - 20, _ROW_H - 4)
                glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                glow.fill((255, 215, 80, self._glow_alpha()))
                surface.blit(glow, glow_rect.topleft)
                pygame.draw.rect(surface, (255, 225, 120), glow_rect, 1, border_radius=4)

            label_surf = f_row.render(row["label"], True, (220, 220, 230))
            surface.blit(label_surf, (self.px + 22, y))

            if "text" in row:
                value_surf = f_val.render(row["text"](game_state), True, (255, 255, 255))
            elif row["kind"] == "trigger":
                value_surf = f_val.render("[ESPACO]", True, (140, 200, 255))
            else:
                value_surf = None
            if value_surf is not None:
                surface.blit(value_surf, (self.px + _PANEL_W - 22 - value_surf.get_width(), y))

        f_hint = font(13)
        draw_text(surface, "W/S seleciona | A/D ajusta | ESPACO aciona | F1 - Fechar",
                  f_hint, SUBTEXT, self.px + _PANEL_W // 2, self.py + self._panel_h - 24)
