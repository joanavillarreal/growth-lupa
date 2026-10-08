# Registro de experimentos

Un archivo por experimento: `EXP-001-nombre-corto.md`, copiando `TEMPLATE.md`.
Se muestran en la solapa **Experimentos** del Monitor de Growth (desde el Q4
2026), agrupados por el trimestre de su fecha de lanzamiento. El
**resultado en métricas** se calcula solo todos los días: compara el canal
entre el lanzamiento y el fin de análisis contra el mismo largo de tiempo
inmediatamente anterior al lanzamiento.

Reglas que hacen que el registro sirva para algo:

1. **Una sola métrica primaria.** Si un experimento se puede declarar ganador
   por tres métricas distintas, siempre gana.
2. **`n_minimo` antes de arrancar.** Con ~230 prospectos por mes, una prueba
   que necesita 400 para leerse no se puede correr en dos semanas: o se
   extiende, o no se corre.
3. **Fechas cargadas.** Sin lanzamiento y fin de análisis no hay antes y
   después contra qué medir.
4. **Se cierra siempre**, aunque salga mal. `resultado` y `decision` completos.
   Un experimento sin conclusión escrita se repite dentro de seis meses.
5. **Un experimento por canal a la vez.** Dos cambios simultáneos en Meta
   hacen que ninguno de los dos se pueda leer.
