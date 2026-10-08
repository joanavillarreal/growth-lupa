# Meta · Panel Meta Ads

Copiado de `agente-meta-ads` (commit f36b3b7, 08/10/2026). **Solo la lectura y el panel**:
lo que propone o ejecuta cambios en la cuenta es de Turbo y no está acá.

- `scripts/panel_meta.py` arma `informes/panel/datos.json` y lo reinyecta en
  `informes/panel-trimestral.html` (link oficial en `paneles.yaml`). Importa sus definiciones
  de `analizar_crm.py`, `analizar_meta.py` y `meta_desde_mcp.py`: no se reimplementan.
- `scripts/traer_prospectos.py` trae el CRM del trimestre con `BITRIX_WEBHOOK_URL`.
- `datos/meta-ads/` son las respuestas crudas del MCP de Meta (guardia diaria y CSV históricos);
  `datos/crm/` los prospectos. Las dos carpetas son el histórico: no se borran.
- `memoria/` tiene las entradas del panel, todas propias (desde el 08/10/2026 no se lee nada de
  `agente-meta-ads`): `cambios-actividad.jsonl` (registro de actividad de Meta,
  `scripts/cambios_desde_actividad.py`), `guardia.jsonl` (las alertas de mi guardia) y
  `experimentos-monitor.jsonl` (la solapa Experimentos del Monitor,
  `scripts/experimentos_desde_monitor.py`). Lo que escribía `agente-meta-ads` quedó en
  `memoria/archivo/` y no se lee.
- `config/` campañas, taxonomía de leads y cuenta.

Detalle del panel: `referencias/panel.md` (copiado).
