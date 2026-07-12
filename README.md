# Dungeon Quest 🗡️

Um action-RPG 2D top-down estilo Zelda, feito em Python com pygame — projeto indie pessoal, sem dependências de assets externos (todo sprite é pixel art gerada em código).

---

## 🕹️ Sobre o jogo

Uma campanha em **3 atos** (13 fases, incluindo uma secreta), com sistema de atributos/profissões estilo Ultima Online, magias, itens, clima dinâmico, afixos de monstro (Paragon/Campeão), 5 níveis de dificuldade e um Bestiário/Atlas pra acompanhar o que já foi descoberto.

### Destaques

- **3 atos, 4 bosses únicos** — cada um com sprite, sala e padrão de ataque próprios (Senhor da Guerra Orc, Necromante, Rei das Sombras, e o Cacodemônio da fase secreta).
- **20 arquétipos de monstro comuns**, cada um com seu próprio rig visual e "magia"/ataque de acordo com a natureza dele (veneno, gelo, choque, fogo, fraqueza...), espalhados pelas 12 fases de combate.
- **Atributos e profissões**: FOR/DES/INT/SAB/VIG/SOR determinam 16 profissões possíveis (5 puras + 10 híbridas + Aventureiro), sem nada "guardado" — é só a leitura dos pontos gastos.
- **Magias**: Bola de Fogo, Nova de Gelo, Luz Curativa — desbloqueadas por requisito de atributo.
- **Status effects**: Veneno, Lentidão, Fraqueza, Fogo, Frio, Calor e Choque, com cura por Antídoto onde faz sentido.
- **5 dificuldades** (Normal → Inferno), cada uma a mesma campanha com monstros mais fortes, chance de Campeões, afixos de fase inteira e enrage de boss mais cedo — desbloqueadas sequencialmente.
- **Paragon**: spawn raro (3%, com pity) de monstro comum upgradado, x4 XP/ouro.
- **Clima dinâmico** por fase (neblina, chuva, neve, tempestade, cinzas...).
- **Paperdoll** com 5 abas: Status, Magias, Bestiário (mobs/bosses descobertos), Atlas (fases já visitadas) e Ajuda.
- **Save/load** persistente (personagem, economia, progressão por dificuldade).
- **Painel de debug** (`F1`, PC apenas) pra testar atributos, economia e dificuldade sem precisar re-jogar a campanha inteira.
- Roda no desktop, no **navegador** (PC e celular, via Pygbag/WebAssembly) e compila pra **.exe** do Windows.

---

## 🎮 Controles

| Tecla | Ação |
|---|---|
| W / A / S / D ou ↑↓←→ | Mover personagem |
| ESPAÇO | Atacar |
| 1 / 2 / 3 | Conjurar magia (se desbloqueada) |
| C | Abrir Paperdoll (Status/Magias/Bestiário/Atlas/Ajuda) |
| I | Abrir Itens |
| ESC | Pausar / Menu |
| ENTER | Confirmar menus |
| F1 | Painel de debug (dev, só PC) |

No navegador/celular, assim que a tela é tocada aparecem controles virtuais (joystick + botão de ataque + pausa).

---

## 🏰 Campanha

| Fase | Título | Tipo | Monstros / Boss | ML |
|---|---|---|---|---|
| 1 | Floresta Encantada | combate | esqueleto, goblin | 1 |
| 2 | Ruínas do Deserto | combate | esqueleto, goblin | 4 |
| 3 | Masmorra das Sombras | combate | esqueleto, goblin, cavaleiro negro | 8 |
| 4 | Acampamento de Guerra | **boss** | Senhor da Guerra Orc | — |
| 5 | Pântano Sombrio | combate | aranha, serpente, treant | 12 |
| 6 | Torre Amaldiçoada | combate | esqueleto, troll, cavaleiro da morte | 16 |
| 7 | Cripta Perdida | combate | zumbi, verme, imp | 20 |
| 8 | Cripta do Necromante | **boss** | Necromante | — |
| 9 | Salão dos Ecos | combate | dark horse, acólito, feiticeira | 24 |
| 10 | Abismo de Cinzas | combate | fire hound, ogro, elemental de pedra | 28 |
| 11 | Corredor Final | combate | quimera, lyzardman, esqueleto sombrio | 32 |
| 12 | Trono das Trevas | **boss** (final da campanha) | Rei das Sombras | — |
| 13 | Fase Secreta: INFERNO | **boss** (desbloqueada após vencer o Inferno) | Cacodemônio | — |

### Condição de vitória
Derrotar o **Rei das Sombras** na Fase 12 (a fase secreta é um bônus pós-campanha).

### Condição de derrota
O jogador perde toda a vida (6 corações).

Detalhes de balanceamento, fórmulas e decisões de design ficam em [`docs/design.md`](docs/design.md) — documento vivo, atualizado a cada mudança de sistema.

---

## ▶ Como Executar (Modo Desenvolvimento)

```bash
pip install pygame
python main.py
```

---

## 🌐 Como Executar no Navegador (PC e Celular)

