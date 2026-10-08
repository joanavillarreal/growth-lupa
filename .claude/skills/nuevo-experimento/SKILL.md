---
name: nuevo-experimento
description: Carga un experimento nuevo de generación en el registro del Monitor de Growth de Boxer Gestión (solapa Experimentos), pidiendo la información paso a paso, fundamentándola con números reales del canal y republicando el Monitor. También cierra experimentos terminados con su conclusión y decisión. Usala SIEMPRE que el usuario diga "nuevo experimento", "cargar un experimento", "sumar un experimento", "quiero probar algo en Meta/Google", "armemos una prueba", "test de conjunto de anuncios", "experimento de canal", o pida cerrar, actualizar o dar de baja un experimento. El flujo es siempre - contexto del canal, preguntas de a un bloque, resumen, confirmación, recién ahí escribir y publicar.
---

# Nuevo experimento

Un experimento es una prueba sobre la **generación** de un canal de
adquisición que ya tenemos (Meta Ads, Google Ads, Redes Sociales…). Queda
registrado en `experiments/EXP-NNN-nombre-corto.md` y aparece como card en la
solapa **Experimentos** del Monitor de Growth
(link en `paneles.yaml`, según el modo). El resultado en
métricas se calcula solo todos los días; esta skill solo tiene que dejar bien
cargado lo que no se puede calcular.

## Reglas

- **No inventes nada.** Cada campo sale de lo que dice la persona o de un
  número del snapshot. Si falta algo, preguntalo.
- **Preguntá de a un bloque**, no las once cosas juntas. Proponé un borrador
  para que la persona corrija en vez de pedirle que escriba de cero.
- **Una sola métrica primaria** y un **n mínimo** decididos antes de lanzar.
- **Un experimento por canal a la vez.** Si ya hay uno corriendo en el canal,
  avisalo antes de seguir: dos cambios a la vez no se pueden leer.
- No escribas el archivo hasta que la persona confirme el resumen.

## Paso 0 · Contexto del canal

Antes de preguntar nada, traé los números reales del canal:

```bash
cd /home/user/growth-lupa && python3 run.py contexto-experimento --canal <clave>
```

Claves de canal: las de `config/definitions.yaml` (`meta`, `google`,
`redes_sociales`…) o `general`. Si el snapshot es de antes de ayer, corré
primero `python3 run.py ingest`.

Te da los últimos 28 días contra los 28 anteriores (leads, gasto, CPL, %
de derivación, costo por derivado, % de no calificación, presupuestados), el
ritmo de leads por semana, si hay otro experimento corriendo en el canal y el
próximo id. Usalo para proponer el problema y los datos que respaldan la
hipótesis.

Si el experimento toca una campaña o un conjunto de anuncios de Meta, podés
listar los que existen con el conector de Meta (cuenta `725901852075382`)
para que la persona elija, en vez de pedirle el nombre de memoria.

## Paso 1 · Las preguntas, en este orden

1. **Qué y dónde.** Nombre corto, canal y una descripción de una o dos
   oraciones. Si la persona ya lo contó, proponé el nombre y la descripción
   vos.
2. **Problema.** Qué está fallando hoy en el canal y cuánto cuesta. Proponé
   uno con los números del paso 0 y que la persona lo confirme o lo cambie.
3. **Hipótesis y datos.** "Si hacemos X, esperamos que Y mejore, porque Z", y
   la lista de números que la respaldan. Los datos tienen que ser reales:
   del contexto del canal, del Monitor o de lo que aporte la persona (por
   ejemplo, resultados del conjunto original en Meta).
4. **Solución a probar.** Qué cambia exactamente, contra qué se compara y
   qué NO se toca durante la prueba (presupuesto de lo demás, creativos,
   formularios).
5. **Métrica primaria y efecto esperado.** Una sola, de estas: `generados`,
   `cpl`, `pct_derivacion`, `costo_por_derivado`, `pct_no_calificacion`,
   `presupuestados`. Sugerí la que corresponde a la hipótesis. El efecto
   esperado va como texto ("-20%", "+5 pp").
