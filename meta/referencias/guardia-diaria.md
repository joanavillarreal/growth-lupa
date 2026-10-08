# La guardia diaria — que mira, que calla y que manda

**Corre todos los dias a las 8:00 ART.** No es un informe: es un centinela.
Existe para que Joana **no tenga que entrar al Administrador de anuncios a
buscar si algo se rompio**. Si no hay nada, no escribe.

Decidido por Joana el 2026-09-15, junto con sacar la corrida del jueves: lo que
el jueves miraba una vez por semana, la guardia lo mira todos los dias.

## La regla que la hace util: el silencio

Una alerta que llega todos los dias deja de leerse en una semana. Entonces:

- **Si no hay nada que decir, no se manda nada a Slack** y no se commitea nada.
- **Una alerta ya avisada no se repite.** Vuelve solo si **escala** (el problema
  crece: de 4 dias sin resultados a 7) o si pasaron los dias de recordatorio
  (`repeticion.recordar_cada_dias`, hoy 7).
- El estado vive en **`memoria/guardia.jsonl`**, una linea por alerta. Lo
  escribe el script solo.

**Lo unico que nunca se calla es no haber podido mirar.** Si el MCP no contesta
dos veces seguidas, eso ES la noticia del dia y se avisa. Un silencio por falta
de datos se lee como "esta todo bien" y es lo contrario.

## Lo que mira

| | Que busca | Umbral |
|---|---|---|
| **G0** | la cuenta dejo de gastar, o **el detalle diario perdio anuncios** | gasto de ayer = 0 · faltan entidades que si estan en el total |
| **G1** | errores de entrega en entidades que **estan corriendo hoy** | cualquiera |
| **G2** | anuncio activo que gasta y no trae **ningun** resultado | dia 1 si quemo ≥6.000 ARS · o 2 dias seguidos |
| **G3** | costo por resultado subiendo, o CTR cayendo | de un dia para el otro · o 3 dias bajo la base |
| **G4** | **plata que se va sin volver** | ver abajo |
| **G5** | **leads que Meta cobra y en el CRM no estan** | ver abajo |
| **G6** | **ayer no entro ningun lead de Meta al CRM** (Joana, 2026-09-30) | CRM en 0 con ≥5.000 ARS de gasto de captacion; se calla si ya disparo G5a |

Todos los numeros salen de `config/umbrales.yaml` -> `guardia_diaria`.
El script no los tiene hardcodeados: se cambian ahi, no en el codigo.

### G0 y el detalle diario incompleto: por que el aviso nombra anuncios

**La regla siempre estuvo bien; lo que estaba mal era como lo decia.** El aviso
era "los datos del MCP no cierran a nivel anuncio (4,4% de diferencia)", y desde
afuera de la corrida eso no significa nada ni dice que hacer. Joana lo saco el
2026-09-25 por eso.

La primera simulacion despues de sacarlo mostro el problema en vivo: el detalle
diario sumaba 361.312 ARS contra 377.906 del total, **faltaban 4 de 18 anuncios
y los cuatro eran los creativos nuevos** (Meme reel - IA, Testimonio - Mendez,
DemoIA, AgilidadMostrador). O sea que G2 y G3 corrieron sobre 14 de 18 sin que
nada lo dijera, y los que faltaban eran justo los que hay que vigilar. Joana lo
repuso el mismo dia.

Ahora el aviso **nombra los anuncios que faltan y cuanto gastaron**, y dice la
consecuencia en una linea: *las alertas de hoy miran una cuenta incompleta*.

**El gasto total del periodo NO esta mal cuando esto pasa** — a nivel campana
cuadra exacto. Lo que falta es el desglose por anuncio, asi que lo que no se
puede leer son G2 y G3, no el gasto.

### G2 y G3 avisan desde el primer dia (cambio del 2026-09-25)

Pedido de Joana: antes G2 esperaba 4 dias y G3 tres. Ahora avisan apenas pasa.
**El cambio no es bajar el umbral: es cambiar que lo filtra.**

