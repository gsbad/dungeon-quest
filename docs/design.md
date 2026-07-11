# Dungeon Quest — Design técnico

Documento vivo. Atualizar sempre que uma fórmula, taxa ou decisão de balanceamento mudar — não deixar a implementação divergir do que está escrito aqui.

## Atributos e stats derivados

Todo personagem (jogador, inimigo, boss) usa `StatBlock` (`game/stats.py`) — mesmas fórmulas para todos:

| Stat derivado | Fórmula |
|---|---|
| Vida máxima | `20 + 3·VIG` |
| Dano físico | `weapon_base + 0.5·STR` |
| Mana máxima | `5 + 2·INT` |
| Regen. mana/s | `1.0 + 0.05·INT` |
| Dano mágico (bônus) | `+4%·WIS` sobre o dano base da magia |
| Velocidade de movimento | `base_speed + 1.2·DEX`, teto `base_speed + 60` |
| CD de ataque (→ velocidade de ataque) | `0.45·(1 − min(0.35, 0.003·DEX))` |

`weapon_base`/`base_speed` são constantes por arquétipo (jogador, goblin, esqueleto, dark_knight, cada boss) — o mesmo papel que uma arma ou build de monstro já fariam, não um número mágico solto.

**Por que DEX não controla velocidade de movimento sem teto:** o jogo é baseado em perseguição — um build DEX puro sem teto ficaria intocável. DEX controla principalmente velocidade de ataque; o componente de movimento é secundário e limitado.

## Profissões

`game/professions.py` — inspirado em Ultima Online. Profissão é **derivada** dos pontos gastos em atributo (`atual - 10`), não armazenada — troca de build (respec gratuito no paperdoll) = troca de profissão, por design, não um caso especial.

Algoritmo:
1. `total_gasto < 20` → **Aventureiro**.
2. Senão, ranqueia os 5 atributos por pontos gastos (empate: STR > DEX > INT > WIS > VIG).
3. Se o segundo colocado gastou menos da metade do primeiro (`spent[p2]/spent[p1] < 0.5`) → profissão **pura** do primeiro.
4. Senão → profissão **híbrida** do par.

5 puras + 10 híbridas (todos os pares de 5 atributos) + Aventureiro = 16 profissões. Cada uma tem uma cor de tint (`TINTS`) aplicada no retrato do paperdoll (multiplicação de canal sobre a sprite procedural existente) — placeholder visual até o Stage C trazer spritesheets reais por profissão.

## XP e nível

`xp_to_next(L) = round(20·L^1.4)`. Nível máximo 30. `POINTS_PER_LEVEL = 4` pontos de atributo por level-up (ver seção "Correções de escopo" abaixo — a implementação inicial usou 3 sem confirmação, corrigido nesta sessão).

XP por inimigo (`game/enemy.py BASE_XP`): esqueleto 10, goblin 8, dark_knight 25. Bosses (`xp_reward`): Rei das Sombras 150, Cacodemon 300. Sem escalonamento por nível de monstro ainda — isso é o passo B1 do roadmap (ver plano em `.claude/plans/`).

## Ouro e itens

Ouro dropa fisicamente no mapa em kills de inimigo comum (`GoldDrop`, 3s visível + 2s piscando, depois desaparece se não coletado) — visualiza a decisão do jogador de arriscar ir buscar ou seguir em frente. Kills de boss creditam ouro instantaneamente (sem pickup: a fase termina imediatamente na morte do boss, não há janela de jogo pra andar até uma moeda).

`GOLD_DROPS` (`game/enemy.py`): esqueleto 4, goblin 3, dark_knight 10. `gold_reward` de boss: Rei das Sombras 60, Cacodemon 120.

Itens (`game/items.py`):
- Poção de Vida — 15g, cura 50% da vida máxima atual.
- Poção de Mana — 12g, cura 60% da mana máxima atual.
- Antídoto — 20g, cura Veneno/Lentidão/Fraqueza instantaneamente.

Cura em *fração* do máximo atual (não valor fixo) — mantém as poções relevantes conforme VIG/INT sobem, mesma convenção já usada pro coração-pickup.

## Status effects (debuffs)