6. **Fechas y n mínimo.** Lanzamiento y fin de análisis. Proponé el
   `n_minimo` y calculá con el ritmo del paso 0 cuántas semanas hacen falta
   para juntarlo: si las fechas no alcanzan, decilo y proponé extender. Una
   prueba de menos de 3 semanas casi nunca se puede leer con este volumen.
7. **Responsable.** Quién la lleva adelante.

**Si el experimento es sobre un conjunto de anuncios de Meta** (un conjunto
nuevo, uno reactivado, un público distinto), el éxito se mide sobre ese
conjunto y no sobre todo el canal. Pedí:

- el conjunto exacto (listalo con el conector para que la persona elija) y
  guardá su id en `conjunto_meta`;
- la meta diaria de leads del conjunto en `meta_leads_dia`, y poné
  `metrica_primaria: leads_conjunto_dia`.

Antes de confirmar, cruzá la meta con el gasto diario del conjunto y el costo
por formulario reciente de Meta: si con ese presupuesto la meta es
inalcanzable (por ejemplo 6 leads por día con un conjunto que gasta para 1),
decilo en el resumen. Agregá el conjunto a `data/meta_adsets.json` con los
días que ya tenga (`level: adset`, campos `amount_spent` y `lead`,
`time_increment: "1"`); de ahí en más lo refresca la corrida diaria.

Estado: `propuesto` si el lanzamiento es futuro, `corriendo` si ya arrancó.

## Paso 2 · Resumen y confirmación

Mostrá el experimento completo en el chat, con los mismos títulos que el
popup (Nombre, Descripción, Problema, Hipótesis, Datos que la respaldan,
Solución a probar, Métrica primaria y efecto esperado, Fechas, n mínimo,
Responsable). Pedí confirmación explícita.

## Paso 3 · Escribir y publicar

1. Copiá `experiments/TEMPLATE.md` a `experiments/EXP-NNN-nombre-corto.md`
   (id del paso 0) y completá el frontmatter. Los textos largos van con `>`;
   los `datos` como lista de strings entre comillas.
2. Verificá que cargue y que el resultado se calcule:
   ```bash
   python3 -c "import sys;sys.path.insert(0,'.');from growth import experiments,ingest;from growth.config import Config;print([ (e['id'],e['resultado']['estado_lectura']) for e in experiments.para_monitor(ingest.cargar_ultimo(),Config())])"
   ```
3. `python3 run.py dashboard`.
4. Si `paneles.yaml` dice `modo: oficial`, republicá `dashboard/index.html` en
   `monitor_growth.link`, leyéndolo antes. **En `modo: ensayo` no se publica**:
   avisá que el experimento queda en el repo y aparece en el Monitor cuando Lupa
   pase a oficial. Si el publish se
   rechaza porque la corrida diaria publicó una versión más nueva, leé esa
   versión, confirmá que lo único distinto es el experimento nuevo y volvé a
   publicar.
5. Commiteá y pusheá a `main` ("Experimento EXP-NNN: <nombre>").
6. Respondé con el link y una línea sobre cuándo se va a poder leer.

## Cerrar o actualizar un experimento

Cuando pase el fin de análisis, o cuando la persona lo pida:

1. Leé el resultado calculado (mismo comando del paso 3.2, o abrí el popup).
   Si no juntó el `n_minimo`, decilo: el resultado no es concluyente.
2. Escribí con la persona `resultado` (conclusión en dos o tres oraciones,
   con el número de la métrica primaria) y `decision` (`adoptar`,
   `descartar` o `repetir con cambios`).
3. `estado: concluido` (o `descartado` si se frenó antes). Regenerá,
   republicá y commiteá igual que arriba.

Un experimento sin conclusión escrita se repite dentro de seis meses: se
cierra siempre, aunque salga mal.
