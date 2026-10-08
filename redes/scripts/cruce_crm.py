#!/usr/bin/env python3
"""
Lupa: prospectos de redes sociales en Bitrix e inversión de la semana, para cruzar con el contenido.

Uso:
    python3 scripts/cruce_crm.py 2026-W40        extrae, guarda el crudo y calcula
    python3 scripts/cruce_crm.py --explorar      lista los orígenes del CRM y los campos del SPA
                                                 de inversión (para completar config/equipo.json)

Lee el webhook de la variable de entorno BITRIX_WEBHOOK_URL (o bitrix-webhook-url).
Escribe data/raw/<semana>/crm.json   (lo que devolvió Bitrix, sin datos personales)
        data/<semana>/crm.json       (los números: prospectos, inversión, costo por prospecto)
Lee también data/raw/<semana>/meta-awareness.json, que deja Lupa con el conector de Meta: el gasto
de redes sociales son solo las campañas de awareness (config/equipo.json → inversion_redes).

Reglas:
- Un prospecto de redes es todo lead creado en la semana con origen redes sociales. Se cuenta
  como total del canal, sin separar por marca: Taller no tiene flujo de conversión propio.
- Del CRM se guardan solo id, fecha, origen, estado y UTM. Nada de nombres ni teléfonos.
- "Sin dato" no es "cero": si el SPA de inversión no está configurado o no devolvió nada, la
  inversión y el costo por prospecto van en null, no en 0.
"""

import json
import os
import sys
import urllib.request
from datetime import timedelta

from equipo import CONFIG_EQUIPO, RAIZ, rango_semana

IR = CONFIG_EQUIPO["inversion_redes"]

B = CONFIG_EQUIPO["bitrix"]
CAMPOS_LEAD = ["ID", "DATE_CREATE", "SOURCE_ID", "STATUS_ID", "UTM_SOURCE", "UTM_MEDIUM", "UTM_CAMPAIGN"]


def webhook():
    for nombre in B["variables_webhook"]:
        v = os.environ.get(nombre)
        if v:
            return v.rstrip("/") + "/"
    sys.exit("No encuentro el webhook de Bitrix. Cargalo en el entorno como BITRIX_WEBHOOK_URL "
             "(o bitrix-webhook-url) y abrí una sesión nueva: las variables se leen al arrancar.")


