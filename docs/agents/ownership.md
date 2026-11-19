# Ownership — ruta → dueño

Cada ruta tiene un único agente que la escribe. El otro agente puede leerla, pero no la edita:
pide el cambio en el handoff (`docs/blocks/block-N-handoff.md`) o en la auditoría
(`docs/audits/block-N-roundK.md`).

| Ruta | Dueño |
|---|---|
| `tests/**` | Claude Code |
| `AGENTS.md` | Claude Code |
| `CLAUDE.md` | Claude Code |
| `.claude/**` | Claude Code |
| `docs/agents/**` | Claude Code |
| `docs/audits/**` | Claude Code |
| `docs/blocks/block-N.md` (especificación) | Claude Code |
| `.github/workflows/**` | Claude Code |
| `pyproject.toml` — secciones `[tool.*]` | Claude Code |
| `src/**` | Antigravity |
| `cli.py` | Antigravity |
| `Dockerfile` | Antigravity |
| `docker-compose.yml` | Antigravity |
| `README.md` | Antigravity |
| `.agents/**` | Antigravity |
| `docs/blocks/block-N-handoff.md` | Antigravity |
| `docs/blocks/captures/**` | Antigravity |
| Resto de `docs/` | Antigravity |

Rutas protegidas (ningún agente las lee ni las edita): `.env`, `data/**`, `config/profile.yaml`,
`config/cv_base.md`, `config/*.pdf`.

Nota: el grupo `[dependency-groups] dev` de `pyproject.toml` lo mantiene Claude Code (herramientas
de calidad). Las dependencias de producción (`requirements.txt`, `[project]`) son de Antigravity.
