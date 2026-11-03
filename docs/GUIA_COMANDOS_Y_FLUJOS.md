# Guía Definitiva de Comandos y Flujo de Trabajo — jobOS-bot

> **Manual integral de operaciones, flujo end-to-end y referencia de comandos para el copiloto de búsqueda laboral y postulación asistida.**

---

## 1. Flujo General del Sistema (Ciclo de Vida de una Vacante)

El siguiente diagrama ilustra cómo fluye una vacante desde su descubrimiento en los portales hasta la preparación de tu entrevista técnica:

```mermaid
flowchart TD
    A["1. Autenticación Única\n(python cli.py auth)"] --> B["2. Escaneo Multi-Portal\n(python cli.py scan --portal all)"]
    
    B --> C{"Evaluación de Compatibilidad\n(src/domain/matcher.py)"}
    C -->|Título Senior / +5 años / Stack ajeno| D["Hard Reject (0%)\nDescarte inmediato sin abrir detalle"]
    C -->|Match < 40%| E["Descartada por baja afinidad\nNo se registra"]
    C -->|Match >= 40%| F["Registro en SQLite (data/jobs.db)\n(dedup_key único, times_applied=1)"]

    F --> G["3. Radar y Estadísticas\n(python cli.py stats)"]
    F --> H["4. Postulación Asistida\n(python cli.py assist <id1> [id2...])"]
    
    H --> I["Navegador Visible (Playwright)\nCarga sesión persistente"]
    I --> J["Detecta 'Solicitud sencilla'\nAbre modal automáticamente"]
    J --> K["Adjunta PDF de tu CV\n(config/CV_Ancizar_Escobar.pdf)"]
    K --> L["Autocompleta Formulario\nVerde: Memoria local (RapidFuzz >= 85%)\nAmarillo: Sugerencia Gemini"]
    L --> M["Avance de Pasos\n(Contacto -> CV -> Preguntas -> Revisión)"]
    M --> N["Envío\n- Manual: Clic final del usuario\n- Automático: Flag --auto-submit"]
    N --> O["Actualiza estado a 'Enviado' en SQLite"]

    O --> P["5. Sincronización en la Nube\n(python cli.py sync)"]
    P --> Q["Dashboard en Notion (Web / Celular)"]
    Q -->|Cambias estado a 'Entrevista'| R["6. Guía Técnica Automatizada\n(python cli.py prep <job_id>)"]
    R --> S["interviews/<empresa>.md\n(Preguntas, Live Coding, Dudas para reclutador)"]
```

---

## 2. Catálogo Completo de Comandos CLI (`cli.py`)

### 1. `python cli.py auth` — Gestor de Autenticación de Portales
Abre el navegador Chromium en modo visible utilizando tu perfil persistente en disco (`data/browser_profile/`).

* **¿Para qué sirve?:** Permite que inicies sesión manualmente en tus cuentas (LinkedIn, GetOnBrd, Computrabajo, Elempleo, Indeed, Glassdoor) una sola vez. Guarda las cookies en `data/storage_state.json` para que el bot nunca vuelva a pedirte login ni bloquee tus postulaciones.
* **Uso:**
  ```bash
  python cli.py auth
  ```
* **Opciones:**
  * `--output <ruta>`: Ruta personalizada del JSON de cookies (por defecto: `data/storage_state.json`).
* **Regla de oro:** Inicia sesión en tus portales en la ventana del navegador. **No cierres la ventana manualmente antes de presionar ENTER** en la terminal para que Playwright pueda volcar el archivo JSON sin interrumpir la conexión.

---

### 2. `python cli.py scan` — Motor de Escaneo Multi-Portal
Escanea de forma secuencial en un solo hilo (*single-thread*) los portales de empleo configurados, respetando pausas humanas aleatorias (2.5s a 6.0s) para evitar bloqueos anti-bot.

