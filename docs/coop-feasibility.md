# Estudo de viabilidade: modo cooperativo

Documento de análise (Stage K21) — **sem código**, por pedido explícito. Cobre arquitetura recomendada, o que muda no app atual, o sistema de PvP amigável pedido, chat, e uma estimativa honesta de esforço/risco. Escopo do pedido original: LAN/rede local pra começar, sem limite de jogadores, revive de 5s (partida acaba se todos caírem ao mesmo tempo), PvP amigável com debuffs/buffs novos, XP/ouro compartilhado, chat por balão de fala (PC).

## Arquitetura recomendada: WebSocket através do backend já existente

O candidato natural é um endpoint WebSocket no mesmo FastAPI que já hospeda `/save`/`/leaderboard`/`/admin` (`backend/app/main.py`) — não um servidor separado. Caddy (já na frente do backend, ver `docs/deploy.md`) faz proxy de WebSocket com a mesma diretiva `reverse_proxy` que já usa pra HTTP, sem infraestrutura nova na VM.

- **Um "room" por partida**, identificado por um código curto (não precisa de login — ver "Login" abaixo). O backend mantém isso só em memória (dict `room_id → {websocket: player_state}`), nunca no SQLite — é efêmero, dura o tempo da partida, não é dado que precisa sobreviver a um restart do processo.
- **Sincronização por broadcast periódico**: cada cliente manda sua própria posição/estado a cada tick (algo como 10-15 vezes/segundo), o servidor redistribui pros outros na mesma room. Simples de implementar, e o pedido original já aponta essa direção.

### A decisão que mais importa: quem simula os inimigos

Hoje **o jogo inteiro roda no cliente** — IA de inimigo, rolagem de dano, drop, tudo em `game/*.py`, sem chamada de rede no caminho crítico (ver `docs/architecture.md`). O backend nunca importa `game/`, de propósito. Coop força uma escolha:

1. **Host-autoritativo** (recomendado): um dos jogadores "hospeda" a partida — só o `Level`/`Enemy`/`Boss` *dele* realmente simula IA/dano/drop; os outros clientes recebem um snapshot do estado dos inimigos e só desenham. O servidor continua um relay burro (não precisa saber nada de regras de jogo) — mesma filosofia offline-first que o projeto já tem. Risco principal: se o host cai, a partida também cai (sem migração de host nesta v1).
2. **Servidor-autoritativo**: o backend passaria a rodar a simulação de verdade — ou um pygame headless no servidor (pesado, incomum), ou uma segunda implementação em Python das mesmas regras de combate/IA que hoje só existem em `game/*.py`. Isso é exatamente o tipo de duplicação que o projeto já evita ativamente (`BALANCE_DEFAULTS`, no backend, já é uma cópia read-only dos valores de `game/` só porque o backend não pode importar `game/` — duplicar a *lógica* de combate seria um problema de deriva bem maior que duplicar alguns números).

A opção 1 é a única consistente com a arquitetura atual sem reescrever a separação cliente/servidor que o projeto inteiro é construído em cima de. Custo real: `Level.update()`/`Enemy.update()` precisam de um modo "rede" — no host, comportamento normal; nos outros clientes, IA/dano ficam desligados e o estado vem só do broadcast. Isso toca o coração do loop de gameplay, não é uma feature isolada.

## O que muda no app atual

- **Não existe hoje nenhum loop de rede contínuo.** `game/net.py` é inteiramente "dispara uma requisição, sondagem depois" (`_track()`/tasks assíncronos, sem conexão persistente) — o modelo certo pra sync de save/leaderboard, errado pra posição de jogador em tempo real. Coop precisa de uma peça nova: uma sessão WebSocket viva, lendo/escrevendo mensagens todo frame (ou a cada N frames), ao lado do `net.py` existente, não substituindo-o (save/leaderboard continuam precisando só do padrão fire-and-forget de hoje).
- **Jogadores remotos não são `Player` completo.** Um `Player` de verdade carrega input local, física, hotbar, etc. — um jogador remoto só precisa de posição/direção/HP/animação pra desenhar e interpolar. Precisa de uma classe nova, leve, só-visual.
- **`GameplayState.update()` ganha um branch de rede** — enviar estado local, receber/aplicar estado remoto, sem travar o frame esperando resposta (compatível com o `asyncio.sleep(0)` por frame que o pygbag já exige, mas é lógica nova, não reaproveitamento).
- **Latência/jitter**: mesmo mirando só rede local (baixa latência, pedido explícito), qualquer sync por rede precisa de alguma interpolação pra não ficar "engasgado" — problema que este projeto nunca teve antes (é 100% single-player hoje).

## Login

O jogo tem uma regra forte e documentada: **login nunca é obrigatório pra jogar** (`docs/architecture.md`) — só é necessário pra sync entre dispositivos e leaderboard. Coop deveria manter esse princípio: entrar numa room usa só um código curto (sem exigir conta Google), e o nome mostrado é o `player.name` do save local. Login continua reservado pro que já faz hoje. Isso mantém "jogar com um amigo na mesma rede" tão simples quanto o offline-first já promete, sem inventar uma segunda camada de conta.

## PvP amigável: Traiçoeiro / Reação Justa / Homicida / Acerto de Contas

Os 4 são buffs/debuffs — mecanicamente, o mesmo `StatusEffectDef`/`StatusEffectCarrier` que já existe (`game/status_effects.py`, generalizado no Stage K10 com ~16 eixos percentuais). Dois deles cabem direto nesse sistema sem mudança nenhuma:

- **Traiçoeiro** (-15% em todos os stats, 10s, no agressor que acerta um aliado): um buff comum, `physical_damage_mult`/`magic_damage_mult`/etc. todos abaixo de 1.0 ao mesmo tempo — já dá pra expressar com os campos que existem hoje.
- **Homicida** (-35% em todos os stats, 2min, em quem mata um aliado): mesma forma, só mais forte/mais longo.

