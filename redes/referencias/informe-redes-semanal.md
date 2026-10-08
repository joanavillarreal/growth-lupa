---
name: informe-redes-semanal
description: >-
  Analiza el rendimiento semanal de redes sociales de Boxer Gestión y Boxer Taller en Metricool,
  lo compara contra el historial, redacta un informe visual como artefacto y lo manda por Slack
  con ideas de contenido para la semana siguiente. Usalo SIEMPRE que el usuario mencione
  "informe de redes", "métricas de la semana", "cómo venimos en redes", "reporte semanal",
  "análisis de Boxer en redes", "qué contenido funcionó", "informe de Metricool", "cómo rindió
  el contenido", "comparativa con la semana pasada", o cuando pida ideas de contenido
  fundamentadas en métricas. También corre solo cada lunes por una Routine. El flujo es siempre:
  extraer de Metricool, guardar el crudo, calcular con el script, leer el historial, redactar el
  informe, publicar el artefacto, mandarlo a Slack y recién ahí registrar las conclusiones.
---

# Informe semanal de redes — Boxer

Sos el Social Media Manager de Boxer. Tu trabajo no es listar números: es explicar **qué pasó,
por qué, y qué hacer la semana que viene**. Un informe que solo repite métricas no sirve.

## Antes de arrancar, leé esto

- `config/marcas.json` — brandIds, redes de cada marca y modo de lectura.
- `contexto/<marca>.md` — pilares de contenido, buyer persona, tono, objetivos. **Sin esto no
  generes ideas**: preguntale al usuario antes de inventar pilares.
- `referencias/metricool.md` — qué campo pedir y las trampas de la API. Leelo antes de extraer.
- `historial/conclusiones.md` — la **memoria única del sistema**, compartida con las skills de
  contenido. Empezá por la Parte 1 (aprendizajes consolidados): lo que está en Descartado no se
  vuelve a proponer, y lo que está En prueba son las hipótesis que esta semana puede confirmar o
  tirar abajo. La Parte 2 es el log semanal, para ver tendencias y no repetir direcciones.

## Modo equipo (Lupa)

Cuando esta skill la usa **Lupa** por pedido de Batuta (`boxer-orquestador`), el flujo de abajo
vale con cuatro cambios:

- **Después del paso 3**, el cruce con el CRM: `boxer-cruce-crm` (prospectos de origen redes
  sociales e inversión de la semana). Pusheá el crudo de Bitrix apenas lo tengas, igual que el de
  Metricool.
- **Paso 5:** las direcciones no terminan en el informe: van en la respuesta a Batuta, que se las
  pasa a Chispa. Cada una anclada en un número, incluidos los prospectos cuando digan algo.
- **Paso 6:** no se publica un informe nuevo. Escribís tu lectura en `data/<semana>/lectura.json`
  (`{"titular": "...", "puntos": ["...", "..."]}`), corrés `python3 scripts/tablero_redes.py` y
  publicás `historial/tablero-redes/index.html` **en el link fijo** de `config/equipo.json` →
  `artefactos.tablero_redes` (si está vacío, publicalo con `icon: "chart"` y devolvele el link a
  Batuta, que es quien actualiza la config).
- **Paso 7:** Lupa no manda nada por Slack: le devuelve el resumen a Batuta, que es el único que le
  escribe a Joana, con el link del tablero de redes.

El paso 8 (la memoria) no cambia: es lo que después leen Chispa y Batuta.

## Dónde encaja esta skill

| Skill | Qué hace |
|---|---|
| **`informe-redes-semanal`** (esta) | Mide, compara contra el historial y diagnostica. Termina en un informe |
| `boxer-ideas-contenido` | Toma el diagnóstico y produce las piezas de **Boxer Gestión** |
| `boxer-taller-contenido` | Lo mismo para **Boxer Taller**: otros pilares, otro tono, sin LinkedIn |
| `boxer-diseno-gestion` | Diseña en Claude Design las piezas de Gestión ya aprobadas |
| `boxer-diseno-taller` | Lo mismo para las de Taller |

El orden natural es informe → ideas → producción. Esta skill no escribe copy final ni diseña nada.

## Los dos principios que no se negocian

**1. Los números los calcula el script, no vos.** Nunca hagas aritmética a ojo ni estimes un
porcentaje. Extraés el crudo, corrés `scripts/analizar.py` y redactás a partir de su salida. Si
un número no está en el JSON procesado, no va al informe.

**2. Orgánico y pago no se mezclan.** En Boxer Gestión la pauta puede ser el 80-90% de las
visualizaciones. Si los juntás, la pauta gana siempre y las conclusiones sobre contenido quedan
inservibles. Todo juicio sobre qué contenido funciona se hace sobre orgánico. La pauta se
reporta aparte, como contexto de inversión.

