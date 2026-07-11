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

`BASE_XP`/`GOLD_DROPS` (`game/stats.py` — dados puros, sem dependência de pygame, para `tools/balance_sim.py` poder rodar headless): esqueleto 10 XP/4 ouro, goblin 8/3, dark_knight 25/10. Bosses (`xp_reward`/`gold_reward` fixos, não escalam por ML — são encontros únicos calibrados à mão, não mobs fungíveis): Rei das Sombras 150 XP/60 ouro, Cacodemon 300/120.

## Nível de monstro (ML) — Stage B1

`MONSTER_GROWTH_VECTOR = {vigor: +2, strength: +1, dexterity: +0.5}` por ML, aplicado em cima do bloco de atributos do arquétipo (`scale_archetype()`). ML1 é um no-op — reproduz exatamente a calibração da Stage A3, sem mudança de comportamento nos monstros de ML1.

XP/ouro por kill escalam pela mesma fórmula (`scale_by_ml`, `+35%` por ML acima de 1), sem tabela de multiplicador separada. **Regra anti-farm:** um monstro 5+ níveis abaixo do jogador dá só 10% do XP — impede que grindar conteúdo trivial também grinde XP trivialmente. Ouro **não** tem essa penalidade de propósito: farmar fase já limpa por ouro (pra comprar poção antes da próxima dificuldade) é o loop pretendido, não algo a suprimir.

`LEVEL_MAPS[n]["monster_level"]`: Floresta Encantada ML1, Ruínas do Deserto ML4, Masmorra das Sombras ML8 — rampa dentro da campanha Normal atual (3 fases).

`tools/balance_sim.py` (roda sem pygame — `python tools/balance_sim.py`) imprime curva de XP, progressão de jogador/monstro, matriz de time-to-kill, XP/ouro por kill, e contribuição de DPS dos status effects. Usar antes de qualquer ajuste manual de número de combate.

## Ouro e itens

Ouro dropa fisicamente no mapa em kills de inimigo comum (`GoldDrop`, 3s visível + 2s piscando, depois desaparece se não coletado) — visualiza a decisão do jogador de arriscar ir buscar ou seguir em frente. Kills de boss creditam ouro instantaneamente (sem pickup: a fase termina imediatamente na morte do boss, não há janela de jogo pra andar até uma moeda).

Itens (`game/items.py`):
- Poção de Vida — 15g, cura 50% da vida máxima atual.
- Poção de Mana — 12g, cura 60% da mana máxima atual.
- Antídoto — 20g, cura Veneno/Lentidão/Fraqueza instantaneamente.

Cura em *fração* do máximo atual (não valor fixo) — mantém as poções relevantes conforme VIG/INT sobem, mesma convenção já usada pro coração-pickup.

## Magias (Stage B2)

`game/spells.py` — 3 magias iniciais, cada uma reaproveitando um sistema existente (nenhuma renderização nova):

| Magia | Efeito | Custo | CD | Requisito | Reaproveita |
|---|---|---|---|---|---|
| Bola de Fogo | Projetil reto, dano mágico | 8 mana | — | INT 15 | `Projectile` (`game/boss.py`) |
| Nova de Gelo | Dano em área + Lentidão | 12 mana | — | INT 20, SAB 15 | O efeito "slow" já existente |
| Luz Curativa | Cura 25% da vida máxima | 15 mana | 10s | SAB 25 | Mesma fórmula de fração das poções |

Magia "desbloqueada" = atende aos requisitos de atributo no momento — não é uma flag persistida (mesmo raciocínio de `profession` não estar no save). Conjuração: teclado 1/2/3 conjura direto; celular seleciona a magia na aba "Magias" do paperdoll e dispara com um botão dedicado.

## Status effects (debuffs)

`game/status_effects.py` — `StatusEffectCarrier` é um componente reutilizável, anexado tanto ao `Player` quanto ao `Enemy` (Stage B2) — a Nova de Gelo lentifica inimigos com o mesmo carrier que os ataques de monstro já usam no jogador, não uma segunda implementação.

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
