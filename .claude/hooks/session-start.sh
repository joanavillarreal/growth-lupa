#!/bin/bash
# Arranque de sesión de Lupa: verifica el entorno y deja el repo idéntico a origin/main.
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

# 2. Repo idéntico a origin/main (solo en la nube). Con cambios sin guardar no se toca nada.
#    checkout -B y no pull: un main local viejo o sin historia común (pasó el 13/10/2026) se
#    descarta en vez de dejar la sesión trabada en él.
ARRANQUE_ESTADO="sin verificar (no es la nube)"
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    ARRANQUE_ESTADO="NO es origin/main: había cambios sin guardar y no toqué nada"
    echo "AVISO: hay cambios sin guardar; no toco el repo (rama $(git branch --show-current)):"
    git status --short | head -10
  else
    fetch_ok=""
    for i in 1 2 3 4; do git fetch -q origin main && { fetch_ok=1; break; }; sleep $((2 ** i)); done
    if [ -z "$fetch_ok" ]; then
      ARRANQUE_ESTADO="NO verificado: git fetch origin main falló 4 veces y no toqué nada"
      echo "AVISO: git fetch origin main falló 4 veces; no toco el repo"
    elif git checkout -q -B main origin/main; then
      ARRANQUE_ESTADO="= origin/main"
    else
      ARRANQUE_ESTADO="NO es origin/main: falló git checkout -B main origin/main"
      echo "ERROR: falló git checkout -B main origin/main"
    fi
  fi
fi
ARRANQUE_COMMIT="$(git log -1 --format='%h')"
echo "rama: $(git branch --show-current) @ $(git log -1 --format='%h %s')"
echo "ARRANQUE: $ARRANQUE_COMMIT ($ARRANQUE_ESTADO)"
# Queda guardado fuera del árbol (en .git) para el mensaje de cierre, aunque se pierda el contexto.
echo "$ARRANQUE_COMMIT ($ARRANQUE_ESTADO)" > "$(git rev-parse --git-dir)/lupa-arranque"

# Modo leído de paneles.yaml (la clave real, no los comentarios): decide si se publica y a dónde va Slack
python3 -c "import yaml; print('modo:', yaml.safe_load(open('paneles.yaml'))['modo'])" 2>/dev/null \
  || echo "ERROR: no se pudo leer el modo de paneles.yaml"

# 3. Qué toca hoy
python3 que_toca_hoy.py || echo "ERROR: que_toca_hoy.py falló"
exit 0
