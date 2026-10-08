# Meta por MCP — como se traen los datos de plataforma

**Desde el 2026-09-11 los datos de Meta entran por el MCP.** Meta habilito el
conector para la cuenta de Boxer. Se termino el export manual como via normal.

## La cuenta

| | |
|---|---|
| `ad_account_id` | **`725901852075382`** (numerico, SIN el prefijo `act_`) |
| Nombre | Cuenta Publicitaria Oficial - Boxer Gestión |
| Business | AIT (`191532801987846`) |
| Moneda | **ARS** |
| `is_ads_mcp_enabled` | `true` |

**Hay otras cinco cuentas colgando del mismo business y NINGUNA es la de Boxer
Gestion.** "Boxer Gestion de AIT (Read-Only)" (`987208277687912`) tiene el
nombre parecido, esta habilitada y **reporta en USD**: si se la consulta por
error, el gasto sale en otra moneda y todos los KPI salen mal sin que nada falle.
**Usar siempre el ID de arriba, nunca buscar la cuenta por nombre.**

Los dos parametros que toda llamada necesita:
- `ad_account_id`: el de arriba.
- `client_conversation_id`: 20 caracteres alfanumericos, **el mismo en todas las
  llamadas de la corrida**. Se genera uno nuevo por corrida.

## El flujo en dos tiempos

El MCP lo llama **el agente**; los scripts de Python no tienen acceso a las
herramientas `mcp__MCP_Meta__*`. Entonces:

```
1. El agente llama a ads_get_ad_entities (campana, conjunto, anuncio)
2. Guarda cada respuesta TAL CUAL en datos/meta-ads/<carpeta>/mcp/<nivel>.json
3. python3 scripts/meta_desde_mcp.py datos/meta-ads/<carpeta>/
      -> escribe campanas_*.csv, conjuntos_*.csv, anuncios_*.csv
4. python3 scripts/analizar_meta.py datos/meta-ads/<carpeta>/ --json ...
5. python3 scripts/cruzar.py --meta ... --crm ...
```

**Por que sigue pasando por CSV y no se analiza el JSON directo:** los CSV son
la evidencia versionada de cada informe y `analizar_meta.py` / `cruzar.py` ya
saben leerlos. El puente conserva todo el pipeline y toda la historia
comparable con los exports viejos. No reescribir eso.

**Guardar el JSON crudo tambien**, en `mcp/`. Es la unica forma de reconstruir
un informe si despues se discute un numero.

## Las llamadas exactas

### Nivel campana (el que trae el gasto)

```
ads_get_ad_entities
  ad_account_id : "725901852075382"
  level         : "campaign"
  time_range    : {"since":"AAAA-MM-DD","until":"AAAA-MM-DD"}
  time_increment: "1"          <- STRING, no numero. Una fila por dia.
  fields        : ["name","amount_spent","impressions","reach","frequency",
                   "website_ctr","results","cost_per_result","effective_status",
                   "objective","cpm","link_click"]
  filtering     : [{"field":"campaign.amount_spent","operator":"GREATER_THAN","value":["0"]}]
```

### Nivel conjunto

Igual, con `level:"adset"`, el filtro en `adset.amount_spent`, y agregando a
`fields`: `"campaign_name"`, `"daily_budget"`, **`"learning_stage_info"`**.

### Nivel anuncio

`level:"ad"`, filtro en `ad.amount_spent`, y agregando `"campaign_name"` y
`"adset_name"`.

### El filtro de gasto no es opcional

Sin el, el MCP devuelve **las ~60 campanas historicas de la cuenta**, casi todas
en cero, paginadas. Con el filtro quedan las 7-9 que gastaron. El script
descarta las filas en cero igual (`--con-gasto-cero` las conserva), pero
filtrar en origen ahorra varias paginas de ida y vuelta.

### Paginacion

Si la respuesta trae `pagination.next_cursor`, hay mas. Volver a llamar con
`cursor` y **todos los demas parametros identicos**: cualquier cambio invalida
el cursor. Guardar cada pagina como un archivo aparte en `mcp/`; el script las
concatena y **deduplica por (id, dia)**, asi que una pagina repetida no infla
el gasto.