El problema de avisar el dia 1 a secas es el tamano de la muestra. Esta cuenta
hace **entre 3 y 10 leads por dia en total**, repartidos en ~10 anuncios:

- Casi cualquier anuncio tiene cero resultados casi cualquier dia. No es una
  falla, es aritmetica.
- Una campana que pasa de 3 leads a 2 muestra el costo por resultado "subiendo"
  50% sin que haya pasado nada. Aritmetica de enteros, no deterioro.

Medido sobre 14 dias, avisar el dia 1 **sin filtro** daba 2,8 mensajes por dia,
todos los dias. Con los filtros de volumen, 1,0. Lo que filtra no son los dias:

| Regla | Que la habilita a hablar el dia 1 |
|---|---|
| **G2** | que haya quemado **6.000 ARS** (dos veces el CPL objetivo) sin traer nada |
| **G3 costo por resultado** | que el dia con el que compara tenga **≥3 resultados** |
| **G3 CTR** | que los dos dias tengan **≥1.500 impresiones** (antes 500) |

**G3 tiene DOS disparos y hacen falta los dos.** El rapido mira ayer contra
anteayer. El sostenido mira 3 dias contra la base de 7. Una metrica que se cae
y **se queda abajo** no empeora de un dia para el otro, asi que el rapido no la
ve — y ese es justo el caso de fatiga de creativo, el mas comun de todos.
Cambiar uno por el otro habria cambiado un punto ciego por otro.

Cuando dispara el rapido, el aviso dice **cuanto** se movio y en cuantos dias
("Subio 68% en 3 dias, de 2.400 a 4.032 ARS"), no solo que se movio. Tambien
pedido de Joana.

**El precio, dicho en numeros:** la guardia paso de ~0,14 mensajes por dia a
~1,0. Sigue callada cuando no pasa nada, pero ya no es raro que hable. Si eso
se vuelve ruido, los dos botones son `cpl.suba_pct` (30 → 40) y
`cpl.resultados_minimos_dia_base` (3 → 4).

### G4 — gastos innecesarios

Pedido de Joana el 2026-09-15. **Ninguna de las tres es "esta caro":** la cuenta
puede estar cara y no tener nada de esto, o estar barata y tener las tres. Lo
que busca es gasto que **no puede** producir nada.

**G4a · El evento que ya paso y sigue gastando.** Una campana de webinar que
gasta despues del webinar es plata tirada sin matices: nadie se puede anotar a
algo que ya ocurrio. Es la unica de las tres que no admite interpretacion, y por
eso es la que mas vale.

Sale de **`fecha_evento`** en `config/campanas.json` — campo opcional que carga
**Joana** al dar de alta la campana del evento:

```json
{"nombre": "JY | Webinar Mostrador - 17 SEPT 2026", "grupo": "eventual",
 "bloque": "evento", "fecha_evento": "2026-09-17", ...}
```

**Sin ese campo la guardia no opina de esa campana, y esta bien que sea asi.**
Adivinar la fecha del nombre ("17 SEPT 2026") funciona hasta que una campana se
llama distinto — y ahi el agente avisa que hay que apagar plata que si estaba
rindiendo. **Cargar la fecha es parte de dar de alta un evento.**

**G4b · El anuncio que quema al mismo publico.** Frecuencia de la ventana por
encima de `frecuencia_maxima_ventana` (5,0): se le esta pagando a Meta por
mostrarle el mismo anuncio a la misma gente. Ese 5,0 sale de proporcionar el
umbral propio del canal (2,5 en 7 dias) a los 14 dias de la ventana.

**La frecuencia se lee del total de la ventana, NUNCA sumando filas diarias.**
Sumar los dias cuenta dos veces a quien vio el anuncio dos dias: por eso hace
falta `anuncio-total.json` y no alcanza con la serie. Medido el 2026-09-11, el
boton a WhatsApp tenia frecuencia **7,95**. Se arregla rotando creativo o
ampliando publico, **no subiendo presupuesto**.

