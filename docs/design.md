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

5 puras + 10 híbridas (todos os pares de 5 atributos) + Aventureiro = 16 profissões. Cada uma tem uma cor de tint (`TINTS`) aplicada no retrato do paperdoll (multiplicação de canal sobre a sprite procedural existente) — placeholder visual até o Stage C trazer spritesheets reais por profissão (ver "Individualização de sprites por profissão" mais abaixo, onde isso finalmente aconteceu).

### As 16 profissões

| Profissão | Base (atributo(s) dominante(s)) |
|---|---|
| Aventureiro | nenhum (< 20 pontos gastos no total) |
| Guerreiro | FOR pura |
| Assassino | DES pura |
| Mago | INT pura |
| Feiticeiro | SAB pura |
| Cavaleiro | VIG pura |
| Duelista | FOR + DES |
| Cavaleiro Arcano | FOR + INT |
| Paladino | FOR + SAB |
| Campeão | FOR + VIG |
| Monge | DES + INT |
| Xamã | DES + SAB |
| Ranger | DES + VIG |
| Arcanista | INT + SAB |
| Druida | INT + VIG |
| Templário | SAB + VIG |

"Pura" = o atributo com mais pontos gastos tem pelo menos o dobro do segundo colocado (`spent[p2]/spent[p1] < 0.5`); caso contrário é a híbrida do par top-2. Empate de pontos gastos é resolvido pela ordem fixa FOR > DES > INT > SAB > VIG (`_PRIORITY`, `game/professions.py`). Sorte (SOR) não entra nessa conta — gastar pontos nela não empurra pra nenhuma profissão específica, de propósito (não existe uma profissão "Sortudo").

### Individualização de sprites por profissão

Até esta rodada, as 16 profissões eram a mesma silhueta (a do Aventureiro) com uma cor multiplicada por cima (`TINTS`, aplicado tanto no sprite do jogador em jogo quanto no retrato do paperdoll) — exatamente o problema que já tinha sido corrigido pra bosses e mobs comuns, só que ainda pendente pro herói (o próprio comentário de `TINTS` já dizia "Stage C5 will swap this for real per-profession spritesheets"). Corrigido: `create_player_sprite(direction, attacking, profession=None)` (`game/assets.py`) agora despacha pra um rig próprio por profissão (`PLAYER_SPRITES`/`_PLAYER_RIG_PAINTERS`, mesmo padrão `ENEMY_SPRITES`/`BOSS_SPRITES` já usado) — `profession=None`/`"Aventureiro"` cai no desenho original, inalterado. As 15 profissões reais têm silhueta, capacete/adereço de cabeça e arma próprios (nunca só recoloração), agrupadas em 4 famílias de corpo que compartilham só o bloco de torso/pernas (`_draw_body_heavy_armor`/`_draw_body_light`/`_draw_body_robed`/`_draw_body_monk`):

| Profissão | Família | Arma/prop | Cabeça |
|---|---|---|---|
| Guerreiro | armadura pesada | espada larga + escudo redondo | elmo de aço simples |
| Cavaleiro | armadura pesada | espada + escudo torre | elmo com asas |
| Campeão | armadura pesada | martelo de guerra (2 mãos, sem escudo) | elmo com chifres |
| Paladino | armadura pesada | maça com brilho + escudo com cruz | elmo alado dourado |
| Templário | armadura pesada | espada + escudo torre com cruz | grande elmo fechado (fresta no lugar dos olhos) |
| Cavaleiro Arcano | armadura pesada | espada com brilho azul | elmo com gema |
| Assassino | leve/couro | adagas gêmeas cruzadas | capuz cobrindo o rosto (olhos brilhantes) |
| Duelista | leve/couro | rapieira + adaga de parada | chapéu emplumado |
| Ranger | leve/couro | arco (retesado ao atacar) + aljava | capuz leve |
| Mago | robe | cajado com orbe brilhante | chapéu pontudo |
| Feiticeiro | robe | orbe flutuante brilhante | capuz (sem chapéu) |
| Arcanista | robe | grimório aberto + varinha | diadema/circlet |
| Xamã | robe | totem com pena pendurada | cocar de penas |
| Druida | robe | cajado com brilho | coroa de folhas |
| Monge | único (sem arma) | punho brilhante (faixas) | bandana |

`Player`/`Paperdoll` deixaram de tingir uma sprite fixa: `Player._get_sprite()` cacheia por `(direction+attacking, profession)` e reconstrói quando a profissão muda (respec já dispara `refresh_profession()`); `Paperdoll._portrait_for()` chama `create_player_sprite("down", False, profession)` direto. `TINTS` (`game/professions.py`) fica no código (não referenciado por nada hoje) como paleta de destaque de UI pra uso futuro, mas parou de colorir sprite.

## Reputação (Stage F5)

`game/reputation.py` — título exibido ao lado do nome/profissão na HUD (`Player._draw_title_line()`) e no cabeçalho do paperdoll, inspirado no par fama/carisma de Ultima Online. **Totalmente derivado** de contadores que já existem no save (mesmo raciocínio de `profession` — nada novo pra manter sincronizado):

