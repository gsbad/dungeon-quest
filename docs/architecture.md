# Arquitetura

Visão geral de como as peças do projeto se encaixam — pensado para quem nunca viu o código e quer se situar antes de mexer em alguma parte. Para fórmulas e decisões de *balanceamento* (não arquitetura), ver [`design.md`](design.md); para o schema do save, [`save-schema.md`](save-schema.md); para deploy/CI, [`deploy.md`](deploy.md).

## Visão de 30.000 pés

```
┌─────────────────────────┐        HTTPS         ┌──────────────────────────┐
│   Cliente (navegador)    │ ───────────────────▶ │   Backend (FastAPI)      │
│   pygame → WASM (pygbag) │ ◀─────────────────── │   Oracle Cloud VM        │
│   game/*.py              │   /auth /save /me     │   backend/app/main.py    │
└─────────────────────────┘   /leaderboard /admin  └──────────────────────────┘
                                                              │
                                                       SQLite (dungeon_quest.db)
```

- **O jogo em si roda inteiramente no cliente** - todo combate, IA de inimigo, física de colisão, geração de sprite, tudo em `game/*.py`, sem chamada de rede nenhuma no caminho crítico de jogar. O backend só existe para o que exige um servidor de verdade: login (para não confiar no cliente), sincronização de save entre dispositivos, e o leaderboard (que por definição precisa agregar dados de todo mundo).
- **Offline-first, deliberado**: sem login, o save vive só em `localStorage` do navegador e o jogo funciona 100%. Login com Google é só para sincronizar entre PC/celular e aparecer no leaderboard - nunca um requisito para jogar.
- **Mesma origem em produção**: o Caddy da VM serve o jogo estático *e* faz proxy reverso do backend no mesmo domínio (`https://<host>/save`, não um subdomínio separado) - então CORS só importa em desenvolvimento local (`localhost:8000` → `localhost:8090`), nunca em produção.

## O jogo (`game/`)

Sem motor externo - é um game loop de pygame puro (`main.py`), com `asyncio.sleep(0)` a cada frame só para devolver o controle ao navegador (exigência do pygbag/emscripten, sem efeito no build nativo).

| Módulo | Responsabilidade |
|---|---|
| `states.py` | Máquina de estados principal (`GameStateManager`) - menu, gameplay, telas de morte/vitória/fase completa. `GameplayState` é o maior arquivo do projeto: orquestra player, inimigos, boss, projéteis, clima, overlays (paperdoll/itens/debug/leaderboard). |
| `player.py` | Personagem jogável - stats derivados, ataque/dash/magias (o *disparo*; o *efeito* de cada spell vive em `states.py`), hotbar, sprite. |
| `input_system.py` | Única camada de tradução de input bruto (teclado/mouse/toque) → `Action` lógica. Resolve o bug histórico de desalinhamento de clique do canvas (ver `[[project_pygbag_canvas_stretch_bug]]` nas notas do projeto) e o combate mirado no mouse/drag-to-aim. |
| `enemy.py` / `boss.py` | IA de inimigo comum e de boss (padrões de ataque por fase), e `Projectile` (usado tanto por magias do jogador quanto por ataques de boss - agnóstico de quem disparou). |
| `level.py` | Carrega `LEVEL_MAPS`, resolve colisão de parede, checa condição de saída de fase. |
| `stats.py` | `StatBlock` - toda fórmula derivada (dano, defesa, HP, mana, velocidade) para jogador *e* monstro, uma fórmula só, sem duplicação por tipo. |
| `professions.py` / `spells.py` / `items.py` / `affixes.py` / `difficulty.py` / `weather.py` / `status_effects.py` / `stances.py` | Sistemas de RPG independentes entre si - cada um é essencialmente uma tabela (`dict`) + uma função pequena que lê a tabela, sem hierarquia de classes. `status_effects.py` cobre tanto debuffs (Veneno, Fogo...) quanto os buffs temporários de poção/elixir - mesmo `StatusEffectDef`/`StatusEffectCarrier`, um player-facing "sofre isso" e outro "bebeu isso". `stances.py` é a única tabela *permanente* (não expira) - uma Postura é derivada direto da profissão atual, igual a profissão já é derivada dos atributos gastos. |
| `keybinds.py` / `settings_overlay.py` | Teclas de ação remapeáveis (ataque/magias/dash/picareta/atalhos de menu) - `keybinds.py` guarda os `BINDINGS` que `input_system.py` de fato consulta; `settings_overlay.py` é a UI que os captura/persiste. Toda UI que mostra uma tecla (hotbar, Paperdoll) lê esse módulo em vez de um literal hardcoded, para nunca ficar desatualizada depois de um remapeamento. |
| `net.py` | Ponte pyodide/emscripten ↔ urllib nativo para chamar o backend - fire-and-forget assíncrono (`schedule()`/`poll_result()`), já que o jogo nunca pode travar esperando uma resposta de rede. |
| `save.py` | Serialização/migração do save (schema versionado, ver `save-schema.md`). |
| `assets.py` | Todo sprite/ícone é pixel art gerada em código (`pygame.draw.*` sobre `Surface`), zero arquivo de imagem externo - o projeto inteiro roda de um clone git sem baixar nenhum asset. Um punhado de sprites (monstros, ícones de item) checa `appearance_overrides.py` antes de cair no pintor procedural - ver "Editor de aparência" abaixo. |
| `appearance_overrides.py` | Overrides de sprite vindos do editor de pixel do painel admin (`/appearance`) - um `pygame.Surface` decodificado de um PNG em base64 por chave de entidade, substituindo o sprite gerado em código quando presente. |
| `leaderboard.py` / `reputation.py` / `balance_config.py` | Leaderboard (busca via `net.py`), reputação derivada de kills/mortes, e o dispatch de overrides de balanceamento vindos do painel admin (`/admin`). |

