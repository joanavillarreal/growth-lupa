---
name: boxer-cruce-crm
description: >-
  Trae de Bitrix24, por el webhook del entorno, los prospectos creados en la semana con origen
  redes sociales y la inversión del SPA "Inversiones y Gastos", y calcula prospectos, inversión y
  costo por prospecto para cruzarlos con el contenido publicado. Usala desde Lupa en el análisis
  semanal, o cuando se pregunte "¿cuántos prospectos trajeron las redes?", "¿cuánto nos cuesta un
  prospecto de redes?" o "cruzá las redes con el CRM".
---

# Cruce con el CRM

## Qué cuenta como prospecto de redes

**Todo lead creado en Bitrix en la semana con origen «Redes»** (`UC_GJPS17`). Se cuenta como total del
canal, sin separar Gestión de Taller: Taller no tiene flujo de conversión propio y los talleres que
llegan vienen de la pauta de Gestión (decisión de Joana, 23/9/2026).

Hoy no se puede saber de qué pieza vino cada prospecto: la palabra clave se responde a mano y el
lead entra sin ella. Por eso el cruce es **por semana**, no por pieza. No atribuyas prospectos a
una publicación.

## Cómo se accede

Por el **webhook de Bitrix del entorno de la nube** (variable `BITRIX_WEBHOOK_URL`, o
`bitrix-webhook-url`), no por el conector de Bitrix. El script la lee sola. Si no la encuentra,
avisá: las variables del entorno se cargan al arrancar la sesión, así que una recién agregada
recién la ve la sesión siguiente.

## La primera vez

```bash
python3 scripts/cruce_crm.py --explorar
```

Lista los orígenes del CRM y los campos del SPA de inversión. Con eso completá
`config/equipo.json` → `bitrix`: el id del origen redes sociales (si el nombre no coincide solo) y
los campos de fecha, monto en USD y canal del SPA. Commiteá la config.

## Cada semana

**Primero, el gasto en redes.** Es solo lo que se gastó en las **campañas de awareness de Meta
Ads** (decisión de Joana, 23/9/2026). En Meta esas campañas tienen objetivo de tráfico, así que se
reconocen por el nombre: las que dicen "Awareness". Con el conector de Meta
(`ads_get_ad_entities`, cuenta `inversion_redes.ad_account_id` de `config/equipo.json`, nivel
campaña, campos `id`, `name`, `objective`, `amount_spent`, el lunes a domingo de la semana en
`time_range` y el filtro `campaign.name` CONTAIN `Awareness`), guardá la respuesta tal cual en
`data/raw/<semana>/meta-awareness.json`:

```json
{"semana": "2026-W38", "fuente": "Meta Ads · ads_get_ad_entities",
 "campanas": [{"id": "...", "name": "JY | Awareness", "objective": "OUTCOME_TRAFFIC",
               "amount_spent": {"value": "17027.52", "unit": "ARS"}}]}
```

Después:

```bash
python3 scripts/cruce_crm.py <semana>
```

Deja el crudo en `data/raw/<semana>/crm.json` (solo id, fecha, origen, estado y UTM: nada de
nombres ni teléfonos) y los números en `data/<semana>/crm.json`. Commiteá los dos apenas estén: son
el historial.

## Cómo se lee

- **El costo por prospecto** es el gasto en awareness de Meta dividido los prospectos de origen
  «Redes». Va en la moneda en que lo informa Meta (pesos): no se convierte a mano.
- **Sin dato no es cero.** Si no se trajo el gasto de Meta, el costo por prospecto queda en
  `null` y se dice "sin dato". Una semana con cero prospectos no tiene costo por prospecto.
- La inversión total del SPA (Meta y Google, en dólares) se muestra como contexto. La carga
  `boxer-carga-inversion` los viernes: si la semana está incompleta, el script lo avisa.
- Una semana con más prospectos y un tipo de contenido distinto es una pista, no una prueba.
  Cuando un patrón se repite, va a la memoria como hipótesis **En prueba**.