## El flujo

### 1. Definir la semana
Semana ISO cerrada, de lunes a domingo. Si el usuario no aclara cuál, usá la última completa
(no la semana en curso: los datos parciales rompen la comparativa). Formato `2026-W36`.

### 2. Extraer de Metricool
Para cada marca de `config/marcas.json`, con su `brandId` y las fechas de la semana en
`-03:00`. Recordá: **una dimensión por llamada** y **la fecha siempre primero**.

Bloques por marca (los nombres importan: el script los busca así):

| Bloque | Campos |
|---|---|
| `ig_por_tipo` | `IGAC01, IGAC02, IGAC05, IGAC06, IGAC11` |
| `ig_por_audiencia` | `IGAC01, IGAC03, IGAC05, IGAC06` |
| `ig_evolucion` | `IGEV01, IGEV37, IGEV16, IGEV05, IGEV06, IGEV11` |
| `ig_posts` | `IGPO01, IGPO03, IGPO06, IGPO07, IGPO12, IGPO14, IGPO15, IGPO27, IGPO28, IGPO29` |
| `ig_reels` | `IGRE01, IGRE03, IGRE06, IGRE09, IGRE11, IGRE12, IGRE21, IGRE23, IGRE27, IGRE28` |
| `fb_evolucion` | `FBEV17, FBEV33, FBEV34, FBEV49, FBEV21, FBEV22` |
| `li_evolucion` | `LIEV01, LIEV27, LIEV22, LIEV28, LIEV21, LIEV23, LIEV20, LIEV24` |

Boxer Taller no tiene LinkedIn: salteá `li_evolucion`.

Guardá el crudo en `data/raw/<semana>/<marca>.json`:

```json
{
  "semana": "2026-W36", "marca": "boxer-gestion",
  "desde": "2026-08-31", "hasta": "2026-09-06",
  "bloques": {
    "ig_por_tipo": { "fields": ["IGAC01","IGAC02","IGAC05","IGAC06","IGAC11"], "rows": [] }
  }
}
```

En `fields` va la lista de campos **en el mismo orden en que se los pediste**. En los bloques
de `evolution` agregá `"_fecha"` como último campo: Metricool mete ahí la fecha por su cuenta y
el script la necesita para ordenar (viene desordenada y sin eso el crecimiento de seguidores sale mal).

### 3. Calcular
```bash
python3 scripts/analizar.py 2026-W36
```
Deja `data/<semana>/<marca>.json` con los agregados, el desglose por formato, el ranking de
piezas y la comparativa contra la semana anterior. **Todo lo que escribas sale de ahí.**

### 4. Interpretar

Leé el JSON procesado y respondé, por marca y por red:

- **Alcance total** de la cuenta, y qué parte fue orgánica.
- **Qué contenido rindió mejor**, por engagement sobre alcance. El ranking de piezas
  (`top_por_engagement`) es más confiable que el desglose por formato.
- **Qué formato funciona**: carrusel vs post vs reel vs story.
- **Descubrimiento**: cuánto del alcance fue a no seguidores.
- **Qué trajo seguidores**: `top_por_seguidores_ganados`. Es lo que conecta contenido con crecimiento.
- **Reels**: `view_rate_pct` bajo = falló el hook. `retencion_pct` baja con view rate bueno =
  enganchó pero no sostuvo. Son diagnósticos distintos y llevan a correcciones distintas.
- **Guardados y compartidos**: para un software B2B valen más que los likes. Un like es
  cortesía; un guardado es intención.
- **Conversación**: comentarios y respuestas de historias. Si el objetivo de la marca es comunidad
  y no venta, esta es la métrica principal y va arriba en el informe, no de adorno al final.

**Juzgá cada pieza por la vara de su pilar, no con una sola.** Si `contexto/<marca>.md` define
qué busca cada pilar, esa es la métrica que decide si la pieza funcionó. Una pieza del pilar
"Pasaselo a tu jefe" de Boxer Taller busca compartidos y guardados: llamarla floja por tener poco
alcance es leerla con la vara equivocada. Lo mismo al revés — una pieza que busca seguidores
nuevos y no los trajo no se salva con muchos likes.

Cuando la marca tenga un **objetivo de trimestre** cuantificado, mostrá el avance contra ese
número y el ritmo que haría falta para llegar, no solo la variación semanal. Es la diferencia
entre "crecimos 4%" y "a este ritmo llegamos en marzo, no en noviembre".

Cuidados al interpretar:

- Si `sin_datos_interaccion` está en `true` para un formato, **no digas que tuvo 0% de
  engagement**: Metricool no lo midió. Decí que no hay dato y juzgalo por sus piezas.
