---
name: boxer-dashboard
description: 'Actualiza y republica el panel de estadísticas de cursos y webinars de Boxer Gestión: carga los datos de un evento en su dashboard.json, arma el HTML con cursos/panel/build.py y lo publica en Cursos en Vivo, a la misma URL de siempre, con la herramienta Artifact. También agrega eventos nuevos al panel y corrige lo que se ve mal. Usalo SIEMPRE que el usuario mencione "actualizá el dashboard", "republicá el panel", "el dashboard de cursos", "subí los datos al panel", "agregá el webinar al dashboard", "el panel está desactualizado", "las estadísticas del curso", "mostrame el panel", o cuando después de cargar datos de un evento haya que reflejarlos donde los ve el equipo. El flujo es: datos medidos en el dashboard.json del evento, correr el build, leer el panel publicado, mostrar qué cambia y publicar a la URL existente.'
---

# Cursos en Vivo (panel de cursos y webinars)

> Copiada de growth-vent el 05/11/2026 y adaptada a Lupa. Desde ese día el panel es de Lupa:
> nadie más lo publica.

El panel vive en **https://claude.ai/artifact/7Vh4FWB6jmE8asFYec5w6A** (`paneles.yaml` →
`cursos_en_vivo`) y se arma desde `cursos/` de este repo. Lo ve toda la organización, y lo que
se publica reemplaza lo anterior al instante.

Leé `cursos/panel/README.md` antes de tocar nada: ahí está el esquema completo de
`dashboard.json`, campo por campo y según el tipo de evento.

## El circuito

```
cursos/eventos/*/dashboard.json  →  cursos/panel/build.py  →  cursos/panel/dist/index.html  →  Artifact
```

1. Los `dashboard.json` los actualiza `cursos/monitoreo.py medir` con datos leídos de la
   planilla, Bitrix y Meta. A mano solo se tocan campos que no se miden (descripción,
   expositor, `agenda`, `inversion_otros`), con el dato que dio Joana o Vent
2. `python3 cursos/panel/build.py`
3. Leer el panel publicado (`Artifact` read, regla 7) y publicar
   `cursos/panel/dist/index.html` **pasando la URL de arriba**

**Publicar sin esa URL crea un panel nuevo**, y el link que tiene el equipo queda mostrando
datos viejos. Si eso llegara a pasar, borrá el duplicado y republicá al original.

`cursos/panel/dist/index.html` es generado: nunca lo edites a mano. Los cambios de diseño o
de cálculo van en `cursos/panel/index.html`, que es la plantilla.

## Antes de publicar

- El build no tira error (valida los campos mínimos de cada `dashboard.json`)
- Revisá el diff de los `dashboard.json`: que los totales cierren (`clientes_si +
  clientes_no = total`) y que no haya un número que apareció de la nada
- Compará lo publicado (bloque `const DATA = [...]`) con lo que vas a publicar y decí qué
  cambia: evento, número antes y después

## Agregar o cerrar un evento

Lo pide Vent abriendo una sesión: `procedimientos/eventos.md`. No se agrega un evento con
datos supuestos.

Elegí bien el `kind` (`curso`, `webinar` o `charla`): decide qué pantalla se dibuja, y no se
cambia después sin rehacer los datos.

## Si hay que tocar el diseño o los cálculos

En `cursos/panel/index.html`:

- El menú de la izquierda son los trimestres (`drawRail`); dentro de cada uno van las
  pestañas (`drawTabs`): primero el calendario (`drawCalendar`) y después una por evento
- `go(trimestre, pestaña)` decide qué se muestra; `drawEvent()` elige la pantalla: si el
  evento tiene `objetivos` va `OBJ_SHELL`, si no, la que corresponde a su `kind`
- Las pantallas son `OBJ_SHELL`, `CURSO_SHELL`, `WEBINAR_SHELL` y `CHARLA_SHELL`
- Cada bloque tiene su función: `drawKpis`, `drawTiles`, `drawLine`, `drawDonut`,
  `drawDerivaciones`, `drawEtapas`, `drawRoster`
- Los colores están como variables en `:root`. Tema claro fijo (lo pidió Joana en octubre
  2026): no tiene modo oscuro

Todo inline: nada de dependencias nuevas, y las únicas fuentes externas son las de Google
Fonts que ya están. Después de tocar la plantilla, corré el build y **mirá el resultado antes
de publicar**: un error de JavaScript deja el panel en blanco para todo el equipo.

## Qué no hace esta skill

- No sale a buscar los datos: para eso está `boxer-evento-monitoreo`
- No borra eventos del panel: para sacar uno de la vista se le pone `"oculto": true` a su
  `dashboard.json`, así los datos no se pierden
