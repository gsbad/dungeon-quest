# Plano de implementação: modo cooperativo

**Status: implementado (L1-L14 completos).** Ver `docs/design.md`'s seção
"Modo cooperativo" pro resumo das mecânicas e `docs/architecture.md` pros
módulos/endpoints - este documento continua valendo como registro
histórico das decisões e da ordem de construção, mas não descreve mais um
plano em aberto.

**Pós-L14 (bugfix round, ver "Correções pós-playtest coop" em `design.md`):**
um playtest real com 2 jogadores achou dois gaps que a v1 não cobria -
quebra de bloco/chave escondida sem sync nenhum, e dano de guest contra
`Enemy`/`Boss` sendo um no-op silencioso (documentado desde a própria L6
como "incremento futuro"). Os dois corrigidos - ver `design.md` pros
detalhes e `tools/coop_harness.py`'s `run_world_sync_test()` pra
verificação via tráfego de rede real.

**Pós-L16 (2ª rodada de bugfix, ver "2ª rodada de correções pós-playtest
coop" em `design.md`):** um novo playtest reportou os mesmos sintomas de
sync ainda presentes - investigação achou que `block_broken`/`hit_request`
já eram simétricos de verdade (confirmado com uma extensão do harness
testando a direção host→guest, nunca coberta antes), e a causa real
era `_cast_frost_nova()` ter ficado de fora do pipeline `hit_request` que
melee/dash/Bola de Fogo já usavam - um guest lançando Nova de Gelo contra
um inimigo do host aplicava dano só local (revertia no snapshot seguinte),
e a magia nunca verificava `remote_players` pra PvP também. Os dois
corrigidos juntos. Tela de vitória de fase coop redesenhada (placar por
jogador) e o easter egg do "mapa do tesouro" também entraram nesta
rodada - ver `design.md`.

Companheiro de `docs/coop-feasibility.md` (Stage K21) — aquele documento
decidiu **o quê** e **por quê** (arquitetura host-autoritativo, WebSocket
pelo backend já existente, o que cada peça pedida exige). Este cobre **em
que ordem construir**, com pontos de entrada concretos no código atual e
as decisões que precisam ser tomadas antes de cada fase começar. Ainda sem
código — é o plano, não a implementação.

## Como usar este documento

Cada sub-estágio abaixo é dimensionado pra ser um PR/sessão coerente,
mesmo padrão de granularidade que K1-K23 usaram nesta sessão (~20
sub-estágios cobriram desde ícones até deploy automatizado). A letra
sugerida é **L** (sequência depois de K) — não é obrigatório seguir a
numeração exata, mas a ordem de dependência entre eles é real e vale
respeitar: um L6 não faz sentido sem L5, mas L10-L14 (PvP/chat) não
dependem de L5-L9 (sync de combate) tanto quanto parece à primeira vista
— ver a nota de reordenação no fim da Fase 3.

## Decisões a tomar antes de começar (a feasibility study deixou em aberto)

Nenhuma delas bloqueia o início da Fase 1, mas todas bloqueiam pelo menos
um sub-estágio específico da Fase 2 ou 3 — marcado em cada uma:

1. **Revive automático ou assistido?** Cai sozinho após 5s, ou precisa de
   outro jogador chegar perto? Muda a UI de L9 (precisa ou não de um
   indicador "reviva-me aqui" no chão/HUD).
2. **Split de XP/ouro: igual ou proporcional?** Dividido em partes iguais
   entre quem está na room, ou proporcional a quem participou do combate
   (dano causado, por exemplo)? Muda a lógica de L8, não sua estrutura.
3. **Código de room: como é gerado/compartilhado?** Curto o bastante pra
   digitar em um teclado virtual mobile (a base já lida bem com
   isso - ver `game/input_system.py`), mas precisa de uma fonte (aleatório
   client-side? sequencial do backend?). Afeta L1 e L4.
4. **Host cai no meio da partida: o que acontece com o resto?** A
   feasibility study já cravou "sem migração de host na v1" — mas não diz
   se os outros jogadores voltam pro menu, ou continuam sozinhos na cópia
   local do `Level` que já tinham. Afeta L5.

## Fase 1 — Infraestrutura de relay (sem combate)

Objetivo do milestone: dois clientes na mesma room se veem andando pelo
mesmo nível, sem nenhuma interação de jogo além de posição/animação.
Comparável em tamanho a 3-4 dos sub-estágios K já concluídos.

- **L1 — Endpoint WebSocket + rooms em memória** (`backend/app/main.py`).
  Um `dict room_id -> {websocket: connection_state}` process-local, nunca
  no SQLite (é efêmero — ver feasibility study). Mensagens: entrar,
  sair, broadcast de posição. Sem autenticação de jogo (login continua
  opcional, ver "Login" na feasibility study) — só o código da room.
  Decisão #3 bloqueia a escolha de como o `room_id` nasce.

- **L2 — Sessão WebSocket do lado cliente** (`game/net_coop.py`, módulo
  novo). Explicitamente ao lado de `game/net.py`, não uma extensão dele —
  `net.py` é fire-and-forget por natureza (`_track()`, sondagem depois),
  isso aqui precisa de uma conexão viva lendo/escrevendo todo frame (ou a
  cada N frames) sem travar o loop `asyncio.sleep(0)` que o pygbag exige.

- **L3 — `RemotePlayer`, entidade leve só-visual** (`game/` — provavelmente
  `game/remote_player.py`, novo). Não é um `Player` completo (esse carrega
  input local, física, hotbar): só posição/direção/HP/animação pra
  desenhar e interpolar. Interpolação entre snapshots é obrigatória aqui,
  mesmo mirando só rede local (ver risco #6 da feasibility study) — sem
  ela, jogadores remotos "piscam" a cada broadcast em vez de deslizar.

- **L4 — UI de entrar/criar room** (novo overlay, mesmo padrão
  `Panel`/`TextButton` de `game/merchant.py`/`game/settings_overlay.py`).
  Lista de quem já está conectado. Decisão #3 define o que essa tela
  realmente pede pro jogador digitar/ler.

- **L1.5 — Harness de teste multiplayer, construído AQUI, não depois.**
  A disciplina atual (Playwright headless, 1 browser, screenshot) não
  cobre "dois clientes na mesma room ao vivo" (risco #5 da feasibility
  study). Adiar isso pra Fase 2 ou 3 significa validar toda a lógica de
  combate/PvP sem uma forma automatizada de reproduzir bugs de sync — o
  mesmo tipo de ponte que já valeu a pena pra bugs single-player só de
  navegador (ver memória do projeto sobre automação Playwright). Pelo
  menos 2 `BrowserContext`s do Playwright coordenados no mesmo teste,
  cada um entrando na mesma room. Vale construir logo depois de L1/L2
  estarem de pé, pra já validar eles com o harness certo em vez de olhar
  screenshot manualmente.

## Fase 2 — Sincronização de combate (host-autoritativo)

Objetivo do milestone: uma partida coop completa de uma fase, com
monstros de verdade (IA/dano/drop simulados só no host), XP/ouro
compartilhado, e revive/fim de partida funcionando. **A fase de maior
risco arquitetural do projeto inteiro** — mexe no núcleo do loop de
gameplay, não é aditiva.

- **L5 — Eleição de host.** V1: quem cria a room é o host, sem migração
  (decisão #4 define o que acontece com os outros se ele cair).

- **L6 — "Modo rede" em `Level`/`Enemy`/`Boss.update()`.** O core do
  trabalho desta fase. No host: comportamento idêntico ao single-player
  de hoje. Nos outros clientes: IA/rolagem de dano/drop ficam desligados,
  o estado dos inimigos vem só do broadcast do host e é aplicado
  direto (mesma relação "recebe snapshot, só desenha" que `RemotePlayer`
  já tem com jogadores). Precisa tocar as 3 classes porque as 3 já têm
  `update()` que mistura IA e física no mesmo método — não dá pra
  interceptar num ponto só.

- **L7 — Dano jogador-contra-jogador do zero.** `Player.take_damage()`
  hoje só reconhece monstro/boss/hazard como origem (ver
  `game/player.py`/`game/combat_fx.py` pros tipos de dano existentes:
  physical/magic/DoT). Precisa de uma origem nova, "outro jogador", que
  os passos de PvP da Fase 3 (L11/L12) vão depender de já existir - por
  isso está aqui, não na Fase 3, mesmo sem PvP amigável ainda ligado a
  ela.

- **L8 — XP/ouro compartilhado.** O ponto de crédito já é centralizado
  (`Level.credit_kill()`, `Player.gain_xp()`/`credit_gold()` — ver
  feasibility study). Trocar "aplica só em quem deu o golpe final" por
  "broadcast pra room, cada cliente aplica no próprio `Player`". Decisão
  #2 (igual vs. proporcional) é a única incerteza real aqui - a mecânica
  de aplicar já existe.

- **L9 — Estado "caído" + revive + fim de partida.** Novo campo de
  estado em `Player` (paralelo a como `dashing`/`key_pose_timer` já
  travam movimento temporariamente - ver `game/player.py`), timer de 5s,
  checagem de "todos caídos ao mesmo tempo" encerra a partida. Decisão #1
  define se esse timer sozinho já revive, ou se precisa de um segundo
  jogador por perto - isso muda se `Level`/`GameplayState` precisam
  rastrear proximidade entre jogadores pra essa checagem.

## Fase 3 — PvP amigável + chat

Objetivo do milestone: os 4 buffs/debuffs de PvP amigável e o chat por
balão de fala funcionando numa partida coop completa.

- **L10 — Traiçoeiro / Homicida.** Direto no `StatusEffectDef` que já
  existe (`game/status_effects.py`, ~16 eixos percentuais desde o Stage
  K10) - `physical_damage_mult`/`magic_damage_mult`/etc. abaixo de 1.0,
  sem estrutura nova nenhuma. O sub-estágio mais barato de toda a Fase 3.

- **L11 — Plumbing de bônus dirigido (jogador→jogador).** Pré-requisito
  de Reação Justa/Acerto de Contas: uma lista de
  `{alvo_id, bonus, expira_em}` por jogador, checada na hora de resolver
  dano PvP (que L7 já deixou existir). Isso é uma estrutura genuinamente
  nova - o `StatusEffectDef` atual só expressa "esse stat do jogador X
  está X% melhor/pior", nunca "X causa mais dano especificamente contra
  Y".

- **L12 — Reação Justa / Acerto de Contas**, montados em cima de L11.

- **L13 — Widget de texto livre**, novo do zero (cursor piscando,
  backspace, Enter confirma/Esc cancela). Sem precedente reaproveitável
  no código hoje — o mais perto é a captura de uma tecla do remapeamento
  (`game/keybinds.py`/Stage K15) ou o nome do personagem (tela dedicada de
  criação, não um campo em jogo). PC-only por escolha deliberada (ver
  feasibility study) - mobile não tem hoje nem teclado virtual nem um
  fluxo de "abrir teclado do celular" pra reaproveitar.

- **L14 — Balão de fala acima do herói**, 3.5s, transportado no mesmo
  canal WebSocket de L2 (mensagem de chat é só mais um tipo de mensagem
  no mesmo transporte, sem persistência - desaparece com o balão).

### Nota de reordenação: chat não depende de combate

L13/L14 (chat) só dependem do transporte WebSocket de L1/L2 - nada de
L5-L9. Se o valor de "jogar junto e conversar" for mais alto que "PvP
amigável" pra uma primeira entrega, dá pra fazer L13/L14 logo depois da
Fase 1, antes de enfrentar o risco arquitetural da Fase 2. L10-L12
(PvP amigável de verdade) são os únicos que realmente precisam esperar
L7.

## Estimativa e sequenciamento

```
Fase 1: L1 → L2 → L3 → L4          (+ L1.5 harness, em paralelo com L2/L3)
Fase 2: L5 → L6 → L7 → L8          (L8/L9 podem ser paralelos entre si)
                  └──→ L9
Fase 3: L10 (paralelo, sem dependência)
        L7 → L11 → L12
        L2 → L13 → L14
```

Contando os 14 sub-estágios (mais o harness) contra os ~20-23 que K1-K23
cobriram nesta sessão, um coop completo é da mesma ordem de grandeza que
a sessão inteira que acabou de rodar - **múltiplas sessões futuras por
conta própria**, não algo pra encaixar de raspão. A Fase 2 concentra o
risco real (L6 é o único sub-estágio que reescreve comportamento
existente em vez de adicionar algo novo ao lado); Fases 1 e 3 são, cada
sub-estágio isoladamente, do mesmo tamanho/risco que qualquer Stage K já
concluído.
