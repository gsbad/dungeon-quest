"""
Developer/test overlay (F1) - lets attributes, level, gold, inventory,
difficulty tier, and a handful of "force this system to happen now" actions
be set directly, for exercising systems (Paragon/Champion rolls, difficulty
gating, boss one-hit testing, etc.) without grinding for them.

Keyboard-first (same precedent as the M/N dev-jump keys - a testing tool,
not a player-facing feature): W/S move a row cursor (pulsing glow
highlight, same look as Paperdoll._draw_glow), A/D adjust a value-row,
Space fires a trigger-row - see handle_keys(). The only pointer affordance
is the Stage J6 page-flip arrows (Carousel), since A/D was already taken
by value adjustment.

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
from game.ui import Panel, draw_text, Carousel
from game.input_system import Action
from game.status_effects import STATUS_EFFECTS
from game.items import ITEMS
from game.difficulty import DIFFICULTIES, ORDER as DIFFICULTY_ORDER
from game.affixes import make_paragon, make_champion
from game.stats import MAX_LEVEL
from game.reputation import kills_total, deaths_total, determine_reputation
from game.professions import PURE, HYBRID, ADVENTURER, BASE_ATTR
import game.save as save
import game.net as net

ATTR_STEP = 5
GOLD_STEP = 50
XP_CHUNK = 500
KILLS_STEP = 10
DEATHS_STEP = 1

ATTR_ROWS = [
    ("strength", "FOR"), ("dexterity", "DES"), ("intelligence", "INT"),
    ("wisdom", "SAB"), ("vigor", "VIG"),
]

# Stage H8 - the 16 professions in a stable cycling order (Aventureiro +
# 5 PURE + 10 HYBRID), each mapped to an attribute recipe that
# game.professions.determine_profession() will read back as that exact
# profession - profession itself has no settable field (see
# game/professions.py's module docstring), so "activating" one from here
# means applying the attribute combination it's derived from.
PROFESSION_ORDER = [ADVENTURER] + list(PURE.values()) + list(HYBRID.values())
_PROFESSION_ATTRS = ["strength", "dexterity", "intelligence", "wisdom", "vigor"]


def _profession_recipe(name):
    if name == ADVENTURER:
        return {}
    for attr, pname in PURE.items():
        if pname == name:
            # Comfortably over the ratio-gate (2nd highest must be < half
            # the highest) since every other priority attr stays at baseline.
            return {attr: BASE_ATTR + 30}
    for pair, pname in HYBRID.items():
        if pname == name:
            a, b = pair
            # Equal split clears both the >=20-spent floor and the "not
            # ratio-gated to PURE" check (spent[a] == spent[b]).
            return {a: BASE_ATTR + 25, b: BASE_ATTR + 25}
    return {}


_PANEL_W = 460
_PY = 20
_TITLE_Y = 18
_ROWS_START_Y = 60
# Stage J6: the row list is paginated now (Carousel from game/ui.py, same
# widget as the paperdoll Help/Achievements tabs) - the panel sizes to
# _ROWS_PER_PAGE, not to the full row count, so it can never creep past
# SH=600 again no matter how many debug rows get added. That also undoes
# Stage I6's emergency 24->20px row squeeze: with only 12 rows per page,
# 24px rows fit with lots of margin (60 + 12*24 + 40 + PY(20) = 408).
_ROW_H = 24
_ROWS_PER_PAGE = 12


def _persist_character(gs):
    save.sync_character(gs.save_state, gs.player)
    save.save(gs.save_state)
    net.trigger_sync(gs.save_state)


def _persist_economy(gs):
    save.sync_economy(gs.save_state, gs.player)
    save.save(gs.save_state)
    net.trigger_sync(gs.save_state)


def _full_heal(gs):
    gs.player.hp = gs.player.max_hp
    gs.player.mana = gs.player.max_mana


class DebugPanel:
    def __init__(self):
        self.px = SW // 2 - _PANEL_W // 2
        self.py = _PY
        self.cursor = 0
        self._difficulty_dirty = False
        self._rows = self._build_rows()
        # Stage J6: height comes from the page size, not the row count -
        # rows beyond _ROWS_PER_PAGE live on later carousel pages.
        panel_h = _ROWS_START_Y + _ROWS_PER_PAGE * _ROW_H + 40
        self.panel = Panel(_PANEL_W, panel_h, PANEL_FILL, PANEL_BORDER, border_width=2)
        self._panel_h = panel_h
        # Page state follows the keyboard cursor (W/S walking past a page
        # edge flips pages naturally, since page = cursor // per-page);
        # the arrows exist for the mouse/tap path and jump the cursor.
        # Widened by 34px per side so the arrows land OUTSIDE the panel
        # (rows span nearly its full width - inside-edge arrows would sit
        # on top of the row labels/values).
        self.carousel = Carousel(self.px - 34, _PANEL_W + 68, self.py + panel_h // 2)

    # ------------------------------------------------------------- rows
    def _build_rows(self):
        rows = []
        for attr, label in ATTR_ROWS:
            rows.append(self._attr_row(attr, label))
        rows.append(self._profession_row())
        rows.append(self._level_row())
        rows.append(self._points_row())
        rows.append(self._gold_row())
        rows.append(self._kills_row())
        rows.append(self._deaths_row())
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
        rows.append(self._all_debuffs_row())
        rows.append(self._login_status_row())
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

    def _profession_row(self):
        def adjust(gs, d):
            current = gs.player.profession if gs.player.profession in PROFESSION_ORDER else ADVENTURER
            idx = PROFESSION_ORDER.index(current)
            target = PROFESSION_ORDER[(idx + d) % len(PROFESSION_ORDER)]
            for attr in _PROFESSION_ATTRS:
                setattr(gs.player.stats, attr, BASE_ATTR)
            for attr, value in _profession_recipe(target).items():
                setattr(gs.player.stats, attr, value)
            gs.player.refresh_profession()
            _full_heal(gs)
            _persist_character(gs)

        def text(gs):
            return gs.player.profession

        return {"label": "Profissao (forcar)", "kind": "adjust", "adjust": adjust, "text": text}

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

    def _kills_row(self):
        # Debug lever for game/reputation.py - kills_total() sums
        # player.kills (in-run) + save_state.counters.kills/boss_kills
        # (persisted) over ALL keys, so a synthetic "debug" bucket bumps the
        # total without needing a real enemy kill. Shows the resulting
        # reputation title inline so testing doesn't need a trip to the HUD.
        def adjust(gs, d):
            counters = gs.save_state["counters"]
            counters["kills"]["debug"] = max(0, counters["kills"].get("debug", 0) + d * KILLS_STEP)
            save.save(gs.save_state)

        def text(gs):
            total = kills_total(gs.player, gs.save_state)
            rep = determine_reputation(total, deaths_total(gs.save_state))
            return f"{total} ({rep})"

        return {"label": f"Kills totais (passo {KILLS_STEP})", "kind": "adjust", "adjust": adjust, "text": text}

    def _deaths_row(self):
        def adjust(gs, d):
            counters = gs.save_state["counters"]
            counters["deaths"] = max(0, counters["deaths"] + d * DEATHS_STEP)
            save.save(gs.save_state)

        def text(gs):
            deaths = deaths_total(gs.save_state)
            rep = determine_reputation(kills_total(gs.player, gs.save_state), deaths)
            return f"{deaths} ({rep})"

        return {"label": "Mortes totais", "kind": "adjust", "adjust": adjust, "text": text}

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

    def _all_debuffs_row(self):
        # Stage J6: instantly afflicted with every status effect at once -
        # exists to eyeball the HUD chips/icons (Stage J4/J5's black-plated
        # debuff icons) without hunting down one applier of each kind.
        def fire(gs):
            for effect_id in STATUS_EFFECTS:
                gs.player.status.apply(effect_id)
            gs.msg_timer, gs.msg_text = 2.0, f"{len(STATUS_EFFECTS)} debuffs aplicados (debug)"

        return {"label": "Contrair todos os debuffs", "kind": "trigger", "fire": fire}

    def _login_status_row(self):
        # Stage I2 spike: read-only proof that Google login -> backend JWT ->
        # localStorage -> game/net.py's js bridge round-trip actually worked,
        # without wiring any real cloud-sync UI yet. No adjust/fire action -
        # ESPACO is a harmless no-op here, same shape as _god_mode_row's
        # trigger+text combo.
        def fire(gs):
            pass

        def text(gs):
            email = net.get_email()
            who = email if email else "desconectado"
            status = net.get_last_sync_status()
            combined = f"{who} | {status}"
            # Short form for the row itself (shares its line with the
            # label) - the cursor-selected hint line at the panel's bottom
            # shows the untruncated version, see draw()'s _hint_text().
            return combined if len(combined) <= 38 else combined[:35] + "..."

        return {"label": "Login/Sync (Stage I2/I6)", "kind": "trigger", "fire": fire, "text": text}

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

    def handle_tap(self, input_mgr):
        """Stage J6: the panel is otherwise keyboard-only, but the carousel
        arrows are clickable - A/D can't flip pages here (they adjust the
        selected row's value), so the keyboard path flips pages by walking
        the cursor past a page edge instead, and clicks jump it directly."""
        before = self.carousel.page
        if self.carousel.handle_tap(input_mgr) and self.carousel.page != before:
            self.cursor = self.carousel.page * _ROWS_PER_PAGE

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

        # Stage J6: only the cursor's page is drawn; the carousel (arrows
        # outside the panel's lateral edges) shows there's more.
        num_pages = math.ceil(len(self._rows) / _ROWS_PER_PAGE)
        self.carousel.set_num_pages(num_pages)
        self.carousel.page = self.cursor // _ROWS_PER_PAGE
        page_start = self.carousel.page * _ROWS_PER_PAGE

        f_row = font(14)
        f_val = font(14, bold=True)
        for slot, i in enumerate(range(page_start, min(page_start + _ROWS_PER_PAGE, len(self._rows)))):
            row = self._rows[i]
            y = self.py + _ROWS_START_Y + slot * _ROW_H
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

        self.carousel.draw(surface, font(13), indicator_y=self.py + _TITLE_Y + 24)

        # Stage I6 debugging: the login/sync row's own value text is
        # truncated to fit next to its label - when the cursor sits on that
        # row, show the FULL untruncated status here instead of the normal
        # control hint, wrapped to the panel width, so a real error message
        # is readable in-game without needing browser DevTools at all.
        if self.cursor == len(self._rows) - 1:
            email = net.get_email()
            who = email if email else "desconectado"
            full_status = f"{who} | {net.get_last_sync_status()}"
            f_hint = font(12)
            words = full_status.split(" ")
            lines, cur = [], ""
            for w in words:
                trial = f"{cur} {w}".strip()
                if f_hint.size(trial)[0] > _PANEL_W - 30 and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = trial
            if cur:
                lines.append(cur)
            lines = lines[:3]
            base_y = self.py + self._panel_h - 14 - (len(lines) - 1) * 14
            for i, line in enumerate(lines):
                draw_text(surface, line, f_hint, SUBTEXT, self.px + _PANEL_W // 2, base_y + i * 14)
        else:
            f_hint = font(13)
            draw_text(surface, "W/S seleciona | A/D ajusta | ESPACO aciona | F1 - Fechar",
                      f_hint, SUBTEXT, self.px + _PANEL_W // 2, self.py + self._panel_h - 24)