## Cuanto pedir: la regla de volumen

Las filas diarias son caras en contexto. El reparto que funciona:

| Ventana | Como pedirla | Por que |
|---|---|---|
| **Semana corta** (lunes-domingo, o lunes-miercoles el jueves) | `time_increment:"1"` | hace falta la serie: ritmo de gasto, que dia cambio algo |
| **Ventana de 4 semanas** | **sin `time_increment`** | solo hacen falta los totales, y ademas asi viene el **alcance unico real** |

Pedir 28 dias x 3 niveles con filas diarias es tirar contexto a la basura.

## Lo que el MCP da y el export manual no daba

1. **Alcance unico y frecuencia de periodo.** Con filas diarias el alcance no se
   puede sumar (cuenta varias veces a quien vio el anuncio en dos dias), y
   `analizar_meta.py` lo dejaba en `null` a proposito. Pidiendo la ventana sin
   `time_increment`, Meta devuelve el alcance unico verdadero y la frecuencia
   real. **Recien ahora se puede medir fatiga en serio.**
   Medido el 2026-09-11 sobre 10/08-06/09: "JY | Conversiones - Copia - Boton a
   WhatsApp" tiene **frecuencia 7,95**. Esta quemando al mismo publico.
2. **Fase de aprendizaje, sin adivinar.** `learning_stage_info` en nivel conjunto
   devuelve `status` (`LEARNING` / `SUCCESS`), `conversions` acumuladas y
   `last_sig_edit_ts` (cuando fue la ultima edicion significativa, epoch).
   La regla "antes de dar un veredicto, chequear la fase de aprendizaje" deja de
   ser una estimacion de ~50 eventos: **se lee**. Si el conjunto dice `LEARNING`,
   el veredicto es `sin_señal` y se extiende `revisar_en`, punto.
3. **Desglose por ubicacion, sin export.** `breakdowns: ["publisher_platform",
   "platform_position"]` da FB vs IG y feed / stories / reels / notification.
   Reemplaza el export #4, que nunca llego (alerta A15).
   Otros desgloses utiles: `["age","gender"]`, `["region"]`, `["device_platform"]`.
   **Al leerlos vale la trampa 6 (efecto de descomposicion): un segmento con
   costo por resultado promedio alto NO se corta por eso.**
4. **Datos de hoy y de ayer**, sin esperar a que Joana exporte.

## Los diagnosticos de relevancia estan, pero en OTRA herramienta

`quality_ranking`, `engagement_rate_ranking` y `conversion_rate_ranking` **no
existen** como campos de `ads_get_ad_entities`: buscarlos ahi devuelve
`unknown_fields`. Es facil concluir que el MCP no los tiene. **Los tiene.**

Salen de **`ads_insights_auction_ranking_benchmarks`**, que ademas agrupa los
anuncios por cohorte (objetivo de optimizacion + evento optimizado + tipo de
publico) — que es justamente el agrupamiento correcto, porque comparar la
calidad de un anuncio de awareness contra uno de lead no significa nada.

```
ads_insights_auction_ranking_benchmarks
  ad_account_id : "725901852075382"
  date_preset   : "last_28d"
```

Devuelve por anuncio: `Quality Ranking`, `Engagement Rate Ranking`,
`Conversion Rate Ranking` y un diagnostico en texto. **`Not Yet Available` es
"todavia no hay volumen", no "malo"**: no tratarlo como una nota baja.

Esa misma herramienta avisa de **solapamiento de subasta** entre conjuntos
parecidos, que es exactamente el problema A7 de esta cuenta.

**Consecuencia: ya no hace falta NINGUN export manual.** Lo unico que sigue
siendo descarga a mano es el CSV de **leads del formulario nativo** (nombres y
telefonos), que **no se versiona crudo**.

## Las otras dos herramientas de diagnostico