**G4c · Cuanto de la ventana se fue sin un solo resultado.** Suma lo que
gastaron los anuncios que no trajeron nada y lo dice en ARS y en % de la
ventana. Es el numero que contesta *"cuanta plata estamos tirando"*, que G2 no
contesta: G2 mira **un anuncio y su racha**, esto mira **la cuenta y su total**.

Pide las dos condiciones juntas —`>=20.000 ARS` **y** `>=10%` de la ventana—
para que un numero chico no dispare. Y arrastra la salvedad de siempre: **"sin
atribuir" no es "sin lead"**, el numero firme sale del cruce del lunes.

**Ninguna de las tres pausa nada.** Se avisa la plata identificada y decide
Joana. Vale entera la trampa 6: cortar algo porque su costo promedio es alto
suele subir el costo total.

### G5 — los leads que Meta cobra y en el CRM no estan

Pedido de Joana el 2026-09-25. **Es la primera regla de la guardia que mira
fuera de la plataforma**, y cambia una decision vieja: hasta ahora la guardia
era plataforma y nada mas, y el CRM era del lunes. Sigue siendo cierto que el
**veredicto** es del lunes; lo que se adelanta al dia siguiente es una sola
pregunta, la mas barata de contestar y la mas cara de descubrir tarde:
*¿los leads que pagamos estan entrando al CRM?*

**La trampa: el hueco es cronico.** Medido sobre 82 dias (jul-sep 2026), la
conciliacion diaria da **69%**, no 100%. Hay re-ingresos que no generan
prospecto —y esta bien (EXP-002)— y leads que Meta cobra y el CRM nunca ve. Una
regla "Meta > CRM" habria disparado **39 de 51 dias**. Seria ruido puro y en una
semana nadie la lee.

Por eso G5 no busca el hueco. Busca **la tuberia cortada**, que no se le parece:
el hueco deja pasar la mayoria, una tuberia cortada no deja pasar ninguno.

**G5a · El CRM en cero habiendo leads en Meta.** Ayer Meta atribuyo
`minimo_leads_meta` (4) resultados o mas de los que **deberian** crear prospecto,
y el CRM no creo **ninguno** en los origenes *Meta Ads Formulario* y *Meta Ads*.
Sobre los 82 dias habria disparado **una vez**. Es el sintoma de n8n caido, del
webhook de leadgen desconectado o del formulario despegado del CRM.

`valor` es la racha de dias, asi que si sigue cortada manana la alerta **escala
sola** y vuelve a sonar en vez de quedar dormida por el dedup.

**G5b · La conciliacion de la ventana se derrumba.** Agarra la rotura parcial,
que G5a no ve: la mitad de los leads dejan de entrar. Ventana de 7 dias, piso en
**25%** contra un normal de 69%, y pide `minimo_leads_meta_ventana` (10) para
que una semana flaca no dispare sola. Sobre los 82 dias: **0 disparos** — el
minimo historico fue 30%.

#### La cuenta tiene TRES patas, no dos

Pedido de Joana el 2026-09-25, y es lo que vuelve accionable a G5:

```
Meta cobro 10  ·  el CRM creo 6  ·  Slack aviso 2 re-ingresos
        -> quedan 2 sin explicar
```

**Por que la tercera pata cambia todo.** Cuando alguien que ya existe en Bitrix
vuelve a completar el formulario, el workflow **no crea un prospecto**: le
avisa a la SDR en `#adqui-automatizaciones` y termina ahi (decision de Joana,
2026-09-09, EXP-002). Meta igual lo cobra. Sin contar esos avisos, esos leads
se ven como perdidos **y no lo estan**: llegaron a quien tenian que llegar.

Los dos avisos que cuentan, los dos del bot Botrix:

| Aviso | Que es |
|---|---|
| `RE-INGRESO DE LEAD EXISTENTE` | volvio a completar un formulario |
| `RECONTACTO DE LEAD EXISTENTE` | volvio a escribir por Hyperflow (WhatsApp) |

**G5a ya no dispara por el hueco crudo sino por lo que queda sin explicar.**
Eso solo puede hacerla disparar MENOS, nunca mas, asi que la calibracion de los
82 dias sigue siendo un techo valido.

