---
name: jobos-conventions
description: jobOS-bot git conventions - branch names feature/block-<N>-<slug>, Conventional Commits in English, and the merge rule (develop only with APPROVED audit plus explicit human approval). Use before creating branches, committing, pushing or proposing a merge.
---

# jobos-conventions

Detalle de referencia: `AGENTS.md` §8–9 y `docs/arquitectura/10-gitflow-y-convenciones.md`.

## Ramas

| Rama | Origen | Uso |
|---|---|---|
| `feature/block-<N>-<slug>` | `develop` | Un bloque de la migración. `<slug>` en kebab-case corto (`block-3-sqlite-vec`). |
| `chore/<slug>` | `develop` | Configuración, tooling, agentes. |
| `docs/<slug>` | `develop` | Solo documentación. |
| `hotfix/<slug>` | `main` | Correcciones urgentes; se fusiona a `main` y `develop`. |
| `release/vX.Y.Z` | `develop` | Preparación de versión. |

Antes de crear una rama: `git status` limpio. Si no lo está, detente y avisa.

## Commits

```
<type>(<scope>): <imperative summary in lowercase>
```

- Inglés, imperativo, minúsculas, sin punto final, ≤ 72 caracteres en el resumen.
- Tipos: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`.
- Scopes habituales: `block-<N>`, `domain`, `db`, `mcp`, `scrapers`, `obsidian`, `agents`, `audit`, `ci`.
- Un commit = un cambio coherente. Nunca incluir `.env`, `data/`, `vault/`, `exports/`, `config/profile.yaml`,
  `config/cv_base.md`, `config/*.pdf`. Revisa `git diff --cached --name-only` antes de cada commit.
- Añade al final las líneas de atribución que indique el entorno (Co-Authored-By).

Ejemplos: `test(block-2): add failing tests for bayesian scorer`, `docs(audit): add block-2 round 1 audit`,
`chore(agents): harden bash guard for protected paths`.

## Push

- Solo a tu rama de trabajo: `git push -u origin <rama>`. Siempre pide confirmación (regla `ask`).
- Prohibido: push a `main`/`develop`, cualquier `--force`/`-f`/`--force-with-lease`/`+refspec` (los bloquea el hook).

## Merge

1. La auditoría más reciente `docs/audits/block-N-roundK.md` dice `APPROVED`.
2. CI en verde en el PR hacia `develop`.
3. El humano lo aprueba **explícitamente** en la conversación.

Solo entonces: `git checkout develop && git merge --no-ff feature/block-<N>-<slug>`. Claude Code no fusiona
por iniciativa propia ni con una aprobación de otra sesión.
