"""
Stage L2 (docs/coop-implementation-plan.md): sessão WebSocket viva do modo
coop, ao lado de game/net.py - não uma extensão dele. net.py é inteiramente
fire-and-forget (`schedule()`/`poll_result()`, sem conexão persistente), o
modelo certo pra save/leaderboard e errado pra posição de jogador em tempo
real. Este módulo mantém uma conexão aberta e é desenhado pra ser sondado
todo frame (`poll_messages()`), sem nunca bloquear o loop `asyncio.sleep(0)`
que o pygbag exige (ver main.py).

Emscripten: o WebSocket nativo do navegador é criado e orquestrado inteiramente
em JS via `js.eval()` - nenhum callback Python é passado pro JS chamar de
volta. Essa é a mesma lição que já queimou uma sessão inteira em game/net.py
(`_fetch_json_emscripten`): `pyodide.ffi.create_once_callable` não existe
nesse build do pygbag, e depender de callback Python-a-partir-do-JS é
exatamente o que a correção de XHR abandonou em favor de sondagem por
atributo/método puro de JsProxy (`xhr.readyState`, `xhr.status`, `xhr.abort()`
- todos confirmados funcionando). Aqui o mesmo princípio: o `onmessage` do
WebSocket só empilha em um array 100% JS (`window._dqCoop.inbox`); Python só
lê esse array com `.length`/`.shift()`, igual a como já lê atributos de XHR.

Achado novo, confirmado ao vivo via Playwright construindo este módulo
(L1.5 adiantado, só pra validar L2): **escrever um atributo em `js.window`
direto do Python (`js.window.foo = valor`) não levanta exceção, mas
também não propaga pro `window` real do navegador** - um no-op silencioso,
categoria de bug irmã da que already documentada em net.py. Ler
`js.window.foo` funciona (inclusive pra objetos aninhados que o JS
escreveu), e um `JsProxy` local devolvido por `js.eval(...)` funciona
para leitura E escrita de atributo. Por isso toda mutação de estado no
lado JS aqui passa por `js.eval()` (string), nunca por atribuição de
atributo Python em `js.window` - a única exceção adicionada por engano
(`js.window._dqCoop = None` em `disconnect()`) foi corrigida pra
`js.eval("window._dqCoop = null")` depois desse achado.

Nativo/desktop (`python main.py` sem navegador): usa o pacote `websockets`
se disponível, numa task asyncio de fundo que drena mensagens pra uma
`collections.deque` sondada do mesmo jeito. Sem navegador nem pygbag, esse
caminho é só conveniência de dev (ver docs/architecture.md - o alvo real de
deploy é sempre o build pygbag) - se `websockets` não estiver instalado,
coop fica indisponível nesse modo em vez de quebrar o processo (mesmo
princípio offline-first que trigger_sync() já segue: rede ausente nunca
derruba o jogo).
"""
import asyncio
import json
import random
import sys
import time
import urllib.parse
from collections import deque

from game.net import _api_base, fetch_json

_JS_STATE_VAR = "_dqCoop"  # window._dqCoop - namespaced, não colide com o resto do bridge JS

_player_id = None
_last_error = None
_is_host = False

# Nativo apenas: a conexão real (websockets.WebSocketClientProtocol) e a
# fila de mensagens recebidas, drenada por poll_messages(). Em emscripten
# ambas ficam só no lado JS (window._dqCoop), nada disso é usado.
_native_ws = None
_native_inbox = deque()
_native_closed = True

# Mesmo pitfall documentado em game/net.py's _track(): asyncio.ensure_future()
# só guarda uma referência fraca da Task - sem isso, o GC pode colher a task
# de recv-loop antes dela nunca rodar.
_background_tasks = set()


