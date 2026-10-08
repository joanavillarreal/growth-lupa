# Análisis `redes` — la semana cerrada en Metricool + leads de redes

Copiado de Lupa en `agente-redes` (`.claude/agents/lupa.md`, skills `informe-redes-semanal` y
`boxer-cruce-crm`; ver `redes/referencias/`). **Solo medición**: las direcciones de contenido,
las ideas, el copy, el diseño y la programación de posts NO son míos (son de Conti y del equipo
creativo). Lunes. Marcas: Boxer Gestión (brandId 4938672, IG + FB + LinkedIn) y Boxer Taller
(brandId 6516272, IG + FB).

## Reglas que no se rompen

- **Los números los calcula el script.** Nada a mano: todo sale de `analizar.py`, `cruce_crm.py`
  o `panel_redes.py`.
- **Orgánico y pago no se mezclan** al juzgar contenido. La pauta es contexto.
- **"Sin dato" no es "cero"** (los reels no informan follows; Metricool deja campos nulos).
- **Cada semana se mide una sola vez, el lunes después del cierre**, y queda como se midió. Re-
  extraerla días después cambia las métricas por pieza (Metricool sigue sumando): verificado el
  08/10/2026 con la W39 y la W40. Si `redes/data/<semana>/boxer-*.json` ya existe, no se rehace.
- Los prospectos son del canal, no de una pieza: no se atribuyen a ninguna publicación.

## Pasos (desde la raíz del repo)

1. **Semana:** la última ISO cerrada (el lunes, la que terminó ayer), formato `2026-W41`.
2. **Metricool**, por marca, con las fechas de lunes a domingo en `-03:00` (`T00:00:00-03:00` a
   `T23:59:59-03:00`). **Una dimensión por llamada y la fecha primero.** Bloques y campos (el
   orden importa: el script los busca así):

   | Bloque | Campos |
   |---|---|
   | `ig_por_tipo` | `IGAC01, IGAC02, IGAC05, IGAC06, IGAC11` |
   | `ig_por_audiencia` | `IGAC01, IGAC03, IGAC05, IGAC06` |
   | `ig_evolucion` | `IGEV01, IGEV37, IGEV16, IGEV05, IGEV06, IGEV11` (+ `"_fecha"` al final de `fields`) |
   | `ig_posts` | `IGPO01, IGPO03, IGPO06, IGPO07, IGPO12, IGPO14, IGPO15, IGPO27, IGPO28, IGPO29` |
   | `ig_reels` | `IGRE01, IGRE03, IGRE06, IGRE09, IGRE11, IGRE12, IGRE21, IGRE23, IGRE27, IGRE28` |
   | `fb_evolucion` | `FBEV17, FBEV33, FBEV34, FBEV49, FBEV21, FBEV22` (+ `"_fecha"`) |
   | `li_evolucion` | `LIEV01, LIEV27, LIEV22, LIEV28, LIEV21, LIEV23, LIEV20, LIEV24` (+ `"_fecha"`), solo Gestión |

   Guardar tal cual en `redes/data/raw/<semana>/<marca>.json`
   (`{"semana","marca","desde","hasta","bloques":{"<bloque>":{"fields":[...],"rows":[...]}}}`)
   y **commitear y pushear el crudo apenas está**: es lo único que no se puede recuperar.
   Trampas de la API: `redes/referencias/metricool.md`.
3. `python3 redes/scripts/analizar.py <semana>` → `redes/data/<semana>/<marca>.json`.
4. **Gasto en awareness** (decisión de Joana, 23/9): `ads_get_ad_entities`, cuenta
   `725901852075382`, `level: "campaign"`, campos `id, name, objective, amount_spent`,
   `time_range` de la semana, filtro `campaign.name CONTAIN ["Awareness"]` → guardar en
   `redes/data/raw/<semana>/meta-awareness.json`. Después
   `python3 redes/scripts/cruce_crm.py <semana>` (prospectos con origen «Redes», UC_GJPS17).
5. **Lectura** en `redes/data/<semana>/lectura.json`:
   `{"titular": "...", "funciono": [...], "no_funciono": [...]}`. Cada punto con su número, del
   JSON procesado. Es lectura, no recomendación: nada de "conviene publicar X".
   Antes, leer `redes/memoria/conclusiones.md` (Parte 1) para no tratar como hallazgo lo que ya
   está confirmado o descartado.
6. **Memoria:** `redes/memoria/conclusiones.md`. Parte 2 (log de la semana, aprendizajes, no
   números) siempre; Parte 1 solo si la semana confirma o tira abajo algo.
7. **Panel:** `python3 redes/scripts/panel_redes.py`. Arma `redes/panel/index.html` con todo el
   histórico más la semana nueva y las alertas automáticas. Leer el link de `paneles.yaml` →
   `panel_redes.link` y republicar `redes/panel/index.html` en ese mismo link (este panel se
   publica también en ensayo).
8. `parte.py redes ok` con titular, prospectos, alertas y el link; commit de `redes/` y push;
   mensaje al DM con el titular, el dato más importante y el link.
