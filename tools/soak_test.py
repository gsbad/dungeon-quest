"""
Soak test for the "extended-session freeze" bug class (see game/theme.py's
font() cache for the original diagnosis: per-frame Surface/Font allocation
on the WASM/emscripten heap - cheap-ish natively, but a heap that grows and
rarely shrinks turns steady per-frame churn into a tab that gradually slows
down and eventually freezes solid, with no console error).

A single screenshot/short Playwright run (the project's normal testing
discipline, see docs/architecture.md's "Testes" section) can't catch this
class of bug by construction - it only shows up after real time passes.
This tool instead runs one real browser session for several minutes of
continuous simulated play, sampling `performance.memory.usedJSHeapSize`
(Chromium-only, no special launch flag needed for the coarse-grained
version this script uses) at a fixed cadence, and reports the growth
trend - a roughly flat/plateauing sampled series means no meaningful
unbounded per-frame allocation is happening; steady linear growth means
something is still allocating every frame without ever being freed/reused.

Deliberately exercises BOTH classes of previously-found offender at once:
- Desktop-only-once: sound/fullscreen buttons (game/audio.py,
  game/input_system.py) draw unconditionally on every screen, every
  frame, regardless of platform - a single tap to enable touch controls
  below doesn't turn these off.
- Mobile-only, but the worse of the two: once a touch context activates
  `InputManager.touch_active` (Stage K24 - a one-way flag, never resets
  for the rest of the session), ~12 virtual controls (joystick + attack/
  dash/pickaxe/pause/3 spell/3 item/debug buttons) draw every frame
  regardless of whether they're actually being touched right now - see
  InputManager.draw()'s `if not self.touch_active: return` guard.
This script creates the browser context with `has_touch=True` and taps
once early specifically to light up that second, larger code path for
the whole test, on top of ordinary WASD/attack/menu activity exercising
the first.

Usage:
    python tools/soak_test.py                       # ~3 min, default
    python tools/soak_test.py --minutes 10           # longer soak
    python tools/soak_test.py --no-rebuild           # reuse build/web
    python tools/soak_test.py --headed               # watch it live
"""
import argparse
import asyncio
import ctypes.util
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_WEB = os.path.join(ROOT, "build", "web")
ALSA_CACHE = os.path.join(ROOT, "build", ".alsa-workaround")

SW, SH = 800, 600


def _log(msg):
    print(f"[soak_test] {msg}", flush=True)


def _ensure_libasound():
    """Same workaround as tools/coop_harness.py - see that file for why."""
    if ctypes.util.find_library("asound"):
        return
    libdir = os.path.join(ALSA_CACHE, "usr", "lib", "x86_64-linux-gnu")
    if not os.path.isdir(libdir):
        _log("libasound.so.2 ausente - baixando/extraindo sem root (uma vez só)...")
        os.makedirs(ALSA_CACHE, exist_ok=True)
        subprocess.run(["apt-get", "download", "libasound2t64"], cwd=ALSA_CACHE, check=False)
        debs = [f for f in os.listdir(ALSA_CACHE) if f.endswith(".deb")]
        if debs:
            subprocess.run(["dpkg-deb", "-x", debs[0], ALSA_CACHE], cwd=ALSA_CACHE, check=False)
    if os.path.isdir(libdir):
        os.environ["LD_LIBRARY_PATH"] = libdir + ":" + os.environ.get("LD_LIBRARY_PATH", "")


def _wait_http_ok(url, timeout_s):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"timeout esperando {url} responder 200")


