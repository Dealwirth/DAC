#!/command/with-contenv bash
set -euo pipefail

echo "[DAC] Starte Dynamic Alarm Clock..."

export DAC_DATA="${DAC_DATA:-/data}"
export DAC_HOST="${DAC_HOST:-0.0.0.0}"
export DAC_PORT="${DAC_PORT:-8099}"

mkdir -p "${DAC_DATA}"

cd /app
exec python -m uvicorn app.main:app \
  --host "${DAC_HOST}" \
  --port "${DAC_PORT}" \
  --proxy-headers \
  --no-server-header \
  --timeout-keep-alive 75 \
  --log-level info
