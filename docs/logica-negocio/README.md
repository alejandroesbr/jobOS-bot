# Documentación de Lógica de Negocio — `jobOS-bot`

Esta carpeta define las **reglas de negocio, fórmulas de decisión y comportamientos estratégicos** de `jobOS-bot`. Mientras que `docs/arquitectura/` explica *cómo está construido técnicamente el software*, esta sección define *qué decisiones toma el bot frente a cada oferta de trabajo*.

---

## Índice de Reglas de Negocio

1. [**01. Motor de Scoring (%) y Postulación Flexible (`01-motor-scoring-y-umbrales.md`)**](./01-motor-scoring-y-umbrales.md)
   * Fórmula exacta del porcentaje de compatibilidad (`Match %`), diferencia entre requisitos obligatorios (*Hard Filters*) y deseables (*Soft Skills*), y la regla de **postular aunque no se cumpla el 100% de los requisitos** (umbral desde `40%`).
2. [**02. Ciclo de Postulación, Re-Postulación y Contador Único (`02-ciclo-postulacion-y-repostulacion.md`)**](./02-ciclo-postulacion-y-repostulacion.md)
   * Qué hace el bot cuando vuelve a encontrar la misma oferta (republicada o en otro portal): **volver a enviar la hoja de vida sin duplicar el registro**, incrementando el contador `times_applied` y guardando la trazabilidad en `submission_history`.
3. [**03. Reglas de Respuesta en Formularios y Filtros ATS (`03-reglas-respuestas-y-formularios.md`)**](./03-reglas-respuestas-y-formularios.md)
   * Cómo responder estratégicamente preguntas de años de experiencia, tecnologías secundarias, expectativa salarial (COP vs. USD), inglés y ubicación para no ser descartado automáticamente por los filtros ATS.
4. [**04. Máquina de Estados, Follow-ups y Entrevistas (`04-estados-seguimiento-y-entrevistas.md`)**](./04-estados-seguimiento-y-entrevistas.md)
   * Ciclo de vida de una postulación desde que se detecta hasta la entrevista, reglas de cadencia para re-postular y recordatorios a los 7 y 14 días.
5. [**05. Estrategia de Hoja de Vida y Optimización ATS (`05-adaptacion-cv-y-estrategia-ats.md`)**](./05-adaptacion-cv-y-estrategia-ats.md)
   * Cómo elegir qué versión de CV enviar según el rango de `%` de la oferta y cómo cubrir brechas de requisitos sin inventar experiencia falsa.