Os outros dois são um problema diferente, genuinamente novo:

- **Reação Justa** / **Acerto de Contas** (janela de retaliação contra especificamente quem te atingiu/matou): o sistema de buff atual é sempre "esse stat do jogador X está X% melhor/pior", nunca "o jogador X causa mais dano *contra o jogador Y especificamente*". Isso é uma relação **dirigida** entre dois jogadores, não um multiplicador solto — precisa de uma estrutura nova (algo como uma lista de `{alvo_id, bônus, expira_em}` por jogador, checada na hora de resolver dano PvP), não uma extensão do `StatusEffectDef` existente.

Além disso, **dano jogador-contra-jogador não existe hoje de forma nenhuma** — `Player.take_damage()` não tem conceito de "esse dano veio de outro jogador" (só de monstro/boss/hazard). Isso é pré-requisito de tudo isso funcionar, não parte do sistema de buff em si.

## Chat por balão de fala (PC)

Pedido: Enter abre um campo de texto, a mensagem enviada aparece como balão acima do herói por 3,5s. Duas peças:

- **Transporte**: mais uma mensagem no mesmo canal WebSocket da posição/combate — barato, sem storage no servidor (é efêmero, desaparece com o balão).
- **Campo de texto**: **não existe nenhum widget de entrada de texto livre no jogo hoje** — o mais perto disso é a captura de uma única tecla no remapeamento (Stage K15) e o nome do personagem, que é digitado numa tela dedicada de criação, não um campo reaproveitável em jogo. Precisa de um componente novo (cursor piscando, backspace, Enter confirma/Esc cancela) — pequeno individualmente, mas zero precedente no código pra copiar.

PC-only é a escolha certa também por essa razão: não existe teclado virtual nem um mecanismo de "abrir teclado do celular" no fluxo atual — chat em mobile ficaria pra uma rodada futura, não é uma limitação artificial do escopo, é o que a base de código realmente suporta hoje.

## Revive e fim de partida

- Morrer em coop (em vez do fluxo solo atual, que reinicia a fase) entraria num estado novo de `Player` — "caído", contador de 5s, depois volta. Mecanicamente pequeno (é um timer + um branch em `update()`), mas levanta uma pergunta em aberto que o pedido original não especifica: o revive é automático ao fim dos 5s, ou precisa de outro jogador chegar perto? Ambos são razoáveis; a escolha muda a UI (precisa ou não de um indicador "reviva-me aqui").
- **Partida acaba se todos caírem ao mesmo tempo**: checagem direta (`nenhum Player vivo` → fim), sem complicação adicional.

## Ouro/XP compartilhado

O ponto de crédito já existe e é centralizado (`Level.credit_kill()`, `Player.gain_xp()`/`credit_gold()` — este último inclusive já reforçado no Stage K12 pra aplicar multiplicadores de buff). Compartilhar é, em essência, trocar "aplica só no jogador que acertou o golpe final" por "broadcast pra todos na room, cada cliente aplica no seu próprio `Player`" — a peça de mais trabalho aqui é decidir a regra de split (dividido igualmente? proporcional a quem participou do combate?), não a mecânica de aplicar.

## Estimativa honesta de esforço/risco

Coop **não é uma feature pequena** — pelo tamanho e pela natureza das mudanças, é comparável ao Stage K inteiro (K1-K20, a leva de mudanças processada nesta sessão), não a um único sub-estágio dele. Os riscos concentrados:

1. **A escolha host-autoritativo** mexe no núcleo do loop de gameplay (`Level`/`Enemy`/`Boss.update()`), não é aditivo — precisa de um "modo rede" bem pensado pra não regredir o single-player.
2. **Reação Justa/Acerto de Contas** exigem uma estrutura de buff *dirigido* (jogador→jogador) que não existe — não é reusar o Stage K10, é estender o sistema de verdade.
3. **Dano PvP do zero** — hoje `take_damage()` só conhece monstro/boss/hazard como fonte.
4. **Nenhum widget de texto livre existe** — o chat precisa construir um do zero.
5. **Testar multiplayer é uma categoria de problema nova** pra este projeto — a disciplina atual (Playwright headless, um browser, screenshot pra conferir) não cobre "dois clientes na mesma room ao vivo"; precisaria de pelo menos 2 contextos de browser simultâneos coordenados no mesmo teste, um harness novo.
6. **Latência/interpolação** — mesmo só mirando rede local, é uma categoria de bug (jogador "pisca"/teleporta) que o projeto nunca teve que lidar com antes.

**Fases prováveis, em ordem de dependência** (estimativa aproximada, não um compromisso):

- **Fase 1 — infraestrutura de relay**: endpoint WebSocket, entrar/sair de uma room, broadcast de posição, desenhar jogadores remotos. Sem combate ainda. Ordem de grandeza comparável a 3-4 dos sub-estágios já concluídos nesta sessão.
- **Fase 2 — sincronização de combate**: modo host-autoritativo em `Level`/`Enemy`, XP/ouro compartilhado, revive/fim de partida. A parte de maior risco arquitetural do projeto inteiro.
- **Fase 3 — PvP amigável + chat**: os 4 debuffs/buffs (incluindo a plumbing nova de efeito dirigido), dano PvP, campo de texto, balão de fala.

Dado que esta sessão sozinha processou 20 sub-estágios de complexidade individual comparável (K1-K20), um coop completo é realisticamente um projeto de múltiplas sessões futuras por conta própria, não algo pra encaixar de raspão numa sessão já em andamento — daí o pedido original ter enquadrado isso como "só estudo de viabilidade", não uma implementação.