def _track(coro):
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def get_player_id():
    """ID por processo, não por conta - coop não exige login (mesmo
    princípio de docs/architecture.md: login nunca é obrigatório pra
    jogar). Gerado uma vez e reusado por todas as rooms desta sessão.

    time.time_ns() é a fonte PRINCIPAL de unicidade aqui, não só um tempero
    - achado ao vivo construindo tools/coop_harness.py (Stage L1.5): dois
    BrowserContexts distintos, cada um seu próprio interpretador
    CPython-WASM booting em paralelo, geraram exatamente o mesmo
    player_id via random.choice() puro. O runtime WASM deste build do
    pygbag aparentemente não garante entropia própria por instância pra
    semear o `random` global (duas instâncias booting quase ao mesmo tempo
    -> mesma semente -> mesma sequência de random.choice()) - resultado:
    dois jogadores reais colidindo na mesma chave do dict `room` no
    backend, o segundo silenciosamente sobrescrevendo a conexão do
    primeiro (o bug real por trás do sintoma "host nunca vê o guest no
    roster" - nada a ver com timing de renderização/throttling, que foi a
    hipótese errada investigada antes desta). Nanosegundos de wall-clock
    somados a um sufixo de random.choice() bastam - não precisa ser
    criptograficamente forte, só não colidir entre jogadores conectando na
    mesma LAN."""
    global _player_id
    if _player_id is None:
        suffix = "".join(random.choice("0123456789abcdef") for _ in range(4))
        _player_id = f"{time.time_ns():x}{suffix}"
    return _player_id


def get_last_error():
    return _last_error


def is_host():
    """Stage L5 (docs/coop-implementation-plan.md): v1 não tem eleição de
    verdade - quem CRIA a room é o host, ponto (sem migração se ele cair,
    já cravado na feasibility study). Setado só por create_room(); connect()
    sozinho (fluxo de quem entra com um código) nunca marca host."""
    return _is_host


async def create_room():
    """POST /coop/room - o backend sorteia e reserva o código (decisão #3
    do plano). Propaga a exceção pro chamador (a UI de L4 decide como
    mostrar a falha) em vez de engolir - diferente de sync_state(), que
    nunca pode falhar visivelmente porque roda em segundo plano; aqui é uma
    ação explícita do jogador ("criar room agora")."""
    global _is_host
    result = await fetch_json("/coop/room", method="POST")
    _is_host = True
    return result["room_id"]


def _ws_url(room_id, player_id, name):
    base = _api_base()
    scheme = "wss" if base.startswith("https") else "ws"
    host = base.split("://", 1)[1]
    query = urllib.parse.urlencode({"player_id": player_id, "name": name})
    return f"{scheme}://{host}/coop/ws/{room_id}?{query}"


async def connect(room_id, name, player_id=None, timeout_s=8.0):
    """Abre a conexão coop pra uma room que já existe (criada por
    create_room() ou digitada por outro jogador). Levanta RuntimeError em
    caso de falha/timeout - conectar é uma ação explícita do jogador, uma
    falha silenciosa aqui deixaria a UI de L4 travada sem explicação."""
    global _last_error, _native_ws, _native_closed
    _teardown()
    _last_error = None
    pid = player_id or get_player_id()
    url = _ws_url(room_id, pid, name)

    if sys.platform == "emscripten":
        import js

        snippet = f"""(function(){{
            var st = {{ ws: null, inbox: [], open: false, closed: false, error: null }};
            try {{
                var ws = new WebSocket({json.dumps(url)});
                st.ws = ws;
                ws.onopen = function(){{ st.open = true; }};
                ws.onmessage = function(ev){{ st.inbox.push(ev.data); }};
                ws.onclose = function(){{ st.closed = true; }};
                ws.onerror = function(ev){{ st.closed = true; st.error = "websocket error"; }};
            }} catch (e) {{
                st.closed = true;
                st.error = String(e);
            }}
            window.{_JS_STATE_VAR} = st;
        }})();"""
        js.eval(snippet)

        deadline = time.monotonic() + timeout_s
        while True:
            state = getattr(js.window, _JS_STATE_VAR, None)
            if state is not None and state.open:
                return
            if state is not None and state.closed:
                _last_error = state.error or "conexão recusada"
                raise RuntimeError(_last_error)
            if time.monotonic() > deadline:
                _last_error = "timeout ao conectar"
                raise RuntimeError(_last_error)
            await asyncio.sleep(0)
    else:
        try:
            import websockets
        except ImportError as e:
            _last_error = "pacote 'websockets' ausente (coop só via navegador/pygbag nesse modo)"
            raise RuntimeError(_last_error) from e
        try:
            _native_ws = await asyncio.wait_for(websockets.connect(url), timeout=timeout_s)
        except Exception as e:
            _last_error = str(e)
            raise RuntimeError(_last_error) from e
        _native_closed = False
        _native_inbox.clear()
        _track(_native_recv_loop())