* **¿Para qué sirve?:** Descubre ofertas de trabajo, extrae la información limpia, evalúa las reglas de descarte (*Hard Rejects*) y el puntaje de afinidad (`Match %`), y realiza un `UPSERT` en SQLite. Si una oferta ya existía (republicada o en otro portal), incrementa `times_applied = times_applied + 1` sin duplicar la fila.
* **Ejemplos de ejecución:**
  ```bash
  # Escanear todos los portales habilitados (por defecto 10 vacantes por portal en segundo plano)
  python cli.py scan --portal all

  # Escanear portales específicos
  python cli.py scan --portal linkedin,getonbrd

  # Limitar el escaneo a 5 vacantes por portal
  python cli.py scan --portal getonbrd --limit 5

  # Ver la ventana del navegador mientras escanea (ideal para verificar en vivo)
  python cli.py scan --portal getonbrd --limit 3 --no-headless
  ```
* **Opciones:**
  * `--portal`: Portales a incluir: `linkedin`, `getonbrd`, `computrabajo`, `elempleo`, `glassdoor`, `indeed` o `all` (separados por coma).
  * `--limit`: Límite máximo de ofertas a inspeccionar por portal (default: 10).
  * `--headless / --no-headless`: Modo invisible (headless) o visible en tu pantalla (default: `--headless`).

---

### 3. `python cli.py assist` — Copiloto de Postulación en Lote
Abre la vacante en el navegador con tu sesión persistente, detecta si tiene botón de *"Solicitud sencilla / Easy Apply / Postularme"*, autocompleta el formulario paso a paso, adjunta tu CV en PDF y actualiza el estado a `Enviado`.

* **Modos de uso:**

  #### A. Por ID específico (una o varias vacantes en una sola línea)
  ```bash
  # Asistir la vacante #4
  python cli.py assist 4

  # Encolar y postular a múltiples vacantes en orden secuencial
  python cli.py assist 1 3 4 8
  python cli.py assist 1,3,4,8
  ```

  #### B. Modo 100% Automático / Desatendido (`--all` y `--auto-submit`)
  Si no quieres tocar el ratón, ni ingresar IDs, ni dar clic en *"Enviar solicitud"*, procesa toda la cola con:
  ```bash
  # Postular a TODAS las vacantes pendientes en cola sin confirmación manual
  python cli.py assist --all --auto-submit

  # Postular solo a vacantes con afinidad alta (ej. Match >= 70%)
  python cli.py assist --all --min-score 70 --auto-submit

  # Ejecutar en segundo plano sin abrir ventanas gráficas
  python cli.py assist --all --auto-submit --headless
  ```

  #### C. Cola por Afinidad Prioritaria (`--min-score` y `--top`)
  ```bash
  # Abre automáticamente en cola las mejores 5 ofertas pendientes con Match >= 70%
  python cli.py assist --min-score 70 --top 5 --auto-submit
  ```

  #### D. Modo Interactivo (sin argumentos)
  ```bash
  python cli.py assist
  ```
  Imprime una tabla Rich con las vacantes en estado `Pendiente` ordenadas por afinidad y te pregunta qué IDs deseas procesar.

---

### 4. `python cli.py autopilot` — Piloto Automático Autónomo End-to-End
Ejecuta el ciclo de vida completo de jobOS-bot de forma **100% desatendida y sin intervención humana**:
1. **Escaneo:** Busca ofertas recientes en todos los portales configurados.
2. **Evaluación:** Filtra descartes duros y calcula el puntaje de afinidad con tu perfil.
3. **Postulación Asistida:** Abre Playwright, adjunta tu CV, responde preguntas y realiza el envío seguro (`--auto-submit`) de cada vacante que califique.
4. **Sincronización:** Actualiza SQLite, empuja los nuevos envíos a Notion CRM y detecta vacantes estancadas tras 7 días.

* **Ejemplos de uso:**
  ```bash
  # Ejecución autónoma completa estándar (Match >= 50%)
  python cli.py autopilot

  # Exigir mayor afinidad (ej. solo vacantes con Match >= 65%)
  python cli.py autopilot --min-score 65

  # Ejecutar en segundo plano silencioso (ideal para cron o servidores)
  python cli.py autopilot --headless

  # Escanear portales específicos y limitar a 20 ofertas por portal
  python cli.py autopilot --portal linkedin,getonbrd --limit 20
  ```

