# 03. Normalización Léxica, URLs Canónicas y Claves (`text_normalizer.py`)

Además de la normalización relacional de las tablas en SQLite, `jobOS-bot` aplica **normalización léxica determinista** en `src/domain/text_normalizer.py` antes de comparar o guardar cualquier dato proveniente de los portales web.

---

## 1. Normalización de Nombres de Empresas (`normalize_company_name`)

Una misma empresa suele escribir su nombre de forma ligeramente distinta en cada portal:
* En LinkedIn: `" Mercado Libre Colombia S.A.S. "`
* En GetOnBrd: `"Mercado Libre"`
* En Computrabajo: `"MERCADO LIBRE S.A."`

### Pipeline de Transformación
1. **Descomposición Unicode (`NFD`):** Elimina tildes y diacríticos (`á -> a`, `ñ -> n`).
2. **Conversión a minúsculas (`lowercase`).**
3. **Eliminación de sufijos societarios y geográficos genéricos** mediante expresión regular con límites de palabra (`\b`):
   * Sufijos removidos: `s.a.s`, `sas`, `s.a`, `sa`, `ltda`, `inc`, `llc`, `corp`, `corporation`, `b.v`, `gmbh`, `colombia`, `latam`.
4. **Limpieza de caracteres no alfanuméricos** y colapso de espacios múltiples a un solo espacio.

| Entrada Cruda (DOM del Portal) | Salida Normalizada (`company_norm`) |
| :--- | :--- |
| `"Globant Colombia S.A.S."` | `"globant"` |
| `"EPAM Systems, Inc."` | `"epam systems"` |
| `" Lean Tech LLC - Latam "` | `"lean tech"` |

---

## 2. Normalización de Títulos de Vacantes (`normalize_job_title`) y `dedup_key`

Los reclutadores suelen agregar etiquetas de urgencia o modalidad entre paréntesis en el título:
* En LinkedIn: `"Desarrollador Full Stack Junior (React / Node.js) - Remoto"`
* En GetOnBrd: `"[URGENTE] Desarrollador Fullstack Jr - React & Node"`

### Pipeline de Transformación del Título
1. **Descomposición Unicode (`NFD`) y minúsculas.**
2. **Unificación de sinónimos comunes (Token Canonicalization):**
   * `jr.` / `jr` $\rightarrow$ `junior`
   * `sr.` / `sr` $\rightarrow$ `senior`
   * `fullstack` $\rightarrow$ `full stack`
   * `node.js` / `nodejs` $\rightarrow$ `node`
   * `react.js` / `reactjs` $\rightarrow$ `react`
   * `nextjs` $\rightarrow$ `next.js`
3. **Eliminación de etiquetas de ruido de modalidad/urgencia en el título:**
   * Remueve tokens como `urgente`, `remoto`, `remote`, `hibrido`, `barranquilla`, `colombia`, `100%` (ya que la ubicación/modalidad tiene su propia columna dedicada).
4. **Construcción del `dedup_key`:**
   ```python
   dedup_key = f"{company_norm}::{title_norm}"
   ```

| Empresa Cruda | Título Crudo | `dedup_key` Resultante |
| :--- | :--- | :--- |
| `"TechCorp S.A.S"` | `"Desarrollador Fullstack Jr (React/Node.js) - Remoto"` | `"techcorp::desarrollador full stack junior react node"` |
| `"TechCorp Colombia"` | `"[Remoto] Desarrollador Full Stack Junior - React / Node"` | `"techcorp::desarrollador full stack junior react node"` |

> Ambas ofertas producen **exactamente el mismo `dedup_key`**, permitiendo que el bot detecte al instante que es la misma vacante, vuelva a postularse en el segundo portal e incremente `times_applied = 2` sobre el mismo registro maestro.

---

## 3. Normalización de URLs Canónicas (`normalize_canonical_url`)

Los portales inyectan decenas de parámetros dinámicos (`?utm_source=...`, `&trackingId=...`, `&refId=...`, `&eBP=...`) que cambian en cada sesión aunque apuntan a la misma oferta.

### Reglas de Limpieza por Portal
1. Se parsea la URL con `urllib.parse.urlsplit`.
2. Se fuerza esquema `https`, dominio en minúsculas y se elimina el fragmento (`#...`) y la barra final (`/`).
3. **Filtro de Query Params (Whitelist por Portal):**
   * **LinkedIn (`/jobs/view/...`):** Se eliminan **todos** los query params si el ID ya está en la ruta (`/jobs/view/4102938471`), o se conserva únicamente `currentJobId`.
   * **Indeed:** Se conserva únicamente el parámetro `jk` (el ID de la oferta en Indeed).
   * **GetOnBrd / Computrabajo / Elempleo / Glassdoor:** El ID de la oferta vive en el `path`; se descartan todos los parámetros `utm_*`, `ref*`, `tracking*`, `source*` y `pos`.

---

## 4. Normalización de Preguntas de Formularios (`normalize_form_question`)

Para que `qa_memory` alcance una tasa de acierto alta con `RapidFuzz` (`>= 85%`) sin llamar a Gemini repetidamente:

1. Convierte a minúsculas y remueve tildes (`NFD`).
2. Elimina asteriscos de campo obligatorio (`*`), signos de interrogación (`¿?`), dos puntos finales (`:`) y texto entre paréntesis meramente instructivo como `(obligatorio)` o `(required)`.
3. Unifica términos técnicos (`react.js -> react`, `node.js -> node`, `typescript -> ts`).

| Etiqueta HTML Cruda (`<label>`) | `question_norm` en `qa_memory` |
| :--- | :--- |
| `"* ¿Cuántos años de experiencia tienes trabajando con React.js? :"` | `"cuantos anos de experiencia tienes trabajando con react"` |
| `"Cuántos años de experiencia tienes con React? (Obligatorio)"` | `"cuantos anos de experiencia tienes con react"` |

Ambas cadenas tienen una similitud **Token Set Ratio de `100%`** en `RapidFuzz`, resolviendo el campo en `< 0.3 ms` desde SQLite.