async def _native_recv_loop():
    global _native_closed
    ws = _native_ws
    try:
        async for raw in ws:
            _native_inbox.append(raw)
    except Exception:
        pass
    finally:
        _native_closed = True


def is_connected():
    if sys.platform == "emscripten":
        import js

        state = getattr(js.window, _JS_STATE_VAR, None)
        return bool(state is not None and state.open and not state.closed)
    return _native_ws is not None and not _native_closed


def send(msg):
    """Nunca levanta - uma mensagem perdida (room cheia, conexão caindo no
    meio da partida) não pode derrubar o frame que a originou, mesmo
    princípio offline-first de game/net.py."""
    if not is_connected():
        return
    text = json.dumps(msg)
    try:
        if sys.platform == "emscripten":
            import js

            js.window._dqCoop.ws.send(text)
        else:
            _track(_native_ws.send(text))
    except Exception:
        pass


def poll_messages():
    """Chamado uma vez por frame (GameplayState.update(), a partir da Fase
    2) - drena e decodifica tudo que chegou desde a última chamada. Nunca
    bloqueia: em emscripten é leitura pura de atributo/método de JsProxy
    (ver docstring do módulo); em nativo só esvazia uma deque já preenchida
    pela task de fundo."""
    msgs = []
    if sys.platform == "emscripten":
        import js

        state = getattr(js.window, _JS_STATE_VAR, None)
        if state is None:
            return msgs
        inbox = state.inbox
        while inbox.length > 0:
            raw = inbox.shift()
            try:
                msgs.append(json.loads(str(raw)))
            except (ValueError, TypeError):
                continue
    else:
        while _native_inbox:
            raw = _native_inbox.popleft()
            try:
                msgs.append(json.loads(raw))
            except (ValueError, TypeError):
                continue
    return msgs


def _teardown():
    """Fecha a conexão sem mexer em _is_host - connect() usa isso pra
    limpar uma conexão anterior antes de abrir uma nova (troca de room),
    sem se auto-desfazer de "sou host": create_room() marca _is_host=True
    e connect() roda logo em seguida no mesmo fluxo (_do_create() no
    overlay), então connect() não pode apagar o que create_room() acabou
    de setar."""
    global _native_ws, _native_closed
    if sys.platform == "emscripten":
        import js

        state = getattr(js.window, _JS_STATE_VAR, None)
        if state is not None and state.ws is not None:
            try:
                state.ws.close()
            except Exception:
                pass
        # A plain `js.window._dqCoop = None` (Python-side attribute write
        # onto js.window) silently no-ops in this pygbag build - confirmed
        # live, the same class of bug _fetch_json_emscripten's header already
        # hit for a different attribute (see module docstring). js.eval()
        # is the one channel confirmed to actually mutate the real `window`.
        try:
            js.eval(f"window.{_JS_STATE_VAR} = null")
        except Exception:
            pass
    else:
        if _native_ws is not None:
            _track(_native_ws.close())
        _native_ws = None
        _native_closed = True
        _native_inbox.clear()


def disconnect():
    """Saída explícita da room (botão "Sair", ou o app decidindo encerrar
    a sessão) - ao contrário do _teardown() interno que connect() usa,
    esta reseta _is_host: reconectar depois começa sem papel nenhum até
    criar/entrar numa room de novo."""
    global _is_host
    _teardown()
    _is_host = False
