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
  python3 -m pip install -q -r requirements.txt >/tmp/lupa-pip.log 2>&1 && break
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
#    - main local sin historia común con origin (la foto vieja del 13/10/2026): se reemplaza.
#    - main local con historia común y commits sin subir: no se pisa; se avisa y se pushea
#      primero. Si el push no entra (origin avanzó por otro lado), no se toca nada.
ARRANQUE_ESTADO="sin verificar (no es la nube)"
a_main() {
  if git checkout -q -B main origin/main; then
    ARRANQUE_ESTADO="= origin/main${1:-}"
  else
    ARRANQUE_ESTADO="NO es origin/main: falló git checkout -B main origin/main"
    echo "ERROR: falló git checkout -B main origin/main"
  fi
}
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    ARRANQUE_ESTADO="NO es origin/main: había cambios sin guardar y no toqué nada"
    echo "AVISO: hay cambios sin guardar; no toco el repo (rama $(git branch --show-current)):"
    git status --short | head -10
  else
    fetch_ok=""
    for i in 1 2 3 4; do git fetch -q origin main && { fetch_ok=1; break; }; sleep $((2 ** i)); done
    sin_subir=""
    if git rev-parse -q --verify refs/heads/main >/dev/null \
       && git merge-base main origin/main >/dev/null 2>&1; then
      sin_subir="$(git rev-list --count origin/main..main)"
      [ "$sin_subir" = "0" ] && sin_subir=""
    fi
    if [ -z "$fetch_ok" ]; then
      ARRANQUE_ESTADO="NO verificado: git fetch origin main falló 4 veces y no toqué nada"
      echo "AVISO: git fetch origin main falló 4 veces; no toco el repo"
    elif [ -n "$sin_subir" ]; then
      echo "AVISO: main local tiene $sin_subir commit(s) sin subir; no lo piso, lo pusheo primero:"
      git log --oneline origin/main..main | head -10
      push_ok=""
      for i in 1 2 3 4; do
        out="$(git push -q origin main:main 2>&1)" && { push_ok=1; break; }
        echo "$out" | grep -qiE "rejected|non-fast-forward|fetch first" && break   # no es la red
        sleep $((2 ** i))
      done
      if [ -n "$push_ok" ]; then
        git fetch -q origin main
        echo "push ok: $sin_subir commit(s) subidos a origin/main"
        a_main " (antes pushé $sin_subir commit(s) que estaban sin subir)"
      else
        ARRANQUE_ESTADO="NO es origin/main: main local tiene $sin_subir commit(s) sin subir y el push falló; no toqué nada"
        echo "ERROR: no pude pushear main (¿origin avanzó por otro lado?); no toco el repo:"
        echo "$out" | grep -v "^hint:" | head -3
      fi
    else
      a_main
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
