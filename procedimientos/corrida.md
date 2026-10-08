# La corrida de Lupa, de punta a punta

Esto es lo que hace la rutina diaria (7:50, hora de Argentina). La rutina solo dice "leé
`procedimientos/corrida.md` y hacelo": todo lo demás vive en el repo.

## 0. Arranque

- El hook de arranque ya verificó Python, las variables de entorno y las fuentes, y dejó el repo
  en `main` al día. Leer lo que imprimió: si dice ERROR, eso va al mensaje final.
- Si no existe `/home/user/growth-lupa/que_toca_hoy.py`, la rutina no tiene el repo como fuente:
  mandar una sola línea al DM D0BRVS7A4A3 diciéndolo y terminar. No intentar clonarlo.
- Leer `paneles.yaml` → `modo`. En `ensayo`, todo Slack va al DM D0BRVS7A4A3 con "[ensayo]"
  adelante; en `oficial`, cada aviso a su destino de `agenda.yaml`.

## 1. Qué toca

`python3 que_toca_hoy.py --json`. Hacer exactamente lo que devuelve, en este orden:
`preparaciones`, después `pendientes` en el orden de la lista. Lo que esté en `ya_hechos` no se
repite; lo que esté en `agotados` o `preparaciones_agotadas` no se intenta y va al mensaje final.

## 2. Verificar herramientas (regla 2)

Antes de cada preparación o análisis, por cada sufijo de `herramientas` (y una vez por corrida,
`herramientas_siempre`): ToolSearch con el sufijo y verificar que aparezca una herramienta cuyo
nombre termine en `__<sufijo>`. Si falta: esperar unos minutos y volver a buscar, hasta 3 veces.
Anotar los nombres completos que cargaron: van al parte con `--herramientas`.
Si después de 3 búsquedas falta alguna: el análisis se registra fallido con el error real ("no
apareció ninguna herramienta que termine en __getBrandSettings después de 3 búsquedas; cargaron:
..."), y se sigue con el siguiente.
Las variables de `entorno` se verifican con `[ -n "$VAR" ]`, nunca mostrando su valor.

## 3. Cada análisis

Seguir su `procedimiento` (en `agenda.yaml`). Al terminar cada uno, sin esperar al final:
1. `python3 parte.py <analisis> ok|fallido ...` (con `--herramientas` y `--datos`).
2. `git add` de lo que generó + `partes/` y `git commit` (`Lupa <AAAA-MM-DD>: <analisis>`),
   `git push origin HEAD:main`. Si se rechaza porque `main` avanzó: `git pull --no-rebase origin
   main`, resolver conservando los datos de los dos lados, y volver a pushear.
3. Los avisos propios del análisis (la alarma del funnel, el bloque de la guardia, la tabla de la
   inversión) se mandan **tal cual** los imprime su script, al destino que corresponda según el
   modo. Si el script dice que no hay novedades, no se manda ese aviso aparte.

En **ensayo**, además, la comparación de "Cómo se compara en ensayo" (CLAUDE.md) para el funnel,
meta e inversión, con el resultado en `--datos` → `comparacion`.

## 4. El mensaje final (regla 5: siempre)

Uno solo por corrida, aunque no haya tocado nada. Formato:

```
[ensayo] Lupa · <día> <dd/mm> · <hh:mm>
✅ <análisis> — <resumen en una línea, con su número principal>
❌ <análisis> — <qué falló, con el error real> (intento n de 3)
⏸ <análisis> — agotado: no se reintenta hasta mañana
<si aplica: Gasto de Meta sin actualizar desde dd/mm>
Paneles: <links que se publicaron hoy>
Parte: partes/<AAAA-MM-DD>.json
```

Si no tocaba nada: `Lupa · <día> <dd/mm>: hoy no tocaba nada (ya estaba hecho: <lista>)`.
Al final, commit y push del parte si quedó algo sin pushear.

## Simular un día

`LUPA_SIMULACION=1` hace que `que_toca_hoy.py` y `parte.py` usen `partes/simulacion/`, para que
una simulación nunca deje un parte que la corrida real lea como "ya hecho". Con `--fecha` se
elige el día. Los datos que se traen son los reales del momento.
