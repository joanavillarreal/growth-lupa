# Cursos y webinars — los datos que usa el monitoreo

> Copiado el 05/11/2026 de `docs/boxer-cursos-datos.md` de growth-vent (Vent), solo las partes
> que necesita el monitoreo: dónde viven los datos, métricas, orígenes en Bitrix, la planilla y
> el registro histórico. El resto (formulario, UTMs, ficha, n8n, bases, partners) es de Vent.
> Desde ese día **esta copia es la que vale para Lupa**: si Vent cambia una definición, llega por
> la sesión que abre (`procedimientos/eventos.md`) y se actualiza acá. Lupa no lee el repo de Vent.
>
> Los números de cada evento viven en `cursos/eventos/<slug>/dashboard.json` (lo que muestra
> Cursos en Vivo) y en los resúmenes diarios `cursos/datos/<fecha>/<slug>.json`.

---

## 1. Dónde viven los datos

Cada evento tiene su **Google Sheet de registro propio**. Ahí caen todos los inscriptos, sean clientes o no, y ahí se marca la asistencia.

De ahí en adelante, el flujo de n8n resuelve la carga automáticamente:

- Si el inscripto **es cliente Boxer**, queda solo en el Sheet y no toca el CRM
- Si **no es cliente y no existe en Bitrix**, se crea contacto y prospecto con el **origen propio del evento**
- Si **ya existe en Bitrix**, no se crea nada: se consulta qué es hoy (prospecto o negociación) y se avisa por Slack
- Las derivaciones las registran los asesores en Bitrix

> El detalle del flujo de n8n está en el repo de Vent: Lupa no lo toca.

---

---

## 2. Métricas y cómo se calculan

| # | Métrica | Cómo se calcula |
|---|---|---|
| 1 | **Inscriptos** | Total de registros en el Sheet del evento, sean clientes o no |
| 2 | **Inscriptos nuevos** | Los que no existían en el CRM |
| 3 | **Inscriptos existentes** | Los que ya estaban en el CRM (leads fríos y clientes) |
| 4 | **Costo por inscripto** | Inversión en pauta / inscriptos provenientes de pauta |
| 5 | **Asistentes** | Presentes en el evento, marcados en el Sheet |
| 6 | **Show rate general** | Asistentes / inscriptos totales |
| 7 | **Show rate de leads nuevos** | Asistentes nuevos / inscriptos nuevos |
| 8 | **Leads no calificados** | Registros fuera del ICP o con datos falsos |
| 9 | **Derivaciones** | Leads que la SDR pasa a un asesor después del evento, nuevos o existentes |
| 10 | **Tasa de derivación** | Derivaciones / asistentes |
| 11 | **Cierres** | Deals ganados atribuibles al evento |
| 12 | **MRR generado** | Suma del MRR de esos cierres |
| 13 | **CAC del evento** | (Pauta + horas de equipo valorizadas) / cierres |

### Valores de referencia

> Se completan con los promedios reales del registro histórico. Todavía no hay suficientes eventos cargados.

| Métrica | Referencia | Alarma |
|---|---|---|
| Show rate general | 40% (Curso IA) y 63% (Webinar Mostrador). Dos eventos, muy distintos entre sí: todavía no hay referencia | — |
| Show rate de leads nuevos | 28% (Curso IA) y 71% (Webinar Mostrador). Un curso de tres clases y un webinar único no se comparan derecho | — |
| Leads no calificados | < 15% de los inscriptos | > 15% |
| Tasa de derivación | 25% (Curso IA, 9 sobre 36 asistentes) y 8% (Webinar Mostrador, 1 sobre 12). Dos eventos, muy distintos entre sí: todavía no hay referencia | — |
| Costo por inscripto | $ 1.218 (Curso IA, 59 de Meta) y $ 3.778 (Webinar Mostrador, 14 de Meta). Dos eventos de volumen muy distinto: todavía no hay referencia | — |
| CAC del evento | ≤ USD 850 (blended del Q) | > USD 850 |

### Objetivos que tiene que cumplir cada evento

Desde el webinar del 10/11/2026 todo evento nuevo se mide contra estos dos, y el panel
muestra si cumple:

| Objetivo | Mínimo | Cómo se calcula |
|---|---|---|
| Inscriptos | **Más de 40** | Registros en el Sheet del evento |
| Porcentaje de derivación | **Más del 15%** | Derivaciones / inscriptos totales |

> Ojo: el porcentaje de derivación se calcula **sobre inscriptos**, no sobre asistentes
> como la tasa de derivación de la tabla de arriba. Son dos números distintos.

### Restricciones que vienen de los objetivos del trimestre

- CAC Paid ≤ USD 150 · CAC Blended ≤ USD 850 · ROAS pauta ≥ 1,5x
- Leads no calificados < 15% del total
- Payback ≤ 6 meses

---

---

## 3. Orígenes en Bitrix24

**Un origen propio por evento.** La medición es evento por evento.

