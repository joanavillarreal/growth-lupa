# Análisis `cursos` — monitoreo de cursos y webinars (todos los días, si hay eventos abiertos)

Lo hacía Vent hasta el 05/11/2026 (skill `boxer-evento-monitoreo`, copiada a
`.claude/skills/`). Desde ese día lo hace Lupa, en la misma corrida que el resto. **Solo
medición:** no se escribe en Bitrix, ni en la planilla, ni en n8n, ni en Hyperflow, y nunca se
manda un mensaje a un inscripto.

`que_toca_hoy.py` lo pone en `pendientes` solo si `cursos/eventos.yaml` tiene algún evento
**por abrir**, **con inscripción abierta** o **realizado sin cerrar** (la lista viene en
`eventos_abiertos` del JSON). Si no hay ninguno, va a `no_tocan` y Cursos en Vivo **no se
republica**.

Antes de alertar, leer `memoria/cursos.md`. Las definiciones (métricas, planilla, orígenes,
registro histórico) están en `cursos/datos.md`.

## Pasos

Para cada evento de `eventos_abiertos`, con `C=cursos/datos/crudos/<hoy>`:

1. **Planilla** (conector de Google Sheets): `get_values` con `spreadsheetId` = `planilla` del
   evento y `range` = `Inscriptos!A1:Q500`. Guardar la respuesta **tal cual** (regla 9) en
   `$C/<slug>-planilla.json`. Ese archivo tiene nombres, teléfonos y emails: está en
   `.gitignore` y no se commitea nunca. Si el evento está por abrir y la planilla todavía no
   tiene filas, se mide igual (todo en cero).
2. **Bitrix** (webhook): `python3 cursos/scripts/bitrix.py origen <source_id> --json
   $C/<slug>-bitrix.json`. Nunca se imprime la URL del webhook.
3. **Meta**, si el evento tiene `meta.campanas`: una sola llamada a `ads_get_ad_entities` para
   todas las campañas de los eventos abiertos (`level: campaign`, `object_ids`, `fields: [id,
   name, amount_spent]`, `date_preset: maximum`, cuenta `725901852075382`). Guardarla tal cual en
   `$C/meta.json`. Solo campañas dedicadas al evento: nunca «JY | Cursos y Webinars» ni otras
   generales.
4. `python3 cursos/monitoreo.py medir <slug> --planilla $C/<slug>-planilla.json --bitrix
   $C/<slug>-bitrix.json [--meta $C/meta.json]`. Valida los crudos (si no abren o falta una
   campaña, corta con el error: se vuelve a pedir una vez y, si sigue, ese evento no se mide),
   actualiza `cursos/eventos/<slug>/dashboard.json`, deja el resumen sin datos personales en
   `cursos/datos/<hoy>/<slug>.json` e imprime la tarjeta con ritmo y alertas.
5. Con todos medidos: `python3 cursos/monitoreo.py resumen` → `cursos/datos/<hoy>/parte.json`
   y las líneas 🎓 para el resumen de cierre.
6. `python3 cursos/panel/build.py`. Leer Cursos en Vivo (`Artifact` read de
   https://claude.ai/artifact/7Vh4FWB6jmE8asFYec5w6A, regla 7) y republicar
   `cursos/panel/dist/index.html` en ese mismo link. Antes, comparar lo publicado con lo que se
   va a publicar (el bloque `const DATA = [...]`): si un número publicado no coincide con el
   dashboard.json de ayer, alguien más publicó; decirlo en el parte.
7. `python3 parte.py cursos ok --resumen "..." --herramientas ... --datos
   cursos/datos/<hoy>/parte.json`. Commit de `cursos/eventos/`, `cursos/datos/<hoy>/` (sin
   los crudos de planilla), `cursos/panel/dist/` y `partes/`; push a `main`.
8. **Sin aviso aparte en Slack.** Las líneas 🎓 (inscriptos, ritmo y alertas de cada evento)
   van dentro del resumen de cierre al DM de Joana (`procedimientos/corrida.md`, paso 4).

## Conectores que necesita la rutina

Google Sheets (para `get_values`) y Meta Ads (`ads_get_ad_entities`), más Slack que ya usa toda
corrida. Al 05/11/2026 la rutina "Lupa · corrida diaria" (`trig_01McumqJBeuquCkoSywDC1YB`) tenía
Metricool, Meta y Slack; Joana le agregó Google Sheets ese mismo día (verificado en la rutina).
Si algún día falta, `cursos` sale fallido por regla 2 y el panel no se republica.
Bitrix no necesita conector: va por `BITRIX_WEBHOOK_URL`, que el entorno ya tiene.

La rutina vieja de Vent ("Boxer — Monitoreo de cursos y webinars (diario)",
`trig_01DWNjf8w2AT4kAjhcw7TqSS`, 9:20) publicaba en el mismo link: el 05/11/2026 ya estaba
desactivada. Si alguien la vuelve a prender, se pisan el panel: avisarlo en el resumen.

## Si algo falla

- **Una fuente no se pudo leer** para un evento (Sheets, Bitrix o Meta): ese evento no se mide
  y su dashboard.json queda como estaba. Si es Meta, se puede medir con `--meta` omitido: la
  inversión queda la del último monitoreo y el script lo pone como alerta. Si ningún evento se
  pudo medir: `parte.py cursos fallido --error "<error real>"` y **no se republica**.
- **Falta `get_values` o `ads_get_ad_entities`** después de 3 búsquedas (regla 2): fallido,
  con los nombres que sí cargaron.
- Nunca se completan números a mano ni se usan los de ayer como si fueran de hoy.

## Qué alerta el script (y nada más)

Del circuito: teléfonos inválidos, «Mensaje Enviado» = No enviado, filas sin «Estado CRM»,
valores de «Estado CRM» fuera de la lista, «Dice ser cliente — no está en el CRM» (una vez
realizado), filas sin «¿Cliente Boxer?», prospectos con el origen en Bitrix que no están en la
planilla, encabezados distintos a la plantilla madre.
Del resultado: ritmo bajo (menos de la mitad del objetivo faltando 3 días o menos), más del 60%
de clientes, asistencia sin cargar después del evento, evento realizado hace más de 15 días sin
cerrar, inversión de Meta que no se pudo leer.

El ritmo se informa siempre en un evento abierto: "van 9, a 2,2 por día; hacen falta 2,3 por
día en los 14 que quedan". La inscripción se acelera fuerte sobre la fecha (en el Curso IA el
día de la primera clase entraron 16 de 91): un evento por la mitad a tres días no está perdido.
