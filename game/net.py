"""
Stage I2/I4: cloud-sync transport, following the same
`sys.platform == "emscripten"` + local `import js` bridge game/save.py
already uses for the save blob (_KEY = "dungeon_quest_save") and
game/states.py uses for the fullscreen toggle - not a new abstraction.

Two real constraints shape this module:
- No native networking exists inside the WASM sandbox at all (no `requests`,
  no `urllib`, no sockets) - the emscripten branch must go through
  `js.fetch`, a real browser call. The native/desktop branch (headless dev,
  `python main.py` without a browser) uses `urllib.request` from the stdlib
  instead of adding `requests` as a dependency - root requirements.txt stays
  pygame-only.
- main.py's loop calls `manager.update(dt)` synchronously every frame, not
  `await`ed - GameStateManager.update() is a plain method. So this module
  never blocks a caller: `schedule()` fires a coroutine on the already-
  running asyncio loop (main.py's `asyncio.run(main())`) and returns
  immediately; callers poll `poll_result()` once per frame instead.
"""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

_JWT_KEY = "dungeon_quest_jwt"
_EMAIL_KEY = "dungeon_quest_email"

# Desktop/native dev-only fallback - there's no window.DQ_API_BASE outside a
# browser tab. Stage I9's deployed HTTPS URL only ever needs to change the
# template's window.DQ_API_BASE; this constant stays a local-dev convenience.
_NATIVE_API_BASE = "http://127.0.0.1:8090"


def get_jwt():
    if sys.platform != "emscripten":
        return None
    import js
    return js.localStorage.getItem(_JWT_KEY) or None


def get_email():
    if sys.platform != "emscripten":
        return None
    import js
    return js.localStorage.getItem(_EMAIL_KEY) or None


def is_logged_in():
    return get_jwt() is not None


def _api_base():
    if sys.platform == "emscripten":
        import js
        return str(js.DQ_API_BASE)
    return _NATIVE_API_BASE


class HTTPError(Exception):
    """Carries the response status so callers (e.g. trigger_sync()'s "no
    save on server yet" 404 case) can branch on it instead of parsing a
    formatted string."""

    def __init__(self, method, path, status, detail):
        super().__init__(f"{method} {path} -> {status}: {detail}")
        self.status = status