| Origen | `SOURCE_ID` | Formato |
|---|---|---|
| Curso en vivo IA | `UC_AZSX3J` | Curso en vivo |
| Webinar Mostrador 2026 | `UC_CQ4N7U` | Webinar en vivo |
| Webinar - Decisiones usando IA | `UC_T93XNH` | Webinar en vivo |
| Webinar Ordenar Stock | `UC_V7TMQ9` | Webinar en vivo |
| Desayuno CERAC | `UC_VN0SA1` | Charla presencial con terceros |
| Demo masiva en vivo | `UC_ZUNX2Y` | Evento de reactivación sobre base propia |

Los `SOURCE_ID` salen de `python3 cursos/scripts/bitrix.py llamar crm.status.list`. Cada
evento nuevo trae el suyo en la sesión de alta de Vent, y va a `cursos/eventos.yaml`.

> Estos son los tres con los que empezó a contarse el canal. Los orígenes anteriores a esta convención quedan como referencia histórica.

---

---

## 5. La planilla de inscriptos

**Una planilla por evento**, todas con la misma estructura. Si los encabezados cambian, el flujo de n8n deja de encontrar las columnas.

**Plantilla madre en Drive**
ID: `1CxDMSVDrDiLVirkMAYL-m1cDPtPthfLTodcm-CKev6A`
Link: https://docs.google.com/spreadsheets/d/1CxDMSVDrDiLVirkMAYL-m1cDPtPthfLTodcm-CKev6A/edit

Es la que se duplica para cada evento, y de ahí salen también los formatos: la columna `Teléfono` en texto y la hoja `Instructivo`. La copia Vent cuando arma un evento (skill `boxer-curso-nuevo`, en su repo).

El `.xlsx` cargado en el proyecto es la misma planilla, pero sirve solo como referencia de la estructura: un adjunto del proyecto no se puede duplicar en Drive.

### Cómo crear la del evento nuevo

1. Duplicar la plantilla en Drive y renombrarla `[Nombre del evento] — Inscriptos`
2. Borrar las filas de ejemplo
3. **No cambiar los encabezados ni el orden de las columnas**
4. **Poner la columna `Teléfono` en formato texto**: seleccionarla y usar Formato → Número → Texto sin formato
5. **No renombrar la hoja `Inscriptos`**
6. Copiar el ID del archivo desde la URL y pegarlo en el nodo `Datos del inscripto` del flujo
7. Compartir la planilla con la cuenta de servicio de n8n, con permiso de edición

### Columnas

| Columna | La completa | Contenido |
|---|---|---|
| Timestamp | n8n | Fecha y hora de la inscripción |
| Nombre / Apellido | n8n | Separados desde el nombre completo |
| Teléfono | n8n | Normalizado a `+549XXXXXXXXXX`. **Es la llave que usa n8n para actualizar la fila, no se toca.** La columna tiene que estar en formato TEXTO: si queda en número, Sheets se come el `+`, n8n no encuentra la fila y el flujo se corta después del mensaje de confirmación |
| Email | n8n | Tal como lo cargó el inscripto |
| Negocio | n8n | Nombre del negocio |
| Tipo de negocio | n8n | Casa de Repuestos · Lubricentro · Taller mecánico · Distribuidora |
| ¿Cliente Boxer? | n8n | Si / No, autodeclarado en el formulario |
| Fuente | n8n | ClickUp o Meta |
| Estado | n8n | Inscripto · Inscripto — Mensaje enviado · Teléfono inválido |
| Mensaje Enviado | n8n | Momento del envío por Hyperflow, o "No enviado" |
| Estado CRM | n8n | Qué hizo el flujo con esta persona |
| Tipo Bitrix | n8n | Qué es hoy en el CRM: prospecto, negociación o sin registro |
| ID Contacto | n8n | ID del contacto en Bitrix |
| ID Registro | n8n | ID del prospecto o de la negociación, según lo que diga Tipo Bitrix |
| **Asistió** | **A mano** | Sí / No, después del evento. Es la base del show rate |
| **Observaciones** | **A mano** | Preguntas que hizo, señales de interés, resultado del llamado |

### Valores de "Estado CRM" — qué hizo el flujo

| Valor | Qué significa |
|---|---|
| `Nuevo — creado en CRM` | No estaba en Bitrix. Se creó contacto y prospecto. **Cuenta como dato nuevo** |
| `Existente — reactivación` | No es cliente pero ya estaba en Bitrix. No se crea nada. **Cuenta como reactivación** |
| `Cliente Boxer` | Ya es cliente y está en el CRM. No se crea nada |
| `Dice ser cliente — no está en el CRM` | Se declaró cliente pero no aparece en Bitrix. Revisar a mano |
| `No procesado` | Teléfono inválido, el flujo cortó antes del CRM |

> **Ojo:** en el Webinar Mostrador el flujo escribió también `Existente — prospecto inactivo`,
> que no es ninguno de los cinco. La segmentación post-evento filtra por texto exacto, así
> que un valor fuera de esta lista deja al inscripto sin mensaje. Está pendiente
> corregirlo en n8n (eso es de Vent). El monitoreo lo marca como alerta.

### Valores de "Tipo Bitrix" — qué es hoy esa persona