**Limite que hay que nombrar cada vez que se reporta:** el aviso **no dice de
que formulario vino**, y ese mismo workflow tambien recibe los formularios web.
Entonces lo que se descuenta es un **techo** de lo que explica: puede perdonar
de mas, nunca de menos. Por eso el aviso lo aclara en el texto.

**Lo trae el agente, no el script.** Las herramientas de Slack son MCP y un
script de Python no las puede llamar — la misma razon por la que los datos de
Meta pasan por el agente. Van a
`datos/meta-ads/guardia/<AAAA-MM-DD>/slack/avisos-slack.json`:

```json
{"desde": "2026-09-17", "hasta": "2026-09-23",
 "por_dia": {"2026-09-17": 1, "2026-09-18": 0, "...": 0}}
```

**Si el archivo no esta, G5 igual corre** con dos patas y lo dice en el aviso,
en vez de fingir que el descuento se hizo.

**G5c · No se pudo mirar el CRM.** Si Bitrix no contesta, **se avisa**. Es la
misma regla que con el MCP: un silencio por falta de datos se lee como "esta
todo bien" y es lo contrario.

#### Que resultados de Meta cuentan

No todos. La cuenta de un lado tiene que ser la misma que la del otro:

- Solo familias **`lead` y `mensaje`**. Una visita al perfil de una campana de
  awareness no genera prospecto: contarla daria un hueco permanente inventado.
- Solo bloques **conversion y remarketing**. Las campanas eventuales (webinar,
  curso, presencial) guardan sus leads en **su propio origen** del CRM.
- **Se restan los conjuntos de evento** que cuelgan de una campana nucleo: son
  parte de la campana en Meta pero van a otro origen en el CRM.

Es la misma definicion de "cruzable" de `analizar_meta.py` y del panel, y el
script la **importa** (`FAMILIA`, `CONJUNTOS_DE_EVENTO`, `bloque_de`) en vez de
reescribirla. Si el criterio cambia, cambia en un solo lugar.

#### La hora, que es la trampa que faltaba

Bitrix devuelve `DATE_CREATE` en la zona del portal, **+03:00**, seis horas
adelante de ART: un lead de las 21:00 del lunes vuelve como martes. Con una
regla que mira "ayer", leer la fecha cruda **inventaria un hueco cada noche**.
Por eso G5 no arma su propia llamada: levanta `traer_prospectos.py`, que ya pide
un dia de mas y convierte a hora argentina.

### Lo que NO mira, y por que

- **El saldo de la cuenta.** *No existe en el MCP*: probado el 2026-09-15,
  `balance`, `account_status` y `funding_source` vuelven como `unknown_fields`.
  Joana pidio el aviso de "nos estamos quedando sin saldo" y **se saco a
  proposito** (2026-09-15) en vez de fingirlo con un proxy. Lo mas cerca que se
  puede estar es G0: si la cuenta deja de gastar de golpe, la guardia avisa.
  **Si alguien lo quiere de vuelta, primero hay que encontrar de donde sacar el
  dato — no alcanza con agregar una regla.**
- **Calidad de lead, CPL real, derivacion, tipo de negocio.** Eso sale el lunes.
  Desde el 2026-09-25 la guardia **si** toca el CRM, pero solo para contar
  cuantos prospectos se crearon (G5). No mira en que etapa estan, ni si derivan,
  ni de que rubro son: contar no es evaluar.
- **Nada que se parezca a una decision.** La guardia avisa; el lunes decide.

## Las llamadas del MCP, exactas

`ad_account_id` siempre **`725901852075382`** (ver `meta-mcp.md`: hay otra cuenta
con nombre parecido que reporta en USD). Un `client_conversation_id` nuevo por
corrida, el mismo en las seis llamadas.

La ventana es de **14 dias terminando ayer** (`guardia_diaria.ventana_dias`):
G3 necesita 3 dias de tramo + 7 de base, y sobra margen.

