# Análisis `meta` — guardia diaria y Panel Meta Ads

Copiado de la rutina "Agente Meta - Guardia diaria" de `agente-meta-ads` (pasos 1 a 6) y de
`meta/referencias/panel.md`. Todo se corre desde `meta/` (`cd meta`). **Solo lectura**: no se
escribe en Meta ni en Bitrix; lo que propone o ejecuta cambios es de Turbo.

Cuenta **`725901852075382`** (ARS; hay otra casi igual en USD: usar siempre el ID). Un
`client_conversation_id` nuevo, el mismo en todas las llamadas. `<hoy>` es la fecha de Argentina.

## 0. Entradas que escribe otro agente (solo lectura)

Copiar desde `/home/user/agente-meta-ads/memoria/` a `meta/memoria/`: `cambios.jsonl`,
`alertas.jsonl` y `experimentos.jsonl`. **Nunca escribir ni pushear en `agente-meta-ads`.**
Si el repo no está en el contenedor, seguir con la última copia y decirlo en el parte (el panel
puede no mostrar cambios recientes). Cuando exista Turbo, se leen de su repo.

`memoria/guardia.jsonl` es de Lupa (lo escribe la guardia de acá): no se copia.
Antes de reportar una entrega rota, leer `/home/user/agente-meta-ads/memoria/bitacora-cambios.md`:
un conjunto recién creado y sin activar da la misma señal que uno roto.

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
conciliación Meta/CRM/Slack y el resultado de la comparación. Commit de la carpeta del día,
`informes/guardia/<hoy>.json`, `memoria/guardia.jsonl`, el CSV del CRM, el panel y su JSON.
