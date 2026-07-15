# Contribuindo

Obrigado pelo interesse em contribuir com o Dungeon Quest! Este é um projeto pessoal/portfólio, mas PRs e issues são bem-vindos.

## Antes de começar

Leia [`docs/architecture.md`](docs/architecture.md) para uma visão geral de como o código se encaixa, e [`docs/design.md`](docs/design.md) se sua mudança mexer em qualquer fórmula/número de balanceamento (dano, XP, drop rate, etc.) - é um documento vivo, deve continuar refletindo a implementação real depois da sua mudança.

## Rodando localmente

```bash
pip install pygame
python main.py
```

Para testar como roda no navegador (PC e celular na mesma rede), veja a seção "Como Executar no Navegador" do [`README.md`](README.md).

Para trabalhar no backend, veja `backend/README.md` (se não existir ainda, `backend/requirements.txt` + `uvicorn app.main:app --reload` a partir de `backend/`).

## Estilo de código

- Sem comentário explicando *o quê* o código faz - nomes de variável/função já fazem isso. Comentário só quando o *porquê* não é óbvio (uma decisão de design não trivial, uma correção de bug específica, uma restrição escondida).
- Prefira um dicionário-registro pequeno + uma função que lê a tabela em vez de hierarquia de classes - é o padrão que o projeto inteiro já segue (`ENEMY_ARCHETYPES`, `SPELLS`, `ITEMS`, `LEVEL_MAPS`, etc.).
- Todo sprite/ícone é pixel art gerada em código (`game/assets.py`, `pygame.draw.*`) - não adicione dependência de arquivo de imagem externo.

## Testando sua mudança

Não há suíte de testes tradicional (pytest) - o jogo é validado ao vivo, num navegador de verdade, via Playwright headless (ver [`docs/architecture.md`](docs/architecture.md#testes)). Se sua mudança afeta qualquer coisa visual, de input, ou de fluxo de tela, confirme com um teste desses (ou manualmente, se preferir) antes de abrir o PR - uma mudança que só "parece certa" na leitura do código já causou bugs reais neste projeto mais de uma vez.

Se sua mudança mexe em balanceamento (dano, XP, custo de item/magia), rode `tools/balance_sim.py` antes/depois e compare.

## Fluxo de branches

`main` é protegida (exige PR + 1 aprovação, sem push direto) e é a branch de produção - todo merge nela dispara o deploy automático pra VM (`.github/workflows/deploy.yml`). Nada de branches `develop`/`release` separadas: é GitHub Flow, não GitFlow completo.

1. Crie uma branch a partir de `main`, nomeada pela issue quando houver uma: `issue-42-fix-boss-hitbox` ou `feature/nome-curto`.
2. Commits pequenos e descritivos, PR quando estiver pronto pra revisão (rascunho antes disso, se quiser feedback cedo).
3. Peça revisão de quem não escreveu o código - o Gustavo ou o Glauco. Depois de aprovado, merge (squash, pra manter o histórico da `main` limpo).
4. O deploy acontece sozinho no merge. Confirme em produção depois (`https://129.80.222.127.sslip.io`), CI verde não garante que uma rota nova está de fato acessível via Caddy - ver a seção de gotchas em `docs/deploy.md`.

## Abrindo um PR

- Descreva o quê e por quê, não só o quê - o "por quê" é o que normalmente falta e o que mais ajuda na revisão.
- PRs pequenos e focados são mais fáceis de revisar que um PR gigante mexendo em várias coisas não relacionadas.
- Se sua mudança precisar de uma nova rota no backend, lembre de adicionar o bloco correspondente no `Caddyfile` de produção também (documentado em `docs/deploy.md`) - só existir no FastAPI não é suficiente.

## Pedindo pro Claude implementar

Este repo tem o [Claude Code GitHub Action](https://github.com/anthropics/claude-code-action) instalado (`.github/workflows/claude.yml`). Marcar `@claude` com uma descrição do que precisa:

- **Numa issue** - Claude implementa a mudança e abre um PR sozinho.
- **Num comentário de review de PR** - Claude aplica o ajuste pedido e empurra um commit na mesma branch.

O PR que ele abre passa pelo mesmo fluxo de revisão de qualquer outro - `main` protegida vale pra ele também, não só pra humanos. Alternativa sem depender do bot: descrever a issue/PR numa sessão interativa do Claude Code (terminal) e pedir pra implementar - mais controle passo a passo, útil pra mudanças maiores ou mais ambíguas.

## Reportando bugs

Abra uma issue com: o que você esperava, o que aconteceu, e se possível um screenshot/GIF (principalmente para bugs visuais/de input - descrição em texto raramente é suficiente para esses).