**Por que o backend duplica alguns defaults do jogo** (`BALANCE_DEFAULTS`, contagem de conquistas): o deploy do backend não tem acesso ao pacote `game/` (são dois deploys/processos separados, o backend nem importa pygame). Em vez de criar uma dependência cruzada esquisita, os poucos valores que o backend precisa saber (preços, custos de magia, stats de monstro, efeitos de buff/debuff, bônus de postura, o que conta como conquista) são pequenas reimplementações somente-leitura, deliberadamente - `BALANCE_DEFAULTS` tem ~330 chaves pontilhadas (`"monster.goblin.strength"`, `"buff.buff_orange.physical_damage_mult"`, `"stance.Guerreiro.physical_damage_mult"`...), geradas diretamente a partir dos dicts reais do jogo (não digitadas à mão) para não desviar dos valores de verdade.

## O backend (`backend/`)

FastAPI + SQLAlchemy + SQLite, todo em `backend/app/main.py`/`models.py` (propositalmente pequeno - é só a parte que *precisa* ser servidor).

- **Autenticação**: dois formatos de claim JWT com o mesmo segredo, nunca intercambiáveis - token de jogador (`sub`/`email`/`name`, emitido a partir de um login Google real) vs. token de admin (`admin: true`, emitido por `/admin/login` com senha própria). `_current_user()`/`_require_admin()` nunca aceitam o token errado.
- **`/save`**: GET/PUT do save do jogador logado, chave é o `sub` do JWT.
- **`/leaderboard`**: só lista jogadores que já sincronizaram pelo menos uma vez com login Google - um save 100% offline nunca aparece, sem precisar de nenhuma lógica extra para isso.
- **`/admin`**: painel HTML+JS auto-contido (uma rota só, sem build de frontend separado) para editar preços/custos de magia/stats de monstro/efeitos de buff-debuff/bônus de postura em runtime, sem redeploy - `game/balance_config.py` aplica os overrides no cliente na próxima sincronização. Organizado em abas por categoria (Geral/Dificuldade/Monstros/Magias/Itens/Buffs/Debuffs/Posturas), cada entidade num `<details>` colapsável. Inclui um editor de pixel real (grade 16x16, `AppearanceOverride` no banco) para sobrescrever a aparência de monstros/itens sem editar código - `game/appearance_overrides.py` decodifica e aplica no cliente.

## Deploy e CI/CD

Ver [`deploy.md`](deploy.md) para o passo a passo completo. Resumo: uma VM Oracle Cloud Free Tier roda Caddy (HTTPS automático via Let's Encrypt) na frente do jogo estático (`/srv/dungeonquest-web`) e do backend (`127.0.0.1:8090`, systemd). `.github/workflows/deploy.yml` builda e publica automaticamente a cada push em `main`, rodando num runner do GitHub Actions **auto-hospedado na própria VM** - nenhuma chave SSH nem endereço de servidor vira secret do GitHub, já que o runner já vive onde o deploy precisa acontecer.

## Testes

Sem framework de teste tradicional (pytest, etc.) - o jogo é validado ao vivo, num navegador de verdade, via [Playwright](https://playwright.dev/python/) headless: abre o próprio build pygbag/WASM, injeta um save via `localStorage`, simula clique/teclado/toque (inclusive eventos de `Touch`/`TouchEvent` sintéticos para testar controles mobile), e tira screenshot para conferência visual. `tools/balance_sim.py` é a exceção - um simulador headless (sem pygame) de tempo-até-matar por combinação de fase/dificuldade/build, usado para calibrar números antes de qualquer mudança de balanceamento.
