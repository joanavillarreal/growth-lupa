# Pendientes

Cosas decididas con Joana que todavía no se pueden hacer porque dependen de algo que no existe.
Se revisa al empezar cada corrida que las toca. Cuando se hacen, se mueven a "Hechos" con la fecha.

## Abiertos

### Rendimiento por pilar y por formato (redes · semana) — espera a Conti
Decidido con Joana el 08/10/2026.

- **Cuándo se activa:** cuando Conti esté funcionando y publique su **Planificación aprobada**
  como artefacto, con cada pieza y su pilar, formato y objetivo.
- **Qué hacer:** en el análisis de los lunes (`redes_semana`), cruzar cada post publicado
  (Metricool, `redes/data/<semana>/boxer-*.json`) con su pieza de la Planificación **por fecha y
  texto**, y mostrar cómo rinde cada pilar y cada formato (orgánico separado de pago, "sin dato" ≠ 0).
  Los posts que no crucen con ninguna pieza se informan aparte: nunca se les asigna un pilar a ojo.
- **De dónde se lee:** del **artefacto** de Conti (`Artifact` con `action: read`), **nunca de su repo**.
- **Mientras tanto:** el "tema" de cada pieza en el bloque `datos-redes` del Panel de redes es la
  primera línea del caption (Metricool no clasifica temas). Cuando el cruce exista, el tema pasa a
  ser el pilar de la Planificación y se sube `formato` del bloque.

## Hechos

(nada todavía)
