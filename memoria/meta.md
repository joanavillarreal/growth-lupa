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

## 01/11/2026 — Vista Anuncios activos rearmada (pedido de Joana)

- Una pestaña por campaña; adentro, cada conjunto con su público (incluye, intereses, excluye,
  edad, lugar, presupuesto) y una tabla con sus anuncios activos: botón Ver anuncio, nombre,
  resultados de Meta, convertidos del CRM (sobre los leads de ese anuncio) y CPL real
  (gasto / leads en el CRM). Todo desde el 08/09 o desde que se creó el anuncio, hasta ayer.
- El texto del anuncio queda plegado ("Texto del anuncio") para la SDR. Se sacaron el
  formulario por anuncio y el link al Administrador.

## 02/11/2026 — "Ver anuncio" abre la pieza en Drive

- Yamila no tiene acceso al Business de Meta y los posteos de los anuncios solo los ve quien
  administra la página. Joana pasa el link de Drive de cada pieza y va a
  `meta/config/anuncios-drive.json` (por nombre exacto del anuncio). Con link, el botón dice
  "Ver anuncio" y abre Drive; sin link, queda "Ver en Facebook" (solo para administradores).
- Cuando aparezca un anuncio activo nuevo sin link de Drive, mencionarlo en el mensaje del día
  para que Joana lo pase. Los links no se inventan.

## 02/11/2026 (tarde) — anuncios en revisión en la vista Anuncios activos

- Joana sumó anuncios a media tarde. Se volvieron a pedir #8, #9 y #11 y se reemplazaron en
  `datos/meta-ads/guardia/2026-11-02/mcp/` (la versión de la mañana queda en git).
- El panel ahora también muestra los anuncios IN_PROCESS / PENDING_REVIEW, con la marca
  "En revisión de Meta" (DemoStock salió IN_PROCESS). No cuentan como activos en el título.

## 24/11/2026 — Torta del CRM por anuncio (pedido de Joana)

- En Anuncios activos, las campañas de conversión (clientes potenciales) y remarketing tienen
  una columna "En el CRM" con una torta por anuncio y por conjunto: al centro, cuántos leads
  entraron; alrededor, derivados (`convertido`), no pasaron de SDR (`inactivo`), no calificados
  (`no_util`), en curso (`abierta`) y, si hay, los que pasaron a otro canal (`otra`).
- Mismos leads que "Convertidos" y "CPL real": con UTM del anuncio, desde el 08/09.

## 24/11/2026 (tarde) — Clientes potenciales Boxer Taller y anuncios "casi sin entrega"

- `JY | Clientes potenciales Boxer Taller (AGENTE META)`: Joana confirmó origen Meta Ads
  Formulario. Formulario "Formulario Boxer Taller - Leads" (UTM Campaign de sus leads), producto
  Boxer Taller. En Bitrix no hubo ningún lead suyo hasta el 24/11; ese día entraron 3 juntos
  (15:18-15:19, hora del portal), contra 7 resultados que contaba Meta al 23/11. El cruce por
  UTM (anuncio + conjunto) los toma: entran al panel en la corrida del 25/11.
- Joana apagó el 24/11 a las 9:18 la campaña Viajes Presenciales Luciana y a las 9:27 el
  conjunto Santi - La Plata y Sur, después de la corrida. Se volvieron a traer #8 y #9 ese día.
- Vista Anuncios activos: cada anuncio muestra lo que gastó en los últimos 3 días (hasta ayer,
  de anuncio-diario.json) y "Casi sin entrega" si se llevó menos del 5% del gasto de su conjunto
  en ese tramo (Meta concentra el presupuesto). Activo en Meta ≠ circulando.

## 24/11/2026 (tarde) — Campaña nueva: JY | Conversiones Entre Rios (AGENTE META)

- Creada el 24/11 a las 11:14, objetivo OUTCOME_LEADS, 2 conjuntos de 2.000 ARS/día en Entre
  Ríos y 2 anuncios. Sumada al mapa como `a_confirmar` (bloque conversion por el nombre): falta
  que Joana confirme producto y origen del CRM.
- No había entrado al panel porque la llamada #8 pedía solo ACTIVE y sus anuncios estaban en
  revisión. Desde el 24/11 la #8 pide ACTIVE, IN_PROCESS y PENDING_REVIEW.
- Joana confirmó el 24/11: Conversiones Entre Rios entra como Meta Ads Formulario, producto
  Boxer Gestión. Esa tarde la campaña pasó a 6 anuncios (4 cargados 11:34-11:35 y uno con
  creativo nuevo); 5 en revisión de Meta y 1 activo.
- Joana (24/11): los anuncios que no tienen link de Drive quedan así ("Ver en Facebook"). No
  pedirle los links que faltan; se suman cuando ella los pase.
