---
id: EXP-001
nombre: Aumentar generación en Meta
canal: meta
estado: corriendo
descripcion: >
  Sumar en Meta un conjunto con anuncios que funcionaron históricamente,
  apuntado al público al que apuntaban entonces (similares de quienes vieron
  videos de Boxer), en paralelo al conjunto actual y sin subir el presupuesto.
problema: >
  Meta pasó de traer 7,6 leads de formulario por día al CRM en marzo de 2026
  a 2,9 en septiembre. En los últimos 28 días entraron 80 leads contra 133 de
  los 28 anteriores, con el mismo gasto (US$ 473 contra US$ 470), y el costo
  por lead subió de US$ 3,53 a US$ 5,91.
hipotesis: >
  Hoy le estamos mostrando los anuncios a públicos distintos de los que
  generaban. Si volvemos a apuntar a similares de gente que vio videos de
  Boxer, con anuncios que ya funcionaron, Meta va a traer más leads por el
  mismo gasto. El público actual de "Conversión segmentación similar"
  (similar 3% cruzado con 5 intereses de mecánica y Advantage+ apagado) es
  mucho más chico, y los públicos armados con nuestras bases de datos
  tampoco dieron resultado.
datos:
  - "Marzo 2026: 237 leads de formulario en el CRM (7,6 por día), 30% de derivación y 13,5% de no calificados. Septiembre: 83 leads (2,9 por día)."
  - "En marzo los leads venían de 4 conjuntos amplios (similares de interacción y de quienes vieron videos, sin intereses y con Advantage+). Hoy vienen de 1 conjunto frío con intereses y Advantage+ apagado, más remarketing."
  - "El anuncio de Jesi trajo 302 formularios entre diciembre de 2025 y abril de 2026, a unos 3.500 ARS cada uno."
  - "La calidad de marzo no era peor: 6,6 leads útiles por día contra 2,7 hoy."
  - "Monitor, últimos 28 días: 80 leads contra 133 de los 28 anteriores, con el costo por lead subiendo de US$ 3,53 a US$ 5,91."
  - "Fuente del análisis histórico: https://claude.ai/artifact/PtZL3uJ8TDJzFafysUG19A"
solucion: >
  Se activa el conjunto "Conversión - LAL Vieron video 1-3% (AGENTE META)"
  (similares 1-3% de quienes vieron videos de Boxer) con los anuncios que
  funcionaron históricamente. "Conversión segmentación similar" sigue
  corriendo y el presupuesto total de Meta no cambia durante la prueba.
metrica_primaria: leads_conjunto_dia
efecto_esperado: "6 leads por día o más del conjunto"
# Se mide sobre el conjunto nuevo, no sobre todo el canal Meta.
conjunto_meta: "120254694684840427"
meta_leads_dia: 6
n_minimo: 60
lanzamiento: 2026-10-05
fin_analisis: 2026-10-25
responsable: "Joana Villarreal"
resultado: ""
decision: ""
---

El éxito se mide sobre el conjunto "Conversión - LAL Vieron video 1-3%
(AGENTE META)" (adset 120254694684840427): tiene que traer 6 leads por día o
más, según lo que reporta Meta. Los números de todo el canal Meta quedan como
contexto, para ver que el resto no empeore.
