---
name: growth
description: Analiza el funnel de adquisición de Boxer Gestión por canal desde Bitrix24 - CPL, CAC, % de derivación y % de conversión, general y por canal - actualiza el dashboard y reporta anomalías. Usalo SIEMPRE que el usuario mencione "cómo viene el funnel", "CPL", "CAC", "costo por lead", "cuántos leads trajimos", "cómo viene Meta", "cómo viene Google", "actualizá el dashboard de growth", "qué pasó esta semana con los canales", "por qué subió el costo", "análisis de adquisición", "canales de adquisición", o cuando pida cargar o proponer un experimento de canales. El flujo es siempre - ingesta, leer la salud del dato, después las métricas, y recién ahí conclusiones.
---

# Agente de Growth — funnel de adquisición

## Antes que nada

Corré la ingesta. Los números se calculan sobre el snapshot, no en vivo:

```bash
python3 run.py daily      # ingesta + dashboard + anomalías
python3 run.py report --mes 2026-08
```

El webhook de Bitrix llega por la variable de entorno `BITRIX_WEBHOOK_URL`.
Nunca la escribas en un archivo ni la muestres en el chat: es acceso al CRM.

## Hora argentina

Bitrix guarda fecha y hora (creación de prospectos y negociaciones, "Completado
el") en el horario de su servidor, +03:00, seis horas adelante de Argentina.
Desde el 08/10/2026 el agente convierte esos campos a hora argentina al cargar
cada snapshot (`ingest.normalizar`), así que un lead del viernes a las 20 hs
cuenta para el viernes y no para el sábado. Los campos de solo fecha
(derivación, presupuestado, cierre, SPA de gastos) son días puros y no se
tocan. Si alguna vez leés un snapshot a mano, usá `ingest.cargar`, no
`json.load`.

## Cómo está definido el funnel

| Etapa | De dónde sale |
|---|---|
| Prospecto | prospecto de Bitrix creado en el período |
| Derivado | negociación con **Fecha de derivación** en el período |
| Presupuestado | negociación con **Fecha de Presupuestado** en el período |
| Cliente | negociación con **Fecha de cierre** en el período |

El canal sale del `SOURCE_ID` (origen), agrupado en canales en
`config/definitions.yaml`. Un canal tiene varios orígenes: Meta Ads son
"Meta Ads" y "Meta Ads Formulario"; Google son "Google Ads", "GA FORM" y
"GA - Remarketing"; Redes Sociales tiene el origen "Redes".

La inversión sale del SPA 1052 (Inversiones y Gastos), ya cargada en USD y
por día. El tipo de gasto define a qué canal se imputa.

## De dónde sale cada número de inversión

- **Meta Ads y Redes Sociales salen del conector de Meta**, no del SPA. El
  SPA guarda un único monto diario para toda la cuenta y ahí adentro no hay
  forma de saber qué parte fue awareness y qué parte performance. Leyendo la
  API a nivel campaña, la división entre los dos canales es exacta y por día.
  Los montos vienen en pesos y se dividen por la cotización configurada.
- **Google Ads sale del SPA**, porque no hay conector.
- Lo que la carga semanal deja en el SPA para Meta queda como **espejo**: no
  se suma a las métricas (sería contar dos veces) pero sí se concilia, para
  avisar si al CRM le faltan días. El dashboard puede estar bien y el CRM
  desactualizado al mismo tiempo, y eso hay que decirlo: el resto de la
  empresa mira el CRM.

### Hay que refrescar `data/meta_spend.json`

Ese archivo tiene el gasto diario de la cuenta separado en `redes_ars` (las
campañas clasificadas como Redes Sociales) y `performance_ars` (todo el
resto). El pipeline no lo puede actualizar solo: hay que leerlo de la API
desde acá. **Actualizalo antes de sacar conclusiones de un período nuevo**:

1. Gasto diario de la cuenta `725901852075382` (`level: "ad_account"`,
   `time_increment: "1"`).
2. Gasto diario de cada campaña de `campanas_redes` (hoy solo
   `JY | Awareness`, id `120252699394270427`).
3. `performance_ars` = total menos la suma de las de redes.
4. Escribí los días nuevos y corré `python3 run.py daily`.

Si querés sumar una campaña a Redes Sociales, agregala a `campanas_redes` y
recalculá los días: el reparto se rehace solo.

Los días que faltan en el archivo cuentan como días sin inversión y abaratan
el CPL, así que el panel de salud los marca.

**Falta de dato y gasto en cero no son lo mismo.** Si el archivo no cubre un
día, la alarma avisa que hay que refrescarlo, no que la cuenta dejó de gastar.
Confundirlos hacía sonar una alarma roja falsa cada día entre refresco y
refresco. Antes de dar por buena cualquier alerta de gasto, mirá hasta qué día
llega el archivo.

## El dashboard: Monitor de Growth

Desde el 30/09/2026 el dashboard es el **Monitor de Growth** (reemplazó al
panel de funnel con Resumen · Histórico · Por trimestre, por pedido de Joana).
Está pensado primero para el teléfono. Arriba se elige el **trimestre** y hay
cuatro solapas que siguen el camino del prospecto. Todo sale de
`growth/monitor.py`; cada número tiene un botón ⓘ que explica cómo se calcula
y de dónde sale (los textos están en `INFO`, en `growth/plantilla.html`: si
cambiás un cálculo, cambiá su explicación).

| Solapa | Qué muestra |
|---|---|
| 1 · Funnel general | tabla del Q (gastos, generados, no calificados, derivados, presupuestados, a futuro, cerrados, MRR) y números sueltos: % inactivo con sus 3 razones y su canal, % no calificación, win rate, % a futuro, días de derivado a cierre, CAC general y por canal |
| 2 · Generación | gasto, generación semana a semana contra el Q anterior, generado por canal, podio de canales, CPL por canal, generados por tipo de negocio |
| 3 · Derivación | derivados por asesor y por canal, semana a semana, por tipo de negocio, actividades del timeline hasta derivar, días de creación a conversión |
| 4 · Ventas | presupuestos semana a semana, presupuestos y cierres (con MRR) por asesor, lo recibido por asesor según su etapa de hoy, cartera a futuro sin agenda, días a cierre por asesor, clientes cerrados (plan, vendedor, tipos de negocio) |

Convenciones que no hay que cambiar sin avisar:

- **Todos los hitos se cortan por su fecha en el Q**: derivados por Fecha de
  derivación, presupuestados por Fecha de Presupuestado, cerrados por Fecha de
  cierre. Al lado va cuántos vienen de prospectos ingresados en el mismo Q
  (vínculo `LEAD_ID`).
- **"A futuro"** son las cuatro columnas a futuro de Ventas 2.0 y
  Presupuestos 2.0 (`monitor.etapas_a_futuro` en el YAML). En la solapa 1 son
  los prospectos del Q que hoy están ahí; en la 4, la cartera entera de hoy.
- **Asesor** es el Responsable actual de la negociación. Desde el 05/10/2026
  el webhook tiene permiso de usuarios y la ingesta guarda los nombres del
  CRM en `catalogos.usuarios` del snapshot (incluidos los inactivos).
  `monitor.asesores` del YAML queda solo como respaldo; un ID que no existe
  en el CRM (usuario borrado) aparece como "Usuario #ID".
- **El podio** suma 3-2-1 puntos en cuatro rankings: más derivados, más
  cierres, más presupuestos y menor % de no calificados (este último solo
  entre canales con 15 prospectos o más). Tres de los cuatro son volumen: no
  lo presentes como el canal más eficiente.
- Las series semanales van de **sábado a viernes** (lo que entra el sábado
  lo trabaja SDR la semana siguiente; pedido de Joana, 08/10/2026). La
  primera y la última semana del Q quedan recortadas por los bordes del Q.
  La semana N del Q se compara contra la semana N del Q anterior. En el Q2 2026 la semana 2 tiene la carga masiva de abril.
- La ingesta ahora trae también las **actividades** (las de prospectos desde
  el inicio del histórico y las pendientes de las negociaciones a futuro), el
  tipo de negocio, el tipo de plan y los nombres de etapa. Se guardan
  compactas porque el snapshot se versiona.

**Cada KPI se compara contra el mismo tramo del Q anterior** (del día 1 al
mismo día del trimestre) y lleva una pastilla: roja si empeoró más que su
umbral, verde si mejoró más que su umbral, gris si se movió menos, y "sin
lectura" las dos primeras semanas del Q o con poco volumen. Los umbrales y
los mínimos están en `monitor.desmejora` del YAML. El Q2 2026 tiene la carga
masiva de abril, así que el Q3 contra el Q2 sale peor de lo que es: decilo
siempre que cites esa comparación.

La UI (desde el 30/09/2026, por pedido de Joana) es de panel de
administración: barra lateral con las solapas y los Q, tarjetas KPI arriba,
gráfico grande, gauges y tablas de ranking. En el teléfono la barra lateral
pasa a una barra de solapas arriba.

**Objetivos del Q** (desde el Q4 2026, fijados por la dirección): cinco
tarjetas arriba de la solapa 1, cada una verde (en objetivo) o roja (fuera).
Las metas viven en `monitor.objetivos` del YAML, por Q de inicio.

| Objetivo | Meta Q4 2026 | Cómo se calcula |
|---|---|---|
| CAC | ≤ US$ 800 | toda la inversión del Q (pauta + otros gastos del SPA) ÷ clientes nuevos del Q |
| ROAS de pauta | ≥ 2 | MRR cerrado en el Q de Meta, Google y Redes ÷ inversión en esos canales |
| Leads no calificados | ≤ 15% | Prospecto no útil ÷ generados del Q |
| Leads generados | 300 en el Q | se juzga por ritmo: lo generado proyectado a los días del Q |
| Casas de repuestos | ≥ 70% | tipo de negocio del prospecto, sobre los que lo tienen definido |
| Win rate | ≥ 5% | cierres del Q ÷ leads generados del Q |
| New MRR | US$ 7.500 en el Q | MRR cerrado en el Q, por ritmo (tarjeta grande) |
| · Acciones en vivo | US$ 1.000 | MRR de clientes cuyo origen empieza con "Curso", "Webinar" o "Charla", por ritmo |
| · Canales no pagos | > 15% del MRR | MRR que no viene de Meta ni Google (sin atribuir no cuenta) |

Orden de la solapa 1: objetivos (cartitas y debajo la tarjeta grande de New
MRR), el funnel del trimestre en horizontal (generados → derivados →
presupuestados → cerrados, con el % que pasa de un paso al siguiente) y el
CAC por canal. El % de prospecto inactivo vive en Derivación; el % de leads
a futuro y el promedio de días de cierre, en Ventas.

En el Q que tiene objetivos, la solapa no repite métricas: leads generados,
% de no calificación, win rate, MRR y CAC general viven solo en las
tarjetas de objetivos. Los Q sin objetivos muestran el armado anterior.
El CAC se calcula solo con lo que hay en el CRM, por decisión de Joana.

Acciones en vivo se define por el NOMBRE del origen, no por canal: todo
origen que empiece con Curso, Webinar o Charla (`monitor.prefijos_en_vivo`),
más los orígenes sueltos de `monitor.origenes_en_vivo` (hoy "Demo masiva en
vivo").
Vendedores Viajantes no es acción en vivo (cuenta como no pago). Cuando
Joana cree un evento nuevo, su origen tiene que llevar ese prefijo para
entrar solo.

Con pocos casos la tarjeta dice "provisorio" (menos de 5 cierres para CAC y
ROAS, menos de 30 leads para los %, primeras dos semanas para el ritmo). El
SPA hoy solo tiene inversión en pauta: si el CAC de 800 incluye sueldos,
comisiones o herramientas, hay que cargarlos en el SPA (tipos 1424-1430) y el
CAC los suma solo. Decilo siempre que leas el CAC contra la meta.

El bloque de salud del dato del Q aparece arriba de la solapa 1. La regla
sigue siendo la misma: si dice que falta gasto, el CPL y el CAC salen baratos.

## Razones de no derivación

Salen del campo **Razón de no derivación del prospecto** (`UF_CRM_1772731499441`),
no del motivo de caída de la negociación. Un prospecto que no se deriva nunca
llega a ser negociación, así que ese motivo no existe para él. Además el campo
del prospecto está cargado en el 97% de los "Prospecto no útil" y el 94% de los
"Prospecto inactivo", contra un campo de negociación con cuatro valores
genéricos que casi no se usa.

Los dos estados significan cosas distintas y no hay que sumarlos sin aclararlo:
**no útil** es un descarte por calidad, **inactivo** es uno que se enfrió o no
respondió.

## Velocidad del funnel — fuera del dashboard por ahora

El cálculo sigue existiendo (`python3 run.py report` lo imprime) pero **no se
muestra en ninguna solapa del dashboard**, por decisión de Joana en septiembre
de 2026. No lo vuelvas a agregar sin que lo pida.

## Por qué una alerta puede contradecir a los titulares

No se contradicen: miran ventanas distintas. Las alertas usan **ventanas
móviles** (7 días para CPL y volumen, 28 para conversión y CAC) y se calculan
**por canal**; los números del Monitor son **del trimestre** y
**generales**. Que el CAC de Google suba en la ventana de 28 días y el CAC
general del mes baje es perfectamente posible.

Por eso cada alerta muestra sus fechas exactas y el cálculo crudo de los dos
lados —"$111 ÷ 1 cierre contra $155 ÷ 4 cierres"—: sin eso, un "+186%" no se
puede verificar ni descartar y el equipo termina ignorando el bloque entero.

El n mínimo se aplica sobre lo que la métrica realmente cuenta: prospectos
para CPL, derivación y volumen; **cierres** para CAC y conversión. Pedirle 15
prospectos a una alerta de CAC no la protege de nada, porque con un solo
cierre el CAC se duplica o se parte al medio según dónde caiga.

## La alarma diaria (la única alerta que queda)

```bash
python3 run.py alarma     # diaria: solo imprime si hay algo
```

**El informe semanal se dio de baja el 30/09/2026**, por pedido de Joana:
toda la información vive en el Monitor. La rutina de los lunes está
desactivada y `run.py semanal` queda solo para consultas a mano.

**La alarma diaria es una alarma.** Solo habla si algo se rompió o si un
número del Monitor pasó a rojo. Si empieza a sonar todos los días, está mal
calibrada y hay que subir umbrales, no acostumbrarse.

Sus reglas: sin prospectos en todo el día; Meta callado un día y Google dos;
inversión del SPA con más de 7 días sin cargar; prospectos sin origen; origen
sin mapear; y **monitor_desmejora**: un KPI del Monitor que hoy está en rojo
y en el snapshot anterior no lo estaba. Avisa el día del cambio y no lo
repite mientras siga en rojo; si el snapshot anterior es de otro Q, cuenta
como que antes no había nada en rojo.

**La alarma no controla cuánto tarda cada prospecto en resolverse.** Hubo una
regla de "4 días hábiles sin convertir ni descartar" y se sacó: hay prospectos
que legítimamente pasan más tiempo según el tratamiento que les da SDR.

Calibraciones heredadas del informe semanal, por si se vuelve a usar:

Dos calibraciones que no hay que deshacer sin medir de nuevo:

- **El % de no calificación no usa umbral simple.** Su mediana histórica es
  exactamente 15,0%, con la mitad de las semanas arriba y la mitad abajo: como
  umbral sonaría a cara o cruz. Se alerta cuando se sostiene arriba del 15%
  dos semanas seguidas, o cuando salta por encima del 20%.
- **Los cierres van a la tabla sin juicio.** Con 1 a 4 por semana, pasar de 4
  a 1 no distingue un problema de la suerte. Su lectura es mensual.

### Las rutinas programadas

| Rutina | Cuándo | Qué hace |
|---|---|---|
| Agente Growth · Monitor y alarma diaria | todos los días 9:00 ART | refresca el gasto de Meta del día cerrado, ingesta, republica el Monitor y manda la alarma **solo si hay algo** |
| Agente Growth · Informe semanal del funnel | desactivada desde el 30/09/2026 | — |

Cada corrida arranca en una **sesión nueva**, así que los prompts de las dos
rutinas son instrucciones completas y no asumen contexto previo.

Esa sesión nueva necesita que la rutina tenga **el repositorio configurado
como fuente**. Eso no se puede setear desde la herramienta de rutinas: se
elige en claude.ai → Routines, igual que los conectores. Entre el 19 y el 21
de septiembre las dos rutinas estuvieron sin fuente y las tres corridas
murieron antes de leer nada, avisando por Slack que no encontraban el
repositorio. Joana lo configuró el 21 a la tarde.

**No intentes resolverlo desde adentro de la corrida.** El repositorio es
privado, la sesión de rutina no tiene `add_repo` ni credenciales de git, y un
clon directo falla. Si `run.py` no está, lo único correcto es avisar por Slack
que hay que revisar la configuración de la rutina y terminar.

Las dos necesitan **dos conectores adjuntos: Slack y Meta.** Slack para
publicar y Meta para refrescar `data/meta_spend.json`. Las rutinas creadas por
herramienta no guardan conectores propios, así que se adjuntan a mano desde
claude.ai → Routines. Sin Meta, la corrida no puede actualizar el gasto y el
CPL sale barato; sin Slack, no llega el mensaje.

El canal es `C0C2XKTLT9N` (#adqui-notificaciones-canales).

No hay informe mensual: la comparación contra dos semanas ya muestra si algo
mejora o empeora, y un mensual más sería ruido acumulado.

## Reglas de lectura — no las saltees

1. **Primero la salud del dato, después las métricas.** Si el gasto del
   período está cargado a medias, el CPL y el CAC salen baratos y no
   significan nada. El dashboard lo marca; el análisis también tiene que
   decirlo antes de cualquier conclusión.
2. **Nunca leas el CAC ni las conversiones a 7 días.** El ciclo mediano
   hasta el cierre ronda los 70 días: una semana no alcanza para que un
   cierre aparezca. CPL y volumen sí aguantan lectura semanal.
3. **Nunca afirmes nada de un canal con menos de 15 prospectos en la
   ventana.** Con ~230 prospectos y ~12 cierres por mes, el ruido domina.
4. **Un CPL barato no es un buen canal.** Mirá siempre el costo por derivado
   y por presupuesto al lado. En agosto 2026 Meta trajo 6 veces más volumen
   que Google y derivó al 15,7% contra el 59,1% de Google: el CPL solo
   escondía eso.
5. **Un porcentaje por encima de 100% no es un error.** El numerador cuenta
   hitos del período y el denominador, prospectos creados en el período:
   en canales de ciclo largo se derivan negociaciones que entraron antes.
6. **El mes en curso no se compara contra un mes completo.** El titular es
   siempre el último mes cerrado, y las series semanales del Q cortan en la
   última semana completa.

## Sumar un canal nuevo

1. Buscá el `SOURCE_ID` del origen: `crm.status.list` con `ENTITY_ID="SOURCE"`.
2. Agregalo a un canal en `config/definitions.yaml` (o creá el canal).
3. Si tiene inversión, agregá su tipo de gasto del SPA en `tipos_gasto` y
   poné `activo: true`.
4. Recalculá: `python3 run.py daily`.

El panel de salud avisa solo cuando aparece un origen nuevo sin mapear, así
que no hace falta revisarlo a mano.

## Experimentos

Desde el 05/10/2026 se muestran en la solapa **Experimentos** del Monitor,
por pedido de Joana: una card por experimento que abre un popup con todo el
detalle. Se agrupan por el Q de su fecha de lanzamiento y el registro arranca
en el Q4 2026 (los Q anteriores muestran un aviso). Son pruebas sobre la
**generación** de los canales que ya tenemos.

Cada experimento es un archivo `experiments/EXP-NNN-nombre-corto.md` que copia
`TEMPLATE.md`. Los campos que pide el Monitor: `nombre`, `descripcion`,
`problema`, `hipotesis`, `datos` (lista de números que la respaldan),
`solucion`, `lanzamiento`, `fin_analisis`, y para el cierre `resultado`
(conclusión escrita) y `decision`. Además `canal`, `estado`,
`metrica_primaria`, `efecto_esperado` y `n_minimo`.

**Cargar uno cuando lo pidan:** armá el archivo con lo que dio la persona,
completá `datos` con números reales del Monitor (nunca inventados), definí con
ella la métrica primaria y el `n_minimo` antes de lanzar, usá
`experiments.siguiente_id()` para el id, corré `python3 run.py dashboard`,
republicá en el mismo link y commiteá. Si falta un campo, preguntalo: no lo
completes por tu cuenta.

**Experimentos sobre un conjunto de Meta** (`conjunto_meta` en el archivo):
se juzgan por los leads diarios que reporta Meta para ese conjunto contra
`meta_leads_dia`, con al menos 7 días de datos. Los datos viven en
`data/meta_adsets.json` y los refresca la corrida diaria (paso 1b). El canal
entero queda como contexto. EXP-001 se mide así desde el 07/10/2026, por
pedido de Joana.

**El resultado en métricas se calcula solo** (`experiments.resultado`): el
canal entre lanzamiento y fin de análisis (o hasta hoy) contra el mismo largo
de tiempo inmediatamente anterior, todo sobre la camada (prospectos creados
en cada tramo). Mide generados, CPL, % de derivación, costo por derivado, %
de no calificación y presupuestados. La camada del experimento es más nueva y
todavía no maduró: no declares un resultado antes de que pase el fin de
análisis y se junte el `n_minimo` (el popup dice "Listo para leer").

Al proponer un experimento nuevo, fundamentalo en un número del período, no
en una idea suelta, y decí cuántos prospectos necesita y cuánto va a tardar en
poder leerse. Un experimento por canal a la vez.

## Qué NO hace este agente

El detalle de campaña, ad set y creativo es del agente de Meta Ads. Acá se
mira el panorama de todos los canales de adquisición. Si la conclusión
depende de qué creativo rinde mejor, decilo y derivá, no lo calcules acá.