async def _fetch_json_emscripten(path, method, jwt, body):
    # History (all confirmed live, in order):
    # (1)-(5) six structurally different ways of attaching an Authorization
    # header from inside pygbag's fetch()/XMLHttpRequest all ended in the
    # same server-side "missing bearer token" - the header never left the
    # browser under any encoding (ruled out CORS block, service worker,
    # extensions). Fix: stopped depending on a browser-delivered header -
    # the JWT moved into the URL as a `token` query param instead (backend's
    # _extract_token() in backend/app/main.py accepts it there).
    # (7) with the header question closed, switched _fetch_json_emscripten
    # to plain `await fetch(url, opts_js)` (query-param URL, no custom
    # headers needed at all anymore). The debug panel's breadcrumb trail
    # (_last_sync_status, added after print() was confirmed to never reach
    # the browser console in this build at all - not even a print() at the
    # very top of trigger_sync(), before any await) showed execution
    # permanently stuck on "1 GET starting", yet DevTools' console AND
    # Network tab both showed the real GET completing with a real 404. The
    # browser genuinely finishes the HTTP round trip; the Promise `await
    # fetch(...)` is waiting on just never resumes the Python coroutine in
    # this build, for a cross-origin request specifically (matches an
    # earlier session's note that this build's request path traced through
    # an EM_ASM/synchronous-XHR mechanism rather than a native
    # Promise-based fetch).
    # Fix: stop `await`ing a JsProxy-wrapped Promise directly. Go back to
    # XMLHttpRequest (attempt 6 already proved xhr.onload/onerror correctly
    # resume a Python asyncio Future via create_once_callable - that part
    # never was the problem, only the Authorization header was, at the time)
    # combined with the query-param URL from (7) - no headers to set at all
    # now, so this is strictly simpler than attempt 6.
    # Mirrors sync_state()'s breadcrumb trick: written to the same
    # _last_sync_status the debug panel already reads live, so a hang here
    # (no exception, nothing in the console - see the history above) still
    # leaves a visible trace of exactly which step never returned.
    global _last_sync_status

    step = "import js"
    try:
        import js

        step = "build url"
        sep = "&" if "?" in path else "?"
        url = _api_base() + path
        if jwt:
            url += f"{sep}token={jwt}"

        # Both js.XMLHttpRequest.new() (confirmed broken in this pygbag/
        # pyodide build for JS constructors in general - attempt 2's
        # js.Headers.new() hit the identical "'NoneType' object is not
        # callable" TypeError) and calling js.XMLHttpRequest() directly
        # (the browser's own native error: "Please use the 'new' operator,
        # this DOM object constructor cannot be called as a function")
        # fail - both confirmed live via an E2E test (headless Chromium
        # through Playwright, driving the real debug panel's Login/Sync row
        # so the full untruncated error text was readable). js.eval() is a
        # plain native JS function (not a constructor itself, no `new`
        # question to even ask) that every build has, and running `new
        # XMLHttpRequest()` as a JS string inside it sidesteps pyodide's
        # broken constructor-proxy binding entirely.
        step = "js.eval(new XMLHttpRequest())"
        xhr = js.eval("new XMLHttpRequest()")

        step = "xhr.open()"
        xhr.open(method, url, True)

        if body is not None:
            xhr.setRequestHeader("Content-Type", "application/json")

        step = "xhr.send()"
        xhr.send(json.dumps(body) if body is not None else None)

        # pyodide.ffi.create_once_callable doesn't exist in this build
        # (ImportError, confirmed live) so onload/onerror callbacks are out.
        # Poll xhr.readyState instead - no pyodide.ffi surface needed at
        # all, just plain JsProxy attribute reads (already proven to work:
        # xhr.status/xhr.responseText below read the same way). readyState
        # 4 == DONE per the XHR spec. asyncio.sleep(0) each iteration yields
        # to the browser event loop exactly like main.py's frame loop
        # already does every frame, so the real XHR has a chance to
        # progress between polls.
        step = "xhr:polling readyState"
        _last_sync_status = step
        # Stage I7: offline-first means a backend that's down/unreachable
        # must never cost the game more than a bounded, silent failure - a
        # hung TCP connection (as opposed to an immediate connection-refused,
        # which already resolves readyState==4/status==0 fast) would
        # otherwise poll forever with no upper bound.
        deadline = time.monotonic() + 8.0
        while xhr.readyState != 4:
            if time.monotonic() > deadline:
                xhr.abort()
                raise RuntimeError("XHR timed out after 8s")
            await asyncio.sleep(0)
        _last_sync_status = "xhr:readyState reached 4"

        step = "read status/responseText"
        status = xhr.status
        text = xhr.responseText
    except Exception as e:
        raise RuntimeError(f"[{step}] {e!r}") from e

    if status == 0:
        # readyState reached DONE but status 0 means the browser never got
        # an actual HTTP response (network failure, DNS, connection
        # refused, or a CORS block) - not a valid HTTPError to parse.
        raise RuntimeError("XHR network error (status 0)")
    if status >= 400:
        raise HTTPError(method, path, status, text)
    return json.loads(text) if text else {}


def _fetch_json_native(path, method, jwt, body):
    data = None
    req = urllib.request.Request(_api_base() + path, method=method)
    if jwt:
        req.add_header("Authorization", f"Bearer {jwt}")
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=5) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise HTTPError(method, path, e.code, detail) from e


async def fetch_json(path, method="GET", jwt=None, body=None):
    """Single entry point both branches share - Stage I6's call sites never
    need to branch on sys.platform themselves."""
    if sys.platform == "emscripten":
        return await _fetch_json_emscripten(path, method, jwt, body)
    return await asyncio.to_thread(_fetch_json_native, path, method, jwt, body)


_pending_results = {}
_next_tag = 0

# asyncio.ensure_future() only keeps a WEAK reference to the Task inside the
# event loop - nothing else in this module held a strong one, so the GC was
# free to collect a fire-and-forget Task before it ever got a turn to run
# (no exception, no console output - it just silently never executes; this
# is the exact pitfall the asyncio docs warn about under create_task()).
# schedule() and trigger_sync() both add their Task here and let this set's
# own done-callback drop it once finished, so at least one strong reference
# survives for the Task's whole lifetime.
_background_tasks = set()


def _track(coro):
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def schedule(path, method="GET", jwt=None, body=None, tag=None):
    """Fire-and-forget: schedules the request on the already-running asyncio
    loop (main.py's asyncio.run(main())) and returns a tag immediately,
    without blocking the caller. Result shows up in poll_result(tag) once
    the request finishes - could be several frames later, or never if the
    tag is never polled (that's fine, offline-first: a dropped sync attempt
    must never block gameplay)."""
    global _next_tag
    if tag is None:
        tag = _next_tag
        _next_tag += 1

    async def _run():
        try:
            result = await fetch_json(path, method, jwt, body)
            _pending_results[tag] = ("ok", result)
        except Exception as e:
            _pending_results[tag] = ("error", str(e))

    _track(_run())
    return tag


