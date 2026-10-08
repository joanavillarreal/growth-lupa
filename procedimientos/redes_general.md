# Análisis `redes_general` — las cuentas al día de hoy (todos los días)

Los números generales del Panel de redes: seguidores, alcance y % de engagement de Boxer Gestión
y Boxer Taller, más los leads de redes del trimestre. Corre todos los días, en la misma corrida
que el funnel y Meta. Solo medición.

1. **Metricool**, por marca, **los 30 días que terminan ayer** (`<ayer-29>T00:00:00-03:00` a
   `<ayer>T23:59:59-03:00`). Nunca el día de hoy, que no cerró. Una dimensión por llamada y la
   fecha primero:

   | Bloque | Campos |
   |---|---|
   | `ig_evolucion` | `IGEV01, IGEV37, IGEV16, IGEV05, IGEV06, IGEV11` (+ `"_fecha"` al final de `fields`) |
   | `ig_por_tipo` | `IGAC01, IGAC02, IGAC05, IGAC06, IGAC11` |
   | `fb_evolucion` | `FBEV17, FBEV33, FBEV34, FBEV49, FBEV21, FBEV22` (+ `"_fecha"`) |
   | `li_evolucion` | `LIEV01, LIEV27, LIEV22, LIEV28, LIEV21, LIEV23, LIEV20, LIEV24` (+ `"_fecha"`), solo Gestión |

   Guardar tal cual en `redes/general/raw/<hoy>/<marca>.json`
   (`{"marca","desde","hasta","bloques":{...}}`, mismo formato que el crudo semanal).
2. `python3 redes/scripts/general.py` → `redes/general/<hoy>.json`: últimos 7 días contra los 7
   anteriores y la serie diaria de 30 días. Usa las funciones de `analizar.py`: los números dan
   igual que el análisis semanal sobre la misma ventana (verificado el 08/10/2026 con W39 y W40).
3. Los leads del trimestre salen del snapshot del funnel del día (el funnel corre antes):
   `panel_redes.py` los lee solo.
4. `python3 redes/scripts/panel_redes.py`, leer el link del Panel de redes y republicar
   `redes/panel/index.html` en ese mismo link (se publica también en ensayo).
5. `parte.py redes_general ok` con seguidores, alcance y engagement de cada marca y los leads del
   Q; commit de `redes/general/` y del panel; push.

Si Metricool no carga después de los reintentos: `redes_general` se registra como fallido y el
panel se republica igual (los leads del trimestre sí están al día) con el aviso "Números de las
cuentas sin actualizar desde <fecha>", que `panel_redes.py` pone solo cuando el último
`redes/general/<fecha>.json` no es de hoy. El mensaje de Slack dice lo mismo. Nunca se muestran
números viejos como si fueran de hoy.