Cada respuesta se guarda **TAL CUAL** en
`datos/meta-ads/guardia/<AAAA-MM-DD>/mcp/<archivo>`.

| # | Archivo | Llamada |
|---|---|---|
| 1 | `anuncio-diario.json` | `ads_get_ad_entities` · `level:"ad"` · `time_range` de 14 dias · `time_increment:"1"` · filtro `ad.amount_spent GREATER_THAN ["0"]` · fields `name,amount_spent,impressions,reach,frequency,website_ctr,results,cost_per_result,effective_status,cpm,link_click,campaign_name,adset_name` |
| 2 | `anuncio-total.json` | igual pero **sin `time_increment`** — es el control de la trampa 6 |
| 3 | `campana-diario.json` | igual al #1 con `level:"campaign"`, filtro `campaign.amount_spent`, y `objective` en fields |
| 4 | `campana-total.json` | el #3 **sin `time_increment`** |
| 5 | `roster.json` | **las tres llamadas de roster juntas en un mismo archivo** (ver abajo) |
| 6 | `errores.json` | `ads_get_errors` · `entity_ids:["725901852075382"]` · `limit:50` |
| 8 | `anuncio-activos.json` | `ads_get_ad_entities` · `level:"ad"` · `date_preset:"last_7d"` · filtro `ad.effective_status IN ["ACTIVE"]` · fields `name,campaign_name,adset_name,effective_status,created_time,creative_id`. **Solo panel** (vistas Dia a dia y Anuncios activos): se pide al final de la corrida y no se reemplaza por el roster, porque una campana creada a media manana no estaria en el roster de las 8:00 |
| 9 | `conjunto-publicos.json` | `level:"adset"` · `date_preset:"maximum"` · filtro `adset.effective_status IN ["ACTIVE","WITH_ISSUES","PENDING_REVIEW","IN_PROCESS"]` · fields `name,campaign_name,effective_status,targeting,optimization_goal,daily_budget,created_time,amount_spent,results,cost_per_result,reach,impressions`. **Solo panel**: el publico de cada conjunto y lo que genero desde que se creo. La respuesta pesa ~65 KB (el targeting es largo): guardarla del archivo que devuelve la herramienta, no reescribirla |
| 10 | `anuncio-historico.json` | `level:"ad"` · **`time_range` desde `2026-09-08` (el dia que arranca la atribucion por UTM) hasta ayer** (cambiado el 2026-10-07: con `maximum`, un anuncio de julio mezclaba gasto sin UTM y su CPL real salia inflado) · filtro `campaign.id IN [<ids de las campanas ACTIVE del roster>]` + `ad.amount_spent GREATER_THAN ["0"]` · fields `name,campaign_name,adset_name,effective_status,created_time,amount_spent,results,cost_per_result,impressions,link_click,website_ctr,frequency`. **Solo panel** (Tendencias) |
| 11 | `creativos.json` | `ads_get_creatives` · `creative_ids:[<los creative_id del #8 que todavia NO esten en ningun datos/meta-ads/guardia/*/mcp/creativos*.json>]` (desde 2026-10-07 el panel busca cada creativo en todas las corridas; si no falta ninguno, no se llama; `panel_meta.py` lista los que faltan en `hoy.creativos_faltantes`) · fields `name,object_type,body,title,description,call_to_action_type,effective_object_story_id,effective_instagram_media_id,link_url`. **Solo panel** (Anuncios activos): el texto que vio la persona y el link al posteo. Se guarda tal cual (`{"ad_creatives": [...]}`) |
| 7 | `conjunto-diario.json` | igual al #1 con `level:"adset"`, filtro `adset.amount_spent`, y `campaign_name` en fields. **No la usa la guardia: la usa el panel** para descontar los conjuntos de evento que corren adentro de campanas nucleo (desde el 2026-09-27). Sin ella el panel avisa que desde el ultimo CSV del lunes no pudo descontarlos |

### El roster: tres llamadas en un archivo

Sin `time_increment`, sin `time_range` (alcanza `date_preset:"last_7d"`), fields
`name,effective_status` mas los padres. Cada una filtra por estado:

