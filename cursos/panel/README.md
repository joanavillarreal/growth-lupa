# Cursos en Vivo — panel de cursos y webinars

> Copiado de growth-vent (`dashboard/README.md`) el 05/11/2026. Desde ese día lo publica
> solo Lupa (análisis `cursos`, `procedimientos/cursos.md`); Vent ya no.

**Vive en:** https://claude.ai/artifact/7Vh4FWB6jmE8asFYec5w6A
**Se publica siempre a esa misma URL.** Si se publica a otra, el link que tiene el equipo
deja de mostrar los datos nuevos.

## Cómo se arma

```
cursos/eventos/*/dashboard.json  →  cursos/panel/build.py  →  cursos/panel/dist/index.html  →  Artifact
```

1. Se edita el `dashboard.json` del evento que cambió
2. `python3 cursos/panel/build.py`
3. Se publica `cursos/panel/dist/index.html` con la herramienta Artifact, pasando la URL de
   arriba para que actualice el panel existente en vez de crear uno nuevo

`cursos/panel/index.html` es la plantilla: tiene el marcador `__DATA__` donde el build mete
los eventos. **`dist/index.html` es generado: no se edita a mano**, se pisa en cada build.

Un evento con `"oculto": true` no se publica.

## Cómo está organizado

- **A la izquierda, los trimestres** (Q4 2026, Q3 2026…), del más nuevo al más viejo.
  Cada evento cae en el trimestre de su primera fecha. El trimestre en curso aparece
  siempre, aunque todavía no tenga eventos, y el panel abre ahí.
- **Dentro de cada trimestre, pestañas:** primero **Calendario** y después una por evento,
  en orden de fecha. La pestaña de un evento muestra sus métricas según su `kind`.
- **El Calendario** dibuja los tres meses del trimestre y, abajo, la lista de lo que hay
  con fecha, hora, tipo, evento, responsable (el `expositor`) y estado (pasó, hoy, faltan N días). Entra cada fecha de `fechas` (en un curso,
  una por clase) y cada hito de `agenda`. Tocando cualquiera se abre la pestaña del evento.

> Republicar cambia lo que ve toda la organización al instante. Lupa lo republica en su
> corrida diaria solo si hay algún evento abierto y los números salieron de la planilla, de
> Bitrix y de Meta; antes lee la versión publicada (regla 7). Si una fuente no se pudo leer,
> ese evento queda como estaba y se dice en el parte.

## Los tres tipos de evento

El campo `kind` decide qué pantalla se dibuja. `tag` es el cartelito de color.

| `kind` | `tag` | Para qué |
|---|---|---|
| `curso` | `CURSO` | Varias clases: mide asistencia clase por clase |
| `webinar` | `WEBINAR` | Encuentro único: mide show rate, derivaciones y etapas en el CRM |
| `charla` | `CHARLA` | Presencial o con terceros: mide inscriptos, pedidos de material y leads |

## Eventos con objetivos (el formato nuevo)

Desde el webinar de noviembre 2026, un evento que trae `objetivos` en su `dashboard.json`
se dibuja con la pantalla de objetivos, sin importar el `kind`. Muestra:

- **De qué se trata:** el texto de `descripcion`
- **Objetivos:** inscriptos (más de `inscriptos_min`) y porcentaje de derivación
  (más de `derivacion_pct_min` % de los inscriptos derivados a ventas), cada uno con su
  barra, la marca del objetivo y si cumple, va en camino o no cumplió
- **Resultados de negocio:** inversión total, cierres, CAC y CPL
- **Inscriptos y asistencia:** inscriptos, clientes, no clientes, asistieron y % de asistencia
- **Inscriptos acumulados por día**, con la línea del objetivo, y **leads nuevos con el
  origen del evento** (prospecto / negociación)

No lleva embudo ni listado de inscriptos: el listado vive en el Google Sheet del evento.

```json
"objetivos": { "inscriptos_min": 40, "derivacion_pct_min": 15 },
"stats": { "total", "clientes_si", "clientes_no", "asistentes", "meta_leads",
           "derivaciones", "cierres", "leads_prospecto", "leads_negociacion" }
```

Los eventos de antes (Curso IA, Webinar Mostrador) no tienen `objetivos` y siguen con su
pantalla de siempre.

## Campos comunes

