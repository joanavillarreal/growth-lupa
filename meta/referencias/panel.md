# El panel trimestral — que contesta y como se mantiene

**El segundo artefacto del canal, y no reemplaza al semanal.** El semanal
contesta *"como fue la semana"*; este contesta *"como se viene moviendo el
trimestre y que le hicimos"*. Pedido de Joana el 2026-09-21.

- **URL estable:** se republica desde `informes/panel-trimestral.html`.
- **Q calendario:** Q3 es julio a septiembre (Joana, 2026-09-21).
- **Titulo estable:** *Panel Meta Ads*. **No se cambia**: Joana lo tiene pineado
  con ese nombre y hace juego con *Panel Growth*. La referencia decia *Meta Ads
  por trimestre* y el HTML tambien, pero lo publicado se llamaba *Panel Meta
  Ads* desde siempre; se alineo el repo con lo publicado el 2026-09-22, no al
  reves, porque republicar con otro titulo le renombra el pin.

## Tres vistas, con un menu a la izquierda (Joana, 2026-09-29)

| Vista | Que contesta | De donde sale |
|---|---|---|
| **Trimestres** (el en curso y el anterior) | todo lo de abajo: las cuatro preguntas, mes a mes, dia a dia, campanas | CSV + guardia + CRM |
| **Dia a dia** | que esta corriendo hoy: anuncios activos por tipo (conversion, remarketing, awareness, eventos) y por producto (Boxer Gestion / Boxer Taller); por campana, a que publico apunta cada conjunto, a quien excluye y lo que genero desde que se creo | llamadas #8 y #9 de la corrida diaria |
| **Tendencias** | en cada campana activa, que anuncio trae mas resultados a menor costo, con el CRM al lado | llamada #10 + leads con UTM |
| **Anuncios activos** (Joana, 2026-10-05) | para la SDR: cada anuncio activo por campana, con su texto, su boton, el link para verlo, a que formulario apunta y a que origen de Bitrix entra el lead | llamadas #8 y #11 + `config/campanas.json` + leads con UTM |

**El formulario de cada anuncio no lo da Meta.** El MCP no expone el
formulario del creativo (ni `ads_get_creatives` ni la vista previa). Se resuelve
asi, en este orden:
1. **Confirmado:** si el anuncio ya trajo leads con UTM, el formulario es su
   `utm_campaign` (n8n manda ahi el nombre del formulario, ver `n8n.md`).
2. **Segun el mapa:** si todavia no trajo leads, `config/campanas.json ->
   formulario` de su campana (cargado para Conversiones y Remarketing:
   *Formulario anuncios 1*).
3. **Sin confirmar:** si no hay ninguna de las dos, el panel lo dice en ambar.
   Pasa con las eventuales (cursos, presenciales), que tienen su propio
   formulario y workflow. Para cerrarlo: cargar `formulario` en el config.

**Los links:** *Ver el anuncio* abre `facebook.com/<effective_object_story_id>`,
el posteo del anuncio (estable; los `preview_url` de la vista previa vienen
firmados y vencen). *Abrir en el Administrador* necesita acceso a la cuenta.

- **Los filtros van plegados** (Joana: "no los dejaria visibles"). Un boton
  *Filtros* abre mes, tipo de negocio y destino; el boton muestra cuantos hay
  puestos. El trimestre se elige en el menu, no en los filtros. Abre en el
  trimestre en curso, entero.
- **Producto:** `config/campanas.json -> producto: boxer_taller` es Boxer
  Taller; todo lo demas es Boxer Gestion. Una campana nueva de Taller tiene que
  entrar al config con ese campo o se cuenta como Gestion.
- **Activo = `ACTIVE`, nada mas.** El MCP devuelve decenas de `WITH_ISSUES` de
  campanas de 2024-2025 apagadas; contarlas inflaria lo que corre hoy.
- **El publico se resume, no se transcribe:** edad, pais, publicos incluidos
  (propios y similares), intereses y cargos, excluidos, y si Advantage+ esta
  prendido (Meta puede salir del publico). Las ubicaciones quedan afuera: dicen
  donde, no a quien.
- **Por conjunto (Joana, 2026-10-07).** En el trimestre, al abrir una campana se
  ve un renglon por conjunto (gasto de `conj_dias`, leads del CRM por
  `utm_term`, CPL real, ICP, derivados) y debajo sus anuncios. "Mejor conjunto"
  = menor CPL real entre los que trajeron 5+ leads al CRM. Tendencias agrupa
  por campana y conjunto: el mejor anuncio de cada conjunto se elige por **CPL
  real** (gasto desde el 08/09 / leads del CRM con su `utm_content`) entre los
  que trajeron 5+ leads; si ninguno llega, por el costo de Meta. Avisa cuando
  otro anuncio deriva 15 puntos mas, cuando Meta le da 70%+ del gasto a uno
  solo (los demas no tuvieron chance) y los que tienen menos de 1.000
  impresiones. **Comparar anuncios dentro de un conjunto esta sesgado** porque
  Meta no reparte parejo: para una comparacion limpia, prueba A/B de Meta.
