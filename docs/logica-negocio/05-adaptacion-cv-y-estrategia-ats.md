# 05. Estrategia de Hoja de Vida y Optimización ATS

Como la lógica de negocio ordena **postularse incluso cuando no se cumple el 100% de los requisitos** (siempre que la oferta esté en el rango `>= 40%`), la forma en que se presenta la Hoja de Vida (CV) se adapta al porcentaje de compatibilidad de la vacante.

---

## 1. Estrategia por Nivel de Compatibilidad (`Match %`)

| Rango de `Match %` | Estrategia de Envío de Hoja de Vida | ¿Cuándo interviene `tailor` (Gemini)? |
| :--- | :--- | :--- |
| **`70% – 100%` (Match Alto)** | **Envío Directo de `cv_base`:** Tu hoja de vida principal ya contiene casi todas las palabras clave que busca el filtro ATS de esa empresa. Se adjunta el PDF base sin demora. | Opcional (solo si es una empresa top donde quieres personalizar el resumen). |
| **`40% – 69%` (Cumplimiento Parcial)** | **Envío + Refuerzo de Keywords Transferibles:** Se envía el CV inmediatamente para asegurar el lugar en la fila, y el módulo `tailor` identifica qué habilidades transferibles de tus proyectos cubren los requisitos faltantes. | Recomendado para ajustar bullets o el mensaje de presentación (*Cover Letter / Nota al reclutador*). |

---

## 2. Reglas Éticas y Técnicas de Adaptación (`python cli.py tailor <job_id>`)

Cuando una oferta pide 8 requisitos y tú cumples 4 o 5 (`~50%–60%`), el módulo `tailor` sigue tres reglas de negocio estrictas:

1. **Prohibido Inventar Experiencia Falsa (Cero Alucinaciones):**
   * Si la oferta pide `React + Node.js + PostgreSQL + AWS Lambda` y tú no has trabajado en una empresa con `AWS Lambda`, el bot **jamás** escribirá que trabajaste 2 años como arquitecto AWS.
2. **Traducción a Habilidades Equivalentes (Bridging):**
   * Si la oferta pide *"Experiencia en bases de datos relacionales (MySQL / Oracle)"* y tú dominas `PostgreSQL`, el bot sugiere incluir explícitamente el término `"Bases de datos relacionales SQL (PostgreSQL / sintaxis compatible con MySQL)"` para que el filtro ATS marque positivo el requisito.
   * Si la oferta pide *"Arquitectura de APIs y servicios backend"* y tú usas `NestJS` y `Node.js`, el bot reenfoca tus bullets de proyectos (como `jobOS-bot` o tus desarrollos full stack) usando el vocabulario exacto de la vacante.
3. **Generación de Nota Breve de Postulación (*Pitch de 3 líneas*):**
   * Muchos portales (como **GetOnBrd** o **LinkedIn**) tienen un campo opcional de *"¿Por qué te interesa este rol? / Mensaje al reclutador"*.
   * Aunque te falten 2 o 3 requisitos secundarios de la oferta, el bot genera un *pitch* directo de 3 líneas enfocado en el **60% que SÍ dominas a la perfección** (`React`, `Node.js`, `NestJS`, `TypeScript`, `PostgreSQL`) y tu capacidad de entrega rápida demostrable con tu portafolio en GitHub.

