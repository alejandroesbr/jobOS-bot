#!/usr/bin/env bash
# ==============================================================================
# jobOS-bot — Autopilot Runner (escaneo desatendido, nunca postula)
# ==============================================================================
# Este script ejecuta sin intervención manual:
#   1. Escanea portales de empleo (LinkedIn, GetOnBrd, Computrabajo, ...)
#   2. Evalúa la afinidad contra tu perfil y registra las compatibles como 'Pendiente'
#   3. Sincroniza con Notion y detecta follow-ups a 7 días
# Las postulaciones se envían siempre a mano con `python cli.py assist`.
#
# Uso manual:
#   ./scripts/autopilot.sh
#   ./scripts/autopilot.sh --headless --limit 20
#
# Para automatizar con cron (ejecutar diario a las 9:00 AM y 2:00 PM):
#   crontab -e
#   0 9,14 * * 1-5 /ruta/a/jobOS-bot/scripts/autopilot.sh --headless >> /ruta/a/jobOS-bot/data/autopilot.log 2>&1
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

# Activar entorno virtual
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Error: No se encontró el entorno virtual (.venv o venv)."
    exit 1
fi

mkdir -p data exports

echo "=================================================================="
echo "🚀 [$(date '+%Y-%m-%d %H:%M:%S')] Iniciando jobOS-bot Autopilot..."
echo "=================================================================="

# Ejecutar el comando autopilot pasando cualquier parámetro adicional
python cli.py autopilot "$@"

EXIT_CODE=$?
echo "=================================================================="
echo "🏁 [$(date '+%Y-%m-%d %H:%M:%S')] Fin de ejecución (Código: ${EXIT_CODE})"
echo "=================================================================="

exit ${EXIT_CODE}