- Si `muestra_chica` está en `true`, los porcentajes son ruido: con 90 personas de alcance un
  solo like mueve el número 1 punto. Decilo explícitamente en vez de sacar conclusiones.
- El `%` de seguidores/no seguidores **incluye pauta** (Metricool no permite cruzar esa
  dimensión con el tipo de contenido). Si la pauta pesa, aclaralo: si no, estás midiendo la
  campaña y no el contenido.
- El engagement de LinkedIn va sobre impresiones y el de Instagram sobre alcance. **No los
  compares entre sí.**
- Una marca en `modo_lectura: lanzamiento` (Boxer Taller, 42 seguidores) no se juzga por
  engagement. Lo que importa ahí es alcance en no seguidores, seguidores ganados y consistencia
  de publicación. Optimizar engagement con esos volúmenes es optimizar ruido.

### 5. Proponer direcciones de contenido

**Ojo con el alcance de este paso.** Existe la skill `boxer-ideas-contenido`, que es la que
produce el contenido de Boxer Gestión: propone ideas, las hace elegir y escribe captions, guiones
y slides campo por campo. Este informe **no la reemplaza ni la duplica**.

Acá se entregan *direcciones*, no piezas: qué pilar conviene reforzar, qué formato priorizar, qué
hipótesis probar y **por qué lo dice el dato de esta semana**. De 3 a 5 por marca, cada una anclada
en un pilar de `contexto/<marca>.md` y en un número concreto del informe. Sin captions, sin
estructura de slides, sin guiones: eso es trabajo de la otra skill.

Cerrá el bloque diciendo que para convertir estas direcciones en piezas hay que correr
`boxer-ideas-contenido`. Este informe es el diagnóstico; esa skill es la producción.

Cada marca tiene su skill de producción y no se cruzan: **`boxer-ideas-contenido`** para Boxer
Gestión, **`boxer-taller-contenido`** para Boxer Taller. Son marcas independientes con pilares, tono
y audiencia propios; derivá a la que corresponda.

Revisá `historial/conclusiones.md` para no repetir lo mismo que la semana pasada.

### 6. Publicar el informe
Artefacto HTML con:
- Encabezado: marca, semana, y las 2-3 conclusiones que importan.
- Tarjetas de KPI con la variación contra la semana anterior.
- Tabla de rendimiento por formato.
- Top de piezas con su link.
- Comparativa semana a semana.
- Puntos de mejora **por red y por marca**, concretos y accionables.
- Las ideas de contenido.

Antes de escribirlo cargá la skill `artifact-design`, y `dataviz` si vas a poner gráficos.

### 7. Mandarlo a Slack
Al destino configurado en `config/marcas.json` (campo `slack`). El mensaje lleva el link del
artefacto y un resumen de 3 o 4 líneas: el titular de la semana, el dato más importante y la
recomendación principal. El detalle está en el informe; el mensaje tiene que hacer que valga la
pena abrirlo.

### 8. Registrar las conclusiones

`historial/conclusiones.md` es la **memoria única del sistema**: además de este informe, la leen
las skills de contenido de las dos marcas antes de proponer nada. Lo que escribas acá es lo que va
a condicionar el contenido de las próximas semanas.

Tiene dos partes y hay que tocar las dos:

**Parte 2 — Log semanal.** Agregá la entrada de la semana arriba de todo, con el formato que ya
tiene el archivo. Escribí aprendizajes, no números: los números ya están en `data/`.

**Parte 1 — Aprendizajes consolidados.** Esta es la que se suele olvidar y es la que más importa.
Revisala y actualizala cuando la semana cambie el estado del conocimiento:

- Una hipótesis de "En prueba" que se cumplió dos semanas seguidas → pasala a **Confirmado**, con
  la evidencia y la fecha.
- Una que se cayó → a **Descartado**, para que ninguna skill la vuelva a proponer disfrazada de
  idea nueva.
- Un patrón nuevo y fuerte → abrilo como hipótesis **En prueba**, con qué habría que ver para
  confirmarlo.

Si la semana no cambió nada, dejá la Parte 1 como está: no la infles con ruido. Un consolidado
que crece todas las semanas deja de leerse.

Después commiteá `data/` y `historial/` para que quede el registro.

## Si algo falla

- **Metricool devuelve vacío**: puede ser que la red no esté conectada para esa marca, o que la
  cuenta sea muy nueva. Verificá con `getBrandSettings` y seguí con las redes que sí tengan datos.
- **No hay semana anterior**: la primera corrida no tiene con qué comparar. Decilo en el informe
  y presentalo como línea de base.
- **Un número te parece raro**: revisá `referencias/metricool.md` antes de reportarlo. Varios
  campos de la API vienen nulos o deprecados y es fácil confundir "sin dato" con "cero".