`game/status_effects.py` — `StatusEffectCarrier` é um componente reutilizável (não hardcoded no `Player`), pra poder ser anexado a `Enemy`/`Boss` depois (ex.: a Frost Nova do jogador vai lentificar inimigos usando o mesmo carrier).

| Efeito | Efeito mecânico | Duração | Cura |
|---|---|---|---|
| Veneno | 3 dano a cada 5s | ~12s (auto-resolve) | Antídoto (instantâneo) |
| Lentidão | -45% velocidade de movimento | ~12s (auto-resolve) | Antídoto (instantâneo) |
| Fraqueza | +30% dano recebido | ~12s (auto-resolve) | Antídoto (instantâneo) |
| Fogo | 2 dano a cada 2s, exatamente 3 ciclos | 6s (fixo) | Nenhuma |

**Decisão deliberada — debuffs são temporários, não permanentes-até-curar:** a leitura literal do pedido original ("cura com Antídoto") não especificava duração para Veneno/Lentidão/Fraqueza. Permanente-até-curar cria risco real de espiral de morte (jogador envenenado sem ouro pra comprar Antídoto, sem conseguir farmar ouro porque está sendo envenenado). Confirmado com o usuário: duração generosa (~12s) que se resolve por conta própria, com o Antídoto acelerando a cura em vez de ser o único jeito de parar o efeito.

Reaplicar um efeito **atualiza a duração** (refresh), não empilha — evitar múltiplas fontes de Veneno virarem um DPS absurdo por acúmulo.

Ticks de dano (DoT) passam direto por `hp -=`, sem passar por `take_damage()` — não devem ser bloqueados pelas i-frames de golpe corpo-a-corpo, e não devem gerar i-frame nenhuma.

## Clima

`game/weather.py` — Nevoeiro (overlay translúcido), Chuva/Neve (partículas caindo), Tempestade (chuva + flash de tela ocasional). `speed_mult`/`visibility_mult` em cada tipo ficam neutros (1.0) por enquanto — gancho pra uma passada futura de jogabilidade (ex.: Nevoeiro reduzindo alcance de agressão de inimigos) sem precisar redesenhar o módulo.

Atribuído por nível via `LEVEL_MAPS[n]["weather"]` — Floresta Encantada (fog), Ruínas do Deserto (rain), Masmorra das Sombras (snow), Trono das Trevas (storm). Atribuição atual é pra cobertura de teste dos 4 tipos, não necessariamente a escolha temática final.

## Debuffs de ataques de inimigos (chance por hit)

`EnemyProjectile`/`Projectile` ganham `status_effect`/`status_chance` opcionais; ao colidir com o jogador, rola a chance e aplica o efeito.

| Fonte | Efeito | Chance |
|---|---|---|
| Poça de ácido do goblin (contato) | Veneno | 20% |
| Projétil mágico do dark_knight | Fraqueza | 15% |
| Rei das Sombras — rajada circular | Lentidão | 10% |
| Rei das Sombras — espiral | Lentidão | 10% |
| Rei das Sombras — tiro mirado (fase 2) | Fraqueza | 25% |
| Rei das Sombras — tiro triplo | nenhum (mantém variedade) | — |
| Cacodemon — tiro triplo | Fogo | 15% por projétil |

## Bugs reais encontrados durante o desenvolvimento (não features, correções)

- **`CacodemonBoss.update()` nunca checava colisão de projétil com o jogador** — o boss da fase secreta não causava dano nenhum desde antes desta rodada de features. Corrigido ao ligar o gancho de debuff de Fogo nesse boss.
- **Clique de mouse desalinhado no build pygbag/navegador** (som/tela cheia/comprar não respondem onde desenhados) — 6 tentativas de fix falharam (ver memória do projeto). Toque real e teclado não são afetados. Deixado de lado por decisão do usuário; não re-tentar sem um diagnóstico novo (console JS do navegador, nunca verificado até agora).

## Correções de escopo aplicadas depois da primeira implementação

- **Pontos de atributo por level-up: 3 → 4.** O usuário especificou 4 desde o início; a implementação inicial usou 3 sem confirmação. Corrigido nesta sessão, com migração de save (ver `save-schema.md`).