```
level:"campaign"  filtering [{"field":"campaign.effective_status","operator":"IN",
                             "value":["ACTIVE","WITH_ISSUES","PENDING_REVIEW",
                                      "PENDING_BILLING_INFO","IN_PROCESS"]}]
level:"adset"     idem con adset.effective_status,  fields + campaign_name
level:"ad"        idem con ad.effective_status + "DISAPPROVED",
                  fields + campaign_name, adset_name
```

Las tres respuestas van **en el mismo `roster.json`, como una lista JSON**:
`[<respuesta campana>, <respuesta conjunto>, <respuesta anuncio>]`. El script las
desanida solo.

**Por que tres y no una.** Esta es la trampa que mas caro sale de esta regla:

> **El `effective_status` de un anuncio NO hereda la pausa de su campana.**

Medido en esta cuenta el 2026-09-15: pidiendo anuncios con estado
`ACTIVE | WITH_ISSUES | DISAPPROVED` volvieron **70**, y **57 de ellos cuelgan de
campanas apagadas hace meses** — "Hot Sale Mayo 2025", "Campana de Mensajes -
Publico Similar 3%", "HotSale". Sus errores son historia. Si se mandan a Slack,
el aviso real queda enterrado y nadie lo vuelve a abrir.

Entonces el script arma el roster **en cadena**: una entidad esta viva solo si
**su campana esta viva**. Con ese filtro, la misma corrida paso de **70
anuncios a 13**, y de **4 errores a 1** — y ese 1 era real: `Meme IA - Reel
feed`, en `JY | Awareness Boxer Taller`, con *Pages Don't Match*.

## Correr la guardia

```bash
python3 scripts/guardia_diaria.py datos/meta-ads/guardia/<AAAA-MM-DD>/ \
        --json informes/guardia/<AAAA-MM-DD>.json
```

**El CRM lo consulta el script solo.** No hay que traerle nada: usa
`BITRIX_WEBHOOK_URL` del environment y deja la evidencia en
`datos/meta-ads/guardia/<AAAA-MM-DD>/crm/prospectos-<ayer>.json`. Es distinto de
Meta —que pasa por el agente porque las herramientas del MCP no las puede llamar
un script de Python— y Bitrix es un webhook REST, asi que el rodeo no hace falta.

`--sin-crm` corre sin G5. **Solo para probar**: en una corrida de verdad dejaria
la pregunta sin contestar y la guardia callaria por no haber mirado.

**`--dry-run` tampoco escribe la evidencia del CRM**, no solo el estado. Es a
proposito: probar contra la carpeta de una corrida vieja escribiria los
prospectos de HOY adentro de la corrida de OTRO dia, y esa carpeta es lo que
alguien va a leer en dos meses para entender que vio la guardia aquel dia.

Imprime **`SIN NOVEDADES`** o un bloque **`MENSAJE DE SLACK`** ya escrito.
Ese bloque se manda **tal cual**, sin reescribirlo ni adornarlo, al canal
`#adqui-notificaciones-canales` (`C0C2XKTLT9N`, en
`config/cuenta.yaml -> entrega.slack.canal_id`).

**Desde el 2026-09-15 no es el DM de Joana: es un canal del equipo.** El bloque
ya viene escrito para eso — dice el nombre completo de cada campana y anuncio,
la plata con unidad y el periodo. No agregarle contexto de la corrida ni
abreviarlo.

**Desde el 2026-09-27, el bloque separa dos cosas que Joana pidio no mezclar.**
Cuando hay alertas de los dos tipos, el mensaje trae dos secciones:

- **"La cuenta y los anuncios"** — problemas reales: delivery roto (G1), gasto
  sin resultado (G2), CPL/CTR empeorando (G3), plata quemada (G4), la tuberia
  con el CRM cortada (G5a). Esto es lo que hay que mirar en la pauta o en n8n.
