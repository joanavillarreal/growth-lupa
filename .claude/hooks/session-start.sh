#!/bin/bash
# Arranque de sesión de Lupa: verifica el entorno y deja el repo en main al día.
# Lo que imprime queda en el contexto de la sesión.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

echo "== Arranque de Lupa =="

# 1. Python y dependencias: todas desde requirements.txt, acá y no en medio de la corrida
if ! command -v python3 >/dev/null; then
  echo "ERROR: falta python3"; exit 0
fi
for i in 1 2 3; do
  pip install -q -r requirements.txt >/tmp/lupa-pip.log 2>&1 && break
  sleep $((2 ** i))
done
python3 -c "import yaml, requests, zoneinfo; zoneinfo.ZoneInfo('America/Argentina/Buenos_Aires')" 2>/dev/null \
  && echo "python: ok (requirements.txt instalado)" \
  || { echo "ERROR: no se pudo instalar requirements.txt:"; tail -3 /tmp/lupa-pip.log; }

# Variables de entorno (solo si existen; nunca su valor)
[ -n "${BITRIX_WEBHOOK_URL:-}" ] && echo "BITRIX_WEBHOOK_URL: definida" \
  || echo "ERROR: falta BITRIX_WEBHOOK_URL (funnel, meta e inversion no pueden leer Bitrix)"
for v in GOOGLE_ADS_CLIENT_ID GOOGLE_ADS_CLIENT_SECRET GOOGLE_ADS_REFRESH_TOKEN GOOGLE_ADS_CUSTOMER_ID GOOGLE_ADS_LOGIN_CUSTOMER_ID; do
  [ -n "${!v:-}" ] || echo "ERROR: falta $v (inversion no puede leer Google Ads)"
done

# 2. Repo en main y al día (solo en la nube y con el árbol limpio)
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "AVISO: hay cambios sin commitear; no cambio de rama ($(git branch --show-current))"
  else
    for i in 1 2 3 4; do git fetch -q origin main && break; sleep $((2 ** i)); done
    git checkout -q main 2>/dev/null || git checkout -q -b main origin/main
    git pull -q --ff-only origin main || echo "AVISO: no pude actualizar main"
  fi
fi
echo "rama: $(git branch --show-current) @ $(git log -1 --format='%h %s')"

# Modo leído de paneles.yaml (la clave real, no los comentarios): decide si se publica y a dónde va Slack
python3 -c "import yaml; print('modo:', yaml.safe_load(open('paneles.yaml'))['modo'])" 2>/dev/null \
  || echo "ERROR: no se pudo leer el modo de paneles.yaml"

# 3. Qué toca hoy
python3 que_toca_hoy.py || echo "ERROR: que_toca_hoy.py falló"
exit 0
