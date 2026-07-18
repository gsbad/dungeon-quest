"""
Coop-specific soak test - same "extended-session freeze" hypothesis as
tools/soak_test.py, but exercising the cooperative code path specifically
(net_coop.py's per-frame poll_messages()/send(), RemotePlayer per-frame
update()/draw(), the L10-L12 debuff/vengeance bookkeeping) instead of
single-player. Built after a single-player-only soak run (tools/soak_test.py)
came back inconclusive - old code and code with the per-frame-Surface-
allocation fixes applied showed statistically similar memory drift, which
doesn't rule out those fixes being worthwhile, but does mean the reported
freeze might have a different or additional root cause specifically in the
coop path, which no test so far had actually exercised for more than a
couple minutes.

Reuses tools/coop_harness.py's boot/room helpers directly (same backend +
build/web servers, same save injection, same "click #canvas -> Space to
continue -> open coop overlay -> create/join room" flow) instead of
duplicating them - this file only adds the "run both clients for N minutes
under continuous activity while sampling memory" part coop_harness.py
doesn't do (its own tests are all short, assertion-driven scenarios).

Tracks the SUM of RSS across every Chromium renderer-type process (there
are two real gameplay sessions in one browser instance here, host +
guest, and SystemInfo.getProcessInfo doesn't hand back a page-to-pid
mapping) - still a meaningful growth signal even without per-page
attribution.

Usage:
    python tools/coop_soak_test.py                    # ~4 min, default
    python tools/coop_soak_test.py --minutes 10
    python tools/coop_soak_test.py --no-rebuild
    python tools/coop_soak_test.py --headed
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coop_harness as ch  # noqa: E402


def _log(msg):
    print(f"[coop_soak] {msg}", flush=True)


async def _renderer_rss_total_kb(browser):
    """Sum of VmRSS across every renderer-type Chromium process - see
    tools/soak_test.py's _heap_bytes()/_renderer_pid() docstrings for why
    performance.memory alone isn't the right signal (JS heap only, not the
    WASM linear memory where pygame/SDL state actually lives)."""
    session = await browser.new_browser_cdp_session()
    info = await session.send("SystemInfo.getProcessInfo")
    total = 0
    found = False
    for proc in info.get("processInfo", []):
        if proc.get("type") != "renderer":
            continue
        pid = proc.get("id")
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1])
                        found = True
                        break
        except (FileNotFoundError, ProcessLookupError, ValueError):
            continue
    return total if found else None


async def run_soak(game_url, backend_health_url, minutes, headed, boot_timeout_s, sample_every_s):
    from playwright.async_api import async_playwright

    ch._wait_http_ok(backend_health_url, timeout_s=10)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed, args=[
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ])
        try:
            ctx_host = await browser.new_context(viewport={"width": ch.SW, "height": ch.SH})
            ctx_guest = await browser.new_context(viewport={"width": ch.SW, "height": ch.SH})
            page_host = await ctx_host.new_page()
            page_guest = await ctx_guest.new_page()

            errors_host, errors_guest = [], []
            page_host.on("pageerror", lambda e: errors_host.append(str(e)))
            page_guest.on("pageerror", lambda e: errors_guest.append(str(e)))

            _log("Host: entrando no jogo e criando room...")
            await ch._boot_into_gameplay(page_host, game_url, "SoakHost",
                                          os.path.join("/tmp", "coop_soak_host"), boot_timeout_s)
            await ch._open_coop_overlay(page_host)
            async with page_host.expect_response(
                    lambda r: "/coop/room" in r.url and r.request.method == "POST") as resp_info:
                await page_host.mouse.click(*ch.CREATE_ROOM_BUTTON)
            room_id = (await (await resp_info.value).json())["room_id"]
            _log(f"Room: {room_id}")
            await asyncio.sleep(1.5)

            _log("Guest: entrando no jogo e entrando na room...")
            await ch._boot_into_gameplay(page_guest, game_url, "SoakGuest",
                                          os.path.join("/tmp", "coop_soak_guest"), boot_timeout_s)
            await ch._open_coop_overlay(page_guest)
            await page_guest.mouse.click(*ch.JOIN_ROOM_BUTTON)
            await asyncio.sleep(0.3)
            await page_guest.keyboard.type(room_id)
            await page_guest.mouse.click(*ch.CONNECT_BUTTON)
            await asyncio.sleep(1.5)

            # Fecha os dois painéis cedo - mesma lição de coop_harness.py
            # sobre não deixar o coop_sync automático (L6) trocar a
            # GameplayState por baixo antes do ESC ter algo pra fechar.
            await page_host.keyboard.press("Escape")
            await page_guest.keyboard.press("Escape")
            await page_host.bring_to_front()
            await asyncio.sleep(4)  # tempo do coop_sync religar o modo rede

            _log(f"Em coop. Rodando {minutes} min de atividade contínua nos dois "
                 f"lados, amostrando RSS combinado a cada {sample_every_s}s...")

            samples = []
            r0 = await _renderer_rss_total_kb(browser)
            samples.append((0.0, r0))
            _log(f"RSS combinado inicial: {r0/1024:.1f} MB" if r0 is not None else "RSS indisponível")

            keys = ["w", "a", "s", "d"]
            deadline = time.monotonic() + minutes * 60
            next_sample = time.monotonic() + sample_every_s
            unresponsive_hits = 0
            round_i = 0
            while time.monotonic() < deadline:
                round_i += 1
                # Movimento + ataque alternando qual página está em
                # primeiro plano (bring_to_front) - as duas seguem
                # processando frames em segundo plano de qualquer forma
                # (confirmado repetidas vezes construindo coop_harness.py),
                # isso só evita o throttling mais agressivo de Chromium
                # acumulando ao longo de vários minutos.
                page = page_host if round_i % 2 == 0 else page_guest
                await page.bring_to_front()
                k = random.choice(keys)
                await page.keyboard.down(k)
                await asyncio.sleep(0.25)
                await page.keyboard.up(k)
                await page.keyboard.down("Space")
                await asyncio.sleep(0.15)
                await page.keyboard.up("Space")

                # Chat periódico - exercita o caminho novo de L13/L14
                # (ChatWidget + balão) nos dois lados.
                if round_i % 8 == 0:
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.15)
                    await page.keyboard.type("oi")
                    await asyncio.sleep(0.1)
                    await page.keyboard.press("Enter")

                now = time.monotonic()
                if now >= next_sample:
                    next_sample = now + sample_every_s
                    t_before = time.monotonic()
                    try:
                        await asyncio.wait_for(page_host.evaluate("() => 1+1"), timeout=5.0)
                        rtt = time.monotonic() - t_before
                    except asyncio.TimeoutError:
                        rtt = None
                        unresponsive_hits += 1
                    r = await _renderer_rss_total_kb(browser)
                    elapsed = now - (deadline - minutes * 60)
                    samples.append((elapsed, r))
                    rtt_txt = f"{rtt*1000:.0f}ms" if rtt is not None else "TIMEOUT (>5s)"
                    rss_txt = f"{r/1024:.1f} MB" if r is not None else "n/d"
                    _log(f"t={elapsed:5.0f}s  RSS combinado={rss_txt:>9}  round-trip(host)={rtt_txt}")

            _log(f"Erros de página - host: {errors_host}  guest: {errors_guest}")
            _log(f"Sondas de responsividade que estouraram 5s: {unresponsive_hits}")

            valid = [(t, r) for t, r in samples if r is not None]
            if len(valid) >= 3:
                t_start, r_start = valid[0]
                t_end, r_end = valid[-1]
                rate = (r_end - r_start) / max(1.0, (t_end - t_start))
                _log(f"RSS combinado: {r_start/1024:.1f} MB -> {r_end/1024:.1f} MB em "
                     f"{t_end-t_start:.0f}s ({rate:+.2f} KB/s)")
                ok = rate < 300 and unresponsive_hits == 0
            else:
                _log("RSS indisponível - resultado só cobre responsividade.")
                ok = unresponsive_hits == 0

            _log(f"RESULTADO: {'OK' if ok else 'SUSPEITO'}")
            return ok
        finally:
            await browser.close()


_PLAYER_W, _PLAYER_H = 32, 36  # game/player.py's Player.__init__


def _approx_screen_pos(world_x, world_y, guest_x, guest_y):
    """Bugfix round 3 finding: page.mouse.move() takes VIEWPORT pixels, not
    world/level coordinates - game/states.py's mouse-aim
    (`world_x, world_y = mx + self.camera.render_x, my + self.camera.render_y`)
    only lines up world==screen while the camera sits at (0, 0), i.e. only
    right next to level spawn. tools/coop_harness.py's own tests get away
    with passing world coords straight to mouse.move() because they stay
    within a few tiles of spawn the whole time - this soak run's guest
    wanders the whole map hunting enemies for minutes, so the camera
    (game/camera.py's Camera.follow(), a plain lerp-to-center-on-player)
    scrolls away from (0, 0) and the naive world-as-screen mouse position
    aims the attack in the wrong direction even while standing right next
    to the target (confirmed live: min_dist_to_target dropped to ~34px with
    zero new hit_request frames). Approximates Camera.follow()'s clamped
    lerp target (converges there quickly at its 8.0/s speed, and this bot's
    already stationary-ish once in melee range) well enough to aim
    correctly without needing to read the real camera object out of the
    page."""
    cam_x = guest_x + _PLAYER_W / 2 - ch.SW / 2
    cam_y = guest_y + _PLAYER_H / 2 - ch.SH / 2
    return world_x - cam_x, world_y - cam_y


def _count_type(frames, msg_type):
    n = 0
    for f in frames:
        try:
            d = json.loads(f)
        except (ValueError, TypeError):
            continue
        if d.get("type") == msg_type:
            n += 1
    return n


async def run_combat_soak(game_url, backend_health_url, minutes, headed, boot_timeout_s, sample_every_s):
    """Bugfix round 3: run_soak() above drives WASD+Space with no guarantee
    of ever standing near an enemy, and always boots a default (no-
    profession) guest - it could never have caught "guest freezes after a
    while" or "guest can't damage monsters" (both reported after the M-Q
    content wave), only the earlier chat-bubble memory leak it was built
    for. This variant boots the guest with a real profession (Guerreiro,
    via _make_save's `attributes` override - determine_profession() in
    game/professions.py needs >=20 spent points, all in strength, to land
    there instead of Aventureiro) and makes it actually hunt down and fight
    the nearest living enemy every round (game/level.py's melee hit_request
    path, plus the default hotbar's Fireball projectile every 5th round -
    game/states.py's _cast_generic_projectile) instead of idling.

    Two extra signals run_soak() doesn't track, straight from the 3 bug
    reports: (1) hit_request frames landing at all (and NOT going quiet for
    a long stretch once combat has started - "can't damage" and "freezes
    after a while" would both show up as this going silent), sampled from
    the host's real received WebSocket frames via ws_state, same source of
    truth tools/coop_harness.py's own assertions already use; (2) guest-
    side responsiveness specifically (run_soak only ever probed page_host),
    since the reports are explicit that only non-host players freeze."""
    from playwright.async_api import async_playwright

    ch._wait_http_ok(backend_health_url, timeout_s=10)
    shots_dir = os.path.join("/tmp", "coop_combat_soak_shots")
    os.makedirs(shots_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed, args=[
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ])
        try:
            session = await ch._connect_coop_session(
                browser, game_url, boot_timeout_s, shots_dir, tag="combat_",
                guest_attributes={"str": 40},
            )
            if not session["ok"]:
                _log("RESULTADO: FALHOU (não conseguiu nem conectar/sincronizar a room - ver log acima)")
                return False

            page_host, page_guest = session["page_host"], session["page_guest"]
            ws_state = session["ws_state"]
            errors_host, errors_guest = session["page_host_errors"], session["page_guest_errors"]

            # Bug #1 (profissão sempre Aventureiro): confirma que o "pos"
            # do guest, do jeito que o host realmente recebe pela rede, já
            # carrega profession="Guerreiro" - a mesma fonte que
            # RemotePlayer.apply_snapshot() (game/remote_player.py) consome
            # pra escolher o sprite.
            deadline = time.monotonic() + 5.0
            prof_ok = False
            while time.monotonic() < deadline:
                if ch._frames_contain(ws_state["host"]["frames"], "pos", profession="Guerreiro"):
                    prof_ok = True
                    break
                await asyncio.sleep(0.3)
            _log(f"Sync de profissão (Guerreiro) confirmado no host via \"pos\": {prof_ok}")
            await page_host.screenshot(path=os.path.join(shots_dir, "combat_host_profession_check.png"))

            _log(f"Em coop. Rodando {minutes} min de combate real (guest cacando o inimigo "
                 f"vivo mais proximo, host com atividade de fundo), amostrando a cada {sample_every_s}s...")

            samples = []
            r0 = await _renderer_rss_total_kb(browser)
            samples.append((0.0, r0))

            start = time.monotonic()
            deadline = start + minutes * 60
            next_sample = time.monotonic() + sample_every_s
            unresponsive_host = 0
            unresponsive_guest = 0
            last_hit_count = 0
            first_hit_seen = False
            stall_streak = 0
            max_stall_streak = 0
            round_i = 0
            # Diagnostic (bugfix round 3): how close the guest actually got
            # to its current target since the last sample - separates "the
            # bot's straight-line _walk_toward can't route around a wall to
            # reach the last enemy" (min_dist stays large) from "it got into
            # melee range and still landed nothing" (min_dist small, no new
            # hit_request - a real bug).
            min_dist_since_sample = None

            while time.monotonic() < deadline:
                round_i += 1

                await page_host.bring_to_front()
                # Bugfix round 3 diagnostic: a level-up auto-opens the
                # paperdoll on the stats tab (GameplayState.update()'s
                # pending_level_up branch) - Stage J2 made this dismissible
                # (not a hard lock), but a real player closes it with ESC/C
                # without thinking twice. A naive bot that only ever sends
                # WASD/Space/F wouldn't, and W/A/S/D get reinterpreted as
                # attribute nav while that panel is open instead of
                # movement - which would look exactly like "frozen, can't
                # move or attack" from outside. ESC every round here so a
                # genuine coop bug isn't masked by (or mistaken for) this.
                await page_host.keyboard.press("Escape")
                k = random.choice(["w", "a", "s", "d"])
                await page_host.keyboard.down(k)
                await asyncio.sleep(0.15)
                await page_host.keyboard.up(k)
                await page_host.keyboard.down("Space")
                await asyncio.sleep(0.12)
                await page_host.keyboard.up("Space")

                await page_guest.bring_to_front()
                await page_guest.keyboard.press("Escape")
                latest = ch._latest_enemies(ws_state["guest"]["frames"])
                gx, gy = ch._latest_pos(ws_state["host"]["frames"])
                alive = [e for e in (latest or {}).get("enemies", []) if e.get("alive")]
                target = (min(alive, key=lambda e: ch._dist(gx, gy, e["x"], e["y"]))
                          if alive and gx is not None else None)
                if target is not None:
                    eid = target["id"]

                    def _enemy_pos(eid=eid):
                        snap = ch._latest_enemies(ws_state["guest"]["frames"])
                        if not snap:
                            return None, None
                        e = next((e for e in snap["enemies"] if e.get("id") == eid), None)
                        return (e["x"], e["y"]) if e else (None, None)

                    await ch._walk_toward(page_guest, _enemy_pos,
                                           lambda: ch._latest_pos(ws_state["host"]["frames"]),
                                           tolerance=45, max_rounds=4)
                    ex, ey = _enemy_pos()
                    gx2, gy2 = ch._latest_pos(ws_state["host"]["frames"])
                    if ex is not None and gx2 is not None:
                        d = ch._dist(gx2, gy2, ex, ey)
                        min_dist_since_sample = d if min_dist_since_sample is None else min(min_dist_since_sample, d)
                        sx, sy = _approx_screen_pos(ex, ey, gx2, gy2)
                        await page_guest.mouse.move(sx, sy)
                    await page_guest.keyboard.down("Space")
                    await asyncio.sleep(0.15)
                    await page_guest.keyboard.up("Space")
                    if round_i % 5 == 0:
                        # Fireball - default hotbar spell for every profession
                        # (game/player.py's hotbar_spells starts at
                        # DEFAULT_SPELLS regardless of class kit), exercises
                        # the projectile hit_request path too, not just melee.
                        await page_guest.keyboard.down("f")
                        await asyncio.sleep(0.1)
                        await page_guest.keyboard.up("f")
                else:
                    kk = random.choice(["w", "a", "s", "d"])
                    await page_guest.keyboard.down(kk)
                    await asyncio.sleep(0.15)
                    await page_guest.keyboard.up(kk)

                now = time.monotonic()
                if now >= next_sample:
                    next_sample = now + sample_every_s
                    elapsed = now - start

                    async def _probe(page):
                        t0 = time.monotonic()
                        try:
                            await asyncio.wait_for(page.evaluate("() => 1+1"), timeout=5.0)
                            return time.monotonic() - t0
                        except asyncio.TimeoutError:
                            return None

                    rtt_host = await _probe(page_host)
                    rtt_guest = await _probe(page_guest)
                    if rtt_host is None:
                        unresponsive_host += 1
                    if rtt_guest is None:
                        unresponsive_guest += 1

                    hit_count = _count_type(ws_state["host"]["frames"], "hit_request")
                    new_hits = hit_count - last_hit_count
                    if hit_count > 0:
                        first_hit_seen = True
                    if first_hit_seen and new_hits == 0:
                        stall_streak += 1
                        max_stall_streak = max(max_stall_streak, stall_streak)
                    else:
                        stall_streak = 0
                    last_hit_count = hit_count

                    r = await _renderer_rss_total_kb(browser)
                    samples.append((elapsed, r))
                    rss_txt = f"{r/1024:.1f} MB" if r is not None else "n/d"
                    rtt_h_txt = f"{rtt_host*1000:.0f}ms" if rtt_host is not None else "TIMEOUT(>5s)"
                    rtt_g_txt = f"{rtt_guest*1000:.0f}ms" if rtt_guest is not None else "TIMEOUT(>5s)"
                    diag_snap = ch._latest_enemies(ws_state["guest"]["frames"])
                    diag_alive = sum(1 for e in (diag_snap or {}).get("enemies", []) if e.get("alive"))
                    diag_total = len((diag_snap or {}).get("enemies", []))
                    dist_txt = f"{min_dist_since_sample:.0f}px" if min_dist_since_sample is not None else "n/d"
                    _log(f"t={elapsed:5.0f}s  RSS={rss_txt:>9}  host_rtt={rtt_h_txt:>12}  "
                         f"guest_rtt={rtt_g_txt:>12}  hit_requests_total={hit_count} (+{new_hits})  "
                         f"alive_enemies={diag_alive}/{diag_total}  min_dist_to_target={dist_txt}")
                    min_dist_since_sample = None

            _log(f"Erros de pagina - host: {errors_host}  guest: {errors_guest}")
            _log(f"Sondas de responsividade que estouraram 5s - host: {unresponsive_host}  guest: {unresponsive_guest}")
            _log(f"Maior sequencia de janelas de amostragem SEM nenhum hit_request novo "
                 f"(depois do primeiro dano real): {max_stall_streak}")
            await page_host.screenshot(path=os.path.join(shots_dir, "combat_host_final.png"))
            await page_guest.screenshot(path=os.path.join(shots_dir, "combat_guest_final.png"))

            valid = [(t, r) for t, r in samples if r is not None]
            rss_ok = True
            if len(valid) >= 3:
                t_start, r_start = valid[0]
                t_end, r_end = valid[-1]
                rate = (r_end - r_start) / max(1.0, (t_end - t_start))
                _log(f"RSS combinado: {r_start/1024:.1f} MB -> {r_end/1024:.1f} MB em "
                     f"{t_end-t_start:.0f}s ({rate:+.2f} KB/s)")
                rss_ok = rate < 300

            ok = (prof_ok and not errors_host and not errors_guest
                  and unresponsive_guest == 0 and unresponsive_host == 0
                  and last_hit_count > 0 and max_stall_streak <= 2 and rss_ok)
            _log(f"RESULTADO: {'OK' if ok else 'SUSPEITO'}")
            return ok
        finally:
            await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-port", type=int, default=8000)
    ap.add_argument("--backend-port", type=int, default=8090)
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--boot-timeout", type=float, default=40.0)
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--sample-every", type=float, default=20.0)
    ap.add_argument("--combat", action="store_true",
                     help="roda run_combat_soak() (guest com profissao real cacando/atacando "
                          "inimigos de verdade) em vez do soak parado original")
    args = ap.parse_args()

    ch._ensure_libasound()

    if not args.no_rebuild or not os.path.isdir(ch.BUILD_WEB):
        ch._build_pygbag()

    game_url = f"http://127.0.0.1:{args.game_port}/index.html"
    backend_health_url = f"http://127.0.0.1:{args.backend_port}/health"
    backend_cmd = [os.path.join(ch.ROOT, "backend", ".venv", "bin", "uvicorn"),
                   "app.main:app", "--port", str(args.backend_port)]
    static_cmd = [sys.executable, "-m", "http.server", str(args.game_port)]

    scenario = run_combat_soak if args.combat else run_soak

    with ch._Server(backend_cmd, cwd=os.path.join(ch.ROOT, "backend"), ready_url=backend_health_url, name="backend"), \
         ch._Server(static_cmd, cwd=ch.BUILD_WEB, ready_url=game_url, name="static server (build/web)"):
        ok = asyncio.run(scenario(game_url, backend_health_url, args.minutes, args.headed,
                                   args.boot_timeout, args.sample_every))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
