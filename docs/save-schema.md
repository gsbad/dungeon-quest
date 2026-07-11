# Save schema — `game/save.py`

Versionado desde o dia 1 (`SAVE_VERSION`). **Regra de casa: nunca mudar o formato sem subir a versão e escrever uma migração em `_migrate()`.** Todo PR que toca o schema testa explicitamente carregar um save da versão anterior, não só um save novo.

Backend: `localStorage` via a ponte `js`/`platform.window` do pygbag no navegador, arquivo JSON nativo (`_save.json`) fora do navegador (`python main.py`).

## v4 (atual)

```json
{
  "version": 4,
  "character": {
    "name": "Aragorn",
    "level": 7,
    "xp": 1240,
    "unspent_points": 4,
    "attributes": {"str": 22, "dex": 12, "int": 10, "wis": 10, "vig": 18}
  },
  "progression": {
    "current_difficulty": "hard",
    "highest_level_cleared": {"normal": 12, "hard": 3},
    "cleared_difficulties": ["normal"]
  },
  "counters": {
    "kills": {"skeleton": 143, "goblin": 87},
    "boss_kills": {"shadow_king": 1},
    "deaths": 6,
    "playtime_s": 5400.0
  },
  "settings": {"muted": false},
  "gold": 340,
  "inventory": {"health_potion": 2, "antidote": 1}
}
```

Current hp/mana e efeitos de status ativos **não são persistidos** — estado transiente, sempre restaurado ao máximo (`character_from_state()`) quando o personagem é carregado ou continua.

`progression.highest_level_cleared` é por dificuldade (Stage B5) — cada tier tem seu próprio progresso dentro da mesma campanha de 12 fases, para CONTINUAR resumir corretamente independente de qual tier está ativo. `cleared_difficulties` é a lista de tiers já vencidos ao menos uma vez (chegou ao resultado `"victory"` na fase 12) — é o que desbloqueia o próximo tier (`game/difficulty.py`'s `is_unlocked()`) e, quando inclui `"inferno"`, a fase secreta (13, Cacodemon).

## Histórico de migrações

- **v1 → v2:** adiciona `character.name` (default `""`), `gold` (default `0`), `inventory` (default `{}`). Sem esses campos, saves antigos ainda carregam — só ficam sem nome/economia até jogar de novo.
- **v2 → v3:** corrige `POINTS_PER_LEVEL` de 3 para 4. Concede `unspent_points += (level - 1)` — o jogador recebeu `3·(nível-1)` pontos e deveria ter recebido `4·(nível-1)`; o déficit exato é `nível-1`. Só afeta personagens que já subiram de nível (nível 1 não tem déficit).
- **v3 → v4:** `progression.highest_level_cleared` vira um dict por dificuldade (era um int global); adiciona `progression.current_difficulty` (default `"normal"`) e `progression.cleared_difficulties` (default `[]`). Também corrige um problema deixado pela renumeração de fases do Stage B4 (que não subiu a versão do save quando fez essa mudança): a fase 4 antiga era o Rei das Sombras, a fase 4 nova é o Senhor da Guerra Orc — conteúdo completamente diferente. Um `highest_level_cleared` antigo além de 3 não pode ser confiado como "a mesma fase" depois da renumeração, então a migração usa `min(valor_antigo, 3)` (só as fases 1-3, que não mudaram) em vez de carregar o número cru.

## O que ainda não está no schema (vem com o sistema que o usa)

- `achievements` (lista de conquistas desbloqueadas) — chega com `game/achievements.py` (Stage B6).
- `displayed_title` — chega com o sistema de títulos (Stage B6).
- `profession` — não precisa persistir; é *derivada* dos atributos gastos (recalculada ao carregar), não um valor independente que possa dessincronizar.
