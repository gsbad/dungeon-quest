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

## Abrindo um PR

- Descreva o quê e por quê, não só o quê - o "por quê" é o que normalmente falta e o que mais ajuda na revisão.
- PRs pequenos e focados são mais fáceis de revisar que um PR gigante mexendo em várias coisas não relacionadas.
- Se sua mudança precisar de uma nova rota no backend, lembre de adicionar o bloco correspondente no `Caddyfile` de produção também (documentado em `docs/deploy.md`) - só existir no FastAPI não é suficiente.

## Reportando bugs

Abra uma issue com: o que você esperava, o que aconteceu, e se possível um screenshot/GIF (principalmente para bugs visuais/de input - descrição em texto raramente é suficiente para esses).
