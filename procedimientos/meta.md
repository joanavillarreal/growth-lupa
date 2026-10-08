# Análisis `meta` — guardia diaria y Panel Meta Ads

Copiado de la rutina "Agente Meta - Guardia diaria" de `agente-meta-ads` (pasos 1 a 6) y de
`meta/referencias/panel.md`. Desde el 08/10/2026 no lee nada de ese repo. Todo se corre desde `meta/` (`cd meta`). **Solo lectura**: no se
escribe en Meta ni en Bitrix; lo que propone o ejecuta cambios es de Turbo.

Cuenta **`725901852075382`** (ARS; hay otra casi igual en USD: usar siempre el ID). Un
`client_conversation_id` nuevo, el mismo en todas las llamadas. `<hoy>` es la fecha de Argentina.

## 0. Cambios en la cuenta y experimentos (todo propio: no se lee el repo de ningún agente)

- **Cambios:** `ads_account_get_activity_logs`, cuenta `725901852075382`, desde el día anterior
  al último cambio de `meta/memoria/cambios-actividad.jsonl` (o 3 días atrás) hasta ahora,
  `limit: 1000`. La respuesta suele ser grande: el entorno la guarda en un archivo; copiarla tal
  cual a `datos/meta-ads/actividad/<hoy>.json` y correr
  `python3 scripts/cambios_desde_actividad.py datos/meta-ads/actividad/<hoy>.json`. Acumula sin
  duplicar. Dice qué cambió, quién y cuándo; el porqué es de Turbo.
- **Experimentos:** `python3 scripts/experimentos_desde_monitor.py` (desde la raíz del repo; lee
  `experiments/EXP-*.md`, los de la solapa Experimentos del Monitor).
- **Alertas:** las de la guardia propia (`memoria/guardia.jsonl`). Las del análisis semanal son
  de Turbo: cuando exista, llegan por su parte.
- Antes de reportar una entrega rota, mirar en `memoria/cambios-actividad.jsonl` si el objeto se
  creó o se pausó hace poco: un conjunto recién creado y sin activar da la misma señal que uno roto.

Si el registro de actividad no se puede leer, el panel muestra los cambios hasta el último día
que se trajeron y el parte lo dice ("cambios en la cuenta sin actualizar desde <fecha>").

## 1. Datos de Meta → `datos/meta-ads/guardia/<hoy>/mcp/`

Las llamadas exactas (campos, filtros, ventanas) están en `meta/referencias/guardia-diaria.md`,
tabla de llamadas #1 a #11. No improvisar parámetros. Cada respuesta se guarda **tal cual**.

| # | Archivo | Para |
|---|---|---|
| 1-4 | `anuncio-diario`, `anuncio-total`, `campana-diario`, `campana-total` (14 días hasta ayer) | guardia y panel |
| 5 | `roster.json` (tres llamadas: campaign, adset, ad) | guardia y #10 |
| 6 | `errores.json` (`ads_get_errors`) | guardia |
| 7 | `conjunto-diario.json` | panel |
| 8-10 | `anuncio-activos`, `conjunto-publicos`, `anuncio-historico` | panel |
| 11 | `creativos.json` (`ads_get_creatives`), solo los `creative_id` que no estén ya en ningún `creativos*.json` | panel |

Si Meta no contesta: reintentar; si sigue, `ads_get_ad_accounts` para ver `is_ads_mcp_enabled`.
Si no se puede leer, el análisis falla y **se avisa que la guardia está ciega**: un silencio por
falta de datos se lee como "todo bien".

## 2. Re-ingresos de Slack → `datos/meta-ads/guardia/<hoy>/slack/avisos-slack.json`

Leer `#adqui-automatizaciones` (`C0BRW04QSUF`), últimos 7 días hasta ayer, y contar los mensajes
del bot Botrix que empiezan con `*RE-INGRESO DE LEAD EXISTENTE*` o `*RECONTACTO DE LEAD
EXISTENTE*`, por día en hora argentina:
`{"desde": "AAAA-MM-DD", "hasta": "AAAA-MM-DD", "por_dia": {"AAAA-MM-DD": 1}}`.
Si no se puede leer, seguir: G5 corre con dos patas y lo dice.

## 2b. Campañas nuevas → `config/campanas.json`

```bash
python3 scripts/campanas_nuevas.py datos/meta-ads/guardia/<hoy>/ --json datos/meta-ads/guardia/<hoy>/campanas.json
```

El mapa campaña → origen del CRM lo mantengo yo (Joana, 08/10/2026). Cada campaña que está en
Meta (roster o gasto de 14 días) y no en el mapa se suma con `a_confirmar: true`,
`origenes_crm: "PENDIENTE"` y el bloque sugerido por el nombre. **No invento el producto ni el
origen**: las que siguen `a_confirmar` van al mensaje del día ("Campañas a confirmar: …"), todos
los días, hasta que Joana conteste. Cuando contesta, cargo `origenes_crm`, `producto`,
`destino` (y `fecha_evento` si es un evento) y borro `a_confirmar`. Cuando exista Turbo, las
campañas nuevas me llegan por su parte, ya con su origen.

## 3. Guardia

```bash
python3 scripts/guardia_diaria.py datos/meta-ads/guardia/<hoy>/ --json informes/guardia/<hoy>.json
```

Imprime `SIN NOVEDADES` o un bloque `MENSAJE DE SLACK` ya redactado. El bloque se manda **tal
cual**, sin reescribirlo (ver "Slack" en CLAUDE.md para el destino según el modo). Las reglas
G0-G5 y lo que la guardia no puede afirmar están en `meta/referencias/guardia-diaria.md`.

## 4. Panel

```bash
python3 scripts/traer_prospectos.py datos/crm/panel/prospectos-q.csv --desde <1er día del Q> --hasta <ayer>
python3 scripts/panel_meta.py
```

Reinyecta los datos en `informes/panel-trimestral.html` y avisa si falta algo.

## 5. Publicar o comparar (según `paneles.yaml`)

- **Ensayo:** no se publica. Ver "Cómo se compara en ensayo" en CLAUDE.md.
- **Oficial:** leer `https://claude.ai/artifact/GVEEa9pDVDPmV6Yzn7gS12` y republicar
  `meta/informes/panel-trimestral.html` en esa misma URL. Título fijo: *Panel Meta Ads*.

## 6. Parte y commit

`parte.py meta ok` con `--datos` = alertas que se mandaron, silenciadas, gasto de ayer,
conciliación Meta/CRM/Slack, `campanas_a_confirmar` y el resultado de la comparación. Commit de la carpeta del día,
`informes/guardia/<hoy>.json`, `memoria/guardia.jsonl`, `config/campanas.json`, el CSV del CRM, el panel y su JSON.
