# 03. Reglas de Respuesta en Formularios y Filtros ATS

Cuando el bot rellena un formulario de postulación (en postulaciones de un clic o formularios multi-paso), las respuestas numéricas o de selección cerradas pasan por filtros automáticos (**ATS Knock-out Questions**). Una mala respuesta descarta el CV antes de que un humano lo abra.

Este documento establece las reglas de negocio que siguen `qa_memory` y el fallback de `gemini-2.5-flash` al responder formularios.

---

## 1. Reglas para Preguntas de "Años de Experiencia"

Cuando te postulas a una oferta en el rango de **`40% – 69%` de Match**, es común que el formulario pregunte por años de experiencia en todas las tecnologías del anuncio, incluyendo alguna que no es tu fuerte principal.

| Tipo de Tecnología Preguntada | Regla de Negocio para Responder |
| :--- | :--- |
| **Tu Core Stack (`React`, `Node.js`, `NestJS`, `TypeScript`, `JavaScript`, `PostgreSQL`, `SQL`, `Git`)** | Responder con el valor exacto configurado en tu `config/profile.yaml` (incluyendo experiencia de proyectos reales, prácticas y portafolio técnico, nunca `0`). |
| **Tecnologías Equivalentes o Cercanas (`Next.js`, `Express`, `Prisma`, `TypeORM`, `Docker`, `REST API`, `Tailwind`)** | Usar el valor de experiencia práctica/proyectos configurada en `profile.yaml` (mínimo `1` año si ya has construido proyectos con ellas). |
| **Tecnologías Complementarias donde tienes nociones básicas (`AWS`, `Redis`, `GraphQL`, `CI/CD`)** | Si el campo es de texto libre, explicar brevemente el uso en proyectos/despliegues; si es numérico estricto, usar el piso configurado en `profile.yaml` para evitar el descarte automático por `0` cuando has tenido exposición académica/proyectos. |

---

## 2. Reglas de Expectativa Salarial (Moneda y Rango)

Uno de los errores más graves en bots de postulación es escribir un salario en **Pesos Colombianos (COP)** dentro de un campo que esperaba **Dólares (USD)**, o viceversa.

1. **Detección de Moneda por Contexto:**
   * Si la etiqueta de la pregunta o el portal indica `USD`, `US$`, `Dollars`, `Remote Latam (GetOnBrd)` -> Usa `salary_expectation_usd_monthly` de tu `profile.yaml` (ej. `1200` – `1800`).
   * Si el portal es colombiano (`Computrabajo`, `Elempleo`) o la pregunta menciona `COP`, `Pesos`, `Millones`, `Colombia` -> Usa `salary_expectation_cop_monthly` (ej. `3500000` – `4500000`).
2. **Formato Limpio para Inputs Numéricos:**
   * Si el `<input type="number">` solo acepta dígitos, enviar el número entero sin puntos, comas ni símbolos de moneda (`3800000` en vez de `$3.800.000 COP`).
   * Si el input es de texto libre (`<input type="text">`), enviar el rango o indicar que es negociable según beneficios.

---

## 3. Reglas de Ubicación, Modalidad y Disponibilidad

* **¿Resides en Barranquilla / Colombia?:** Siempre **`Sí`**.
* **¿Cuentas con permiso legal para trabajar en Colombia?:** Siempre **`Sí`** (ciudadano colombiano, sin necesidad de patrocinio de visa local).
* **¿Requiere patrocinio de visa (Visa Sponsorship) para trabajar remoto desde Latam?:** Siempre **`No`** (para contratos como *Contractor* / prestación de servicios desde Colombia no se requiere visa estadounidense ni europea).
* **¿Disponibilidad para trabajar Remoto / Híbrido en Barranquilla?:** Siempre **`Sí`**.
* **¿Disponibilidad de incorporación (Notice Period)?:** **`Inmediata`** (o los días configurados en `profile.yaml`, ej. `Inmediata / 1 semana`).

---

## 4. Aprendizaje Continuo de Respuestas (`qa_memory`)

1. Cada vez que aparece una pregunta nueva (similitud `< 85%` en `RapidFuzz`), Gemini genera la respuesta siguiendo estrictamente las reglas de las secciones 1, 2 y 3.
2. Si tú corriges o ajustas manualmente esa respuesta antes de enviar, **tu respuesta editada tiene prioridad absoluta** y se guarda en `qa_memory` con `source = 'user_confirmed'`.
3. En la siguiente postulación que haga la misma pregunta, el bot usará tu respuesta confirmada en `< 0.5 ms` sin volver a consultar a Gemini.

