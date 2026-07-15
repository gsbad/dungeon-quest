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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-port", type=int, default=8000)
    ap.add_argument("--backend-port", type=int, default=8090)
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--boot-timeout", type=float, default=40.0)
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--sample-every", type=float, default=20.0)
    args = ap.parse_args()

    ch._ensure_libasound()

    if not args.no_rebuild or not os.path.isdir(ch.BUILD_WEB):
        ch._build_pygbag()

    game_url = f"http://127.0.0.1:{args.game_port}/index.html"
    backend_health_url = f"http://127.0.0.1:{args.backend_port}/health"
    backend_cmd = [os.path.join(ch.ROOT, "backend", ".venv", "bin", "uvicorn"),
                   "app.main:app", "--port", str(args.backend_port)]
    static_cmd = [sys.executable, "-m", "http.server", str(args.game_port)]

    with ch._Server(backend_cmd, cwd=os.path.join(ch.ROOT, "backend"), ready_url=backend_health_url, name="backend"), \
         ch._Server(static_cmd, cwd=ch.BUILD_WEB, ready_url=game_url, name="static server (build/web)"):
        ok = asyncio.run(run_soak(game_url, backend_health_url, args.minutes, args.headed,
                                   args.boot_timeout, args.sample_every))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