def _build_pygbag():
    _log("Empacotando o build pygbag (main.py + pygbag_template.tmpl)...")
    r = subprocess.run(
        [sys.executable, "-m", "pygbag", "--build", "--width", str(SW), "--height", str(SH),
         "--template", "pygbag_template.tmpl", "main.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"pygbag --build falhou:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    _log("Build pronto em build/web/.")


class _Server:
    def __init__(self, cmd, cwd, ready_url, name):
        self.cmd, self.cwd, self.ready_url, self.name = cmd, cwd, ready_url, name
        self.proc = None

    def __enter__(self):
        _log(f"Subindo {self.name}: {' '.join(self.cmd)}")
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            _wait_http_ok(self.ready_url, timeout_s=20)
        except RuntimeError:
            self.proc.terminate()
            raise
        _log(f"{self.name} no ar.")
        return self

    def __exit__(self, *exc):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _make_save(name):
    return {
        "version": 8,
        "character": {
            "name": name, "level": 1, "xp": 0, "unspent_points": 0,
            "attributes": {"str": 10, "dex": 10, "int": 10, "wis": 10, "vig": 10, "lck": 10},
        },
        "progression": {
            "current_difficulty": "normal", "highest_level_cleared": {"normal": 0},
            "cleared_difficulties": [], "levels_seen": [],
        },
        "counters": {"kills": {}, "boss_kills": {}, "deaths": 0, "playtime_s": 0.0},
        "settings": {"muted": True, "keybinds": {}},
        "gold": 0, "inventory": {}, "hotbar_items": ["health_potion", "mana_potion", "antidote"],
    }


async def _heap_bytes(page):
    """None if performance.memory isn't exposed (non-Chromium) - caller
    treats that as "can't measure", not "zero growth". Kept alongside the
    RSS probe below (not on its own) - a first pass at this soak test
    trusted this metric alone and it stayed dead flat on BOTH the fixed
    AND the pre-fix code, which turned out to be a methodology gap, not a
    real absence of the bug: performance.memory.usedJSHeapSize only
    tracks the V8 JS object heap. The actual Python interpreter and
    every pygame/SDL Surface pygbag creates live in the WASM module's
    linear memory instead - a completely separate arena this call can't
    see into at all. Real signal is _renderer_rss_kb() below."""
    try:
        val = await page.evaluate("() => (performance.memory ? performance.memory.usedJSHeapSize : null)")
        return val
    except Exception:
        return None


async def _renderer_pid(browser):
    """The OS pid of the renderer process actually running our page - a
    browser-level CDP session (not a page-level one; SystemInfo is a
    browser domain) lists every Chromium subprocess by type. Only one
    "renderer" is expected since this script only ever opens one page."""
    session = await browser.new_browser_cdp_session()
    info = await session.send("SystemInfo.getProcessInfo")
    for proc in info.get("processInfo", []):
        if proc.get("type") == "renderer":
            return proc.get("id")
    return None


def _rss_kb(pid):
    """Real resident memory of the renderer process, /proc directly (same
    machine, no CDP round-trip needed) - this is what actually shows a
    WASM linear-memory leak: growth here with a flat JS heap is exactly
    the signature that would slip past _heap_bytes() alone."""
    if pid is None:
        return None
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])  # kB
    except (FileNotFoundError, ProcessLookupError, ValueError):
        return None
    return None


