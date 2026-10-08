# Referencia Metricool — campos y trampas

Verificado contra la API real el 2026-09-05 con las cuentas de Boxer.

## Reglas que hay que respetar sí o sí

1. **Las dimensiones no se cruzan.** Si pedís `IGAC02` (tipo de contenido) y `IGAC03` (tipo de audiencia)
   en la misma llamada, Metricool no devuelve la combinación: devuelve las filas de una dimensión con la
   otra vacía. Cada dimensión va en su propia llamada.

2. **Pedí siempre la fecha como primer campo.** El orden de columnas de la respuesta respeta el orden en
   que pediste los campos, pero si no pedís la dimensión temporal Metricool la agrega al final por su
   cuenta y te desordena el mapeo. Pedila explícita y primera (`IGAC01`, o `IGPO01` / `IGRE01` en posts y reels).

3. **`followersGained` / `followersLost` (`IGEV43` / `IGEV44`) vienen vacíos.** No sirven.
   El crecimiento se calcula por delta del total de seguidores (`IGEV01`) entre el primer y el último día.

4. **`AD` no es contenido propio.** En el desglose por tipo (`IGAC02`), el valor `AD` es pauta.
   Nunca se mezcla con lo orgánico para juzgar contenido. Los valores posibles son
   `AD`, `CAROUSEL_CONTAINER`, `POST`, `REEL`, `STORY`.

5. **El engagement no significa lo mismo en cada red.** En Instagram y Facebook se calcula sobre
   *alcance* (personas). En LinkedIn se calcula sobre *impresiones* (veces mostrado). No son comparables
   entre sí: nunca pongas el engagement de LinkedIn y el de Instagram en la misma tabla como si midieran
   lo mismo.

6. **Los campos marcados `Deprecated` devuelven basura o nulos.** No usar ninguno.

## Campos que usa el agente

### Instagram — cuenta por tipo de contenido (connector `AC`)
Es la mejor fuente para separar orgánico de pago y comparar formatos.

| Campo | Qué es |
|---|---|
| `IGAC01` | Fecha |
| `IGAC02` | Tipo: AD / CAROUSEL_CONTAINER / POST / REEL / STORY |
| `IGAC03` | Audiencia: FOLLOWER / NON_FOLLOWER / UNKNOWN |
| `IGAC05` | Views |
| `IGAC06` | Alcance |
| `IGAC11` | Interacciones totales |

### Instagram — evolución de la cuenta (connector `evolution`)
| Campo | Qué es |
|---|---|
| `IGEV01` | Seguidores (total al día) |
| `IGEV37` | Publicaciones (posts + reels) |
| `IGEV05` | Views de cuenta (incluye pauta) |
| `IGEV06` | Alcance de cuenta (incluye pauta) |
| `IGEV11` | Alcance de posts (orgánico) |
| `IGEV16` | Stories publicadas |

### Instagram — publicación por publicación
Posts: `IGPO01` fecha · `IGPO03` texto · `IGPO06` url · `IGPO07` tipo · `IGPO10` engagement ·
`IGPO12` interacciones · `IGPO14` alcance · `IGPO15` guardados · `IGPO27` compartidos ·
`IGPO28` views · `IGPO29` **follows generados**

Reels: `IGRE01` fecha · `IGRE03` texto · `IGRE06` url · `IGRE08` engagement · `IGRE09` interacciones ·
`IGRE11` alcance · `IGRE12` guardados · `IGRE21` compartidos · `IGRE23` views ·
`IGRE24` tiempo medio visto · `IGRE27` **retención %** · `IGRE28` **view rate (>3s)**

`IGPO29` (follows) es la métrica que conecta contenido con crecimiento: qué pieza concreta trajo gente.
`IGRE27` y `IGRE28` distinguen "el hook no funcionó" (view rate bajo) de "no sostuvo" (retención baja).

### Facebook (connector `evolution`)
`FBEV17` seguidores · `FBEV33` publicaciones · `FBEV34` interacciones · `FBEV49` views de contenido ·
`FBEV11` alcance medio por post · `FBEV21` reels publicados · `FBEV22` views de reels · `FBEV35` stories

### LinkedIn (connector `evolution`)
`LIEV01` seguidores · `LIEV27` publicaciones · `LIEV22` impresiones · `LIEV28` interacciones ·
`LIEV21` reacciones · `LIEV23` comentarios · `LIEV20` compartidos · `LIEV24` clics

LinkedIn no expone alcance, solo impresiones (ver regla 5).

## Estado de las cuentas al montar esto

- **Boxer Gestión** (4938672): IG + FB + LinkedIn + Meta Ads. En la semana del 24-30/8 el 82% de las
  visualizaciones de Instagram fueron pauta. Sin separar orgánico de pago, cualquier conclusión sobre
  contenido es falsa.
- **Boxer Taller** (6516272): IG + FB, sin LinkedIn. Conectada el 8/7/2026, 42 seguidores.
  Volúmenes de 8 a 400 views por pieza. Está en `modo_lectura: lanzamiento` por eso.
