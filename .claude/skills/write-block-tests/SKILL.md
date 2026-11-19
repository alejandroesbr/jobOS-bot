---
name: write-block-tests
description: Turn a block specification (docs/blocks/block-N.md) into failing pytest tests with offline fixtures (recorded Gemini JSON, sanitized portal HTML, fictitious CV). Use when starting a jobOS-bot block or when the user says "escribe los tests del bloque N".
---

# write-block-tests

Procedimiento para pasar de `docs/blocks/block-N.md` a tests RED. Lo ejecuta el subagente `test-writer`
(o Claude Code directamente para bloques pequeños).

## 1. Preparar

1. Rama: `feature/block-<N>-<slug>` desde `develop` (ver skill `jobos-conventions`). Si ya existe, úsala.
2. Lee `AGENTS.md`, `docs/blocks/block-N.md`, `docs/agents/gemini-api-facts.md` (si el bloque toca Gemini)
   y los tests existentes del área.
3. Lista los criterios de aceptación de la spec. Cada uno tendrá al menos un test.

## 2. Fixtures (cero red)

| Necesidad | Ubicación | Regla |
|---|---|---|
| Respuestas Gemini (LLM y embeddings) | `tests/fixtures/gemini/<caso>.json` | Respuesta grabada; el adaptador se prueba con un cliente falso que devuelve este JSON. Vectores de 768 dims (puede generarse determinísticamente en un helper en vez de guardarlo). |
| HTML de portales | `tests/fixtures/html/<portal>/<caso>.html` | Sanitizado: empresas y personas ficticias, sin emails/teléfonos, sin tokens, sin scripts de tracking, URLs canónicas de ejemplo. |
| CV / perfil | `tests/fixtures/profile/fake_profile.yaml`, `fake_cv.md` | 100% inventado. Nunca derivado de `config/profile.yaml` ni `config/cv_base.md` (no se leen). |
| Base de datos | `tmp_path` + SQLite en archivo temporal o `:memory:` | Nunca `data/jobs.db`. |
| Vault de Obsidian | `tmp_path / "vault"` | Nunca `vault/`. |

- Bloquea la red en los tests que lo necesiten con un fixture que haga `monkeypatch` de `socket.socket.connect`
  para lanzar error, o inyecta el cliente HTTP falso por el puerto.
- Nada de `time.sleep`; reloj y aleatoriedad se inyectan.

## 3. Escribir los tests

- Un archivo por unidad: `tests/test_<modulo>.py` o `tests/block_<N>/test_<tema>.py`.
- Nombres `test_<unidad>_<comportamiento>_<condición>`, Arrange-Act-Assert, `-> None`.
- `@pytest.mark.parametrize` para tablas de casos (umbrales, alias técnicos, títulos con Hard Reject).
- Casos borde obligatorios cuando apliquen: vacío/`None`, Unicode NFD y tildes, `C#`/`C++`/`.NET`, límites de umbral
  (justo debajo, igual, encima), duplicados/re-postulación, error del puerto externo.
- Los tests importan la API pública que define la spec aunque aún no exista.

## 4. Verificar RED

```bash
python -m pytest <tests nuevos> -q          # deben FALLAR por ImportError/AttributeError/AssertionError
mypy --strict <tests nuevos>                 # deben tipar (salvo imports de módulos aún inexistentes)
ruff check <tests nuevos> && ruff format --check <tests nuevos>
```

Si un test pasa antes de implementar, no aporta señal: reescríbelo o elimínalo.

## 5. Entregar

- Commit: `test(block-<N>): add failing tests for <tema>`.
- Resume en la respuesta: tabla archivo → tests → criterio, salida RED, preguntas abiertas sobre la spec.