- **`ads_get_opportunity_score`** — puntaje 0-100 de la cuenta mas
  recomendaciones concretas ordenadas por `opportunity_score_lift`. Medido el
  2026-09-11: **71/100**. Lo mas util que trae no son los consejos genericos
  sino los de tipo **`delivery_error`**: conjuntos activos, con presupuesto, que
  no entregan nada porque todos sus anuncios tienen error. Encontro uno
  ("Conjunto 1 — Lookalike CRM", 2.000 ARS/dia, cero gasto en 14 dias).
  **Revisarlo todas las corridas del jueves: es plata reservada que no corre.**
- **`ads_insights_industry_benchmark`** — comparacion contra anunciantes
  parecidos. Probada el 2026-09-11 con `CPR` + `LEAD_GENERATION`: devolvio
  *"No industry benchmark data available for the given criteria"*. Puede ser
  falta de volumen o de cohorte en Argentina. **No inventar un benchmark si no
  contesta**: decir que no hay dato y seguir con el umbral propio.

## Las trampas del formato

**1. La plata viene formateada, y la forma cambio sin aviso.**
Hasta el 2026-09-16, `amount_spent`/`cpm` eran texto en es-AR: `"$20.498,46
ARS"` (punto de miles, coma decimal). Parsear eso con `float()` directo da
`20.498` — veinte pesos en vez de veinte mil. Desde el 2026-09-22 (visto por
primera vez en la guardia de ese dia) el MCP los devuelve como dict:
`{"value": "20498.46", "unit": "ARS"}`, con el numero ya en punto decimal
plano. `meta_desde_mcp.py` maneja las dos formas y tiene test. **Nunca leer
`amount_spent` a ojo de un JSON crudo para escribirlo en el informe: pasarlo
siempre por `moneda()`.**

Ojo con el error compuesto: pasar el dict nuevo por el parser viejo (el que
solo esperaba texto) no fallaba con una excepcion — daba un numero *cien veces
mas grande* y en silencio. `str({"value": "2418.05", "unit": "ARS"})` deja
`"2418.05,"` despues de sacar todo lo que no es digito/coma/punto (la coma
que separa las claves del dict sobrevive), y el parser la lee como el
separador decimal es-AR y borra el punto de por medio. La guardia del
2026-09-22 lo agarro por su propio control de totales (G0): el gasto de la
ventana salio de ~380.000 a ~34.000.000 ARS y disparo un aviso de "los datos
no cierran" que en realidad era un bug de parseo, no un problema del MCP.

**2. `results` cambia de forma segun haya datos.**
```
con datos:  {"indicator":"actions:lead","values":[{"attribution_windows":["default"],"value":"3"}]}
sin datos:  {"indicator":"actions:lead","value":"Not available"}
```
`"Not available"` es **ausencia de dato, no un cero**. Un dia con gasto y sin
resultado atribuido todavia no es un dia con cero leads. El script lo deja
vacio para que el analizador no lo cuente.

**3. `ad_entities` viene como STRING con JSON adentro**, no como lista. Hay que
parsearlo dos veces. El script ya lo hace.

**4. Los numeros se reajustan para atras.** Comparado el 2026-09-11 contra el
export del 2026-09-08 para la misma ventana (10/08-06/09): el total coincidio
salvo ~7 ARS sobre 774.550 (0,001%) — "JY | Remarketing" +5,32 y "JY | Viajes
Presenciales" +2,06. Es normal: Meta cierra el gasto despues. **Consecuencia: un
numero ya publicado no se recalcula.** Vale lo mismo que la regla cuatro del
CRM — una semana cerrada se lee de su CSV versionado, no se vuelve a pedir.

**5. `time_increment` va como string** (`"1"`, no `1`) o la llamada falla.

