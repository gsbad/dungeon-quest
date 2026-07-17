"""
Stage L1.5 (docs/coop-implementation-plan.md): harness Playwright pra testar
o modo coop com DOIS BrowserContexts reais coordenados no mesmo processo,
cada um entrando na mesma room - a lacuna que a disciplina de testes atual
(Playwright headless, 1 browser, screenshot) não cobre (risco #5 da
feasibility study). Construído logo depois de L1-L4 estarem de pé, não
adiado pra depois - pensado pra ser reusado sem mudança nas Fases 2/3
(sync de combate, PvP, chat), não só nesta. Já reusado uma vez pra validar
L5 (Stage 2): depois de confirmar que os dois estão na mesma room, fecha o
BrowserContext do host e confirma que o WebSocket coop do guest fecha
sozinho (decisão #4 - sem migração de host, a sessão acaba pros demais).

Este harness JÁ achou dois bugs reais que nenhum teste anterior (1 browser
+ 1 cliente `websockets` cru simulando o segundo jogador) pegaria: uma
colisão de player_id entre duas instâncias WASM separadas (game/net_coop.py)
e um vazamento de foco de teclado entre o campo de código da room e os
atalhos de dev M/N (game/states.py) - ver o histórico de commits/memória
do projeto pros detalhes. Vale manter estendendo em vez de descartar.

O que este script NÃO faz: ler texto renderizado no canvas via OCR/pixel
(frágil, e nenhuma dependência de OCR existe no projeto). Em vez disso
observa o tráfego real - resposta HTTP de POST /coop/room, frames do
WebSocket coop - via `page.on("response")`/`page.on("websocket")` do
Playwright, e mesmo assim navega a UI de verdade (clique/teclado) pros dois
lados, não um atalho por trás da UI. Screenshots em cada etapa continuam
sendo tiradas (mesmo padrão que já valeu a pena nesta sessão - ver memória
de projeto sobre automação Playwright) como conferência visual adicional,
não como a fonte de verdade do teste.

Pré-requisitos que este script GERENCIA sozinho (sobe e derruba):
- Backend real (backend/app/main.py) via uvicorn, porta --backend-port.
- Build pygbag (main.py + pygbag_template.tmpl) servido estaticamente,
  porta --game-port.

Uso:
    python tools/coop_harness.py
    python tools/coop_harness.py --no-rebuild        # reusa build/web existente
    python tools/coop_harness.py --headed             # útil pra debugar ao vivo

Stage (bugfix round, ver .claude/plans): duas novas verificações depois de
um playtest real ter achado que blocos quebrados e monstros mortos por um
lado não sumiam pro outro. run_world_sync_test() cobre as duas - rodada
separada de run_test() (sessão coop própria, fechada no final) em vez de
inserida no meio da sequência PvP/downed/revive já delicada de run_test,
pra não herdar o risco de deriva de posição/câmera que aquela sequência
já acumula (knockback repetido desloca os dois jogadores de forma
imprevisível). Reaproveita a mesma sequência de boot/join (extraída pra
_connect_coop_session) em vez de duplicá-la.
"""
import argparse
import asyncio
import ctypes.util
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_WEB = os.path.join(ROOT, "build", "web")
ALSA_CACHE = os.path.join(ROOT, "build", ".alsa-workaround")