def poll_result(tag):
    """(status, value) for a finished request, popping it - or None if the
    request hasn't finished yet (or was never scheduled/already polled)."""
    return _pending_results.pop(tag, None)


# Last outcome of a sync_state() call, for the debug panel (Stage I2's
# login-status row) - sync_state() itself must never raise, which also means
# it has no other way to surface *why* a sync failed for diagnosis.
_last_sync_status = "never attempted"


def get_last_sync_status():
    return _last_sync_status


async def sync_state(save_state):
    """Stage I6: the full offline-first round trip, fired from the same
    call sites that already do a local save.save(save_state) (see
    trigger_sync() below). Never raises - a dropped/failed sync must never
    surface as a crash or a blocked frame, the local save (already written
    by the caller before this coroutine even starts) stays authoritative
    either way.

    save_state is mutated in place (clear+update, not reassigned) rather
    than replaced, since callers (game/states.py etc.) hold long-lived
    references to this exact dict - a reassignment here wouldn't be visible
    to them."""
    import game.save as save
    global _last_sync_status

    jwt = get_jwt()
    if not jwt:
        _last_sync_status = "not logged in"
        return

    # print() is confirmed NOT to reach the browser DevTools console in this
    # pygbag build (a print() at the very top of trigger_sync(), before any
    # await, never showed up even though the GET it leads to demonstrably
    # fires) - _last_sync_status itself is the only channel proven visible
    # (the debug panel reads it live), so every stage below leaves a
    # breadcrumb in it, not just the failure paths. A stage's breadcrumb
    # staying on screen after the action means execution stopped exactly
    # there.
    _last_sync_status = "1 GET starting"
    remote = None
    try:
        remote = await fetch_json("/save", "GET", jwt=jwt)
        _last_sync_status = "2 GET ok(200)"
    except HTTPError as e:
        _last_sync_status = f"2 GET HTTPError {e.status}"
        if e.status != 404:  # 404 = nothing on the server yet, local wins by default
            _last_sync_status = f"GET failed: {e}"
            return
    except Exception as e:
        _last_sync_status = f"GET unreachable: {e!r}"
        return  # backend unreachable/offline - local save already stands

    _last_sync_status = "3 before merge/PUT"
    if remote is not None:
        merged = save.merge_states(save_state, remote["state"], save.get_synced_at(), remote["updated_at"])
        save_state.clear()
        save_state.update(merged)
        save.save(save_state)

    _last_sync_status = "4 PUT starting"
    try:
        put_result = await fetch_json("/save", "PUT", jwt=jwt, body={"state": save_state})
        save.set_synced_at(put_result["updated_at"])
        _last_sync_status = "ok"
    except Exception as e:
        _last_sync_status = f"PUT failed: {e!r}"
        # merged copy (if any) is already persisted locally above regardless


def trigger_sync(save_state):
    """Fire-and-forget entry point for the existing local-save call sites
    (game/states.py, game/merchant.py, game/debug_panel.py) - schedules
    sync_state() on the already-running asyncio loop and returns
    immediately, exactly like schedule() does for a single request."""
    global _last_sync_status
    # Set synchronously, before the Task even gets a turn to run - if the
    # debug panel never shows this (even "0 scheduled" flashing by), this
    # function was never called at all, as opposed to sync_state() starting
    # and stalling somewhere past its first await.
    _last_sync_status = "0 scheduled"
    _track(sync_state(save_state))


async def _fetch_and_apply_balance():
    try:
        config = await fetch_json("/balance", "GET")
    except Exception:
        return  # offline/backend down - game.balance_config's defaults stand
    import game.balance_config as balance_config
    balance_config.apply_overrides(config)


def trigger_balance_fetch():
    """Stage I4: fire-and-forget at boot (game/states.py's
    GameStateManager.__init__) - the game already runs fine on the code's
    own defaults immediately, so this never blocks startup; whenever/if it
    resolves, it live-patches ITEMS/DIFFICULTIES/SPELLS/game.stats in
    place. No JWT needed - /balance is a public endpoint, same as /health."""
    _track(_fetch_and_apply_balance())
