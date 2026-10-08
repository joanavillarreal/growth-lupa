# Preparación `gasto_meta` — refresco diario del gasto de Meta

Copiado de los pasos 1 y 1b de la rutina "Agente Growth · Monitor y alarma diaria" de
`agente-growth`. Corre **una sola vez por día**, antes del primer análisis que lo necesita
(`funnel` y `meta`), y los dos usan el mismo resultado.

Herramienta: la de Meta cuyo nombre termina en `__ads_get_ad_entities` (buscarla por sufijo,
hasta 3 búsquedas con unos minutos entre una y otra). Cuenta publicitaria `725901852075382`.
Es **solo lectura**: no se toca nada de la cuenta.

## 1. Qué pedir

`python3 run.py gasto-meta rango` → `desde`, `hasta` (siempre ayer, nunca el día en curso), los ids
de redes (y de cursos, si el archivo los tiene) y los conjuntos de experimentos con su rango. Si
`al_dia` es `true` y no hay conjuntos, no hay nada que pedir: registrar ok y seguir.

Si a `data/meta_spend.json` le falta un día, el Monitor lo cuenta como inversión cero y el CPL
sale más barato de lo real: por eso se pide todo lo que falte hasta ayer.

## 2. Pedir a Meta y guardar cada respuesta EXACTA en `meta/datos/meta-ads/gasto/<hoy>/`

Regla 9: nunca se escriben montos a mano. Si la respuesta es grande, se copia con `cp` el archivo
de resultado que deja el entorno; si es chica, se escribe el texto tal cual vino (heredoc con
`'EOF'`, sin reformatear). Todas con `ad_account_id: "725901852075382"`,
`include_additional_context: false`, `time_range` `{"since":"<desde>","until":"<hasta>"}`:

| Archivo | Llamada |
|---|---|
| `cuenta-diario.json` | `level: "ad_account"`, `time_increment: "1"`, `fields: ["amount_spent"]` |
| `cuenta-total.json` | igual, **sin** `time_increment` (el total del rango, para cuadrar) |
| `redes-diario.json` | `level: "campaign"`, `object_ids` = `redes`, `time_increment: "1"`, `fields: ["amount_spent"]` |
| `cursos-diario.json` | solo si `rango` trae ids de cursos: campañas y conjuntos de cursos, igual que redes |
| `conjunto-<id>.json` | por cada conjunto de `rango`: `level: "adset"`, `object_ids: [id]`, `time_increment: "1"`, `fields: ["name","amount_spent","lead"]`, con su propio rango |

## 3. Validar y cargar

```bash
python3 run.py gasto-meta cargar meta/datos/meta-ads/gasto/<hoy>/
```

Antes de escribir valida que todo abra como JSON, que cada fila sea un día dentro del rango sin
repetidos, que la suma diaria de la cuenta dé el total (±1 ARS) y que redes/cursos no superen el
total del día. Si dice `NO CUADRA` no escribió nada: volver a pedir lo que falla y correrlo otra
vez; si sigue, la preparación es fallida con ese mensaje. Si sale bien, actualiza
`data/meta_spend.json` (`total_ars`, `redes_ars`, `cursos_ars` si corresponde, `performance_ars`)
y `data/meta_adsets.json`. Commit de esos dos archivos y de la carpeta del día.

## Registrar

- Salió bien: `python3 parte.py gasto_meta ok --herramientas <nombre completo> --datos <json>`,
  con `{"meta_spend_hasta": "AAAA-MM-DD", "meta_adsets_hasta": "AAAA-MM-DD"}`.
- Falló: `python3 parte.py gasto_meta fallido --error "<lo que realmente pasó>"`. Los análisis
  corren igual: el Monitor muestra solo, arriba de todo, "Gasto de Meta sin actualizar desde
  <fecha>" (`growth/monitor.py: gasto_meta_atrasado`). En el mensaje de Slack también hay que
  decirlo, con esa fecha. Nunca dar un CPL o un CAC como si estuvieran al día.
