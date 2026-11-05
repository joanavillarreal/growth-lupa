# Eventos que me pasa Vent: alta y cierre

Vent (el agente de cursos y webinars) define los eventos y escribe sus post-mortem. **Vent no
escribe en mi repo y yo no leo el suyo.** Cuando necesita algo de mí abre una sesión mía con los
datos en el pedido. Hay dos pedidos posibles: dar de alta un evento y cerrarlo.

Las dos sesiones trabajan directo sobre `main` (como toda sesión de Lupa) y terminan con commit
y push. Mi respuesta a Vent es el **último mensaje de la sesión**; si el pedido trae el
`session_id` de la sesión de Vent, además se la mando con `send_message` a esa sesión.

## Alta de un evento

### Lo que tiene que traer el pedido

| Dato | Ejemplo | Dónde va |
|---|---|---|
| slug (carpeta) | `2026-12-webinar-cuenta-corriente` | clave en `cursos/eventos.yaml` y `cursos/eventos/<slug>/` |
| nombre | `Webinar: Cobrá la cuenta corriente` | `nombre` y `titulo` |
| tipo | `webinar` / `curso` / `charla` | `tipo`, y `kind`/`tag` del dashboard.json |
| fechas y hora | `2026-12-03`, `13:00` (un curso: una fecha por clase) | `fechas`, `hora` |
| apertura de la inscripción | `2026-11-20` | `apertura` (antes de esa fecha: "por abrir") |
| objetivo | más de 40 inscriptos, más del 15% derivados | `objetivos` |
| planilla | link o ID del Google Sheet | `planilla` (ID) y `sheet_url` |
| origen en Bitrix | `Webinar Cuenta Corriente` · `UC_XXXXXX` | `origen_crm`, `source_id` |
| campañas de Meta | `JY | Webinar ... (AGENTE META)` · ID | `meta.campanas` (puede venir vacío) |
| expositor y descripción | `Santi`, 3 a 5 líneas | dashboard.json (las muestra el panel) |

### Pasos

1. **Validar sin inventar.** Si falta un dato obligatorio (slug, nombre, tipo, fechas, planilla,
   origen y `SOURCE_ID`), no lo completo: lo anoto como faltante y se lo devuelvo a Vent. Lo
   que sí puedo, lo verifico:
   - la planilla abre con `get_values` (`Inscriptos!A1:Q1`) y sus encabezados son los de la
     plantilla madre (`cursos/datos.md`, sección 5);
   - el `SOURCE_ID` existe: `python3 cursos/scripts/bitrix.py llamar crm.status.list` (solo
     lectura) y el nombre coincide con `origen_crm`;
   - cada campaña de Meta existe en la cuenta 725901852075382 (`ads_get_ad_entities` con
     `object_ids`).
   Lo que no verifique queda escrito en la respuesta como "no verificado".
2. Sumar el bloque a `cursos/eventos.yaml`.
3. Copiar `cursos/eventos/_plantilla/dashboard.json` a `cursos/eventos/<slug>/dashboard.json`
   y completarlo con los datos del pedido: `id` = slug, contadores en cero, `inversion_total`
   `null` (no 0) hasta que Meta tenga gasto, `objetivos` y `descripcion` como en la plantilla.
   El `kind` decide la pantalla del panel y no se cambia después.
4. Si la inscripción ya está abierta, medirlo como en `procedimientos/cursos.md` (pasos 1 a 4)
   para que el panel arranque con datos reales.
5. `python3 cursos/panel/build.py`, leer Cursos en Vivo y republicarlo en su link (regla 7).
6. Commit (`Cursos: alta de <nombre>`) y push a `main`. Desde la corrida siguiente entra solo
   al monitoreo diario (`que_toca_hoy.py` lo ve en `eventos_abiertos`).
7. Responder a Vent: qué quedó cargado, qué verifiqué, qué falta y el link del panel.

## Cierre de un evento

Vent lo pide cuando terminó el ciclo de mensajes y llamados y va a escribir el post-mortem.

1. Medirlo una última vez, como en `procedimientos/cursos.md` (pasos 1 a 4). Si una fuente no
   se puede leer, no cierro con números viejos: le digo a Vent qué no se pudo leer y lo dejo
   abierto.
2. Agregar `cerrado: <hoy>` a su bloque en `cursos/eventos.yaml`. Desde ahí no se monitorea más
   ni hace correr el análisis `cursos`.
3. Sumar la fila al registro histórico de `cursos/datos.md` (sección 9) con los números
   finales; lo que no esté medido va `[FALTA]` y el aprendizaje queda "lo escribe Vent".
4. `python3 cursos/panel/build.py`, leer y republicar Cursos en Vivo, commit
   (`Cursos: cierre de <nombre>`) y push a `main`.
5. **Devolverle a Vent los números finales**, todos de la medición de hoy y con la fuente:

```
<Nombre> · cerrado el <dd/mm/aaaa>
Inscriptos       N (planilla) · objetivo más de 40: cumple / no cumple
Clientes / no    N / N
Estado CRM       nuevos N · reactivaciones N · clientes N · dice ser cliente N · no procesados N
Asistieron       N (N%) · show rate de nuevos: N de N
Derivaciones     N (N% de los inscriptos · objetivo más del 15%: cumple / no) — Bitrix
Cierres          N (negociaciones en Seguimiento Clientes) — Bitrix
Pauta Meta       $ N · N inscriptos de Meta · $ N por inscripto
Leads no calif.  [FALTA] (no se mide desde la planilla)
Alertas abiertas …
Panel            https://claude.ai/artifact/7Vh4FWB6jmE8asFYec5w6A
```

El show rate de nuevos y la composición por `Estado CRM` salen del resumen del día
(`cursos/datos/<hoy>/<slug>.json`, `composicion`). Lo que no esté ahí no lo calculo a mano.

## Lo que no hago en estas sesiones

Escribir la ficha, los mensajes, el post-mortem o los aprendizajes (es de Vent); tocar n8n,
Hyperflow o Bitrix; mandar mensajes a inscriptos; abrir o modificar el repo de Vent.
