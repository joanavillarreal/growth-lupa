# Preparación `gasto_meta` — refresco diario del gasto de Meta

Copiado de los pasos 1 y 1b de la rutina "Agente Growth · Monitor y alarma diaria" de
`agente-growth`. Corre **una sola vez por día**, antes del primer análisis que lo necesita
(`funnel` y `meta`), y los dos usan el mismo resultado.

Herramienta: la de Meta cuyo nombre termina en `__ads_get_ad_entities` (buscarla por sufijo,
hasta 3 búsquedas con unos minutos entre una y otra). Cuenta publicitaria `725901852075382`.
Es **solo lectura**: no se toca nada de la cuenta.

## 1. Gasto diario (`data/meta_spend.json`)

Si a este archivo le falta un día, el Monitor lo cuenta como inversión cero y el CPL sale más
barato de lo real. Traer **todos los días que falten hasta ayer** (nunca el día en curso):

- total de la cuenta: `level: "ad_account"`, `time_increment: "1"`
- campaña `JY | Awareness`, id `120252699394270427`
- webinars y cursos, **solo si el archivo tiene `campanas_cursos` y `conjuntos_cursos`**: la
  campaña `JY | Webinar Mostrador - 17 SEPT 2026` (id `120254108819070427`, `level: "campaign"`)
  y los conjuntos `Clases de IA en vivo - Joa y Pri` (id `120253191497490427`) y
  `Campaña Webinar Marketing` (id `120244530275810427`), con `level: "adset"`. Si el archivo
  ya tiene más ids en esas listas, usar los del archivo.

Cada uno por `object_ids`, con `time_increment: "1"` y `time_range` desde el día siguiente al
último cargado hasta ayer.

Cada día lleva cuatro campos:
- `total_ars`: el total de la cuenta
- `redes_ars`: lo de awareness
- `cursos_ars`: la suma de webinars y cursos (cero si ese día no hubo pauta)
- `performance_ars`: el total menos redes menos cursos

Si el archivo no tiene `campanas_cursos`, no agregar `cursos_ars`, y `performance_ars` es el
total menos redes.

## 1b. Conjuntos de los experimentos (`data/meta_adsets.json`)

Para cada id de `conjuntos` (y cada `conjunto_meta` de un experimento con `estado: corriendo`
en `experiments/EXP-*.md` que todavía no esté en el archivo): `level: "adset"`,
`object_ids: [id]`, campos `amount_spent` y `lead`, `time_increment: "1"`, desde el día
siguiente al último cargado hasta ayer. Cada día se guarda como
`{"gasto_ars": <amount_spent>, "leads": <lead, 0 si viene vacío>}`. Nunca el día en curso.

## Registrar

- Salió bien: `python3 parte.py gasto_meta ok --herramientas <nombre completo> --datos <json>`,
  con `{"meta_spend_hasta": "AAAA-MM-DD", "meta_adsets_hasta": "AAAA-MM-DD"}`.
- Falló: `python3 parte.py gasto_meta fallido --error "<lo que realmente pasó>"`. Los análisis
  corren igual: el Monitor muestra solo, arriba de todo, "Gasto de Meta sin actualizar desde
  <fecha>" (`growth/monitor.py: gasto_meta_atrasado`). En el mensaje de Slack también hay que
  decirlo, con esa fecha. Nunca dar un CPL o un CAC como si estuvieran al día.