**6. Una llamada diaria de 4 semanas con muchas campanas/conjuntos puede
perder entidades enteras, sin cursor de paginacion que lo avise.** Verificado
el 2026-09-14: pedir `campaign`/`adset` con `time_increment:"1"` para 28 dias
y ~9 campanas / ~14 conjuntos devolvio 108.335 ARS menos que la misma
ventana pedida sin `time_increment` (faltaba una campana entera —
`JY | Webinar Mostrador`— y 6 de 14 conjuntos, sin ningun `pagination.next_cursor`
en la respuesta que avisara del corte). **Regla dura: si se pide detalle
diario de una ventana larga, sumar el total y compararlo contra el total de
la misma ventana pedida sin `time_increment` antes de seguir.** Si no
coinciden al peso, pedir las entidades que faltan por separado con
`object_ids` (pocas por llamada) y fusionar los JSON antes de correr
`meta_desde_mcp.py`. Por esto conviene seguir pidiendo la ventana de 4
semanas **sin `time_increment`** como manda la regla de volumen de arriba: la
llamada agregada no mostro este problema. Solo hace falta el detalle diario
de una ventana larga cuando `cruzar.py` necesita el dia exacto de cada
campana para su chequeo de "origen contaminado" — y en ese caso, verificar
el total antes de confiar en el resultado. Ver `memoria/aprendizajes.md`,
2026-W37.

**7. El pull agregado (sin `time_increment`) de una ventana larga no sirve para el
chequeo de "origen contaminado" de `cruzar.py`.** Ese chequeo compara cada lead
del CRM contra el rango `primer_dia`-`ultimo_dia` de la campana/conjunto que lo
genero, y `analizar_meta.py` solo llena esos dos campos cuando hay fecha por
fila. Sin `time_increment`, salen `None` para TODAS las entidades y **el 100%
de los leads aparece "fuera de ventana"** — una alerta de contaminacion sobre
todo el canal, algo que nunca pasa de verdad. Si eso aparece, la primera
hipotesis es el dato incompleto, no un hallazgo: pedir un segundo pull, solo
con `amount_spent` y `time_increment:"1"`, a nivel campana y conjunto (no hace
falta a nivel anuncio para este chequeo), **verificar que el total sumado
coincida al peso** contra el pull agregado (trampa 6, arriba), y fusionar
unicamente los campos `primer_dia`/`ultimo_dia` corregidos sobre el `meta.json`
que ya tiene el gasto y los resultados buenos del pull agregado. Verificado
2026-W39: el chequeo desaparecio y ningun otro numero (CPL, conciliacion, costo
por Convertido) cambio. Ver `memoria/aprendizajes.md`, 2026-W39.

**8. Guardar la respuesta cruda sin retipearla.** Hay que guardar cada respuesta
TAL CUAL en `mcp/`, pero la herramienta solo la deja en un archivo cuando supera
~70.000 caracteres; las mas chicas vuelven en el contexto y no hay forma de
escribirlas sin retipear, que es donde se cuelan los errores. Truco medido el
2026-10-05: agregar a `fields` campos de mas (`cost_per_action_type`,
`video_play_actions`, `clicks`, `ctr`, `cpc`, `video_p25_watched_actions`...;
en conjunto, `targeting`) hasta pasar el limite. La herramienta guarda el JSON en
archivo (`tool-results/*.txt`, mismo formato) y se copia a `mcp/<nivel>.json`.
`meta_desde_mcp.py` ignora los campos de mas. Si ni asi pasa el limite (campana
con pocas filas), reconstruir el JSON con un script desde los valores que
devolvio la herramienta y dejarlo anotado en el informe.

**9. Un conjunto que cambia de publico conserva el id.** `Conversion - LAL
Presupuestados 2%` paso a `Conversion - LAL Envio formulario 1-2%` el 28/09 con
el mismo id: el gasto de antes del cambio queda bajo el nombre nuevo. Para leer
un experimento hay que cortar la serie diaria en la fecha del cambio.

## Escribir en la cuenta

Ver la seccion "Actuar sobre la cuenta" del SKILL. El resumen:
**hoy el agente NO escribe en Meta.** Las herramientas existen
(`ads_update_entity`, `ads_create_campaign`, `ads_create_ad`, ...) y el permiso
esta, pero la politica sigue siendo la de siempre — el agente propone, Joana
ejecuta — hasta que Joana la cambie explicitamente y quede escrito en
`config/cuenta.yaml` -> `meta_ads.mcp.escritura`.