---

### 5. `python cli.py stats` — Radar de Mercado y Pipeline
Genera dos paneles analíticos con la información real almacenada en SQLite:

1. **Pipeline de Postulaciones:** Total de vacantes por estado (`Pendiente`, `Enviado`, `Requiere Seguimiento`, `Entrevista Programada`, etc.) y contador de re-postulaciones históricas.
2. **Radar de Tecnologías:** Ranking de los lenguajes, frameworks y bases de datos más solicitados en las ofertas reales, contrastados con tu porcentaje de cobertura personal.

* **Uso:**
  ```bash
  python cli.py stats
  ```

---

### 6. `python cli.py tailor <job_id>` — Optimización Quirúrgica de CV (Gemini)
Compara la descripción de la vacante seleccionada contra tu plantilla base en Markdown ([`config/cv_base.md`](../config/cv_base.md)).

* **¿Para qué sirve?:** Identifica la **Brecha ATS** (conceptos clave que pide la oferta y que no están explícitos en tu CV) y redacta de 2 a 3 viñetas (*bullets*) listas para copiar en tu perfil o carta de presentación, adaptadas a esa empresa sin inventar experiencia falsa.
* **Ejemplo:**
  ```bash
  python cli.py tailor 4
  ```

---

### 7. `python cli.py prep <job_id>` — Generador de Guía de Entrevista Técnica
Genera un documento Markdown completo en `interviews/<empresa>.md` para preparar tu entrevista con éxito.

* **Contenido generado:**
  1. Resumen técnico del cargo y mapa de temas críticos.
  2. 5 preguntas técnicas nivel Junior/Mid con respuestas guía fundamentadas en tu stack real.
  3. Reto de Live Coding con enunciado y solución comentada en código.
  4. 3 preguntas inteligentes de ingeniería para hacerle al entrevistador.
* **Ejemplo:**
  ```bash
  python cli.py prep 4
  ```

---

### 8. `python cli.py sync` — Sincronizador con Notion y Detección de Follow-ups
Mantiene tu base de datos local SQLite sincronizada con tu dashboard privado de Notion.

* **¿Qué ejecuta?:**
  * **Push:** Sube vacantes nuevas detectadas por el escáner a Notion con tags de colores, Match %, salario y enlace directo.
  * **Pull:** Si desde la app móvil de Notion cambiaste una vacante a *"Entrevista Programada"*, el bot lo detecta y genera automáticamente la guía técnica con `prep`.
  * **Follow-ups:** Si una postulación lleva más de 7 días sin respuesta de la empresa, la cambia a estado *"Requiere Seguimiento"*.
  * **Bootstrap:** Si descargas el proyecto en otro computador sin base de datos, reconstruye tu SQLite automáticamente desde Notion.
* **Ejemplo:**
  ```bash
  python cli.py sync
  ```

---

### 9. `python cli.py export` — Exportación de Datos
Vuelca los registros de SQLite a formatos estándar para análisis en hojas de cálculo o respaldo.

* **Ejemplos:**
  ```bash
  # Exportar a CSV (abre directamente en Excel / Google Sheets)
  python cli.py export --format csv

  # Exportar a JSON
  python cli.py export --format json

  # Exportar únicamente las vacantes enviadas
  python cli.py export --format csv --status "Enviado" --output exports/mis_postulaciones.csv
  ```

---

## 3. Automatización 100% Desatendida (Sin Intervención Humana)

Si deseas que el bot busque vacantes nuevas, complete los formularios, adjunte tu CV y envíe las postulaciones todos los días sin que tengas que abrir una terminal ni hacer un solo clic:

### Opción A: Script Autopilot bajo demanda
Ejecuta el script unificado [`scripts/autopilot.sh`](../scripts/autopilot.sh) en cualquier momento:
```bash
./scripts/autopilot.sh
```
O con opciones avanzadas (segundo plano silencioso y afinidad estricta):
```bash
./scripts/autopilot.sh --headless --min-score 60
```