- **Tendencias — la regla del mejor anuncio (version anterior, solo Meta):** menor costo por resultado entre
  los que ya tienen volumen (5 clientes potenciales o 100 visitas al perfil).
  Con menos, un costo bajo es suerte. Ademas avisa: si el mejor esta pausado,
  si el que mas gasta es bastante mas caro que el mejor, frecuencia >= 3,5
  (fatiga), y si el mas barato trae menos ICP en el CRM que el promedio de la
  campana. **Es una lectura, no una orden de pausar** (trampa 6 del SKILL).
  El CRM se cruza por `utm_content` = nombre del anuncio y `utm_term` = conjunto.

## Que contesta, y en que orden (Joana, 2026-09-27)

> "Lo primero que tengo que ver es si el canal esta gastando mas o menos y si
> esta generando mas o menos, si lo que esta generando es de calidad y si la
> SDR esta pudiendo derivarlos, y despues el desglose por las campanas."

Ese orden **es** el panel, de arriba hacia abajo:

| # | Pregunta | Numero principal | Grafico dia a dia |
|---|---|---|---|
| 1 | ¿Gasta mas o menos? | gasto total ARS | gasto por dia: generan leads / awareness / eventos |
| 2 | ¿Genera mas o menos? | leads en el CRM + CPL real | leads por dia por destino + promedio 7 dias; CPL real movil de 7 dias |
| 3 | ¿Es de calidad? | % ICP (+ no calificados) | leads por dia por tipo de negocio; razones **del canal** |
| 4 | ¿La SDR deriva? | derivacion sobre leads maduros (+ contacto efectivo) | cada dia pintado por la etapa de hoy; razones **del seguimiento** |
| 5 | Desglose | una fila por campana | gasto diario en miniatura; clic abre los anuncios |

Arriba de todo, las cuatro preguntas en cuatro tarjetas con la variacion; abajo
de ellas, una tabla **mes a mes** (el ultimo mes del Q anterior en gris, los
meses del Q y el total) para leer la tendencia sin mirar dia por dia.

**Navegacion: Q y, adentro, mes. Los graficos son siempre por dia.** Desde el
2026-09-29 abre en el trimestre entero; el mes se elige en *Filtros*. Ya no hay
selector de "dia / semana / Q": la granularidad es fija, cambia la ventana.

### Contra que se compara

Siempre contra **el mismo tramo** del periodo anterior, nunca contra el periodo
entero: septiembre al 26 va contra agosto del 1 al 26, y el Q al dia 88 contra
los primeros 88 dias del Q anterior. Comparar un mes a medias contra uno
completo haria parecer que todo se derrumba hasta el dia 30.

- El **gasto** no tiene direccion buena: su variacion va en gris.
- Leads, % ICP, derivacion y contacto efectivo: subir es verde.
- CPL real, costo por derivado, no calificados y sin tipificar: bajar es verde.
- Por eso el JSON trae **el Q anterior entero**: julio necesita junio.

### El desglose por campana, con UTM

Desde el ~08/09 los leads de formulario llegan con UTM: `utm_term` es el
**conjunto** y `utm_content` el **anuncio** (`utm_campaign` trae el nombre del
formulario, "Formulario anuncios 1", no la campana). La campana sale del mapa
conjunto -> campana que el panel ya arma con el MCP (`campana_del_lead`).

- Las columnas del CRM de la tabla (leads, % ICP, contacto, derivacion, CPL
  real) **arrancan el 08/09** aunque el periodo empiece antes, y el CPL por
  campana usa el gasto de esos mismos dias. El encabezado lo dice.
- Un lead sin UTM queda en la fila "sin campana". **Nunca se reparte por el
  origen**: eso seria inventar la atribucion.
- WhatsApp no manda UTM: esa campana se lee por destino, en la seccion 2.
- Awareness y eventos no llevan columnas del CRM: se dice en la fila por que.

## Como se actualiza, todos los dias

Desde el 2026-09-27 el panel se regenera **despues de la guardia de las 8:00**,
todos los dias, y se republica en su URL. No manda nada a Slack (el link sale
los lunes con el semanal).

