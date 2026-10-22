# Memoria — Meta (guardia y Panel Meta Ads)

Lo ya revisado con Joana que no hay que volver a marcar.

## 22/10/2026 — Panel Meta Ads puesto al día con `agente-meta-ads`

- Entre el 08 y el 22/10 el panel se siguió cambiando en `agente-meta-ads` y Lupa lo pisaba
  cada mañana con la versión vieja (el 22/10 a las 07:56 se perdió el bloque Presupuesto diario).
  Joana mandó un paquete (patch + plantilla + LEEME) y se aplicó: Presupuesto diario, Meta → CRM
  solo con formularios (+ re-ingresos aparte), vista Anuncios activos, CPL con límite 4.000 ARS
  (14/10), y el bloque de cada campaña lo manda `config/campanas.json`.
- **Desde ahora los cambios del panel los pide Joana a Lupa.** `agente-meta-ads` deja de
  publicar en ese link; si hace falta algo de ese lado, llega como un paquete así.
- Meta → CRM puede pasar de 100% con los re-ingresos (el 22/10: 116 nuevos + 19 re-ingresos
  contra 134 cobrados). No es un error: el aviso de re-ingreso no distingue formulario de Meta
  y de la web. La tarjeta lo topea en 100% y lo explica.
- `JY | Provincias Visitadas (AGENTE META)` es conversión (Formulario anuncios 1, origen Meta
  Ads Formulario), aunque el nombre diga otra cosa (Joana, 19/10).

## 22/10/2026 — Meta → CRM en un solo %, sin pruebas internas

- Meta → CRM = (prospectos nuevos + re-ingresos) / formularios que cobró Meta (Joana). Que un
  re-ingreso no cree prospecto está bien. Un solo %, topeado en 100%. Con datos al 21/10:
  100% (116 nuevos + 18 re-ingresos de 134).
- Las pruebas internas no cuentan como re-ingreso (la de Joana del 01/10 va en 0).
- `JY | Visitas a tu Local (AGENTE META)`: sus leads caen en la etapa "Visitas presenciales".
  No se le fija origen del CRM (`etapa_crm` en `config/campanas.json`); ya no está a confirmar.