- **Kills** (`kills_total(player, save_state)`): soma `player.kills`/`player.boss_kills` da run atual (ainda não sincronizados) **+** `save_state["counters"]["kills"]`/`["boss_kills"]` já persistidos (`game/save.py`'s `sync_counters()` faz esse merge no fim da fase). Some sobre **todas** as chaves dos dois dicts — um mob comum, um boss, ou (só em debug) o bucket sintético `"debug"` contam igual.
- **Mortes** (`deaths_total(save_state)`): lê `save_state["counters"]["deaths"]` direto (int simples, incrementado em `game/states.py`'s `GameStateManager.update()` — `self.save_state["counters"]["deaths"] += 1` — só na transição real `"game_over"`, isto é, quando o HP do jogador chega a 0; morte de boss/matar inimigos não conta como morte do jogador, só o inverso).
- **Pontuação**: `score = kills_total - deaths*3` — cada morte custa o equivalente a 3 kills, punição real sem exigir uma run inteira de grind pra recuperar.
- **Tiers** (`REPUTATION_TIERS`, ordem crescente por `score` mínimo): Novato (0) → Combatente (25) → Veterano (75) → Herói (150) → Lenda Viva (300). `score < 0` (mais mortes do que o kill count sustenta) retorna o título **"Amaldiçoado"** (`CURSED_TITLE`) em vez de ficar preso em "Novato" — uma run ruim tem que parecer visivelmente pior, não só "sem progresso".

**Testando via painel de debug (`F1`):** linhas "Kills totais" (passo 10, escreve em `counters["kills"]["debug"]`) e "Mortes totais" (passo 1, escreve em `counters["deaths"]`) — cada uma mostra o total resultante **e** o título de reputação junto, pra não precisar alternar pra HUD. Verificado ponta-a-ponta (contador de kills, contador de mortes, e o título calculado) com um `save_state` real via `game.save.new_game_state()` — incrementar mortes não mexe em kills e vice-versa, e o título vira "Amaldiçoado" corretamente quando o placar fica negativo.

## XP e nível

`xp_to_next(L) = round(20·L^1.4)`. Nível máximo 30. `POINTS_PER_LEVEL = 4` pontos de atributo por level-up (ver seção "Correções de escopo" abaixo — a implementação inicial usou 3 sem confirmação, corrigido nesta sessão).

`BASE_XP`/`GOLD_DROPS` (`game/stats.py` — dados puros, sem dependência de pygame, para `tools/balance_sim.py` poder rodar headless): esqueleto 10 XP/4 ouro, goblin 8/3, dark_knight 25/10. Bosses (`xp_reward`/`gold_reward` fixos, não escalam por ML — são encontros únicos calibrados à mão, não mobs fungíveis): Rei das Sombras 150 XP/60 ouro, Cacodemon 300/120.

## Nível de monstro (ML) — Stage B1

`MONSTER_GROWTH_VECTOR = {vigor: +2, strength: +1, dexterity: +0.5}` por ML, aplicado em cima do bloco de atributos do arquétipo (`scale_archetype()`). ML1 é um no-op — reproduz exatamente a calibração da Stage A3, sem mudança de comportamento nos monstros de ML1.

XP/ouro por kill escalam pela mesma fórmula (`scale_by_ml`, `+35%` por ML acima de 1), sem tabela de multiplicador separada. **Regra anti-farm:** um monstro 5+ níveis abaixo do jogador dá só 10% do XP — impede que grindar conteúdo trivial também grinde XP trivialmente. Ouro **não** tem essa penalidade de propósito: farmar fase já limpa por ouro (pra comprar poção antes da próxima dificuldade) é o loop pretendido, não algo a suprimir.

`LEVEL_MAPS[n]["monster_level"]`: Floresta Encantada ML1, Ruínas do Deserto ML4, Masmorra das Sombras ML8 — rampa dentro da campanha Normal atual (3 fases).

`tools/balance_sim.py` (roda sem pygame — `python tools/balance_sim.py`) imprime curva de XP, progressão de jogador/monstro, matriz de time-to-kill, XP/ouro por kill, e contribuição de DPS dos status effects. Usar antes de qualquer ajuste manual de número de combate.

## Paragon e afixos (Stage B3)

`game/affixes.py` — um registro, dois consumidores por design: Paragon agora, afixos de nível de dificuldade (Cursed Ground, etc.) depois no Stage B5, reusando o mesmo `AFFIXES`.

- **Taxa:** 3% por spawn (tier Normal — dificuldades futuras somam +2%/tier). **Pity:** contador de spawns sem Paragon (`player.paragon_pity`, não persistido); ao atingir 20 spawns sem nenhum, o próximo é forçado — ~um "ato" de 3 fases.
- **Efeito:** +2 níveis de monstro, x4 XP e ouro na morte, aura dourada pulsante + nome flutuante, 1 afixo sorteado dos 6:

| Afixo | Efeito |
|---|---|
| Frenetico | +40% velocidade de ataque |
| Colossal | +80% HP, +15% tamanho (visual + colisão) |
| Volatil | Explode ao morrer (15 dano em raio 70 se o jogador estiver perto) |
| Veloz | +30% velocidade de movimento |
| Protegido | 25% de chance de bloquear completamente um golpe |
| Vampirico | Cura 20% do dano causado ao jogador |

O rolamento de Paragon acontece uma vez, logo após `Level` spawnar os inimigos (`apply_paragon_rolls`, chamado por `GameplayState.__init__`) — `game/level.py` nunca precisa saber que Paragon existe.

**Correção feita durante esta etapa:** matar um inimigo com Bola de Fogo não concedia XP/ouro nenhum — essa lógica só existia no caminho de ataque corpo-a-corpo. Extraída pra `Level.credit_kill()`, chamada pelos dois caminhos (corpo-a-corpo em `game/level.py`, Bola de Fogo em `game/states.py`) — inclui também o crédito de XP/ouro de boss morto por Bola de Fogo, que tinha o mesmo problema.

## Ouro e itens

Ouro dropa fisicamente no mapa em kills de inimigo comum (`GoldDrop`, 3s visível + 2s piscando, depois desaparece se não coletado) — visualiza a decisão do jogador de arriscar ir buscar ou seguir em frente. Kills de boss creditam ouro instantaneamente (sem pickup: a fase termina imediatamente na morte do boss, não há janela de jogo pra andar até uma moeda).

Itens base (`game/items.py`):
- Poção de Vida — 30g, cura 50% da vida máxima atual.
- Poção de Mana — 24g, cura 60% da mana máxima atual.
- Antídoto — 40g, cura Veneno/Lentidão/Fraqueza instantaneamente.

Cura em *fração* do máximo atual (não valor fixo) — mantém as poções relevantes conforme VIG/INT sobem, mesma convenção já usada pro coração-pickup.

**Overlay "Itens" (`game/merchant.py`'s `ItemsOverlay`, tecla `I`):** "seus itens" (usar, topo) + "loja" (comprar, embaixo) na mesma tela — mesmo padrão do Paperdoll (tela cheia, congela o jogo). Compra é persistida na hora (`save.sync_economy`/`save.save`), mesmo peso de "ação deliberada" que o toggle de mute já tinha, não só no checkpoint de saída de fase. Navegação 100% por teclado (W/S percorre a lista única usar-depois-comprar na mesma ordem em que aparece na tela, ESPAÇO age conforme a linha) pelo mesmo motivo do Paperdoll — clique de mouse não confiável no build pygbag/navegador (ver "Bugs reais encontrados" abaixo). Stage K12 fez `ITEMS` crescer de 3 pra ~25 entradas (ver seção "Poções/elixires e seleção de hotbar" abaixo), o que forçou uma reforma em abas (SEUS ITENS/LOJA) + paginação (`Carousel`) - a lista única não cabia mais numa tela.

## Magias (Stage B2)

`game/spells.py` — 3 magias iniciais, cada uma reaproveitando um sistema existente (nenhuma renderização nova):

| Magia | Efeito | Custo | CD | Requisito | Reaproveita |
|---|---|---|---|---|---|
| Bola de Fogo | Projetil reto, dano mágico | 8 mana | — | INT 15 | `Projectile` (`game/boss.py`) |
| Nova de Gelo | Dano em área + Lentidão | 12 mana | — | INT 20, SAB 15 | O efeito "slow" já existente |
| Luz Curativa | Cura 25% da vida máxima | 15 mana | 10s | SAB 25 | Mesma fórmula de fração das poções |

Magia "desbloqueada" = atende aos requisitos de atributo no momento — não é uma flag persistida (mesmo raciocínio de `profession` não estar no save). Conjuração: teclado **F** (Bola de Fogo) / **Q** (Nova de Gelo) / **R** (Luz Curativa) conjura direto — trocado de 1/2/3 pra ficar mais perto do teclado de movimento (WASD); `R` também continua reiniciando na tela de pausa/morte (`Action.RESTART`), sem colisão real entre os dois usos porque cada `Action` só é consumida no branch certo (pausado vs. em jogo) e `InputManager.update()` limpa qualquer ação não consumida a cada frame. Celular seleciona a magia na aba "Magias" do paperdoll e dispara com um botão dedicado. A aba Magias mostra a tecla *atual* de cada magia (`game/paperdoll.py`'s `SPELL_ACTIONS` resolvido via `game.keybinds.display_key()`, Stage K20) em vez de um número de lista ou um literal fixo — segue o remapeamento (ver "Teclas remapeáveis" abaixo) em vez de ficar desatualizada.

**Nova de Gelo "não fazia nada" — dois problemas reais, não um bug na mecânica:** testado diretamente (`GameplayState._cast_frost_nova` com um inimigo próximo) e o dano/lentidão/gasto de mana já funcionavam corretamente. O que faltava era *feedback*:
1. **Cast falho era 100% silencioso.** `_attempt_cast()` só fazia algo quando `Player.try_cast()` retornava `True`; se a magia estivesse bloqueada por atributo, em recarga, ou sem mana suficiente, apertar a tecla não tinha efeito nenhum visível — indistinguível de "a tecla não faz nada". Corrigido com `_cast_fail_message()`, reusando o mesmo `msg_timer`/`msg_text` toast que level-up/troca de profissão já usam, explicando exatamente qual dos 3 motivos bloqueou o cast.
2. **O efeito visual não mostrava alcance nenhum.** A explosão original espalhava 24 partículas a partir do próprio jogador com velocidade/direção aleatória — sem nada indicando "isso atingiu até aqui", fácil de achar que nada foi lançado, especialmente contra um inimigo fora do alcance de 110px (que é *por design* uma explosão centrada no jogador, não um projétil mirado — mesma geometria de estouro circular que os bosses já usam, ver `game/boss.py`'s `_shoot_circle`). Trocado por um anel de 32 partículas nascendo exatamente na circunferência do raio real (110px), plus 12 partículas centrais — o alcance verdadeiro da magia agora pisca visivelmente na tela em vez de ficar implícito.

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

## Bestiário — descrição de todos os mobs e bosses

Texto de identidade (nome + descrição) vem de `game/bestiary.py`'s `BESTIARY` — mesma fonte usada pela aba "Bestiário" do paperdoll in-game; nenhuma lore nova foi inventada aqui, só documentada. Números de HP/dano/velocidade não são repetidos nesta seção porque já vivem em "Atributos e stats derivados" e mudam com ML/dificuldade — aqui é só identidade + formato de ataque.

### Mobs comuns

Individualização (fases 5/6/7/9/10/11 — Atos 2 e 3): `swamp_troll`/`cursed_mage`/`crypt_wraith`/`ash_fiend`/`royal_guard` foram aposentados (eram só recolorações dos 3 rigs de `skeleton`/`goblin`/`dark_knight`, sem sprite/ataque próprios) e substituídos por um elenco novo, um por fase, cada um com seu próprio rig (`game/assets.py`'s `ENEMY_SPRITES`/`_RIG_PAINTERS`) e ataque (`game/enemy.py`'s `ENEMY_FLAVOR`). `skeleton`/`goblin`/`dark_knight` continuam como estavam — usados nas fases 1-3, não tocadas nesta passada.

| Fase | Mob | Descrição | Ataques |
|---|---|---|---|
| 1-3 | Esqueleto (`skeleton`) | Um guerreiro morto reanimado por magia negra - ataca sem hesitar e sem sentir dor. | Corpo a corpo + à distância sem efeito adicional (dano direto). |
| 1-3 | Goblin (`goblin`) | Pequeno e covarde sozinho, mas perigoso em grupo - suas poças de veneno cobrem o chão de armadilhas. | Corpo a corpo + à distância sem efeito adicional; deixa poças venenosas pelo chão. |
| 1-3 | Cavaleiro Negro (`dark_knight`) | Um cavaleiro caído, blindado e implacável - dispara um raio arcano de longe quando não pode alcançar. | À distância: Fraqueza (15%). |
| 5 | Aranha (`aranha`) | Emboscada suas presas nas sombras do pântano. | Toque: Veneno (30%). |
| 5 | Serpente (`serpente`) | Furtiva e traiçoeira. | Toque: Veneno (25%). |
| 5 | Treant (`treant`) | Árvore ancestral desperta que protege o pântano. | À distância, em leque de 3 (`ranged_shape="spread3"`): Lentidão (25%). |
| 6 | Esqueleto (`skeleton`) | (reaproveitado, ver acima) | — |
| 6 | Troll (`troll`) | Amaldiçoado pela torre. | Toque: Fraqueza (25%). |
| 6 | Cavaleiro da Morte (`death_knight`) | Jurou lealdade além da morte. | À distância: Fraqueza (22%, mais forte que o `dark_knight`). |
| 7 | Zumbi (`zumbi`) | Cadáver reanimado, só ataca de perto. | Toque: Veneno (30%); sem ataque à distância. |
| 7 | Verme (`verme`) | Se arrasta pela cripta. | Toque: Veneno (25%). |
| 7 | Imp (`imp`) | Pequeno demônio travesso e rápido. | À distância, rajada errática de 5 (`ranged_shape="spread5"`): Choque (20%). |
| 9 | Dark Horse (`dark_horse`) | Corcel espectral do salão gelado. | Toque: Frio (25%). |
| 9 | Acólito (`acolito`) | Seguidor de rituais profanos. | À distância: Fraqueza (20%). |
| 9 | Feiticeira (`feiticeira`) | Elite caster do salão gelado. | À distância: Frio (25%), dano maior. |
| 10 | Fire Hound (`fire_hound`) | Cão infernal veloz. | À distância: Queimadura (25%). |
| 10 | Ogro (`ogro`) | Brutal e resistente. | Corpo a corpo puro, sem efeito - só dano bruto. |
| 10 | Elemental de Pedra (`elemental_pedra`) | Tanque extremo, o mais lento de todos. | À distância, explosão radial de 6 (`ranged_shape="circle6"`): sem efeito, dano alto. |
| 11 | Quimera (`chimera`) | Fusão de leão, cabra e serpente. | À distância: Queimadura (25%) **e** toque: Fraqueza (20%) - as duas ativas ao mesmo tempo (distâncias diferentes). |
| 11 | Lyzardman (`lyzardman`) | Guerreiro reptiliano ágil. | Toque: Veneno (25%). |
| 11 | Esqueleto Sombrio (`dark_skeleton`) | Versão sombria e elite do esqueleto comum. | À distância: Choque (20%); único mob comum com `luck` > 0 (chance de crítico), papel que era do `royal_guard`. |

### Bosses (Stage B4b — sprite e sala individualizados por boss, ver seção "Campanha em 3 atos" abaixo)

| Boss | Descrição | Identidade visual | Ataques (fase 1) |
|---|---|---|---|
| Senhor da Guerra Orc (`orc_warlord`) | Lidera pela força bruta - sua investida é capaz de esmagar quem estiver no caminho. | Humanoide verde, sobrancelha franzida ("olhar de mau"), segurando um tacape. | Investida (dano físico de contato); tiro triplo mirado. |
| Necromante (`necromancer`) | Comanda os mortos, invocando esqueletos e lançando maldições a distância. | Figura sombria de manto/capuz preto, rosto = caveira. | Invoca até 3 esqueletos; rajada circular de projéteis; maldição a distância (Fraqueza). |
| Rei das Sombras (`shadow_king`) | O tirano final do reino - mestre em rajadas de magia sombria em todas as direções. | Espectro negro sólido, sem rosto além dos olhos brancos brilhantes (estilo Noob Saibot), bordas esfarrapadas. | Rajada circular de projéteis; tiro triplo mirado; espiral de projéteis. |
| Cacodemônio (`cacodemon`) | Demônio infernal da fase secreta - um demônio humanoide, chifrudo e de olho único, que cospe fogo em todas as direções. | Humanoide (deixou de ser a esfera flutuante original), olho central grande, chifres, pequenas asas. | Rajada de projéteis de fogo em todas as direções (ver tabela de debuffs acima para a chance de Fogo). |

As 4 salas de boss (fases 4/8/12/13) também deixaram de ser o mesmo retângulo vazio recolorido: cada uma tem um piso (`create_tile()`) e um layout de obstáculos temáticos próprios — acampamento de guerra (caixotes/estacas), colunata de tumbas, salão do trono (dais + pilares esparsos) e um abismo de obsidiana esparso e assimétrico para o Cacodemônio (substituindo o piso de lava/magma original, que não combinava com o tema).

## Bugs reais encontrados durante o desenvolvimento (não features, correções)

- **`CacodemonBoss.update()` nunca checava colisão de projétil com o jogador** — o boss da fase secreta não causava dano nenhum desde antes desta rodada de features. Corrigido ao ligar o gancho de debuff de Fogo nesse boss.
- **Clique de mouse desalinhado no build pygbag/navegador** (som/tela cheia/comprar não respondem onde desenhados) — 6 tentativas de fix falharam (ver memória do projeto). Toque real e teclado não são afetados. Deixado de lado por decisão do usuário; não re-tentar sem um diagnóstico novo (console JS do navegador, nunca verificado até agora).
- **Boss "piscava" com um retângulo translúcido mesmo quando o golpe do herói errava, de qualquer distância.** `GameplayState.update()` (`game/states.py`) chamava `boss.take_damage(dmg, ...)` **incondicionalmente** sempre que `player.attacking` era `True` — `dmg` só virava 0 quando o golpe não acertava (`atk_rect.colliderect(boss.rect)` falso), mas `Boss.take_damage()`/`CacodemonBoss.take_damage()` sempre ligam `hit_flash` e criam partículas de acerto, não importa o valor de `amount`. Corrigido: só chama `take_damage()` dentro do `if atk_rect.colliderect(boss.rect):`.
- **O próprio flash de "tomou dano" pintava um quadrado/losango translúcido em volta do boss inteiro, não só a silhueta.** `Boss.draw()`/`CacodemonBoss.draw()`/`Enemy.draw()` pintam o flash branco (ou vermelho, no windup do orc) borrando uma superfície branca por cima do sprite com `pygame.BLEND_RGBA_ADD` — esse blend soma o canal **alfa** também, então uma margem transparente da sprite (alfa 0) mais um overlay de alfa 200 vira alfa ~200 (translúcido), pintando o retângulo/losango inteiro do canvas em vez de só o personagem. Passou despercebido com o rig genérico antigo (preenchia quase todo o canvas), mas ficou bem visível com os rigs individualizados (props assimétricos como o tacape do orc ou os tentáculos do Rei das Sombras deixam bem mais margem transparente). Corrigido trocando pra `pygame.BLEND_RGB_ADD` nos 3 lugares (`game/boss.py` x2, `game/enemy.py` x1) — soma só RGB, alfa do destino fica intocado.

## Navegação por teclado no Paperdoll e no menu de Itens

Como o bug de clique acima bloqueia especificamente os botões desses dois overlays no navegador, ambos ganharam um caminho 100% por teclado, paralelo ao clique de mouse (que continua funcionando normalmente fora do pygbag/navegador) — nenhum botão existente foi removido, só ganhou um segundo jeito de ser acionado:

- **Paperdoll (`C`):** `TAB` alterna entre as abas Status/Magias. Dentro de cada aba, `W`/`S` movem um cursor com destaque luminoso (pulsante, `Paperdoll._draw_glow`) entre as linhas selecionáveis. Na aba Status, `A`/`D` gastam/devolvem um ponto no atributo selecionado (mesma função que os botões -/+ já chamavam). Na aba Magias, `ESPAÇO` seleciona a magia destacada (equivalente ao botão "Selecionar").
- **Itens (`I`):** `W`/`S` percorrem uma lista única (primeiro as linhas "Usar", depois as linhas "Comprar", na mesma ordem em que aparecem na tela). `ESPAÇO` age de acordo com a seção da linha destacada — usa o item ou compra, sem precisar de uma tecla separada para cada ação.

Implementação: `InputManager` (`game/input_system.py`) ganhou `Action.MENU_LEFT`/`MENU_RIGHT` (A/D, mesmo padrão dual-uso de MENU_UP/DOWN com W/S) e `Action.TAB_NEXT` (tecla Tab). `Paperdoll.handle_keys()`/`ItemsOverlay.handle_keys()` são chamados em `GameplayState.update()` ao lado dos `handle_tap()` já existentes — mouse e teclado convivem, não são exclusivos.

## Atalhos de teste (dev-only)

`M`/`N` (`Action.DEV_NEXT_LEVEL`/`DEV_PREV_LEVEL`) avançam/voltam um nível da campanha (`GameplayState._dev_jump`), ignorando boss vivo ou saída bloqueada — deixa qualquer uma das 13 fases alcançável pra teste sem precisar jogar a campanha inteira a cada verificação. Reusa o mesmo caminho de transição (`next_state = "next:N"`) que a saída normal de fase já usa, então nenhum estado novo foi criado. Efeito colateral aceito: como qualquer transição de nível, atualiza `highest_level_cleared` mesmo sem a fase ter sido de fato cumprida — é uma ferramenta de debug, não uma mecânica de jogo, então isso não é tratado como bug.

## Correções de escopo aplicadas depois da primeira implementação

- **Pontos de atributo por level-up: 3 → 4.** O usuário especificou 4 desde o início; a implementação inicial usou 3 sem confirmação. Corrigido nesta sessão, com migração de save (ver `save-schema.md`).
- **Sprite de ataque não parecia uma espada.** A pose "attacking" de `create_player_sprite()` (`game/assets.py`) desenhava só 4 pixels soltos na diagonal, e `Player.draw()` (`game/player.py`) ainda cobria a área de alcance do golpe com um retângulo translúcido (alpha 80/255) por cima — o resultado lido como uma mancha clara de baixa opacidade, não uma arma. Substituído por uma espada de verdade (lâmina + guarda + cabo + pomo, desenhada com `pygame.draw.polygon`/`line` em espaço de pixel em vez do grid `x*SC`, mesma técnica já usada nos acessórios dos rigs de boss) e o retângulo translúcido foi removido — a espada por si só já comunica o ataque. `get_attack_rect()` (a hitbox real do golpe) não mudou, só o desenho.

## Dificuldade (Stage B5)

5 tiers (`game/difficulty.py`): Normal, Dificil, Muito Dificil, Pesadelo, Inferno. Cada um é a mesma campanha de 12 fases jogada de novo — não multiplicadores simples de dano/vida (pedido explícito do usuário), e sim os mesmos mecanismos que os Stages B1/B3/B4 já construíram, com o dial girado:

| Mecanismo | O que faz | Reusa |
|---|---|---|
| `ml_bonus` | soma ao `monster_level` de toda fase de combate do tier | `MONSTER_GROWTH_VECTOR`/`xp_for_kill`/`gold_for_kill` (Stage B1) — monstro mais forte E vale mais, uma única curva |
| `champion_chance` | chance por spawn de virar Campeão (ver abaixo) | `AFFIXES` (Stage B3) |
| `level_affixes` | efeitos de fase inteira (ver abaixo) | mesmo dict `AFFIXES`, entradas `scope="level"` |
| `boss_enrage_frac` | limiar de HP em que o boss entra na fase 2 (enrage) | `Boss.take_damage()` (Stage B4) — estrutural, não um número maior |

Tabela de tiers:

| Tier | ml_bonus | Campeão | Afixos de fase | Enrage do boss |
|---|---|---|---|---|
| Normal | +0 | 0% | — | 50% HP |
| Dificil | +6 | 8% | Chao Amaldicoado | 55% HP |
| Muito Dificil | +14 | 14% | + Penumbra | 60% HP |
| Pesadelo | +24 | 20% | + Horda Apressada | 65% HP |
| Inferno | +36 | 28% | (mesmos 3) | 70% HP |

**Campeões** (`game/affixes.py`'s `make_champion()`): irmã mais branda de `make_paragon()` — mesma ideia (crescer pela curva de ML, sortear um afixo `scope="monster"`), mas +1 ML (não +2) e bônus de afixo mais fracos, x2 recompensa (não x4) — porque Campeão é comum em dificuldade alta, Paragon continua raro em qualquer tier (`PARAGON_CHANCE` não sobe com dificuldade, de propósito: são eixos diferentes). Aura prateada + rótulo "CAMPEAO" (vs. dourado "PARAGON") em `Enemy.draw()`.

**Afixos de fase** (`scope="level"` no mesmo dict `AFFIXES`, não um registro paralelo):
- **Chao Amaldicoado:** Veneno periódico (8s) enquanto o jogador está numa fase de combate daquele tier, independente de combate — pune demora, não é dano de golpe.
- **Penumbra:** força o clima `dimming_fog` (novo tipo em `game/weather.py`, overlay mais escuro que a neblina comum) nas fases de combate — visual por enquanto (`visibility_mult=0.6` ainda é gancho pra uma passada futura de IA, mesma ressalva que `game/weather.py` já documentava desde a Stage RPG-expansion).
- **Horda Apressada:** `Level` ganha um `extra_speed_mult` (multiplica em cima do `speed_multiplier` que a própria fase já podia ter) — `Level` continua sem saber que dificuldade existe, só recebe um número, mesma separação de responsabilidade que Paragon/clima já usavam.

Nenhum dos 3 afixos de fase se aplica em salas de boss (arena de boss já é teste de combate suficiente por si só).

**Seleção de dificuldade:** `DifficultySelectState` (tela de seleção de mapa/tier), acessível pelo menu principal (opção "DIFICULDADE", ao lado de "CONTINUAR"). Tiers destravam sequencialmente — só é possível jogar um tier depois de vencer o anterior (chegar ao resultado `"victory"` na fase 12) pelo menos uma vez (`is_unlocked()`). `progression.highest_level_cleared` guarda progresso por tier (não um int global) — jogar Dificil não reseta nem é resetado pelo progresso em Normal.

**Fase secreta (13, Cacodemon):** desbloqueada só depois de vencer Inferno pelo menos uma vez (`"inferno" in cleared_difficulties`) — antes disso o botão aparece na tela de vitória mas não faz nada, visível como incentivo, não escondido.

## Painel de debug (`game/debug_panel.py`)

Overlay de desenvolvedor, tecla `F1` (livre, confirmado por grep completo do teclado antes de escolher) — só teclado, só PC, sem botão mobile, mesmo precedente das teclas `M`/`N` de salto de fase (ferramenta de teste, não feature de jogador). Reusa exatamente o idioma de navegação do Paperdoll/Itens: W/S move um cursor com brilho pulsante, A/D ajusta uma linha, ESPAÇO aciona um "trigger". Entra no mesmo grupo de exclusão mútua que Paperdoll/Itens (C/I) — no máximo um overlay aberto por vez.

21 linhas, 2 tipos:
- **Ajuste** (atributos ±5, nível ±1, pontos livres ±1, ouro ±50, **kills totais ±10, mortes totais ±1** — ver abaixo —, os 3 itens ±1, dificuldade atual — circula livre pelas 5, ignorando o desbloqueio sequencial, que é o próprio propósito da ferramenta).
- **Trigger** (adicionar 500 XP via `gain_xp` — caminho real de nivelamento, não um set cru; desbloquear todas as dificuldades; forçar Paragon/Campeão num inimigo comum aleatório da fase; matar todos os inimigos da fase; Modo Deus; one-hit no chefe atual).

**Kills/mortes totais (linhas novas, pra testar `game/reputation.py` sem precisar grindar):** `game/reputation.py`'s `kills_total()` já soma **qualquer** chave dentro de `save_state["counters"]["kills"]`/`["boss_kills"]` (mais o que ainda não foi sincronizado da run atual) — a linha de kills só incrementa/decrementa um bucket sintético `counters["kills"]["debug"]`, sem precisar simular uma morte de inimigo de verdade. A linha de mortes ajusta `counters["deaths"]` (um int simples) direto. As duas mostram o total resultante **e** o título de reputação que ele produz (`determine_reputation()`) na mesma linha, pra não precisar alternar pra o HUD só pra conferir o efeito de cada ajuste.

**Achados que mudaram o design (auditoria antes de implementar):**
- `player.level` não afeta nenhuma fórmula de combate (só XP-pra-próximo/regra anti-farm/rótulo do HUD) — o rótulo da linha deixa isso explícito, pra não parecer bugado.
- Mudar um atributo pra baixo pode deixar `hp`/`mana` acima do novo máximo (nada no `Player` clampa isso pra baixo) — a linha de atributo cura o personagem por completo depois de cada ajuste, em vez de tentar clampar manualmente.
- `CacodemonBoss` (fase secreta) não tem `enable_one_hit()`/`restore_hp()` como `Boss` tem — a linha de one-hit usa `hasattr()` e mostra aviso em vez de quebrar.
- O tick de dano (Veneno/Chão Amaldiçoado) escreve direto em `player.hp` dentro de `Player.update()`, sem passar por `take_damage()` — "Modo Deus" (`player.debug_invincible`, novo, nunca persistido) guarda os dois pontos, senão o personagem ainda morre de veneno com o modo "ligado".
- Trocar a dificuldade atual não tem efeito visível imediato: `GameplayState.difficulty`/`difficulty_id` são fixados na construção, não lidos a cada frame. Em vez de recarregar a fase a cada ajuste (o que recarregaria 4x só pra passar de Normal a Inferno), o painel marca uma flag "dirty" e só recarrega a fase atual (reusando `_dev_jump(0)`, zero lógica nova) quando o painel *fecha*, se a dificuldade foi mesmo tocada.

**Persistência:** atributos/nível/pontos/ouro/itens/dificuldade/desbloqueio escrevem no save imediatamente (`save.sync_character`/`sync_economy` + `save.save()`, mesmo padrão que `merchant.py` já usa nas compras) — é ferramenta de teste, o valor setado precisa sobreviver a um refresh. Modo Deus/one-hit/forçar Paragon-Campeão/matar todos tocam objetos efêmeros (nunca existiram no save) e ficam só em memória — `debug_invincible` mora na instância de `Player`, sobrevive entre fases na mesma sessão, mas zera ao carregar um save novo, por design.

## Campanha em 3 atos e bosses generalizados (Stage B4)

O que era 1 boss único (Rei das Sombras) + 1 fase secreta virou 3 atos, cada um com 3 fases de combate + 1 boss próprio — sem duplicar a classe `Boss`. `game/boss.py`'s `Boss.__init__(x, y, boss_id=...)` agora lê um bloco de atributos de `BOSS_ARCHETYPES` (`game/stats.py`) em vez de ter valores fixos no corpo da classe — mesma jogada de "um rig, várias skins" que `ENEMY_ARCHETYPES`/Paragon já usam. O boost de velocidade da fase 2 (enrage) passou de um valor fixo (`130`) para proporcional (`stats.speed * 1.625`), preservando o número exato do Rei das Sombras enquanto funciona para qualquer arquétipo.

**Individualização de sprite e sala (Stage B4b):** o "um rig, várias skins" valia só para os *stats* — visualmente os 3 bosses (+ Cacodemon numa classe própria) ainda compartilhavam uma única silhueta genérica recolorida (`create_boss_sprite(phase, body_colors, eye_colors)`), e as 4 salas de boss eram o mesmo retângulo vazio com piso levemente diferente. Corrigido: `create_boss_sprite(boss_id, phase)` (`game/assets.py`) agora despacha pra um rig próprio por `boss_id` (`BOSS_SPRITES`/`_BOSS_RIG_PAINTERS`, mesmo padrão `ENEMY_SPRITES`/`_RIG_PAINTERS` já usado pelos mobs comuns) — `BOSS_ARCHETYPES` perdeu as chaves `body_colors`/`eye_colors` (viraram dado morto, nenhum stat numérico mudou). Cacodemon deixou de ser uma esfera flutuante desenhada inline em `CacodemonBoss.draw()` e passou a usar o mesmo `create_boss_sprite("cacodemon", ...)`, cacheado uma vez em `__init__` como `Boss` já fazia com `sprite_p1`/`sprite_p2`. Ver a tabela de bosses no Bestiário acima pra identidade visual de cada um. As 4 salas (`LEVEL_MAPS[4/8/12/13]`) ganharam piso (`create_tile()`) e layout de obstáculos próprios; o piso de lava do Cacodemon foi trocado por um abismo de obsidiana mais discreto (era "magma gritante" demais pro tema).

`BOSS_REGISTRY` (`game/states.py`) mapeia a chave `"boss"` de cada `LEVEL_MAPS[n]` pra uma fábrica — Orc Warlord/Necromante/Rei das Sombras compartilham a fábrica lambda genérica (`Boss(x, y, boss_id=...)`); só o Cacodemon (fase secreta) continua sendo uma classe própria, por ter um padrão de ataque realmente diferente, não por limitação do registry.

**Numeração de fases (`LEVEL_MAPS`, 1-13):**

| Fase | Título | Tipo | Boss/Monstros | ML |
|---|---|---|---|---|
| 1-3 | Floresta Encantada / Ruínas do Deserto / Masmorra das Sombras | combate | esqueleto, goblin, cavaleiro negro | 1/4/8 |
| 4 | Acampamento de Guerra | boss | Senhor da Guerra Orc | — |
| 5 | Pântano Sombrio | combate | aranha, serpente, treant | 12 |
| 6 | Torre Amaldiçoada | combate | esqueleto, troll, cavaleiro da morte | 16 |
| 7 | Cripta Perdida | combate | zumbi, verme, imp | 20 |
| 8 | Cripta do Necromante | boss | Necromante | — |
| 9 | Salão dos Ecos | combate | dark horse, acólito, feiticeira | 24 |
| 10 | Abismo de Cinzas | combate | fire hound, ogro, elemental de pedra | 28 |
| 11 | Corredor Final | combate | quimera, lyzardman, esqueleto sombrio | 32 |
| 12 | Trono das Trevas | boss (final da campanha, `victory:"victory"`) | Rei das Sombras | — |
| 13 | Fase Secreta: INFERNO | boss (`victory:"secret_victory"`) | Cacodemon | — |

Recompensa dos 3 bosses escalada à mão pra refletir a posição na campanha (não pela fórmula de ML, que é só pra mobs comuns): Orc Warlord 100 XP/40 ouro, Necromante 200/80, Rei das Sombras 300/120 (subiu de 150/60 — deixou de ser o único boss do jogo pra ser o final do Ato 3). `game/states.py`'s `_continue_level()` (cap do botão CONTINUAR) e o alvo da transição `"secret"` foram atualizados de `4`/`5` pra `12`/`13`.

**Individualização de mobs comuns (Stage B4b, fases 5/6/7/9/10/11):** o parágrafo acima ficou desatualizado - as 6 fases de combate dos Atos 2/3 tinham cada uma seu próprio `monster_level`, mas reusavam só `goblin`/`skeleton`/`dark_knight` recolorados (via `swamp_troll`/`cursed_mage`/`crypt_wraith`/`ash_fiend`/`royal_guard`) em vez de um elenco visualmente próprio. Corrigido junto com os bosses: 17 arquétipos novos (ver tabela de mobs comuns no Bestiário acima), cada um com seu rig em `game/assets.py` e ataque em `game/enemy.py`'s `ENEMY_FLAVOR` — `skeleton`/`goblin`/`dark_knight` continuam intactos, usados só nas fases 1-3. `Enemy._shoot_at_player()` ganhou um parâmetro opcional `flavor["ranged_shape"]` (`"spread3"`/`"spread5"`/`"circle6"`, default `"single"` = comportamento antigo inalterado) pros 3 mobs cujo ataque pedia mais que um tiro reto (treant, imp, elemental_pedra) — a mesma técnica de leque/rajada circular que `game/boss.py` já usava, adaptada pra `Enemy`/`EnemyProjectile` em vez de `Boss`/`Projectile`. Nenhum mob comum ganhou charge/dash ou invocação — essas continuam exclusivas de boss (exigiriam a máquina de estados de `Boss._update_charge`/o dreno de `pending_summons`, fora do escopo pedido). Cenário: fase 6 ganhou `"cursed_floor"` (pedra + runas roxas) e fase 9 ganhou `"ritual_floor"` (pedra pálida + círculo arcano), fase 7 passou a reusar `"crypt_floor"` (já existia, criado pro Necromante); fases 5/10/11 mantiveram `swamp`/`lava`/`boss_floor` (já combinavam com o elenco novo).

**Bestiário além de 12 entradas (`game/paperdoll.py`):** a aba Bestiário tinha um grid fixo de exatamente 3 linhas (`_BESTIARY_DETAIL_Y` hardcoded pra `3 * _BESTIARY_CELL`) porque nunca tinha passado de 8 mobs + 4 bosses. Com o elenco crescendo pra 20 mobs + 4 bosses (24 entradas), isso viraria 6 linhas e o painel de detalhe ficaria por cima do grid. Corrigido pra ser derivado (`math.ceil(len(BESTIARY_ORDER)/_BESTIARY_COLS)` linhas, nunca mais um literal solto) e o grid passou de 4 colunas/70px pra 6 colunas/56px (cabe na mesma largura de painel, menos linhas no total). Atlas não precisou de nenhuma mudança de código — já lia `title`/`description`/`enemies` de `LEVEL_MAPS` dinamicamente.

## Combate físico: recuo e não-sobreposição (Stage K9)

Todo dano (herói→monstro, monstro→herói, boss↔herói) empurra o alvo pra longe da fonte por um vetor curto (`game/combat_fx.py`'s `knockback_vector()`, força fixa `KNOCKBACK_SPEED=380`, `KNOCKBACK_DURATION=0.15s`) — um estado temporário que assume o controle da posição, mesmo princípio já usado pelo Dash, checado com prioridade *antes* do movimento normal/IA e passando pelas mesmas resoluções de colisão de parede já existentes (nunca atravessa parede). Além disso, herói e monstro/boss nunca ocupam o mesmo espaço: uma resolução de de-penetração AABB padrão (empurra pela metade da sobreposição, no eixo com menor overlap) roda toda vez que os dois colidem — deliberadamente desligada durante o Dash, já que o Dash depende da sobreposição acontecer de verdade pra aplicar o dano de contato.

Todo acerto também gera um número de dano flutuante (`FloatingNumber`, mesmo módulo) que sobe e desaparece — vermelho para dano físico, roxo para mágico, laranja-escuro para dano-ao-longo-do-tempo (Veneno/Fogo/Calor). Nomes de monstro comum passaram a ficar sempre visíveis acima da barra de HP (antes só Paragon/Campeão tinham rótulo).

## Buff percentual unificado (Stage K10)

`StatusEffectDef` (`game/status_effects.py`) ganhou ~16 eixos percentuais além de `speed_mult`/`damage_taken_mult` originais (dano físico/mágico, defesa física/mágica, crítico, velocidade de ataque, vida/mana máxima, regen. de vida/mana, custo de mana, chance/resistência a debuff, XP/ouro ganho) — todos com default neutro (1.0 multiplicativo / 0.0 aditivo), então nenhum dos 7 debuffs originais precisou mudar pra ganhar essa infraestrutura. `Player._mult(field)`/`_bonus(field)` são o único ponto que toda stat derivada relevante lê: `status.multiplier(field) * stance_multiplier(field)` (multiplicativo) ou `status.bonus(field) + stance_bonus(field)` (aditivo) — uma Postura (permanente) e um buff de poção (temporário) empilham exatamente como dois debuffs já empilhavam, sem nenhuma stat property precisar mudar de novo quando um novo buff é adicionado.

## Posturas — bônus permanente por profissão (Stage K11)

`game/stances.py`'s `STANCES` — ao contrário de um debuff/buff (`StatusEffectCarrier`, expira), uma Postura é **derivada** da profissão atual, exatamente como a própria profissão é derivada dos atributos gastos: não tem duração, não precisa de `apply()`/expiração, só existe enquanto aquela profissão existir. Aventureiro (sem build definido) não tem Postura.

| Profissão | Postura | Bônus |
|---|---|---|
| Guerreiro | Postura do Colosso | +15% dano físico, +10% defesa física |
| Assassino | Passos das Sombras | +20% velocidade, +15% crítico |
| Mago | Concentração Arcana | +20% mana máxima, +25% regen. de mana |
| Feiticeiro | Olho do Oráculo | +20% dano mágico, +10% chance de aplicar debuffs |
| Cavaleiro | Muralha Viva | +25% vida máxima, -10% dano recebido |
| Duelista | Lâmina Dançante | +10% dano físico, +10% vel. ataque, +5% esquiva |
| Cavaleiro Arcano | Espada Encantada | +10% dano mágico, +10% mana máxima, -10% custo de mana |
| Paladino | Luz Sagrada | +10% dano físico, +15% resist. a debuffs, +2% regen. vida/s |
| Campeão | Conquistador | +20% vida máxima, +10% dano físico, +10% defesa física |
| Monge | Serenidade | +20% regen. de mana, +10% vel. ataque, -15% custo de mana |
| Xamã | Espíritos | +15% chance de aplicar debuffs, +10% velocidade, +10% dano mágico |
| Ranger | Caçador | +15% velocidade, +10% crítico, +2% regen. vida/s |
| Arcanista | Eclipse | +25% dano mágico, +20% regen. de mana |
| Druida | Natureza | +2% regen. vida/s, +2% regen. mana/s, +10% velocidade, +10% vida máxima |
| Templário | Guardião | -15% dano recebido, +20% resist. a debuffs, +3% regen. vida/s |

**Aproximações deliberadas:** "Cavaleiro Arcano" pedia "ataques físicos causam +10% de dano mágico" — não existe um sistema de proc-on-hit (um ataque não causa dois tipos de dano ao mesmo tempo hoje), então foi modelado como um bônus fixo de dano/mana mágico em vez de inventar um sistema de proc só pra essa profissão. Ícone dedicado por profissão (`create_stance_icon`, `game/assets.py`) num badge de HUD maior que os ícones de debuff comuns, sempre visível (não expira, não entra na fileira de buffs temporários) — hover mostra a descrição exata (`STANCE_DESCRIPTIONS`).

## Poções/elixires e seleção de hotbar (Stage K12)

`ITEMS` (`game/items.py`) cresceu de 3 pra 25 entradas — cada poção/elixir novo aponta pra um `StatusEffectDef` (`game/status_effects.py`, mesma tabela dos debuffs, campo `"buff": "<effect_id>"`) aplicado direto via `player.status.apply()` quando usado (sem passar pela rolagem de resistência — resistência só existe pra debuff *inimigo*, não pra um buff que o próprio jogador escolheu beber).

| Categoria | Qtd. | Preço | Duração | Exemplo |
|---|---|---|---|---|
| Atributo (Preta/Laranja/Roxa/Branca/Verde/Azul-Escura/Amarela) | 7 | 100g | 3min | +15% no eixo correspondente (força→dano físico, destreza→vel. ataque...) |
| Defensiva (Cinza/Prateada/Marrom) | 3 | 120g | 3min | +15-20% defesa/resist. a debuff |
| Ofensiva (Vermelho-Escura/Violeta/Rubra) | 3 | 150g | 3min | +20% dano físico/mágico, +10% crítico |
| Utilitária (Ciano/Rosa/Dourada/Turquesa) | 4 | 100-250g | 3-5min | regen. de vida/mana, +20% XP/ouro ganho |
| Elixir (Carmesim/Arcano/Guardião/Caçador/Campeão) | 5 | 400-600g | 2-5min | combinações de 2+ eixos, Campeão é +10% em quase tudo |

**Hotbar (`player.hotbar_items`, máx. 3):** com 25 itens, a hotbar não pode mais mostrar todo mundo — o jogador escolhe até 3 no menu Itens (tecla `H` numa linha "seus itens" pra marcar/desmarcar). `hotbar_slots()` (`game/player.py`) passou a ler `player.hotbar_items` em vez de iterar `ITEMS` inteiro; as teclas 1/2/3 usam o slot correspondente da lista, não mais um índice fixo no dict. `SAVE_VERSION` 6→7 persiste a seleção (default: as 3 poções originais, pra não mudar a hotbar de ninguém que nunca abriu o menu novo).

## Masmorra: picareta, chave escondida e baú (Stage K14)

Substituiu "matar todo mundo abre a saída" — o objetivo agora é achar uma chave escondida. `Level.layout` deixou de ser a lista compartilhada de `LEVEL_MAPS` (módulo-level, a mesma pra toda instância do mesmo `level_num`) e virou uma cópia por instância, porque quebrar um bloco muda esse grid permanentemente e isso não pode vazar entre partidas/dificuldades.

- **Picareta (tecla `E`, cooldown 1s, sem requisito de atributo):** golpeia o SQM na frente do jogador (mesmo vetor `aim_dx`/`aim_dy` do combate mirado). Bloco interno (`#`, nunca a borda do mapa - convenção confirmada nos 13 layouts) racha no 1º golpe (`create_cracked_wall_overlay`), quebra no 2º (vira chão, remove da lista de colisão, rola um drop: 12% coração / 8% mana / 4% poção).
- **Chave escondida:** um SQM de chão específico por fase de combate (nunca embaixo de bloco, longe do spawn do jogador, longe de spawn de monstro) — cavar esse SQM libera a saída. Marcador sutil no próprio chão (não um brilho óbvio - a ideia é procurar, não seguir uma seta).
- **Saída vira baú (`create_chest_sprite`):** sempre visível, fechado/"TRANCADO" até a chave ser achada, abre com brilho dourado quando `exit_open` vira `True`.
- **Drop de monstro reformulado:** ouro deixou de ser incondicional (era o que o usuário reclamou) — agora 75% de chance, mais coração (10%)/mana (6%)/poção (6%) independentes.
- **Respawn gradual:** depois que todo o elenco original de uma fase morre, uma onda extra (mesmo elenco/nível) volta aos poucos, uma a cada 6s, até o dobro do total original — dá o que fazer enquanto o jogador ainda procura a chave, sem virar spam infinito.

Níveis de boss (`type != "combat"`) não têm chave/baú/blocos destrutíveis — já transicionam direto na morte do boss, e os obstáculos de arena são estruturais pro padrão de ataque, não decoração.

## Teclas remapeáveis (Stage K15)

`game/keybinds.py`'s `BINDINGS` — 10 ações "de habilidade" (ataque, 3 magias, dash, picareta, e os atalhos de menu Personagem/Itens/Ranking/marcar-hotbar) podem ser remapeadas individualmente via um novo botão de engrenagem (`SettingsOverlay`). Deliberadamente **não** remapeável: movimento (WASD, lido por polling contínuo, caminho de código diferente do sistema de `Action`) e navegação pura de menu (CONFIRM/PAUSE/TAB/MENU_UP-DOWN-LEFT-RIGHT/RESTART) — mexer nessas quebraria a navegação por teclado de todo overlay do jogo.

`InputManager.begin_key_capture(callback)` intercepta o próximo `KEYDOWN` inteiro (não deixa a tecla capturada também disparar a ação antiga) — assim capturar uma tecla nova pra Picareta não também aciona a Picareta com a tecla atual. Toda UI que mostra uma tecla (hotbar, aba Magias, aba Ajuda) lê `keybinds.display_key(action_name)` em vez de guardar um literal — ver "Bugs reais encontrados" mais abaixo pra por que isso importava.

## Painel de balanceamento: categorias, abas e editor de pixel (Stage K16-K19)

`BALANCE_DEFAULTS` (`backend/app/main.py`) cresceu de ~20 pra ~330 chaves pontilhadas, cobrindo monstro (`monster.<etype>.<campo>`), buff/debuff (`buff.`/`debuff.<id>.<campo>`, mesma tabela `STATUS_EFFECTS` dividida só pelo prefixo) e postura (`stance.<profissão>.<campo>`) além do que já existia (item/dificuldade/stats/magia) — gerado direto dos dicts reais do jogo, não digitado à mão, pra nunca desviar dos valores de verdade. A tabela plana virou 8 abas por categoria, cada entidade num bloco colapsável (`<details>`), com um botão "Editar aparência" (Monstros/Itens por enquanto) que abre um editor de pixel de verdade: grade 16x16 clicável/arrastável, salva como PNG em base64 (`AppearanceOverride` no banco). O cliente (`game/appearance_overrides.py`) busca todos os overrides uma vez no boot (`GET /appearance`, público, mesmo padrão fire-and-forget de `/balance`) e `create_enemy_sprite()`/`create_potion_icon()` checam por um override antes do pintor procedural normal.

## Bugs reais encontrados nesta rodada (Stage K20)

- **Rótulo de tecla desatualizado depois de um remapeamento.** A hotbar (`game/player.py`), a aba Magias e a lista de atalhos da aba Ajuda guardavam a tecla como um literal (`"F"`, `"X"`, `"SPC"`) escrito antes do sistema de remapeamento (Stage K15) existir — remapear Bola de Fogo pra `G` continuava mostrando "F" em todo lugar. Corrigido lendo `game.keybinds.display_key(action_name)` sempre, em vez de um literal.
- **Aba Ajuda > Debuffs rodava pra fora do painel.** A listagem iterava `STATUS_HELP` inteiro sem paginação - inofensivo com os 7 debuffs originais, mas Stage K12 acrescentou 22 buffs de poção na mesma tabela, e o conteúdo extra simplesmente ficava inalcançável abaixo da borda do painel, sob um título ("DEBUFFS") que também parou de fazer sentido pra metade do conteúdo. Corrigido separando em páginas paginadas de Debuffs/Buffs, mais uma página nova de Posturas (Stage K11 não tinha nenhuma superfície além do tooltip do badge).
- **`LeaderboardButton.draw()` perdeu suas últimas 2 linhas (blit final + badge "L") no meio de uma edição** que adicionava `SettingsButton` logo depois - um `Edit` cujo texto de origem terminava exatamente onde essas linhas ficavam as substituiu junto. Só um botão sumiu (o troféu ficou invisível, círculo vazio) - pego revisando o screenshot ao vivo da fileira de botões, não por inspeção de código.