| Valor | Qué significa |
|---|---|
| `Prospecto` | Tiene un prospecto abierto. Estado normal de un inscripto nuevo |
| `Negociación` | Tiene una negociación abierta. **Ya lo está trabajando un asesor**: la SDR no lo llama sin avisar |
| `Negociación cerrada` | Tuvo una negociación cerrada. Cliente, o alguien que dijo que no en su momento |
| `Prospecto cerrado` | Tuvo un prospecto que se cerró sin avanzar |
| `Contacto sin registro` | Está como contacto, sin prospecto ni negociación |
| `—` | Sin procesar o teléfono inválido |

> Contar por `Estado CRM` da las cifras del canal: datos nuevos, reactivaciones y clientes.
> Cruzar `Tipo Bitrix` con `Asistió` le dice a la SDR a quién puede llamar y a quién ya está atendiendo un asesor.

### Qué crea el flujo en Bitrix

Cuando el inscripto es nuevo, el flujo crea **contacto + prospecto (lead)**. Nunca crea negociaciones: la negociación la genera después el asesor cuando la SDR deriva.

Cuando el inscripto ya existe, el flujo **no crea nada**, pero consulta sus negociaciones y sus prospectos para completar `Tipo Bitrix` e `ID Registro`. La prioridad es: negociación abierta, prospecto abierto, negociación cerrada, prospecto cerrado.

---

---

## 9. Registro histórico

> Se carga después de cada evento. Sin esto el canal repite errores.

| Fecha | Evento | Formato | Inscriptos | Nuevos | Asistentes | Show rate gral. | Show rate nuevos | No calif. | Derivaciones | Cierres | Pauta | Aprendizaje |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10-14/08/2026 | Curso en vivo IA | Curso en vivo | 91 | 46 con origen propio en Bitrix (37 prospectos + 9 negociaciones) | 36 en la clase 1 · 36 en la 2 · 24 en la 3 | 40% (clase 1) | 28% | [FALTA] | 9 (25% de los asistentes) | 1 | $ 71.856,57 · CPL $ 1.218 sobre 59 inscriptos de Meta | Convoca y deriva; donde se cae es del asesor para adelante |
| 17/09/2026 | Webinar Mostrador | Webinar en vivo | 19 | 7 | 12 | 63% | 71% (5 de 7) | [FALTA] | 1 (8% de los asistentes · 5% de los inscriptos) | 0 | $ 52.896,60 · CPL $ 3.778 sobre 14 inscriptos de Meta | Vino casi todo el que se anotó, pero convocó poco y derivó poco. (post-mortem en el repo de Vent) |
| [FALTA] | Desayuno CERAC | Charla presencial | [FALTA] | | | | | | | | | |
| [FALTA] | Demo masiva en vivo | Reactivación de base | [FALTA] | | 15 | | | | 5 | | | Formato validado, repetible con base nueva |

> Los números del Curso en vivo IA salen del panel de estadísticas. Los que dicen `[FALTA]` no están medidos todavía: derivaciones y leads no calificados de ese curso nunca se contaron, y hasta que se cuenten no se pueden usar como referencia.

### Formatos con resultado negativo

No repetir sin un cambio explícito.

| Formato / campaña | Cuándo | Qué pasó |
|---|---|---|
| Campaña "cuánto perdés por desorden" | Q2 2026 | Bajo resultado |
| Serie de contenidos Boxer + Claude | Q2 2026 | Bajo resultado |

---

---

## Cómo lee Lupa cada fuente

| Fuente | Cómo | Qué sale |
|---|---|---|
| Planilla | Conector de Google Sheets, `get_values` sobre `Inscriptos!A1:Q500` | total, clientes, asistentes, `meta_leads` (Fuente = Meta), `leads_prospecto` / `leads_negociacion` (columna `Tipo Bitrix`), la curva por día (Timestamp) y las alertas del circuito |
| Bitrix24 | Webhook `BITRIX_WEBHOOK_URL`, `python3 cursos/scripts/bitrix.py origen <SOURCE_ID> --json` | derivaciones (prospectos en *Convertido*), prospectos abiertos, cierres (negociaciones en *Seguimiento Clientes*), etapas |
| Meta Ads | Conector de Meta, `ads_get_ad_entities` nivel campaña, `amount_spent` con `date_preset: maximum`, cuenta 725901852075382 | `inversion_total`: solo las campañas dedicadas al evento (`cursos/eventos.yaml`) |

Verificado el 05/11/2026: con estas reglas, el Webinar Ordenar Stock da exactamente los mismos
números que tenía cargados Vent (57 inscriptos, 23 clientes, 26 asistentes, 39 de Meta, 21 en
`Prospecto` y 22 en `Negociación` según la planilla, y la misma curva por día).

> El Timestamp de la planilla viene en 12 horas sin AM/PM (`3/11/2026, 03:47:44` es a las
> 15:47): para la curva se usa solo el día, que sí es confiable.

> Al registro histórico lo completa Vent cuando cierra un evento, con los números finales que
> le devuelve Lupa. Lupa agrega acá la fila con esos mismos números (y `[FALTA]` en lo que no
> está medido); el aprendizaje lo escribe Vent.