# game/theme.py's SW/SH e as posições de game/states.py's CoopButton/
# CoopOverlay - hardcoded aqui de propósito (mesmo trade-off que qualquer
# harness de UI tem: se esses números mudarem no jogo, este script precisa
# acompanhar, não há como descobrir a posição de um botão desenhado num
# canvas de outra forma sem instrumentar o jogo só pra teste).
SW, SH = 800, 600
COOP_BUTTON = (SW - 40, 316)
CREATE_ROOM_BUTTON = (SW // 2, SH // 2 - 150 + 100)   # (400, 250)
JOIN_ROOM_BUTTON = (SW // 2, SH // 2 - 150 + 150)     # (400, 300)
CONNECT_BUTTON = (SW // 2, SH // 2 - 150 + 165)        # (400, 315)

# game/level.py's LEVEL_MAPS[1] - o pequeno bloco de parede interior em
# (col=6, row=2)/(col=7, row=2), a 4 tiles a direita do player_start (2,2)
# na mesma linha (nenhum movimento vertical necessario). Hardcoded (nao lido
# via rede, ao contrario de posicao de jogador/inimigo) porque geometria de
# parede e estatica - se LEVEL_MAPS[1] mudar, este script precisa
# acompanhar, mesmo trade-off que COOP_BUTTON etc acima.
WALL_TILE_COL, WALL_TILE_ROW = 6, 2
TILE = 48


def _log(msg):
    print(f"[coop_harness] {msg}", flush=True)


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _latest_pos(frames):
    """Ultima posicao de MUNDO real vista numa lista de frames WS - a
    mesma fonte de verdade que o L7 (PvP) ja usa em vez de adivinhar
    posicao de tela: `frames` sao mensagens RECEBIDAS por um lado (logo,
    a posicao TRANSMITIDA pelo outro lado)."""
    x = y = None
    for f in frames:
        try:
            d = json.loads(f)
        except (ValueError, TypeError):
            continue
        if d.get("type") == "pos":
            x, y = d.get("x"), d.get("y")
    return x, y


def _latest_downed(frames):
    downed = None
    hp = None
    for f in frames:
        try:
            d = json.loads(f)
        except (ValueError, TypeError):
            continue
        if d.get("type") == "pos":
            downed, hp = d.get("downed"), d.get("hp")
    return downed, hp


def _latest_enemies(frames):
    """Ultima mensagem "enemies" (snapshot completo, ver game/states.py)
    vista numa lista de frames - None se nenhuma ainda chegou."""
    latest = None
    for f in frames:
        try:
            d = json.loads(f)
        except (ValueError, TypeError):
            continue
        if d.get("type") == "enemies":
            latest = d
    return latest


def _frames_contain(frames, msg_type, **fields):
    """True se algum frame na lista e do `msg_type` dado e (opcionalmente)
    bate com os pares campo=valor extras - usado pelas novas checagens de
    "block_broken"/"hit_request" abaixo, mesmo estilo dos checks
    `enemies_seen`/`pvp_seen`/`chat_seen` que run_test ja fazia com
    substring matching, so que via json.loads pra poder checar campos
    especificos (col/row/enemy_id) em vez de so o tipo."""
    for f in frames:
        try:
            d = json.loads(f)
        except (ValueError, TypeError):
            continue
        if d.get("type") != msg_type:
            continue
        if all(d.get(k) == v for k, v in fields.items()):
            return True
    return False


async def _walk_toward(page, target_fn, self_pos_fn, tolerance=50, max_rounds=30):
    """Anda o jogador de `page` em direcao a `target_fn()` (um (x, y) de
    MUNDO, fixo ou dinamico) lendo a posicao real via `self_pos_fn()`
    (mesma tecnica de correcao dinamica que o L7/downed-chase de run_test
    ja usa em vez de um passo as cegas de duracao fixa) a cada rodada, ate
    ficar a `tolerance`px ou esgotar `max_rounds`. Retorna True se chegou
    perto o bastante."""
    for _ in range(max_rounds):
        tx, ty = target_fn()
        sx, sy = self_pos_fn()
        if None in (tx, ty, sx, sy):
            await asyncio.sleep(0.3)
            continue
        if _dist(sx, sy, tx, ty) <= tolerance:
            return True
        dx, dy = tx - sx, ty - sy
        key = ("d" if dx > 0 else "a") if abs(dx) > abs(dy) else ("s" if dy > 0 else "w")
        await page.keyboard.down(key)
        await asyncio.sleep(0.15)
        await page.keyboard.up(key)
        await asyncio.sleep(0.35)
    return False


def _ensure_libasound():
    """Chromium/Firefox headless nesta máquina falham ao iniciar sem
    libasound.so.2 (ALSA), e não há sudo sem senha aqui - ver memória de
    projeto "Testes E2E automatizados via Playwright". Baixa e extrai o
    .deb sem instalar (não precisa de root), uma vez só, cacheado em
    build/.alsa-workaround. No-op se a lib já existir no sistema."""
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
    """Sobe um subprocesso e mata no __exit__ - mesmo padrão pros dois
    servidores que este harness precisa (backend uvicorn, static server do
    build)."""

    def __init__(self, cmd, cwd, ready_url, name):
        self.cmd = cmd
        self.cwd = cwd
        self.ready_url = ready_url
        self.name = name
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


async def _boot_into_gameplay(page, game_url, character_name, shot_prefix, boot_timeout_s):
    """Injeta um save válido (pula a criação de personagem - MenuState
    seleciona CONTINUAR sozinho quando character.name já existe, ver
    memória de projeto), abre o jogo, espera o boot terminar de verdade
    (não um sleep às cegas: espera a requisição real que o boot sempre
    dispara pro backend, GET /balance - ver game/net.py's
    trigger_balance_fetch()) e entra na fase."""
    save = _make_save(character_name)
    await page.add_init_script(f'localStorage.setItem("dungeon_quest_save", {json.dumps(json.dumps(save))});')

    async with page.expect_request(lambda r: "/balance" in r.url, timeout=boot_timeout_s * 1000):
        await page.goto(game_url)
        await page.click("#canvas")
    # A requisição de /balance dispara bem cedo no boot (GameStateManager.
    # __init__), antes do MenuState estar de fato desenhado/clicável -
    # ainda precisa de uma folga curta depois dela.
    await asyncio.sleep(3)
    await page.screenshot(path=f"{shot_prefix}_01_menu.png")

    await page.keyboard.press("Space")  # CONTINUAR
    await asyncio.sleep(1.5)
    await page.screenshot(path=f"{shot_prefix}_02_gameplay.png")


async def _open_coop_overlay(page):
    await page.mouse.click(*COOP_BUTTON)
    await asyncio.sleep(0.5)


async def _connect_coop_session(browser, game_url, boot_timeout_s, shots_dir, tag=""):
    """Boota os dois BrowserContexts, cria+entra na mesma room, e confirma
    as 3 garantias basicas de sync (join/pos/enemies) - extraido de
    run_test original pra tambem ser reusado por run_world_sync_test sem
    duplicar esta sequencia de boot/join cuidadosamente ajustada (timings
    de sleep, ordem dos listeners de WebSocket antes de qualquer
    navegacao, etc - ver comentarios inline). Retorna um dict com tudo que
    os chamadores precisam; `ok=False` se qualquer uma das 3 garantias
    falhar (chamador so precisa fechar os contexts e retornar False)."""
    ctx_host = await browser.new_context(viewport={"width": SW, "height": SH})
    ctx_guest = await browser.new_context(viewport={"width": SW, "height": SH})
    page_host = await ctx_host.new_page()
    page_guest = await ctx_guest.new_page()

    page_host_errors, page_guest_errors = [], []
    page_host.on("pageerror", lambda e: page_host_errors.append(str(e)))
    page_guest.on("pageerror", lambda e: page_guest_errors.append(str(e)))

    # Registrado ANTES de qualquer navegação/clique - page.on("websocket")
    # só pega conexões abertas DEPOIS do listener existir, e o WS coop
    # do host abre assim que ele cria a room, bem antes do guest sequer
    # existir.
    ws_state = {"host": {"frames": [], "closed": False}, "guest": {"frames": [], "closed": False}}

    def _make_ws_handler(key):
        def _on_ws(ws):
            if "/coop/ws/" in ws.url:
                ws.on("framereceived", lambda payload: ws_state[key]["frames"].append(payload))
                ws.on("close", lambda: ws_state[key].__setitem__("closed", True))
        return _on_ws

    page_host.on("websocket", _make_ws_handler("host"))
    page_guest.on("websocket", _make_ws_handler("guest"))

    _log(f"{tag}Host: entrando no jogo...")
    await _boot_into_gameplay(page_host, game_url, "HostPlayer",
                               os.path.join(shots_dir, f"{tag}host"), boot_timeout_s)

    _log(f"{tag}Host: abrindo overlay coop e criando room...")
    await _open_coop_overlay(page_host)
    async with page_host.expect_response(lambda r: "/coop/room" in r.url and r.request.method == "POST") as resp_info:
        await page_host.mouse.click(*CREATE_ROOM_BUTTON)
    room_resp = await resp_info.value
    room_id = (await room_resp.json())["room_id"]
    _log(f"{tag}Room criada pelo host: {room_id}")
    await asyncio.sleep(1.5)
    await page_host.screenshot(path=os.path.join(shots_dir, f"{tag}host_03_room_created.png"))

    _log(f"{tag}Guest: entrando no jogo...")
    await _boot_into_gameplay(page_guest, game_url, "GuestPlayer",
                               os.path.join(shots_dir, f"{tag}guest"), boot_timeout_s)

    _log(f"{tag}Guest: abrindo overlay coop e entrando na room {room_id}...")
    await _open_coop_overlay(page_guest)
    await page_guest.mouse.click(*JOIN_ROOM_BUTTON)
    await asyncio.sleep(0.3)
    await page_guest.keyboard.type(room_id)
    await page_guest.mouse.click(*CONNECT_BUTTON)
    await asyncio.sleep(1.5)  # dá tempo do connect() assíncrono resolver antes do ESC abaixo

    # Fecha os dois painéis (ESC não desconecta, só esconde - ver
    # toggle_coop()) JÁ AQUI, antes da espera longa mais abaixo - achado ao
    # vivo construindo este harness: esperar demais antes de fechar corria
    # o risco real de o coop_sync automático (L6) já ter trocado a
    # GameplayState por uma instância nova ENQUANTO isso, com coop_open já
    # de volta a False.
    await page_host.keyboard.press("Escape")
    await page_guest.keyboard.press("Escape")

    await page_host.bring_to_front()
    deadline = time.monotonic() + 15
    joined = False
    while time.monotonic() < deadline:
        if any('"type":"join"' in f or "'type': 'join'" in f or '"join"' in f for f in ws_state["host"]["frames"]):
            joined = True
            break
        await asyncio.sleep(1.0)

    await asyncio.sleep(1)
    await page_host.screenshot(path=os.path.join(shots_dir, f"{tag}host_04_after_guest_joined.png"))
    await page_guest.screenshot(path=os.path.join(shots_dir, f"{tag}guest_03_connected.png"))

    _log(f"{tag}Host recebeu frame de join do guest: {joined}")
    session = {
        "ctx_host": ctx_host, "ctx_guest": ctx_guest,
        "page_host": page_host, "page_guest": page_guest,
        "ws_state": ws_state,
        "page_host_errors": page_host_errors, "page_guest_errors": page_guest_errors,
        "ok": False,
    }
    if not (joined and not page_host_errors and not page_guest_errors):
        _log(f"{tag}RESULTADO: FALHOU (fase 1: entrar na mesma room)")
        return session
    _log(f"{tag}Fase 1 OK - dois BrowserContexts reais, mesma room, join confirmado no WebSocket real.")

    await asyncio.sleep(2)
    await page_host.screenshot(path=os.path.join(shots_dir, f"{tag}host_05_world_with_remote_player.png"))
    await page_guest.screenshot(path=os.path.join(shots_dir, f"{tag}guest_05_world_with_remote_player.png"))

    pos_seen = any('"type":"pos"' in f or "'type': 'pos'" in f for f in ws_state["host"]["frames"])
    _log(f"{tag}Host recebeu mensagens \"pos\" do guest (broadcast de posição real): {pos_seen}")
    if not pos_seen:
        _log(f"{tag}RESULTADO: FALHOU (fase 1.5: broadcast de posição / RemotePlayer)")
        return session

    # Stage L6: entrar na room no MEIO de uma fase já carregada (o único
    # jeito que a UI de L4 permite) só liga o modo rede a partir da PRÓXIMA
    # transição de fase - o guest força essa transição sozinho ao receber
    # o primeiro level_sync do host. TransitionState leva 1.5s; dá uma
    # folga.
    _log(f"{tag}Esperando o guest re-entrar na fase em modo rede (coop_sync)...")
    await asyncio.sleep(4)
    await page_guest.screenshot(path=os.path.join(shots_dir, f"{tag}guest_06_after_coop_sync.png"))
    await page_host.screenshot(path=os.path.join(shots_dir, f"{tag}host_06_enemies_synced.png"))

    enemies_seen = any('"type":"enemies"' in f or "'type': 'enemies'" in f for f in ws_state["guest"]["frames"])
    _log(f"{tag}Guest recebeu mensagens \"enemies\" do host (broadcast de inimigos real): {enemies_seen}")
    if not enemies_seen or page_guest_errors or page_host_errors:
        _log(f"{tag}RESULTADO: FALHOU (fase 1.6: modo rede de Enemy/Boss - "
             f"erros host={page_host_errors} guest={page_guest_errors})")
        return session
    _log(f"{tag}Fase 1.6 OK - guest recebeu snapshots de inimigos do host, sem erros de página.")

    session["ok"] = True
    return session


async def run_test(browser, game_url, headed, boot_timeout_s, shots_dir):
    session = await _connect_coop_session(browser, game_url, boot_timeout_s, shots_dir)
    ctx_host, ctx_guest = session["ctx_host"], session["ctx_guest"]
    page_host, page_guest = session["page_host"], session["page_guest"]
    ws_state = session["ws_state"]
    page_host_errors, page_guest_errors = session["page_host_errors"], session["page_guest_errors"]
    try:
        if not session["ok"]:
            return False

        # Stage L7: os dois nascem no MESMO tile de spawn - Player.
        # get_attack_rect() (game/player.py) estende o retângulo de
        # ataque PRA FORA do próprio jogador, na direção da mira
        # (offset = attack_range/2 + tamanho/2, ~48px com os valores
        # atuais) - não cobre "embaixo de mim mesmo". Dois jogadores
        # exatamente sobrepostos nunca se alcançam (achado ao vivo com
        # este harness). O guest anda um pouco pra baixo primeiro,
        # abrindo a distância certa pra cair dentro do alcance da mira
        # padrão do host ("baixo").
        _log("Guest andando um pouco pra abrir distância de melee...")
        await page_guest.bring_to_front()  # senão o "s" pode nem ser processado a tempo - mesma lição de antes
        await asyncio.sleep(0.5)
        await page_guest.keyboard.down("s")
        await asyncio.sleep(0.2)
        await page_guest.keyboard.up("s")
        await asyncio.sleep(1.5)  # ~12Hz de broadcast + interpolação convergirem antes do host mirar
        await page_host.screenshot(path=os.path.join(shots_dir, "host_06a_after_guest_moved.png"))

        # O jogo mira pelo mouse em PC (states.py's set_aim() a partir
        # de input.mouse_pos(), todo frame) - o cursor do Playwright
        # nunca foi movido perto do host desde os cliques de UI lá
        # atrás (o botão Criar Room etc.), então Player.get_attack_rect()
        # apontava pra onde quer que esse último clique tenha deixado o
        # cursor, não pro guest logo abaixo (achado ao vivo com este
        # harness). Move o mouse pra baixo do próprio host antes de
        # atacar, mirando de propósito na direção onde o guest está.
        hx, hy = 120, 260  # abaixo do spawn do host na tela (ver host_06a screenshot)
        await page_host.mouse.move(hx, hy)
        await asyncio.sleep(0.2)

        _log("Host atacando (deve acertar o RemotePlayer do guest, dano PvP real)...")
        await page_host.screenshot(path=os.path.join(shots_dir, "host_06b_before_attacks.png"))
        # states.py's try_attack() (o ataque de PC) é acionado por
        # pygame.key.get_pressed() - polling contínuo de tecla
        # SEGURADA (Stage K23, "hold-to-fire"), não por um evento de
        # KEYDOWN isolado. keyboard.press() do Playwright aperta e
        # solta rápido demais pro jogo nunca ver a tecla "pressionada"
        # em nenhum frame (achado ao vivo com este harness - mesma
        # categoria do "s" de movimento, que já usava down()/up()).
        # down()/sleep()/up() seguns a tecla por tempo o bastante pra
        # aparecer em pelo menos um get_pressed().
        for _ in range(3):
            await page_host.keyboard.down("Space")
            await asyncio.sleep(0.3)
            await page_host.keyboard.up("Space")
            await asyncio.sleep(0.3)
        await asyncio.sleep(1)
        await page_host.screenshot(path=os.path.join(shots_dir, "host_07_after_pvp_attack.png"))
        await page_guest.screenshot(path=os.path.join(shots_dir, "guest_07_after_pvp_hit.png"))

        pvp_seen = any('"type":"player_hit"' in f or "'type': 'player_hit'" in f for f in ws_state["guest"]["frames"])
        _log(f"Guest recebeu mensagem \"player_hit\" do host (dano PvP real via rede): {pvp_seen}")
        if not pvp_seen or page_guest_errors or page_host_errors:
            _log(f"RESULTADO: FALHOU (fase 1.7: dano PvP - erros host={page_host_errors} guest={page_guest_errors})")
            return False
        _log("Fase 1.7 OK - dano jogador-contra-jogador confirmado via WebSocket real.")

        # Stage L13/L14 (docs/coop-implementation-plan.md): chat não
        # depende de combate (nota de reordenação do próprio plano) -
        # testado aqui, depois do walk da fase 1.7 já ter separado
        # host/guest na tela, pra ter um screenshot limpo (uma
        # tentativa anterior testou logo após a fase 1.6, quando os
        # dois ainda ocupam o mesmo tile de spawn - nameplate/HP-bar
        # do RemotePlayer desenham por cima na MESMA posição de tela e
        # escondem o balão por baixo; a mensagem em si já chegava
        # certa via WebSocket, só a confirmação visual que ficava
        # ambígua). Host manda uma mensagem real.
        _log("Host mandando uma mensagem de chat...")
        await page_host.bring_to_front()
        await asyncio.sleep(0.2)
        await page_host.keyboard.press("Enter")
        await asyncio.sleep(0.2)
        await page_host.keyboard.type("oi time")
        await asyncio.sleep(0.2)
        await page_host.keyboard.press("Enter")
        await asyncio.sleep(1)
        await page_host.screenshot(path=os.path.join(shots_dir, "host_07a_own_chat_bubble.png"))
        await page_guest.screenshot(path=os.path.join(shots_dir, "guest_07a_remote_chat_bubble.png"))

        chat_seen = any(
            ('"type":"chat"' in f or "'type': 'chat'" in f) and ("oi time" in f)
            for f in ws_state["guest"]["frames"]
        )
        _log(f"Guest recebeu a mensagem de chat do host via WebSocket real: {chat_seen}")
        if not chat_seen or page_guest_errors or page_host_errors:
            _log(f"RESULTADO: FALHOU (fase 1.7b: chat - erros host={page_host_errors} guest={page_guest_errors})")
            return False
        _log("Fase 1.7b OK - chat confirmado via WebSocket real (L13/L14).")

        # Stage L9 (docs/coop-implementation-plan.md): estado "caído"/
        # revive automático/fim de partida quando todos caem.
        #
        # Uma tentativa anterior tentou um "double KO" de verdade (os
        # dois jogadores derrubando um ao outro ao mesmo tempo) pra
        # também exercitar next_state="menu". Não deu pra fazer de
        # forma confiável NESTE harness: qualquer BrowserContext que
        # não está em primeiro plano (bring_to_front()) leva throttling
        # de aba em segundo plano do Chromium forte o bastante pra
        # travar o game loop dela por completo depois de poucos
        # segundos, mesmo com --disable-backgrounding-occluded-windows
        # etc. - inspecionado direto via ausência total de novas
        # mensagens "pos"/"player_hit" no meio do teste. E com só 2
        # jogadores, "downed = não pode mais atacar" cria um paradoxo
        # de ordenação real: quem cai primeiro nunca termina de
        # derrubar o outro, então uma sequência estritamente
        # sequencial (só um lado ativo por vez) também não fecha o
        # "os dois caídos" de forma confiável. A checagem de
        # next_state="menu" em si (states.py, logo após o death-check)
        # já tem cobertura direta e determinística fora do browser -
        # ver tools/../l9_menu_transition_test.py style check (chama
        # GameplayState.update() de verdade com player.downed=True e
        # um RemotePlayer downed=True, sem mock de lógica de jogo).
        #
        # O que ESTE harness cobre (e só ele pode, por depender de
        # rede real): o CAMINHO de rede completo de L9 - dano PvP
        # real derrubando um jogador até 0 HP overs a rede (não só a
        # transição local unitária), o RemotePlayer espelhando
        # "downed"/"downed_timer" via "pos" no OUTRO cliente (visual,
        # via screenshot), a checagem "só eu caído, o outro não" NÃO
        # encerrando a partida prematuramente (confirmação negativa
        # via "pos" continuando a chegar), e o revive automático de
        # 5s se propagando de volta pela rede.
        #
        # Mirar num ponto de tela ADIVINHADO (olhando pixel de
        # screenshot) não funcionou de forma confiável em tentativas
        # anteriores - o spawn fica perto do canto do mapa e
        # Camera.follow() clampa em (0,0) nesse caso (game/camera.py),
        # então tela == mundo pra quem está clampado, mas cada hit
        # aplica knockback de verdade (desloca o alvo), degradando
        # uma mira fixa a cada rodada. Em vez de adivinhar, lê a
        # posição de MUNDO real do guest direto das mensagens "pos"
        # já recebidas (fonte de verdade) e mira o mouse do
        # Playwright nela.
        # Stage L10: a partir do primeiro hit acima, o próprio host
        # carrega "Traicoeiro" (-15% em physical_damage_mult, entre
        # outros - ver game/status_effects.py) e continua se
        # refrescando a cada novo acerto dentro da janela de 10s - o
        # host bate mais fraco a partir daqui, precisa de mais rodadas
        # pra derrubar o guest do que precisava antes de L10 existir.
        _log("Host batendo repetidamente no guest, uma rodada por vez, até ele cair de verdade (\"downed\")...")
        for i in range(40):
            for _ in range(6):
                hwx, hwy = _latest_pos(ws_state["guest"]["frames"])  # posição real do próprio host
                gwx, gwy = _latest_pos(ws_state["host"]["frames"])   # posição real do guest
                if None in (hwx, hwy, gwx, gwy):
                    break
                d = _dist(hwx, hwy, gwx, gwy)
                if d <= 50:
                    break
                dx, dy = gwx - hwx, gwy - hwy
                # Corrige pelo eixo com maior desvio (não só vertical) -
                # o knockback de take_damage() pode empurrar o guest pro
                # lado, não só pra longe na mesma direção do golpe; uma
                # correção só-vertical (tentativa anterior) deixa uma
                # deriva horizontal se acumular sem nunca ser corrigida.
                if abs(dx) > abs(dy):
                    key = "d" if dx > 0 else "a"
                else:
                    key = "s" if dy > 0 else "w"
                await page_host.keyboard.down(key)
                await asyncio.sleep(0.06)
                await page_host.keyboard.up(key)
                await asyncio.sleep(0.25)
            if gwx is not None:
                await page_host.mouse.move(gwx, gwy)
            await page_host.keyboard.down("Space")
            await asyncio.sleep(0.3)
            await page_host.keyboard.up("Space")
            await asyncio.sleep(1.2)
            downed, hp = _latest_downed(ws_state["host"]["frames"])
            if downed:
                _log(f"Guest ficou \"downed\" via rede depois de {i + 1} rodada(s) (hp={hp}).")
                break
        await page_host.screenshot(path=os.path.join(shots_dir, "host_08_guest_downed_remote.png"))
        await page_guest.screenshot(path=os.path.join(shots_dir, "guest_08_self_downed.png"))

        guest_downed, _ = _latest_downed(ws_state["host"]["frames"])
        _log(f"Host viu o guest \"caído\" via rede (RemotePlayer.downed): {guest_downed}")
        if not guest_downed or page_guest_errors or page_host_errors:
            _log(f"RESULTADO: FALHOU (fase 1.9a: guest deveria ter caído via dano PvP real - "
                 f"erros host={page_host_errors} guest={page_guest_errors})")
            return False
        _log("Fase 1.9a OK - guest \"caiu\" (0 HP, downed=True) via dano PvP real pela rede, "
             "RemotePlayer espelhou isso no host.")

        # Stage L10 (docs/coop-implementation-plan.md): "Homicida" -
        # a vítima (guest) manda "friendly_kill" pro agressor (host) no
        # momento em que cai, via a mesma checagem de morte de L9. O
        # host aplica "homicida" em si mesmo ao receber - confirma via
        # o frame real chegando (mensagem nova, transporte novo) e via
        # screenshot (chip "HOM" no HUD do host, mesma fileira que
        # "TRA" já devia ter aparecido depois do ataque da fase 1.7).
        friendly_kill_seen = any(
            '"type":"friendly_kill"' in f or "'type': 'friendly_kill'" in f
            for f in ws_state["host"]["frames"]
        )
        _log(f"Host recebeu \"friendly_kill\" do guest (Homicida deve se aplicar nele mesmo): {friendly_kill_seen}")
        if not friendly_kill_seen:
            _log("RESULTADO: FALHOU (fase 1.10: Homicida - friendly_kill nao chegou via rede)")
            return False
        await asyncio.sleep(0.5)
        await page_host.screenshot(path=os.path.join(shots_dir, "host_10_homicida_chip.png"))
        _log("Fase 1.10 OK - \"friendly_kill\" confirmado via WebSocket real (Homicida aplicado no agressor).")

        # Confirmação negativa: só o guest caiu, o host continua de pé -
        # a condição em states.py exige os DOIS ("all(others_downed)"),
        # então o guest NÃO deve ter saído de GameplayState (continua
        # mandando "pos" normalmente, só com downed=True).
        guest_frames_before = len(ws_state["host"]["frames"])
        await asyncio.sleep(1.5)
        guest_kept_playing = any(
            ('"type":"pos"' in f or "'type': 'pos'" in f)
            for f in ws_state["host"]["frames"][guest_frames_before:]
        )
        _log(f"Guest continua em GameplayState mandando \"pos\" (não foi pro menu sozinho): {guest_kept_playing}")
        if not guest_kept_playing:
            _log("RESULTADO: FALHOU (fase 1.9b: guest caído sozinho não deveria encerrar a partida)")
            return False
        _log("Fase 1.9b OK - \"caído\" sozinho (o outro ainda de pé) não termina a partida.")

        # Revive automático (DOWNED_DURATION = 5.0s, decisão #1) - espera
        # passar da janela e confirma via rede que o guest voltou com
        # downed=False e HP em ~50% do máximo (DOWNED_REVIVE_HP_FRAC).
        _log("Esperando o revive automático de 5s do guest...")
        await asyncio.sleep(6)
        await page_host.screenshot(path=os.path.join(shots_dir, "host_09_guest_revived_remote.png"))
        revived_downed, revived_hp = _latest_downed(ws_state["host"]["frames"])
        _log(f"Guest depois do revive automático: downed={revived_downed} hp={revived_hp}")
        if revived_downed:
            _log("RESULTADO: FALHOU (fase 1.9c: guest deveria ter revivido sozinho depois de 5s)")
            return False
        _log("Fase 1.9c OK - revive automático de 5s confirmado via rede (L9 completo neste harness).")

        # Stage L5 (docs/coop-implementation-plan.md): decisão #4 - sem
        # migração de host, o guest deve ser jogado de volta pro menu
        # quando o host cai. Fechar o CONTEXTO inteiro do host (não só
        # a página) derruba o WS dele server-side de verdade, o mesmo
        # jeito que fechar a aba/perder rede faria - não um
        # net_coop.disconnect() explícito do lado do host, que não é o
        # cenário que decisão #4 cobre.
        _log("Fechando o BrowserContext do host (simulando ele cair)...")
        await ctx_host.close()

        l5_deadline = time.monotonic() + 15
        guest_ws_closed = False
        while time.monotonic() < l5_deadline:
            if ws_state["guest"]["closed"]:
                guest_ws_closed = True
                break
            await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        await page_guest.screenshot(path=os.path.join(shots_dir, "guest_04_after_host_left.png"))

        _log(f"Guest teve seu WebSocket coop fechado sozinho (host caiu): {guest_ws_closed}")
        _log(f"Erros de página (guest): {page_guest_errors}")

        ok = guest_ws_closed and not page_guest_errors
        if not ok:
            _log("RESULTADO: FALHOU (fase 2: host cai -> guest deveria ser desconectado/voltar pro menu)")
        else:
            _log("RESULTADO: OK - guest detectou o host caindo e encerrou a sessão coop (decisão #4).")
        return ok
    finally:
        # ctx_host já pode ter sido fechado acima (fase 2) - close() num
        # context já fechado é um no-op seguro no Playwright.
        await ctx_host.close()
        await ctx_guest.close()


async def run_world_sync_test(browser, game_url, headed, boot_timeout_s, shots_dir):
    """Bugfix round: playtest real achou que (a) blocos quebrados por um
    lado continuavam solidos pro outro, e (b) monstros mortos por um lado
    continuavam vivos/parados pro outro - os dois eram lacunas REAIS de
    sync (ver .claude/plans), nao uma race condition. Sessao coop propria
    (fecha no final, independente de run_test) pra nao herdar a deriva de
    posicao/camera que a sequencia PvP/downed/revive de run_test acumula -
    os dois jogadores aqui continuam perto do canto do spawn (2,2), onde
    Camera.follow() clampa em (0,0) e tela == mundo (mesma premissa que
    run_test's L9 ja documentava)."""
    session = await _connect_coop_session(browser, game_url, boot_timeout_s, shots_dir, tag="ws_")
    ctx_host, ctx_guest = session["ctx_host"], session["ctx_guest"]
    page_host, page_guest = session["page_host"], session["page_guest"]
    ws_state = session["ws_state"]
    page_host_errors, page_guest_errors = session["page_host_errors"], session["page_guest_errors"]
    try:
        if not session["ok"]:
            return False

        # --- (a) Coop: quebra de bloco sincroniza ---
        # O guest anda da spawn (2,2) ate ficar colado no bloco de parede
        # interior em (col=6, row=2) - mesma linha, sem componente
        # vertical - e quebra com a Picareta (2 hits). O bloco nao tem
        # posicao de rede (e estatico), entao o alvo de _walk_toward e uma
        # constante, nao uma leitura de frame.
        _log("[world-sync] Guest andando ate a parede interior pra testar quebra de bloco...")
        wall_target = (WALL_TILE_COL * TILE - 24, WALL_TILE_ROW * TILE + TILE / 2)  # colado a esquerda do bloco
        await page_guest.bring_to_front()
        reached = await _walk_toward(
            page_guest, lambda: wall_target,
            lambda: _latest_pos(ws_state["host"]["frames"]),
            tolerance=40, max_rounds=20,
        )
        _log(f"[world-sync] Guest chegou perto da parede: {reached}")
        gx, gy = _latest_pos(ws_state["host"]["frames"])
        if gx is not None:
            # Mira pra direita (na parede) - tela == mundo perto do canto,
            # mesma premissa que run_test's fase 1.7/downed-chase usa.
            await page_guest.mouse.move(gx + 60, gy)
        await asyncio.sleep(0.2)
        await page_guest.screenshot(path=os.path.join(shots_dir, "ws_guest_11_before_pickaxe.png"))

        # PICKAXE_COOLDOWN = 1.0s (game/player.py) - duas cavadas com folga.
        for _ in range(2):
            await page_guest.keyboard.down("e")
            await asyncio.sleep(0.15)
            await page_guest.keyboard.up("e")
            await asyncio.sleep(1.3)
        await asyncio.sleep(0.5)
        await page_host.screenshot(path=os.path.join(shots_dir, "ws_host_11_after_block_broken.png"))
        await page_guest.screenshot(path=os.path.join(shots_dir, "ws_guest_11_after_block_broken.png"))

        # Aceita qualquer tile do bloco 2x2 (col 6-7, row 2-3, ver
        # LEVEL_MAPS[1]) em vez de exigir exatamente (6, 2) - a folga do
        # _walk_toward acima (tolerance=40px) pode deixar o guest colado
        # perto o bastante pra picareta acertar o tile vizinho do mesmo
        # bloco em vez do alvo exato, o que ainda prova a mesma coisa
        # (quebra de bloco sincronizando).
        def _is_target_wall_break(f):
            try:
                d = json.loads(f)
            except (ValueError, TypeError):
                return False
            return (d.get("type") == "block_broken" and d.get("col") in (6, 7) and d.get("row") in (2, 3))

        block_synced = any(_is_target_wall_break(f) for f in ws_state["host"]["frames"])
        _log(f"[world-sync] Host recebeu \"block_broken\" do guest pro bloco de parede alvo: {block_synced}")
        if not block_synced or page_guest_errors or page_host_errors:
            _log(f"RESULTADO: FALHOU (bloco não sincronizou - erros host={page_host_errors} guest={page_guest_errors})")
            return False
        _log("[world-sync] OK - quebra de bloco do guest chegou no host via WebSocket real.")

        # --- (b) Coop: guest consegue de fato ferir/matar um inimigo ---
        # Antes da correção, todo golpe do guest contra um Enemy follower
        # era um no-op silencioso (game/level.py) - a prova real e o guest
        # mandar "hit_request" (nao apenas atacar) E o HP daquele inimigo
        # de fato cair num snapshot "enemies" seguinte, nao so localmente.
        # O mais PROXIMO do guest, não só "o primeiro vivo" - um alvo do
        # outro lado do mapa (ou atrás de uma parede) nunca fica alcançável
        # em 25 rodadas de _walk_toward (que anda em linha reta, sem
        # contornar parede) - achado ao vivo (o guest nunca chegou perto o
        # bastante e o teste falhava por limitação do harness, não por um
        # bug real de sync).
        latest = _latest_enemies(ws_state["guest"]["frames"])
        gx0, gy0 = _latest_pos(ws_state["host"]["frames"])
        alive_enemies = [e for e in (latest or {}).get("enemies", []) if e.get("alive")]
        target_enemy = (min(alive_enemies, key=lambda e: _dist(gx0, gy0, e["x"], e["y"]))
                         if alive_enemies and gx0 is not None else None)
        if target_enemy is None:
            _log("RESULTADO: FALHOU (nenhum inimigo vivo no snapshot recebido pelo guest)")
            return False
        enemy_id = target_enemy["id"]
        hp_before = target_enemy["hp"]
        _log(f"[world-sync] Guest vai atacar o inimigo id={enemy_id} (hp inicial={hp_before})...")

        def _enemy_pos():
            snap = _latest_enemies(ws_state["guest"]["frames"])
            if not snap:
                return None, None
            e = next((e for e in snap["enemies"] if e.get("id") == enemy_id), None)
            return (e["x"], e["y"]) if e else (None, None)

        await _walk_toward(page_guest, _enemy_pos, lambda: _latest_pos(ws_state["host"]["frames"]),
                            tolerance=45, max_rounds=25)
        ex, ey = _enemy_pos()
        if ex is not None:
            await page_guest.mouse.move(ex, ey)  # tela == mundo perto do spawn, mesma premissa de sempre
        await asyncio.sleep(0.2)
        await page_guest.screenshot(path=os.path.join(shots_dir, "ws_guest_12_before_attack_enemy.png"))

        for _ in range(5):
            gx, gy = _latest_pos(ws_state["host"]["frames"])
            ex, ey = _enemy_pos()
            if gx is not None and ex is not None:
                await page_guest.mouse.move(ex, ey)
            await page_guest.keyboard.down("Space")
            await asyncio.sleep(0.3)
            await page_guest.keyboard.up("Space")
            await asyncio.sleep(0.6)
            if _frames_contain(ws_state["host"]["frames"], "hit_request", enemy_id=enemy_id):
                break
        await asyncio.sleep(0.5)
        await page_host.screenshot(path=os.path.join(shots_dir, "ws_host_12_after_guest_hit_request.png"))
        await page_guest.screenshot(path=os.path.join(shots_dir, "ws_guest_12_after_attack_enemy.png"))

        hit_request_seen = _frames_contain(ws_state["host"]["frames"], "hit_request", enemy_id=enemy_id)
        _log(f"[world-sync] Host recebeu \"hit_request\" do guest pro inimigo {enemy_id}: {hit_request_seen}")
        if not hit_request_seen or page_guest_errors or page_host_errors:
            _log(f"RESULTADO: FALHOU (guest não conseguiu forwardar dano - "
                 f"erros host={page_host_errors} guest={page_guest_errors})")
            return False

        # O host resolve o hit_request e o broadcast "enemies" (12Hz,
        # já confirmado na fase 1.6) devolve o resultado - confirma o HP
        # de fato caindo (ou o inimigo morrendo) num snapshot mais recente.
        await asyncio.sleep(1.5)
        latest_after = _latest_enemies(ws_state["guest"]["frames"])
        entry_after = next((e for e in (latest_after or {}).get("enemies", []) if e.get("id") == enemy_id), None)
        # entry_after is None também conta como prova - Level.update()
        # (game/level.py) poda um inimigo morto da lista ~0.7s depois de
        # morrer (assim que os floating damage numbers terminam), então
        # sumir da lista de todo é o resultado esperado de uma morte real,
        # não um sinal de falha.
        damage_applied = entry_after is None or not entry_after.get("alive") or entry_after["hp"] < hp_before
        _log(f"[world-sync] Inimigo {enemy_id} depois do ataque do guest: {entry_after} "
             f"(hp antes={hp_before}): dano aplicado de verdade = {damage_applied}")
        if not damage_applied:
            _log("RESULTADO: FALHOU (hp/alive do inimigo não refletiu o dano do guest no broadcast do host)")
            return False
        _log("[world-sync] OK - dano de guest contra Enemy follower agora é resolvido pelo host e "
             "sincronizado de volta (antes era um no-op silencioso).")

        _log("RESULTADO: OK - bloco e morte de monstro sincronizam entre host e guest.")
        return True
    finally:
        await ctx_host.close()
        await ctx_guest.close()


async def run_all(game_url, backend_health_url, headed, boot_timeout_s, shots_dir):
    from playwright.async_api import async_playwright

    os.makedirs(shots_dir, exist_ok=True)
    _wait_http_ok(backend_health_url, timeout_s=10)

    async with async_playwright() as p:
        # Stage L9: sem essas flags, a página que NÃO está em primeiro
        # plano (bring_to_front()) leva throttling agressivo de aba em
        # segundo plano do Chromium - o game loop dela (requestAnimation
        # Frame) praticamente para depois de alguns segundos, não só
        # desacelera.
        browser = await p.chromium.launch(headless=not headed, args=[
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ])
        try:
            main_ok = await run_test(browser, game_url, headed, boot_timeout_s, shots_dir)
            world_sync_ok = await run_world_sync_test(browser, game_url, headed, boot_timeout_s, shots_dir)
            return main_ok and world_sync_ok
        finally:
            await browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-port", type=int, default=8000)
    ap.add_argument("--backend-port", type=int, default=8090)
    ap.add_argument("--no-rebuild", action="store_true", help="reusa build/web existente em vez de empacotar de novo")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--boot-timeout", type=float, default=40.0)
    ap.add_argument("--shots-dir", default=os.path.join(ROOT, "build", "coop_harness_shots"))
    args = ap.parse_args()

    _ensure_libasound()

    if not args.no_rebuild or not os.path.isdir(BUILD_WEB):
        _build_pygbag()

    # 127.0.0.1, não localhost: pygbag resolve o CDN do pygame_ce errado
    # (relativo ao próprio servidor local) especificamente com o hostname
    # "localhost" - reproduzido de forma determinística construindo este
    # harness, ver o comentário de ALLOWED_ORIGINS em backend/app/main.py.
    game_url = f"http://127.0.0.1:{args.game_port}/index.html"
    backend_health_url = f"http://127.0.0.1:{args.backend_port}/health"

    backend_cmd = [os.path.join(ROOT, "backend", ".venv", "bin", "uvicorn"), "app.main:app", "--port", str(args.backend_port)]
    static_cmd = [sys.executable, "-m", "http.server", str(args.game_port)]

    with _Server(backend_cmd, cwd=os.path.join(ROOT, "backend"), ready_url=backend_health_url, name="backend"), \
         _Server(static_cmd, cwd=BUILD_WEB, ready_url=game_url, name="static server (build/web)"):
        ok = asyncio.run(run_all(game_url, backend_health_url, args.headed, args.boot_timeout, args.shots_dir))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