async def run_soak(game_url, minutes, headed, boot_timeout_s, sample_every_s):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # --enable-precise-memory-info: without it usedJSHeapSize is still
        # readable but bucketed/coarser - fine for a growth TREND, but the
        # flag makes samples less noisy and easier to eyeball.
        browser = await p.chromium.launch(headless=not headed, args=[
            "--enable-precise-memory-info",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ])
        try:
            # has_touch=True: lets a single synthetic tap flip
            # InputManager.touch_active permanently, exercising the mobile
            # virtual-control draw path (the bigger of the two suspects)
            # for the whole soak, not just the always-on desktop buttons.
            ctx = await browser.new_context(viewport={"width": SW, "height": SH}, has_touch=True)
            page = await ctx.new_page()

            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            save = _make_save("SoakTester")
            await page.add_init_script(f'localStorage.setItem("dungeon_quest_save", {json.dumps(json.dumps(save))});')

            async with page.expect_request(lambda r: "/balance" in r.url, timeout=boot_timeout_s * 1000):
                await page.goto(game_url)
                await page.click("#canvas")
            await asyncio.sleep(3)
            await page.keyboard.press("Space")  # CONTINUAR
            await asyncio.sleep(1.5)

            # One tap near the joystick's usual corner - just needs to land
            # inside the canvas to register as a real touch/FINGERDOWN and
            # flip touch_active for good; exact position doesn't matter
            # since gameplay itself proceeds via keyboard below.
            await page.touchscreen.tap(120, SH - 120)
            await asyncio.sleep(0.5)

            _log(f"Em jogo. Rodando {minutes} min de atividade contínua, "
                 f"amostrando heap a cada {sample_every_s}s...")

            renderer_pid = await _renderer_pid(browser)
            if renderer_pid is None:
                _log("AVISO: não consegui achar o pid do processo renderer via "
                     "SystemInfo.getProcessInfo - só o heap JS vai ser medido.")
            else:
                _log(f"Processo renderer: pid {renderer_pid}")

            samples = []
            t0 = await _heap_bytes(page)
            r0 = _rss_kb(renderer_pid)
            samples.append((0.0, t0, r0))
            heap_txt = f"{t0/1e6:.2f} MB" if t0 is not None else "n/d"
            rss_txt = f"{r0/1024:.1f} MB" if r0 is not None else "n/d"
            _log(f"Inicial: heap JS={heap_txt}  RSS do renderer={rss_txt}")

            keys = ["w", "a", "s", "d"]
            deadline = time.monotonic() + minutes * 60
            next_sample = time.monotonic() + sample_every_s
            unresponsive_hits = 0
            round_i = 0
            while time.monotonic() < deadline:
                round_i += 1
                # Movement (also keeps the joystick's knob-position math
                # live, though the button/joystick surfaces themselves
                # stay cached now regardless of movement).
                k = random.choice(keys)
                await page.keyboard.down(k)
                await asyncio.sleep(0.3)
                await page.keyboard.up(k)

                # Attack a few times (K23 hold-to-fire needs a real hold).
                await page.keyboard.down("Space")
                await asyncio.sleep(0.15)
                await page.keyboard.up("Space")

                # Periodically open/close a menu (paperdoll) and re-tap the
                # touch controls area, so press_flash/alpha animate through
                # their full range repeatedly instead of sitting idle.
                if round_i % 5 == 0:
                    await page.keyboard.press("c")
                    await asyncio.sleep(0.2)
                    await page.keyboard.press("c")
                if round_i % 3 == 0:
                    await page.touchscreen.tap(120, SH - 120)

                now = time.monotonic()
                if now >= next_sample:
                    next_sample = now + sample_every_s
                    # Responsiveness probe: a stalled/frozen main thread
                    # delays even a trivial JS round trip - this is the
                    # same signal that (accidentally) surfaced Chromium
                    # background-tab throttling while building
                    # tools/coop_harness.py earlier this project.
                    t_before = time.monotonic()
                    try:
                        await asyncio.wait_for(page.evaluate("() => 1+1"), timeout=5.0)
                        rtt = time.monotonic() - t_before
                    except asyncio.TimeoutError:
                        rtt = None
                        unresponsive_hits += 1
                    h = await _heap_bytes(page)
                    r = _rss_kb(renderer_pid)
                    elapsed = now - (deadline - minutes * 60)
                    samples.append((elapsed, h, r))
                    rtt_txt = f"{rtt*1000:.0f}ms" if rtt is not None else "TIMEOUT (>5s, congelado?)"
                    heap_txt = f"{h/1e6:.2f} MB" if h is not None else "n/d"
                    rss_txt = f"{r/1024:.1f} MB" if r is not None else "n/d"
                    _log(f"t={elapsed:5.0f}s  heap={heap_txt:>10}  RSS={rss_txt:>9}  round-trip={rtt_txt}")

            await page.screenshot(path=os.path.join(ROOT, "build", "soak_test_final.png"))

            _log(f"Erros de página durante o teste: {page_errors}")
            _log(f"Sondas de responsividade que estouraram 5s (congelamento real): {unresponsive_hits}")

            def _rate(field_idx):
                """field_idx: 0 for heap bytes, 1 for RSS kB, within each
                sample's (elapsed, heap, rss) tuple (heap/rss offset by
                the leading elapsed field, hence +1 below)."""
                valid = [(t, s[field_idx]) for t, s in ((row[0], row[1:]) for row in samples)
                         if s[field_idx] is not None]
                if len(valid) < 3:
                    return None, None, None
                t_start, v_start = valid[0]
                t_end, v_end = valid[-1]
                return v_start, v_end, (v_end - v_start) / max(1.0, (t_end - t_start))

            heap_start, heap_end, heap_rate = _rate(0)
            rss_start, rss_end, rss_rate = _rate(1)

            if heap_rate is not None:
                _log(f"Heap JS: {heap_start/1e6:.2f} MB -> {heap_end/1e6:.2f} MB "
                     f"({heap_rate/1e3:+.2f} KB/s)")
            if rss_rate is not None:
                _log(f"RSS do renderer: {rss_start/1024:.1f} MB -> {rss_end/1024:.1f} MB "
                     f"({rss_rate:+.2f} KB/s)")

            # RSS is the real signal (covers the WASM linear-memory arena
            # where pygame/SDL Surfaces actually live - see _heap_bytes()'s
            # docstring for why the JS heap alone missed this on a first
            # pass). Heuristic threshold, not a hard proof: some KB/s of
            # drift is ordinary (level data, sprite cache warming up,
            # allocator fragmentation settling) - sustained unbounded
            # per-frame Surface churn reads as hundreds of KB/s to low
            # MB/s given how many draw() calls run per second across every
            # always-on control this soak deliberately exercises.
            if rss_rate is not None:
                ok = rss_rate < 200 and unresponsive_hits == 0
            elif heap_rate is not None:
                _log("AVISO: RSS indisponível, caindo pro heap JS (sinal mais fraco).")
                ok = heap_rate < 50_000 and unresponsive_hits == 0
            else:
                _log("Nenhuma métrica de memória disponível - resultado só cobre responsividade.")
                ok = unresponsive_hits == 0

            _log(f"RESULTADO: {'OK' if ok else 'SUSPEITO'} - "
                 f"{'sem crescimento de memória sustentado nem travamento' if ok else 'ver amostras acima'}.")
            return ok
        finally:
            await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-port", type=int, default=8000)
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--boot-timeout", type=float, default=40.0)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--sample-every", type=float, default=15.0)
    args = ap.parse_args()

    _ensure_libasound()

    if not args.no_rebuild or not os.path.isdir(BUILD_WEB):
        _build_pygbag()

    # 127.0.0.1, não localhost - mesmo motivo de tools/coop_harness.py
    # (pygbag resolve o CDN do pygame_ce errado com o hostname "localhost").
    game_url = f"http://127.0.0.1:{args.game_port}/index.html"
    static_cmd = [sys.executable, "-m", "http.server", str(args.game_port)]

    with _Server(static_cmd, cwd=BUILD_WEB, ready_url=game_url, name="static server (build/web)"):
        ok = asyncio.run(run_soak(game_url, args.minutes, args.headed, args.boot_timeout, args.sample_every))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
