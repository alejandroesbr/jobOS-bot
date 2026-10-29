# 02. Ciclo de Postulación, Re-Postulación y Registro Único (`times_applied`)

En la búsqueda de empleo real ocurren tres situaciones frecuentes con una misma vacante:
1. La empresa **republica la misma oferta** unos días después para volver a subirla al tope del portal.
2. La misma oferta aparece publicada simultáneamente en **dos o más portales** (por ejemplo, en LinkedIn y también en GetOnBrd o Computrabajo).
3. El bot vuelve a pasar por la oferta en un nuevo escaneo cuando la vacante sigue abierta.

---

## 1. Regla de Oro: Volver a Postularse, pero NUNCA Duplicar el Registro

La lógica de negocio de `jobOS-bot` ante una oferta repetida cumple dos mandatos simultáneos:

1. **Acción externa (Hacia la empresa):** **Sí vuelve a enviar la hoja de vida / postularse** (especialmente si aparece en otro portal o si fue republicada tras el periodo de enfriamiento configurado), porque postular por un canal adicional o quedar arriba en la bandeja de entrada del reclutador aumenta la probabilidad de que lean tu CV.
2. **Acción interna (En tu base de datos y Notion):** **Prohibido crear una fila nueva por la misma vacante.** En su lugar, se mantiene **un único registro maestro** y se incrementa el contador de envíos (`times_applied`), guardando el historial de cada envío.

---

## 2. Flujo de Decisión ante Vacantes Existentes

```mermaid
flowchart TD
    NewOffer["Scraper detecta vacante válida\n(Match >= 40%)"] --> GenKey["Genera dedup_key:\ncompany_norm::title_norm"]
    GenKey --> CheckDB{"¿Ya existe dedup_key\nen SQLite?"}

    CheckDB -->|No existe (Primera vez)| FirstApply["1. Envía CV y Postula\n2. INSERT en applications con:\n   times_applied = 1\n   first_applied_at = hoy\n   last_applied_at = hoy\n   submission_history = [envío_1]"]

    CheckDB -->|Sí existe| CheckRules{"¿Permite nueva postulación?\n(Otro portal o >= cooldown_days\ny estado != Entrevista/Rechazado)"}

    CheckRules -->|Sí permite| ReApply["1. Vuelve a enviar CV y Postular\n2. UPDATE del MISMO registro:\n   times_applied = times_applied + 1\n   last_applied_at = hoy\n   submission_history.append(envío_N)\n3. Actualiza contador en Notion"]

    CheckRules -->|No (Ya se envió hoy en ese\nmismo URL o ya estás en entrevista)| Skip["No duplica ni re-envía\n(Mantiene registro intacto)"]
```

---

## 3. Estructura del Registro Único en SQLite (`applications`)

Para soportar esta lógica sin duplicar filas, la tabla `applications` incluye campos específicos de conteo y trazabilidad:

| Columna | Tipo | Comportamiento en Primera Postulación | Comportamiento en Re-Postulación (`2da, 3ra... vez`) |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER PK` | Se asigna ID único (ej. `42`). | **Se conserva el mismo `id = 42`.** |
| `dedup_key` | `TEXT UNIQUE` | `acme::desarrollador full stack react node` | Se usa para detectar que es la misma vacante (`ON CONFLICT(dedup_key)`). |
| `times_applied` | `INTEGER` | Inicia en `1`. | **Se incrementa (`times_applied + 1` -> `2`, `3`, ...).** |
| `portals_seen` | `TEXT (JSON)` | `["linkedin"]` | Agrega el nuevo portal si aplica: `["linkedin", "getonbrd"]`. |
| `first_applied_at` | `TEXT (ISO)` | `2026-10-28T09:00:00` | **No se modifica** (recuerda cuándo empezó todo). |
| `last_applied_at` | `TEXT (ISO)` | `2026-10-28T09:00:00` | **Se actualiza** a la fecha y hora del último envío. |
| `submission_history` | `TEXT (JSON)` | `[{"attempt": 1, "date": "2026-10-28", "portal": "linkedin", "url": "..."}]` | Añade un objeto nuevo al arreglo JSON con la fecha, portal y URL del nuevo envío. |

---

## 4. Condiciones de Seguridad para Re-Postular (`reapply_policy`)

Para maximizar tus probabilidades sin que el portal marque tu cuenta como spam en el mismo minuto, `config/filters.yaml` define la política de re-postulación:

1. **Misma vacante en un portal DIFERENTE (Re-postulación inmediata):**
   * Si te postulaste hoy a *"Desarrollador Junior React"* de la empresa *X* en **LinkedIn**, y media hora después el scraper encuentra la misma oferta de la empresa *X* en **GetOnBrd** o **Computrabajo**:
   * **Se postula inmediatamente también en el segundo portal** (muchas veces el reclutador revisa más GetOnBrd que LinkedIn o viceversa) y actualiza el registro único a `times_applied = 2`.
2. **Misma vacante en el MISMO portal (Cooldown de republicación):**
   * Si la oferta sigue en el mismo portal, el bot vuelve a enviar el CV si han pasado al menos `reapply_cooldown_days` (por defecto **3 a 5 días**, o cuando el portal genera un `external_id`/URL nuevo por republicación) y aumenta `times_applied`.
3. **Excepción por Estado Avanzado:**
   * Si el registro único ya está en estado **`Entrevista Programada`** o **`Rechazado Definitivo`**, el bot no vuelve a enviar el CV aunque encuentre la oferta otra vez.