```bash
# antes: las llamadas #8, #9 y #10 de referencias/guardia-diaria.md, guardadas en
#        datos/meta-ads/guardia/<hoy>/mcp/ (anuncio-activos, conjunto-publicos,
#        anuncio-historico). Sin ellas Dia a dia y Tendencias quedan con la
#        ultima corrida que las tuvo, y el script lo avisa.
python3 scripts/traer_prospectos.py datos/crm/panel/prospectos-q.csv \
        --desde <1er dia del Q> --hasta <ayer>
python3 scripts/panel_meta.py            # sin --q, el trimestre de hoy
```

- **Plataforma:** `panel_meta.py` lee `datos/meta-ads/guardia/*/mcp/campana-diario.json`
  (y `conjunto-diario.json`, la llamada #7 de la guardia) ademas de los CSV del
  lunes. Gana **la foto mas nueva** de cada (nivel, dia, entidad): Meta corrige
  los dias recientes durante unos dias.
- **No lee `anuncio-diario.json`**: viene cortado en 200 filas (medido el
  2026-09-27, le faltan 1.000 a 5.600 ARS por dia desde el 17/09).
- **CRM:** `datos/crm/panel/prospectos-q.csv` se pisa cada dia con el Q hasta
  ayer. Los snapshots del lunes siguen siendo la historia (los prospectos se
  borran de Bitrix); el panel deduplica por ID y la carpeta `panel/` ordena
  ultima, asi que su lectura gana.
- **Nunca mas alla de ayer**: el dia en curso esta a medio cargar en Meta.
- **El JSON se reinyecta solo** en el `<script type="application/json"
  id="datos">` del HTML. Antes era a mano, y si se olvidaba el panel mostraba
  la semana pasada sin que nada fallara. `--sin-html` lo evita, solo para probar.
- Se commitea aparte: `Panel <AAAA-MM-DD>`.

**Quien lo corre es la rutina de la guardia** (`trig_0122tJ3eH91B5NWnhgzyoQ3s`,
paso 6 de su prompt). Hasta el 2026-10-07 el prompt de la rutina no lo decia y
el panel no se actualizaba solo: el 06 y el 07/10 quedo en los datos del 04/10.
La rutina tiene su propio prompt y no lee este archivo entero: **si cambia el
procedimiento, hay que cambiar tambien el prompt de la rutina**.

Si en la corrida no hay `conjunto-diario.json`, el script avisa desde que dia
no pudo descontar conjuntos de evento, y el panel lo muestra en "Limites".

## Las definiciones no se reimplementan

`panel_meta.py` **importa** la clasificacion de etapas y el grupo de negocio de
`analizar_crm.py`, y el bloque de campana y la lista de conjuntos de evento de
`analizar_meta.py`. Si el panel calculara la derivacion con criterio propio
habria dos numeros distintos con el mismo nombre. **No copiar esas reglas aca.**

El gasto cruzable sale igual que en el informe: campanas de **conversion y
remarketing** que optimizan por lead o por mensaje, **menos** los conjuntos de
evento que corren adentro. El awareness queda afuera aunque sea nucleo: sus
visitas al perfil no son leads.

## Las tres cosas que el panel se niega a hacer

Son las que lo vuelven confiable. Sacarlas lo convierte en un tablero lindo que
miente.

**1. No calcula plata con un filtro de leads puesto.** Meta no sabe que rubro
tiene quien completo el formulario, asi que el gasto **no se puede partir** por
tipo de negocio ni por destino. Con un filtro activo, el CPL y el costo por
Convertido quedan **en blanco**, no estimados. Dividir un numerador filtrado por
un denominador entero da un numero que parece razonable y esta mal.

**2. Las tasas de calidad van solo sobre cohortes maduras.** Un lead de las
ultimas 2 semanas todavia puede convertir. Si entra al denominador, la
derivacion del trimestre se hunde y la semana en curso parece un derrumbe todas
las semanas. Las barras de esas semanas van marcadas **provisional** y los KPI
las excluyen diciendo cuantos leads dejaron afuera.

**3. No muestra atribucion por anuncio antes del 08/09.** Hasta ese dia el CRM
no guardaba ni un UTM. Para esas fechas no se puede saber que anuncio trajo un
lead, y el panel no lo insinua.

## Los dos costos, en dos graficos

CPL real y costo por Convertido son la misma unidad pero de escala muy distinta
(5.781 contra 30.641 ARS en Q3). **Nunca en un eje doble**: superponerlos
aplastaria el CPL contra el piso. Desde el 2026-09-27 el CPL va en su grafico
diario (movil de 7 dias, con la linea del objetivo) y el costo por Convertido
—en el panel, "costo por derivado"— va en la tarjeta de al lado y en la tabla
mes a mes: un costo por Convertido diario no existe, porque los leads de un dia
tardan semanas en derivar.

**Se leen juntos siempre.** Entre marzo y agosto el costo que reporta Meta bajo
31% mientras el costo por Convertido subia 214%: un panel que mostrara solo el
CPL habria pintado ese periodo como un exito.

## De donde salen los cambios y las alertas

| Que | Archivo | Quien lo escribe |
|---|---|---|
| marcas de cambios | `memoria/cambios.jsonl` | la corrida del lunes, cuando Joana ejecuta algo |
| alertas del canal | `memoria/alertas.jsonl` | la corrida del lunes |
| alertas diarias | `memoria/guardia.jsonl` | `scripts/guardia_diaria.py`, solo |

**Los cambios arrancan el 2026-09-21.** Lo anterior vive como prosa en
`bitacora-cambios.md` y **no se migro** (decision de Joana): estructurar seis
meses de narrativa era el grueso del trabajo y ella prefirio empezar limpio.

El corte era el 22/09 y se corrio un dia el 2026-09-22, por el primer caso que
lo puso a prueba: la suba de presupuesto de Conversiones del 21/09 a las 16:19
mueve las curvas del 22/09 en adelante. Dejarla afuera habria dado un panel con
el gasto subiendo y ninguna marca que lo explicara. **La regla que queda: el
corte se corre hacia atras cuando un cambio de antes explica un movimiento de
adentro** — nunca para migrar historia, solo para no dejar huerfano un salto
que el panel si dibuja.

**Un cambio ejecutado se escribe en los dos lados:** la prosa explica el porque,
el jsonl es lo que se dibuja. El campo `antes` no es opcional — sin el valor
previo un cambio no se puede deshacer ni leer como causa.

La serie A1..A33 vieja tampoco se migro: una alerta entra al jsonl recien cuando
una corrida la toca. Las cinco estructurales (CPL, derivacion, mezcla de ICP,
creativos por conjunto, conciliacion de eventos) ya estan cargadas.

## Las razones de no derivacion van agrupadas, nunca en una lista sola

Se agrupan con `config/taxonomia-lead.yaml` por **a quien le corresponde el
problema**: del canal, del seguimiento comercial, producto o precio, timing.

Medido en Q3: **139 de 195 razones son de seguimiento comercial y 41 del canal.**
En una lista unica, "No responde mensajes ni llamada" encabeza todo e invita a
cambiar campanas para resolver algo que no se arregla en Meta. Agrupado, se ve
de un vistazo cual de los dos problemas es.

## Si algun numero del panel no coincide con el informe del lunes

Antes de tocar nada: **el panel corta por trimestre y el informe por semana o
por 4 semanas.** Un mismo KPI sobre ventanas distintas da distinto y las dos
cifras pueden estar bien. Solo es un bug si coinciden la ventana y el filtro y
aun asi difieren — y ahi el sospechoso es la reinyeccion del JSON, no el calculo.

## El mapa conjunto → campana, y por que hace falta

**Un conjunto de evento se descuenta SOLO si cuelga de una campana nucleo.**
`CONJUNTOS_DE_EVENTO` tiene nombres que viven en campanas eventuales propias
(Viajes Presenciales, Webinar Mostrador): restarlos igual descuenta plata que el
numerador nunca sumo. Es el mismo bug que la corrida del lunes encontro en
`analizar_meta.py` el 2026-09-21, y el panel lo tenia clonado hasta el 22/09.

Para scopearlo hace falta saber de que campana cuelga cada conjunto, y ahi esta
la trampa: **los export del Administrador no traen esa columna a nivel conjunto;
los del MCP si.** `panel_meta.py` arma el mapa juntando **todas** las respuestas
crudas del MCP que hay en `datos/meta-ads/**/mcp/*.json` y lo aplica hacia atras
— el nombre de un conjunto es estable, asi que lo aprendido en septiembre vale
para julio.

**Si aparece un conjunto de evento con gasto y sin campana conocida, el script
lo dice y NO lo descuenta**, con el monto al lado. Se arregla con una llamada al
MCP a nivel conjunto que cubra esos dias, guardada como
`datos/meta-ads/<carpeta>/mcp/conjunto.json`. Asi se armo
`datos/meta-ads/2026-Q3-mapa-conjuntos/`, que resolvio julio y agosto.

**No inventar el mapa a mano.** Descontar un conjunto que no corresponde
deflacta el gasto cruzable y baja el CPL sin que nada falle — y un CPL que baja
es exactamente el error que nadie revisa.
