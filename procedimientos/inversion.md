# Análisis `inversion` — carga del gasto publicitario al SPA 1052 de Bitrix

Copiado de la rutina "Agente Growth · Carga de inversión al SPA" de `agente-growth` (módulos
`growth/inversion.py` y `growth/google_ads.py`, de la rama `claude/elegant-tesla-suja3c`).
Lunes y jueves. **Es la única escritura que Lupa hace en una plataforma**, autorizada por
Joana el 08/10/2026: crear registros de gasto en el SPA "Inversiones y Gastos". Nada más.

- Un registro por día y por canal (Meta Ads, Google Ads), en USD, cotización **1500**
  (`config/definitions.yaml` → `gasto.meta_api.cotizacion_ars_usd`).
- Sin confirmación previa. Deduplica por (fecha, canal), re-chequea antes de escribir, no carga
  días en $0 y nunca el día en curso. No crear ni borrar registros a mano por fuera del script,
  ni tocar los registros viejos con títulos tipo `Gasto Meta - ...`.
- Google Ads se lee de la API con las variables `GOOGLE_ADS_*` (verificado el 08/10/2026:
  coincide al centavo con lo cargado del 01/10 al 07/10). No hace falta archivo semanal.

## Pasos

1. `python3 run.py inversion rango`. Si `al_dia` es `true`, no hay nada que cargar: ir al 4.
2. Meta, **con su propia llamada** (no se reusa `data/meta_spend.json`: Meta corrige los días
   recientes y ese archivo puede diferir en centavos de lo que se cargaría hoy):
   `ads_get_ad_entities` con `ad_account_id: "725901852075382"`, `level: "ad_account"`,
   `time_increment: "1"`, `time_range: '{"since":"<desde>","until":"<hasta>"}'`,
   `fields: ["amount_spent"]`, `include_additional_context: false`. Guardar la respuesta tal
   cual en el scratchpad (`meta_inversion.json`). Si Meta no está, seguir sin `--meta`: Google
   se carga igual y Meta queda pendiente.
3. `python3 run.py inversion cargar --meta <scratchpad>/meta_inversion.json`. Si falla a mitad
   de camino se puede volver a correr una vez: lo creado se saltea.
4. Mandar a #adqui-notificaciones-canales (`C0C2XKTLT9N`) la tabla que imprime el script, tal cual (registros creados por día,
   canal, ARS, USD e ID; salteados; días sin gasto; pendientes y huecos). Si algo falló, decir
   exactamente qué días quedaron cargados y cuáles no.
5. `parte.py inversion ok|fallido` con el reporte en `--datos`.

**En modo oficial (desde el 09/10/2026) se carga de verdad**: la rutina vieja está pausada.
**En modo ensayo no se carga**: se corre con `--dry-run` y se
compara lo que se habría creado contra lo que la rutina vieja cargó (ver CLAUDE.md).
