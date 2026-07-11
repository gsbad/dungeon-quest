# Dungeon Quest 🗡️
**Trabalho de Linguagem de Programação Aplicada – UNINTER 2026**

Jogo 2D top-down estilo Zelda, desenvolvido em Python com pygame.

---

## ▶ Como Executar (Modo Desenvolvimento)

```bash
pip install pygame
python main.py
```

---

## 🎮 Controles

| Tecla | Ação |
|---|---|
| W / A / S / D | Mover personagem |
| ↑ ↓ ← → | Mover (alternativo) |
| ESPAÇO | Atacar |
| ESC | Pausar / Menu |
| ENTER | Confirmar menus |

---

## 🏰 Estrutura do Jogo

| Fase | Ambiente | Inimigos |
|---|---|---|
| 1 | Floresta Encantada | Esqueletos e Goblins |
| 2 | Ruínas do Deserto | Goblins e Esqueletos |
| 3 | Masmorra das Sombras | Cavaleiros das Trevas |
| Boss | Trono das Trevas | Shadow King (2 fases!) |

### Condição de Vitória
Derrotar o **Shadow King** na Fase 4.

### Condição de Derrota
O jogador perde toda a vida (6 corações).

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
  `ip addr` no Linux/WSL).
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
5. Copie a pasta `assets/` para dentro de `dist/` (ao lado do `main.exe`)
6. Compacte a pasta `dist/` em um ZIP e entregue

> **Dica:** Se o .exe der erro, execute pelo CMD para ver a mensagem de erro.

---

## 📁 Estrutura do Projeto

```
zelda_game/
├── main.py              ← Ponto de entrada
├── requirements.txt
├── README.md
└── game/
    ├── __init__.py
    ├── states.py        ← Menu, Gameplay, GameOver, Vitória
    ├── player.py        ← Personagem jogável
    ├── enemy.py         ← Inimigos com IA
    ├── boss.py          ← Boss com 2 fases e projéteis
    ├── level.py         ← Mapas e carregamento de fases
    ├── camera.py        ← Sistema de câmera suave
    └── assets.py        ← Sprites pixel art gerados em código
```

---

*Todos os sprites são gerados programaticamente em código Python puro (sem arquivos externos de imagem), garantindo portabilidade total.*