- **"El conector (no es un problema de la pauta)"** — la guardia no pudo mirar
  bien: el desglose diario del MCP se comio filas (G0), Bitrix no contesto
  (G5c), o no hay ni una fila de gasto (G0, caso ambiguo). Esto se arregla
  reintentando la llamada, no tocando un anuncio.

`TIPOS_CONECTOR` en `scripts/guardia_diaria.py` es la lista que decide en cual
cae cada alerta. Si aparece un tipo nuevo, hay que sumarlo ahi a mano: por
defecto cae en "la cuenta", que es la seccion que mas importa leer si alguien
solo lee una linea.

```bash
python3 scripts/guardia_diaria.py --autotest      # las reglas, sin tocar disco
python3 scripts/guardia_diaria.py <carpeta> --dry-run   # sin gastar el silencio
```

**`--dry-run` importa:** una corrida normal marca las alertas como avisadas. Si
se prueba sin `--dry-run`, la de manana se calla porque cree que ya aviso.

## Que hace el agente despues

**Pase lo que pase con las alertas, despues se actualiza el panel trimestral**
(`referencias/panel.md` -> "Como se actualiza, todos los dias"). No manda nada
a Slack y se commitea aparte.

1. **Nada que disparo** -> no manda Slack, no commitea, termina. Es el caso
   normal y es el correcto.
2. **Algo disparo** -> manda el bloque al canal y commitea `memoria/guardia.jsonl`,
   el JSON del dia, los JSON crudos del MCP y `crm/prospectos-<ayer>.json`.
   Mensaje de commit: `Guardia <AAAA-MM-DD>: <n> alertas` .
3. **Una alerta de G1 sobre algo que Joana toco a proposito** (lo dice
   `memoria/bitacora-cambios.md`) -> no es alerta. Anotarlo en el estado y
   seguir. Ya paso una vez: A18, 2026-09-11, un conjunto sin activar que parecia
   roto.
4. **Si un dia la guardia encuentra algo grande** (entrega caida de la cuenta,
   todos los anuncios rechazados) -> avisa igual y **no intenta arreglarlo**.
   `escritura.nivel` sigue en `ninguno`: el agente propone, Joana ejecuta.

## Lo que la guardia NO puede afirmar

- **"Este anuncio no trae leads."** Lo que sabe es que **Meta no le atribuyo
  resultados**. Con 0% de UTM hasta el 08/09, un lead puede estar en el CRM sin
  que Meta lo cuente. El aviso lo dice asi y manda el veredicto al lunes.
- **"Hay que pausar esto."** Nunca, y menos por un costo promedio alto en un
  desglose: es el efecto de descomposicion (trampa 6 del SKILL). G3 abre una
  **hipotesis**, no una accion.
- **"Faltan N leads."** G5 compara **resultados que Meta atribuye** contra
  **prospectos creados**, y esas dos cosas no tienen por que dar igual ni en una
  cuenta sana: el normal de esta es 69%. Lo que la alerta afirma es "hay un cero
  donde deberia haber algo", nunca "nos robaron N leads". El numero firme sale
  del cruce del lunes.
- **"Esta todo bien."** Solo puede decir que no encontro nada de lo que mira.


### G6 — un dia sin leads en el CRM (2026-09-30)

Pedido de Joana: "tomemos como alarma los dias que no generen nada a nivel
leads en el CRM". Mira el **resultado**, no la tuberia: dispara aunque Meta
tampoco haya atribuido nada. Si G5a ya disparo, G6 se calla (ese cero ya tiene
mejor explicacion). `valor` es la racha, asi que un segundo dia en cero escala.

**El piso de 5 leads/dia que definio Joana el mismo dia NO es una alarma**, y es
a proposito: sobre el Q3 (91 dias al 29/09) solo 27 dias llegaron a 5, asi que
como alerta sonaria 2 de cada 3 dias y dejaria de leerse. Vive en
`config/umbrales.yaml -> objetivos.leads_crm_por_dia` y se mide en el panel y el
lunes, por semana (35). El cero, en cambio, paso 5 dias de 91 — y 2 de esos
fueron la falla de n8n del 23-24/09.