def llamar(metodo, params):
    req = urllib.request.Request(webhook() + metodo + ".json", data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = json.loads(r.read().decode())
    if "error" in datos:
        raise RuntimeError(f"Bitrix {metodo}: {datos.get('error')} — {datos.get('error_description')}")
    return datos


def todos(metodo, params, clave=None):
    """Recorre la paginación de Bitrix (de a 50)."""
    salida, inicio = [], 0
    while True:
        d = llamar(metodo, dict(params, start=inicio))
        res = d.get("result") or []
        if clave:
            res = res.get(clave, []) if isinstance(res, dict) else res
        salida.extend(res)
        if "next" not in d:
            return salida
        inicio = d["next"]


def origenes():
    return todos("crm.status.list", {"filter": {"ENTITY_ID": "SOURCE"}})


def ids_redes():
    if B["origen_redes"]["ids"]:
        return B["origen_redes"]["ids"], None
    nombres = {n.lower() for n in B["origen_redes"]["nombres"]}
    todos_o = origenes()
    ids = [o["STATUS_ID"] for o in todos_o if o.get("NAME", "").lower() in nombres]
    return ids, [{"id": o["STATUS_ID"], "nombre": o.get("NAME")} for o in todos_o]


def explorar():
    print("Orígenes del CRM (ENTITY_ID=SOURCE):")
    for o in origenes():
        print(f"  {o['STATUS_ID']:24} {o.get('NAME')}")
    spa = B["spa_inversion"]["entity_type_id"]
    print(f"\nCampos del SPA de inversión (entityTypeId {spa}):")
    campos = llamar("crm.item.fields", {"entityTypeId": spa}).get("result", {}).get("fields", {})
    for k, v in campos.items():
        print(f"  {k:32} {v.get('title')} · {v.get('type')}")
    print("\nCompletá config/equipo.json → bitrix.spa_inversion con los nombres de fecha, monto en USD y canal.")


def extraer(semana):
    lunes, domingo = rango_semana(semana)
    desde = f"{lunes.isoformat()}T00:00:00-03:00"
    hasta = f"{(domingo + timedelta(days=1)).isoformat()}T00:00:00-03:00"
    ids, catalogo = ids_redes()
    if not ids:
        sys.exit("No encontré el origen «redes sociales» en el CRM. Corré --explorar y cargá su id en "
                 "config/equipo.json → bitrix.origen_redes.ids.")
    leads = todos("crm.lead.list", {"filter": {">=DATE_CREATE": desde, "<DATE_CREATE": hasta, "SOURCE_ID": ids},
                                    "select": CAMPOS_LEAD, "order": {"DATE_CREATE": "ASC"}})
    leads = [{k: l.get(k) for k in CAMPOS_LEAD} for l in leads]

    spa = B["spa_inversion"]
    inversion, nombres_canal = None, {}
    if spa.get("campo_fecha") and spa.get("campo_monto_usd"):
        items = todos("crm.item.list", {"entityTypeId": spa["entity_type_id"],
                                        "filter": {f">={spa['campo_fecha']}": lunes.isoformat(),
                                                   f"<={spa['campo_fecha']}": domingo.isoformat()},
                                        "select": ["id", spa["campo_fecha"], spa["campo_monto_usd"]] + ([spa["campo_canal"]] if spa.get("campo_canal") else [])},
                      clave="items")
        inversion = items
        if spa.get("campo_canal"):
            campo = llamar("crm.item.fields", {"entityTypeId": spa["entity_type_id"]})["result"]["fields"].get(spa["campo_canal"], {})
            nombres_canal = {str(i.get("ID")): i.get("VALUE") for i in campo.get("items", [])}

    crudo = {"semana": semana, "desde": lunes.isoformat(), "hasta": domingo.isoformat(),
             "origenes_redes": ids, "leads": leads, "inversion": inversion,
             "nombres_canal": nombres_canal}
    ruta = RAIZ / "data" / "raw" / semana / "crm.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(crudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return crudo


def calcular(semana, crudo):
    spa = B["spa_inversion"]
    leads = crudo["leads"]
    por_dia, por_estado = {}, {}
    for l in leads:
        dia = (l.get("DATE_CREATE") or "")[:10]
        por_dia[dia] = por_dia.get(dia, 0) + 1
        por_estado[l.get("STATUS_ID")] = por_estado.get(l.get("STATUS_ID"), 0) + 1

    inversion_usd, por_canal, dias_cargados = None, None, None
    monedas_no_usd = set()
    nombres = crudo.get("nombres_canal") or {}
    if crudo.get("inversion") is not None:
        inversion_usd, por_canal = 0.0, {}
        dias_cargados = len({str(it.get(spa["campo_fecha"]))[:10] for it in crudo["inversion"]})
        for it in crudo["inversion"]:
            crudo_monto = str(it.get(spa["campo_monto_usd"]) or "0")
            valor, _, moneda = crudo_monto.partition("|")  # los campos money de Bitrix vienen "123.45|USD"
            if moneda and moneda.upper() != "USD":
                monedas_no_usd.add(moneda.upper())
                continue
            try:
                monto = float(valor or 0)
            except (TypeError, ValueError):
                monto = 0.0
            inversion_usd += monto
            if spa.get("campo_canal"):
                c = str(it.get(spa["campo_canal"]))
                c = nombres.get(c, c)
                por_canal[c] = round(por_canal.get(c, 0) + monto, 2)
        inversion_usd = round(inversion_usd, 2)

    n = len(leads)
    notas = []
    if inversion_usd is None:
        notas.append("Sin dato de la inversión total: falta configurar el SPA en config/equipo.json.")
    elif dias_cargados != 7:
        notas.append(f"La inversión total del SPA está incompleta: tiene cargados {dias_cargados} de 7 días.")

    # El gasto de redes: solo las campañas de awareness de Meta (decisión de Joana, 23/9/2026)
    inversion_redes, moneda_redes, campanas = None, None, []
    meta = RAIZ / "data" / "raw" / semana / "meta-awareness.json"
    if meta.exists():
        crudo_meta = json.loads(meta.read_text(encoding="utf-8"))
        filtro = IR["filtro_nombre"].lower()
        inversion_redes = 0.0
        for c in crudo_meta.get("campanas", []):
            if filtro not in (c.get("name") or "").lower() or not c.get("amount_spent"):
                continue
            monto = float(c["amount_spent"]["value"])
            moneda_redes = c["amount_spent"].get("unit")
            inversion_redes += monto
            campanas.append({"campana": c["name"], "monto": round(monto, 2)})
        inversion_redes = round(inversion_redes, 2)
    else:
        notas.append("Sin dato del gasto en redes: Lupa no trajo las campañas de awareness de Meta de esta semana.")
    nota = " ".join(notas) or None
    procesado = {
        "semana": semana, "prospectos_redes": n, "por_dia": dict(sorted(por_dia.items())),
        "por_estado": por_estado, "inversion_usd": inversion_usd, "inversion_por_canal": por_canal,
        "dias_con_inversion_cargada": dias_cargados,
        "inversion_redes": inversion_redes, "moneda_inversion_redes": moneda_redes, "campanas_awareness": campanas,
        "costo_por_prospecto": round(inversion_redes / n, 2) if inversion_redes is not None and n else None,
        "nota": nota,
        "monedas_no_usd_excluidas": sorted(monedas_no_usd) or None,
    }

    lunes_prev = rango_semana(semana)[0] - timedelta(days=7)
    y2, w2, _ = lunes_prev.isocalendar()
    previa = RAIZ / "data" / f"{y2}-W{w2:02d}" / "crm.json"
    if previa.exists():
        p = json.loads(previa.read_text(encoding="utf-8"))
        procesado["comparativa"] = {
            "semana_previa": p["semana"],
            "prospectos_redes_var_pct": round(100 * (n - p["prospectos_redes"]) / p["prospectos_redes"], 1) if p["prospectos_redes"] else None,
        }
    ruta = RAIZ / "data" / semana / "crm.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(procesado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return procesado


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--explorar":
        explorar()
        return
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    semana = sys.argv[1]
    p = calcular(semana, extraer(semana))
    print(json.dumps(p, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
