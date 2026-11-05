---
name: boxer-evento-monitoreo
description: 'Revisa cómo viene cada curso, webinar o charla del canal educativo de Boxer Gestión: lee la planilla de inscriptos del evento y el CRM, compara el ritmo de inscripción contra el objetivo y contra los eventos anteriores, detecta problemas del circuito (teléfonos inválidos, mensajes no enviados, inscriptos trabados, asistencia sin cargar, checklist sin terminar), actualiza el dashboard.json del evento y entrega un reporte corto con ritmo y alertas. Usalo SIEMPRE que el usuario pregunte "cómo viene el webinar", "cuántos inscriptos hay", "cómo va el curso", "estado de los eventos", "revisá el evento", "monitoreo", "cómo venimos para el webinar del jueves", "llegamos al objetivo", "hay algo roto en el flujo", o cuando pida un chequeo periódico del canal. También cuando se dispare una revisión programada del canal. El flujo es: ubicar el evento, leer la planilla y el CRM, comparar contra objetivo e histórico, listar alertas y actualizar los datos de Cursos en Vivo.'
---

# Monitoreo de eventos

> Copiada de growth-vent el 05/11/2026 y adaptada a Lupa. En la corrida diaria es el análisis
> `cursos` (`procedimientos/cursos.md`); esta skill es para cuando Joana lo pide en una sesión.
> Altas y cierres de eventos que pide Vent: `procedimientos/eventos.md`.

Mira el estado real de los eventos del canal y avisa lo que hay que corregir **mientras
todavía se puede corregir**. Un evento con pocos inscriptos a tres días se salva; a un día
ya no. Lupa mide, explica y alerta: no propone campañas ni toca el circuito.

## Antes de empezar

Leé `cursos/datos.md` (métricas, valores de referencia, la planilla, orígenes en Bitrix,
registro histórico) y `memoria/cursos.md`.

## Paso 1 — Ubicar qué se monitorea

`python3 cursos/monitoreo.py estado`. Cada evento de `cursos/eventos.yaml` sale como:

| Estado | Cuándo | Qué se mira |
|---|---|---|
| `por_abrir` | Antes de `apertura` | Que la planilla y el origen existan |
| `inscripcion_abierta` | Desde `apertura` hasta el día del evento | Ritmo, composición, salud del flujo |
| `realizado` | Pasó y Vent todavía no lo cerró | Asistencia cargada, derivaciones, cierres |
| `cerrado` | Tiene `cerrado` | Nada: ya está medido |

Si Joana nombró un evento, andá directo a ese. Si no, todos los que no estén cerrados,
empezando por el más cercano.

## Paso 2 — Leer los datos de verdad

No repitas lo que dice el `dashboard.json`: ese es el último estado guardado, no el de ahora.
Seguí los pasos 1 a 4 de `procedimientos/cursos.md`:

- **Planilla**: Google Sheets `get_values` sobre `Inscriptos!A1:Q500`, guardada tal cual (regla
  9) en `cursos/datos/crudos/<hoy>/<slug>-planilla.json` (no se commitea: datos personales).
- **Bitrix**, por el webhook `BITRIX_WEBHOOK_URL`, nunca por el conector:
  `python3 cursos/scripts/bitrix.py origen <SOURCE_ID> --json ...`
- **Meta**: `ads_get_ad_entities` de las campañas dedicadas al evento (`cursos/eventos.yaml`).
- `python3 cursos/monitoreo.py medir <slug> ...` calcula todo y actualiza el dashboard.json.

Si alguna fuente no responde, decilo y seguí con el resto. **No completes un número que no
pudiste leer:** se escribe `[FALTA]` o "no se pudo leer".

## Paso 3 — Comparar

Cada cifra va contra dos cosas:

1. **El objetivo** del evento (`objetivos` en `cursos/eventos.yaml`): más de 40 inscriptos y
   más del 15% de derivación sobre inscriptos, salvo que Vent diga otra cosa.
2. **Los eventos anteriores**: el registro histórico y los valores de referencia de
   `cursos/datos.md`. Con un solo evento medido se dice "único evento medido", no "por debajo
   del promedio".

Para un evento abierto, el ritmo concreto: "van 34 de más de 40, a 4 por día; hacen falta 1,8
por día en los 4 que quedan". La inscripción se acelera fuerte sobre la fecha (Curso IA: 16 de
91 el día de la primera clase).

## Paso 4 — Alertas

Las calcula `cursos/monitoreo.py` (lista completa en `procedimientos/cursos.md`). Reportá solo
lo que da alerta; si no hay ninguna, "sin alertas". Antes, mirá `memoria/cursos.md`: lo que ya
se revisó con Joana no se vuelve a marcar.

## Paso 5 — El reporte

La tarjeta que imprime `medir`, una por evento, la más cercana primero:

```
[Nombre] · [tipo] · [fecha] — faltan N días (estado)
Inscriptos    34 · objetivo más de 40 · 4,0 por día · hacen falta 1,8 por día en los 4 que quedan
Clientes      15 (44%) · no clientes 19 (56%)
Derivaciones  0 (0% de los inscriptos; objetivo más del 15%) · cierres 0 · prospectos abiertos 12
Pauta Meta    $ 24.000,00 · $ 1.263,16 por inscripto de Meta (19)
Alertas
  · 2 teléfono(s) inválido(s): ...
```

Explicás qué significa cada alerta con hechos. Lo que hay que hacer con eso (campañas,
mensajes, n8n) lo decide el equipo y lo arma Vent: Lupa no propone acciones.

## Paso 6 — Dejar el rastro

1. `python3 cursos/panel/build.py`
2. Leer Cursos en Vivo y republicarlo en su link (`paneles.yaml` → `cursos_en_vivo`), si todos
   los números salieron de la planilla, de Bitrix o de Meta. Es panel de Lupa: no hace falta
   pedir permiso, pero sí leerlo antes (regla 7).
3. Commit y push a `main` con el nombre del evento en el mensaje.

## Reglas

- **No inventes números.** Lo que no se pudo leer se dice; lo no medido es `[FALTA]`.
- No toques Bitrix (ni prospectos, ni negociaciones, ni comentarios), ni Hyperflow, ni n8n, ni
  la planilla: el monitoreo mira y avisa.
- **Nunca mandes mensajes a inscriptos.**
- Las bases de inscriptos no se commitean ni se pegan en Slack.
- En argentino, de vos, sin jerga.