O jogo também roda no navegador via [Pygbag](https://github.com/pygame-web/pygbag)
(compila o Pygame para WebAssembly), sem precisar instalar nada além do Python no
computador que serve o jogo.

```bash
pip install pygbag

# Terminal 1 - para abrir no navegador do próprio PC
python -m pygbag --bind localhost --port 8000 main.py

# Terminal 2 - para abrir no celular (rode em paralelo, IP diferente, porta diferente)
python -m pygbag --bind <IP-do-PC-na-rede> --port 8001 main.py
```

- No **PC**, abra `http://localhost:8000`.
- No **celular**, conecte-o na mesma rede Wi-Fi do PC e abra
  `http://<IP-do-PC-na-rede>:8001` (descubra o IP com `ipconfig` no Windows ou
  `ip addr` no Linux/WSL). **Atenção à porta:** é **8001**, não 8000 — só a
  8000 tem bind em `localhost`, a 8001 é a única que aceita conexão de outros
  dispositivos na rede. (Testamos usar 8080 no lugar de 8001 para reduzir essa
  confusão, mas nessa rede especificamente 8080 deu "connection refused" no
  celular enquanto 8001 funciona — provavelmente uma regra de firewall do
  Windows já liberada para 8001 e não para 8080 — por isso voltamos pra 8001.)
- **Por que dois processos em portas diferentes, e não um só?** O servidor de
  desenvolvimento do Pygbag copia literalmente o valor de `--bind` para dentro
  da página (para montar a URL do runtime/CDN), então só existe UM endereço
  válido por processo. `--bind 0.0.0.0` quebra tudo (gera a URL inválida
  `http://0.0.0.0:8000/...`, que o navegador recusa). E mesmo usando o IP real
  da rede num único processo, se o PC que roda o servidor for uma máquina
  WSL/Windows, o próprio PC pode não conseguir se conectar nesse IP (timeout),
  mesmo o `ping` funcionando e o celular acessando normalmente — isso é uma
  limitação de rede do WSL2 (o tráfego TCP do Windows para o IP dele mesmo,
  exposto pelo WSL, precisa de um "hairpin" que nem sempre funciona; o `ping`
  usa um caminho diferente que não depende disso, e o celular funciona porque
  chega genuinamente pela rede Wi-Fi). Rodando dois processos — um em
  `localhost` para o PC, outro no IP da rede para o celular — cada dispositivo
  usa o caminho de rede que realmente funciona para ele.
- Depois que a página carregar, **clique/toque uma vez em qualquer lugar da
  tela**: os navegadores exigem esse gesto do usuário antes de liberar áudio/o
  jogo (mensagem "Ready to start! Please click/touch page").
- **Controles no celular:** assim que qualquer toque/clique é detectado, aparecem
  controles virtuais na tela — um joystick analógico (canto inferior esquerdo)
  para mover o personagem, um botão "ATK" (canto inferior direito) para atacar
  e um botão de pausa (canto superior direito). Nos menus, basta tocar
  diretamente nas opções de texto. No navegador do PC os controles de teclado
  continuam funcionando normalmente (os virtuais só aparecem se você usar
  mouse/toque).
- A primeira execução baixa o runtime do Pygbag (Pyodide); é necessário ter internet
  nesse primeiro build.

---

## 📦 Como Compilar para Windows (.exe)

1. Instale o PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Navegue até a pasta do projeto e abra o CMD aqui
3. Execute:
   ```bash
   PyInstaller --onefile main.py
   ```
4. O arquivo `main.exe` será gerado em `dist/`
5. Compacte a pasta `dist/` em um ZIP e entregue

> **Dica:** Se o .exe der erro, execute pelo CMD para ver a mensagem de erro.

---

## 📁 Estrutura do Projeto

```
trab-uninter-game/
├── main.py                 ← Ponto de entrada
├── requirements.txt
├── README.md
├── docs/
│   ├── design.md            ← Documento vivo de design/balanceamento
│   └── save-schema.md        ← Formato do arquivo de save
├── tools/
│   └── balance_sim.py        ← Simulador headless de curva de XP/combate
└── game/
    ├── states.py             ← Menu, Gameplay, GameOver, Vitória
    ├── player.py             ← Personagem jogável
    ├── enemy.py               ← Inimigos comuns (IA, ataques, status effects)
    ├── boss.py                ← Bosses (fases, padrões de ataque, projéteis)
    ├── level.py                ← Mapas e carregamento de fases (LEVEL_MAPS)
    ├── stats.py                ← StatBlock, arquétipos, fórmulas de dano/XP
    ├── status_effects.py        ← Veneno/Lentidão/Fraqueza/Fogo/Frio/Calor/Choque
    ├── affixes.py                ← Paragon/Campeão e afixos de fase
    ├── difficulty.py              ← 5 tiers de dificuldade
    ├── professions.py              ← Derivação de profissão a partir dos atributos
    ├── spells.py                    ← Magias do jogador
    ├── items.py                      ← Poções/consumíveis
    ├── merchant.py                    ← Loja
    ├── weather.py                      ← Clima dinâmico por fase
    ├── reputation.py                    ← Reputação/facções
    ├── bestiary.py                       ← Dados do Bestiário (nome/descrição/discovery)
    ├── paperdoll.py                       ← UI do painel do personagem (5 abas)
    ├── debug_panel.py                      ← Painel de debug (F1)
    ├── save.py                              ← Persistência (save/load)
    ├── camera.py                             ← Câmera suave
    ├── audio.py                               ← Som
    ├── input_system.py                         ← Teclado/mouse/touch unificados
    ├── theme.py                                 ← Paleta de cores e fontes
    ├── ui.py                                     ← Componentes de UI reutilizáveis
    └── assets.py                                  ← Sprites/tiles pixel art gerados em código
```

---

*Todos os sprites são gerados programaticamente em código Python puro (sem arquivos externos de imagem), garantindo portabilidade total.*
