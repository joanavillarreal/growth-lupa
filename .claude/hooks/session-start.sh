#!/bin/bash
# Arranque de sesión de Lupa: verifica el entorno y deja el repo en main al día.
# Lo que imprime queda en el contexto de la sesión.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

echo "== Arranque de Lupa =="

# 1. Python y dependencias
if ! command -v python3 >/dev/null; then
  echo "ERROR: falta python3"; exit 0
fi
python3 -c "import yaml, zoneinfo; zoneinfo.ZoneInfo('America/Argentina/Buenos_Aires')" 2>/dev/null \
  || pip install -q pyyaml tzdata 2>&1 | tail -1
[ -f requirements.txt ] && pip install -q -r requirements.txt 2>&1 | tail -1
python3 -c "import yaml" 2>/dev/null && echo "python: ok" || echo "ERROR: no se pudo instalar pyyaml"

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

# 3. Qué toca hoy
python3 que_toca_hoy.py || echo "ERROR: que_toca_hoy.py falló"
exit 0
