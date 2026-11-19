---
name: implement-block
description: >-
  Use this workflow to implement a migration block (block-N) in jobOS-bot v3.3
  following TDD red-green, ownership boundaries, the 4 quality gates, handoff
  documentation, and audit round responses.
---

# Workflow: Implement Block (`block-N`)

Sigue estos pasos en orden estricto para implementar cualquier bloque de la migración `jobOS-bot v3.3`:

## 1. Sincronizar la Rama del Bloque
- Asegúrate de estar en la rama o worktree correspondiente al bloque (`feature/block-<N>-<slug>`).
- Ejecuta `git pull` de la rama del bloque para traer la especificación y los tests creados por Claude Code.

## 2. Leer Especificación y Verificar Estado Inicial (Rojo)
- Lee `docs/blocks/block-N.md` y los tests que escribió Claude Code en `tests/`.
- Si el bloque involucra Gemini, lee `docs/agents/gemini-api-facts.md`. Si involucra `crawlee`, `sqlite-vec`, `google-genai`, `FastMCP` o `rapidfuzz`, consulta **Context7**.
- Corre `python -m pytest`: **los tests nuevos deben fallar** (estado rojo).
- Si encuentras algún test incorrecto o contradictorio con la especificación, **no edites `tests/**`**: documéntalo en `docs/blocks/block-N-questions.md` y detente para avisar al usuario.

## 3. Plan de Implementación y Aprobación
- Presenta al usuario un plan de implementación conciso (archivos de `src/` o `cli.py` a crear/modificar, contratos, decisiones de diseño).
- **Espera la aprobación explícita del usuario** antes de escribir código de producción.

## 4. Implementación Mínima (Verde)
- Implementa lo mínimo necesario en las rutas de tu propiedad (`src/**`, `cli.py`, etc.) para dejar los tests en verde, respetando estrictamente:
  - Clean Architecture + Ports & Adapters + CQS.
  - Núcleo puro (`src/domain/` / `src/core/`): `0% I/O`, `@dataclass(frozen=True, slots=True)`, `StrEnum`, sin importar adaptadores ni librerías externas prohibidas (`sqlite3`, `httpx`, `playwright`, `crawlee`, `google`, `pydantic`, `mcp`).
  - Logs siempre a `stderr`.
  - SQL siempre parametrizado.

## 5. Ejecutar los 4 Quality Gates
Corre localmente los 4 gates y asegúrate de que todos pasen con cero errores:
```bash
python -m pytest
mypy --strict src cli.py tests .claude/hooks
ruff check .
ruff format --check .
lint-imports
```

## 6. Documentar Handoff (`docs/blocks/block-N-handoff.md`)
Escribe `docs/blocks/block-N-handoff.md` incluyendo:
- **Qué cambió**: resumen de módulos creados/modificados.
- **Decisiones técnicas**: justificación de diseño o algoritmos aplicados.
- **Resultados de los 4 gates**: confirmación de salida limpia.
- **Dudas o solicitudes a Claude Code**: si se requiere algún ajuste en rutas ajenas.

## 7. Commit y Push
- Realiza el commit en inglés siguiendo Conventional Commits:
  `feat|fix|refactor(block-N): <imperative summary in lowercase>`
- Haz `git push` únicamente a la rama del bloque (`feature/block-<N>-<slug>`). **Nunca hagas push ni merge a `main` o `develop`.**

## 8. Atención a Rondas de Auditoría (`docs/audits/block-N-roundK.md`)
- Si existe `docs/audits/block-N-roundK.md` con veredicto `CHANGES_REQUESTED`:
  1. Atiende todos los hallazgos severos (`🔴` y `🟠`).
  2. Vuelve a correr los 4 quality gates.
  3. Actualiza `docs/blocks/block-N-handoff.md` respondiendo a **cada** hallazgo explícitamente como:
     - `fixed`: indicando archivo y líneas donde se resolvió.
     - `disagree + motivo`: fundamentando técnicamente con referencia a la especificación o arquitectura.
  4. Haz commit y push en la rama del bloque.