### Opción B: Cronjob Diario en Linux Debian (Recomendado)
Configura una tarea programada para que se ejecute de lunes a viernes en los horarios con más ofertas laborales nuevas (ej. 9:00 AM y 2:00 PM):

1. Abre el editor de tareas programadas del sistema:
   ```bash
   crontab -e
   ```
2. Agrega la siguiente línea al final del archivo:
   ```cron
   0 9,14 * * 1-5 /home/alejandro/Developer/jobOS-bot/scripts/autopilot.sh --headless >> /home/alejandro/Developer/jobOS-bot/data/autopilot.log 2>&1
   ```
3. Guarda y sal. El bot trabajará por ti en segundo plano y registrará todo el progreso en `data/autopilot.log`.

---

## 4. Matriz de Estados de una Aplicación (`ApplicationStatus`)

Toda vacante transita por los siguientes estados dentro de SQLite y Notion:

| Estado | Significado | ¿Permite Re-postulación? |
| :--- | :--- | :---: |
| **`Pendiente`** | Vacante escaneada con Match $\ge 40\%$, pendiente por asistir. | Sí |
| **`Enviado`** | Formulario completado y enviado exitosamente. | Sí (tras 3 días de cooldown o en otro portal) |
| **`Requiere Seguimiento`** | Postulación enviada hace más de 7 días sin respuesta de la empresa. | Sí |
| **`Entrevista Programada`** | La empresa te contactó y estás en proceso de entrevistas. | **No (Congelado)** |
| **`Oferta Recibida`** | Propuesta formal recibida. | **No (Congelado)** |
| **`Rechazado`** | Proceso concluido por decisión de la empresa. | **No (Congelado)** |
| **`Descartado`** | Descartado manualmente por ti. | **No (Congelado)** |

---

## 5. Servidor MCP (`Model Context Protocol`)

`jobOS-bot` incluye un servidor nativo MCP via `stdio` que permite interactuar con tu pipeline mediante lenguaje natural desde Claude Desktop, Antigravity o Cursor.

* **Iniciar el servidor directamente:**
  ```bash
  python -m src.adapters.mcp.server
  ```
* **Herramientas disponibles para el agente:**
  1. `get_pipeline_overview`: Resumen global de postulaciones por estado.
  2. `search_applications`: Búsqueda de vacantes por empresa, cargo o tecnología.
  3. `get_market_stack_radar`: Estadísticas de las tecnologías más demandadas.
  4. `prepare_job_application_kit`: Dispara CV Tailor y Guía de Entrevista en un solo llamado.
  5. `sync_pipeline_with_notion`: Sincronización bajo demanda con Notion.

---

## 6. Preguntas Frecuentes y Solución de Problemas (FAQ)

### ¿Por qué `python cli.py auth` me dio error de `TargetClosedError`?
Ocurre cuando cierras la ventana del navegador con el mouse antes de presionar `ENTER` en la terminal. El navegador debe permanecer abierto mientras el bot ejecuta `storage_state()` para volcar las cookies a disco. En las últimas versiones, el sistema captura este evento y conserva las cookies directamente en `data/browser_profile/`.

### ¿Por qué Gemini mostró un aviso de `503 UNAVAILABLE`?
Los servidores gratuitos de Google AI Studio experimentan picos de saturación esporádicos. El cliente de IA cuenta con una lista de modelos de respaldo (`gemini-3.8-flash` $\rightarrow$ `gemini-2.0-flash` $\rightarrow$ `gemini-1.5-flash`) y degradación elegante a valores por defecto seguros para que tu postulación nunca se detenga.

### ¿Dónde configuro mis datos personales y CV?
- **Perfil ATS:** Edita [`config/profile.yaml`](../config/profile.yaml) (nombre, teléfono, ciudad, salario, años de experiencia).
- **Filtros de Búsqueda:** Edita [`config/filters.yaml`](../config/filters.yaml) (tecnologías core, whitelists, títulos buscados).
- **CV en PDF:** Coloca tu archivo en [`config/CV_Ancizar_Escobar.pdf`](../config/CV_Ancizar_Escobar.pdf) para que el bot lo adjunte automáticamente.

