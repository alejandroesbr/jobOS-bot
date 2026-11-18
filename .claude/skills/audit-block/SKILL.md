---
name: audit-block
description: Audit a jobOS-bot block implemented by Antigravity - run the quality gates, launch code-reviewer, security-auditor (and schema-auditor if the schema changed) in parallel, and consolidate the result in docs/audits/block-N-roundK.md with a verdict. Use when the user says "audita el bloque N" or a handoff arrives.
---

# audit-block

## 0. Entrada

- Bloque `N` y rama `feature/block-<N>-<slug>`. Lee `docs/blocks/block-N.md` (spec) y
  `docs/blocks/block-N-handoff.md` (handoff de Antigravity).
- Ronda `K`: 1 + número de archivos `docs/audits/block-N-round*.md` existentes.
- Alcance: `git diff --name-only develop...HEAD`.

## 1. Gates (deterministas, primero)

```bash
ruff check .
ruff format --check .
mypy --strict src cli.py tests .claude/hooks
lint-imports
python -m pytest --cov=src --cov-report=term-missing -q
```

Anota exit code y un resumen de cada gate. Un gate rojo ya implica `CHANGES_REQUESTED`, pero continúa con la
revisión para entregar todos los hallazgos en una sola ronda.

## 2. Auditores en paralelo

Lanza en **un solo mensaje** (en paralelo) con la lista de archivos del diff y la ruta de la spec:

- `code-reviewer` — siempre.
- `security-auditor` — siempre.
- `schema-auditor` — solo si el diff toca `src/adapters/db/schema.sql`, migraciones o SQL en
  `src/adapters/db/**`.

Cada uno devuelve hallazgos 🔴/🟠/🟡 con `archivo:línea`, escenario de fallo, arreglo sugerido y su veredicto.

## 3. Verificar y consolidar

- Verifica tú mismo cada 🔴 y 🟠 (abre el archivo y la línea). Descarta lo que no se sostenga y anótalo.
- Deduplica hallazgos repetidos entre auditores.
- Comprueba que la spec se cumple: cada criterio de aceptación tiene test y está en verde.

## 4. Escribir `docs/audits/block-N-roundK.md`

```markdown
# Auditoría block-N — ronda K

- Rama: feature/block-<N>-<slug> @ <sha corto>
- Fecha: YYYY-MM-DD
- Alcance: <n> archivos (lista o resumen)

## Gates
| Gate | Resultado |
|---|---|
| ruff check | ✅ / ❌ (resumen) |
| ruff format --check | |
| mypy --strict | |
| lint-imports | |
| pytest (+ cobertura) | |

## Hallazgos
### 🔴 Bloqueantes
- <título> — `ruta:línea` (auditor)
  - Escenario de fallo: ...
  - Arreglo sugerido: ...
### 🟠 Importantes
### 🟡 Menores

## Descartados en verificación
- ...

## Cumplimiento de la spec
| Criterio | Test | Estado |
|---|---|---|

## Veredicto: APPROVED | CHANGES_REQUESTED
```

Regla: `APPROVED` solo si todos los gates están en verde y no queda ningún 🔴 ni 🟠 verificado.

## 5. Cerrar

- Commit en la rama del bloque: `docs(audit): add block-<N> round <K> audit`.
- Informa al humano el veredicto. **No fusionar**: el merge a `develop` requiere `APPROVED` y su aprobación
  explícita (ver `jobos-conventions`).