| Campo | Qué es |
|---|---|
| `id` | Identificador del evento, igual al slug de la carpeta |
| `titulo` | Cómo aparece en el panel |
| `tag`, `kind` | Los de la tabla de arriba |
| `fechas` | Lista `["aaaa-mm-dd"]`. Un curso lleva una fecha por clase |
| `hora` | Solo para eventos que todavía no pasaron (se muestra en el preaviso) |
| `expositor` | Idem |
| `sheet_url` | La planilla de inscriptos del evento |
| `origen_crm` | Nombre del origen en Bitrix, tal cual está escrito en el CRM |
| `origen_source_id` | El `SOURCE_ID` que usa n8n |
| `inversion_total` | Pauta gastada. `null` mientras no se sepa: el panel muestra un guión |
| `inversion_moneda` | `"$"` |
| `inversion_otros` | Opcional. Gastos que no son de Meta (un envío de WhatsApp, por ejemplo): `[{"fecha","concepto","monto","moneda","aprox"}]`. Se muestran abajo de la inversión, sin sumarse a `inversion_total` ni al CPL, porque pueden estar en otra moneda y el CPL es de los leads de Meta |
| `signups_por_dia` | `[{"fecha","nuevos","acumulado"}]` para la curva |
| `descripcion` | Opcional. De qué se trata el evento; se muestra arriba de las métricas |
| `enrollees` | Un objeto por inscripto, para la tabla del final (no va en los eventos con objetivos) |
| `agenda` | Opcional. Otros momentos programados del evento que van al calendario: `[{"fecha": "aaaa-mm-dd", "hora": "09:00", "que": "Envío de cosecha"}]`. La `hora` es opcional |

## `stats` según el tipo

**curso:** `total`, `clientes_si`, `clientes_no`, `clase1`, `clase2`, `clase3`,
`con_crm_id`, `meta_leads`, `cierres`, `leads_curso_ia_prospecto`,
`leads_curso_ia_negociacion`, `leads_curso_ia_total`.

**webinar:** `total`, `clientes_si`, `clientes_no`, `nuevos`, `reactivaciones`,
`asistentes`, `meta_leads`, `derivaciones`, `prospectos_abiertos`, `cierres`.
Lleva además `etapas_crm`: `[{"nombre": "Webinars", "n": 12}]`.

**charla:** `inscriptos_presencial`, `solicitan_material`, `nuevos_leads`,
`leads_derivados`. Lleva además `no_clientes`:
`[{"nombre","negocio","solapa","crm_id","crm_stage"}]`.

## `enrollees` según el tipo

**curso:** `nombre`, `apellido`, `negocio`, `cliente` (`"Si"`/`"No"`), `fuente`
(`"ClickUp"`/`"Meta"`), `clase1`, `clase2`, `clase3` (booleanos), `crm_id`, `crm_tipo`
(`"PROSPECTO"`/`"NEGOCIACION"`), `crm_stage`, `fecha`.

**webinar:** `nombre`, `apellido`, `negocio`, `cliente`, `fuente`, `asistio` (booleano),
`estado_crm` (el valor de la columna `Estado CRM` de la planilla), `crm_id`, `crm_stage`,
`fecha`.

## Cómo se calcula lo que muestra

- **CPL** = `inversion_total` ÷ `meta_leads`
- **CAC** = `inversion_total` ÷ `cierres`
- **Show rate** = `asistentes` ÷ `total` (en un curso, asistencia a la clase 1)
- **Tasa de derivación** = `derivaciones` ÷ (`derivaciones` + `prospectos_abiertos`)
- **Porcentaje de derivación** (eventos con objetivos) = `derivaciones` ÷ `total`
- **% de asistencia** (eventos con objetivos) = `asistentes` ÷ `total`
- **Cierres** = negociaciones con el origen del evento que llegaron al pipeline
  *Seguimiento Clientes* de Bitrix24
- **Derivaciones** = prospectos con ese origen que ya pasaron a etapa *Convertido*

Cuando un número no está, se deja en `0` o `null` y el panel lo muestra apagado, con una
nota de qué falta. **Nunca se rellena con un estimado.**

## Un evento nuevo en el panel

No hace falta esperar a que pase: se crea el `dashboard.json` con los datos de la ficha y
los contadores en cero apenas se abre la inscripción. El panel muestra un preaviso con
los días que faltan y la curva se dibuja sola a medida que entran los inscriptos.
