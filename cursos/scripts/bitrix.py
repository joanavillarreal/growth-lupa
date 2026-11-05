#!/usr/bin/env python3
"""Consulta Bitrix24 por el webhook del entorno, sin conector.

Necesita la variable de entorno **BITRIX_WEBHOOK_URL**, con la URL del webhook
entrante del portal:

    https://<portal>.bitrix24.es/rest/<id>/<token>/

El token no va nunca en el repo ni en un commit: se declara en el entorno de la
nube y se lee de ahí.

Copiado de growth-vent (scripts/bitrix.py) el 05/11/2026.

Uso:

    python3 cursos/scripts/bitrix.py origen UC_CQ4N7U
        Cuenta prospectos y negociaciones con ese origen, repartidos por etapa y
        por pipeline, con los nombres resueltos. Devuelve derivaciones, cierres,
        prospectos abiertos y etapas listos para el `dashboard.json` del evento.

    python3 cursos/scripts/bitrix.py origen UC_CQ4N7U --json salida.json
        Lo mismo, y además deja el resumen en un JSON (lo usa cursos/monitoreo.py).

    python3 cursos/scripts/bitrix.py etapas
        La tabla de etapas de prospecto y la lista de pipelines, con sus IDs.

    python3 cursos/scripts/bitrix.py llamar crm.status.list
        Llama un método cualquiera y escupe el JSON. Para explorar.

La consulta es de solo lectura: `crm.lead.list`, `crm.deal.list` y los métodos
de catálogo. Nada que escriba en el CRM.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

WEBHOOK = os.environ.get("BITRIX_WEBHOOK_URL", "").strip().rstrip("/")
PAGINA = 50

# Un prospecto derivado a un asesor queda en esta etapa. Es el ID de Bitrix,
# no el nombre: el nombre se resuelve con crm.status.list.
ETAPA_DERIVADO = "CONVERTED"

# Los cierres del canal son las negociaciones que llegaron a este pipeline.
# Se busca por nombre para que sobreviva a un cambio de ID.
PIPELINE_CIERRES = "Seguimiento Clientes"


def llamar(metodo, params=None):
    """Llama un método REST, resolviendo la paginación de Bitrix."""
    if not WEBHOOK:
        sys.exit(
            "Falta BITRIX_WEBHOOK_URL.\n"
            "Se declara en el entorno de la nube de Lupa, "
            "con la URL del webhook entrante del portal. No se pone en el repo."
        )

    items, start = [], 0
    while True:
        cuerpo = dict(params or {})
        cuerpo["start"] = start
        datos = urllib.parse.urlencode(cuerpo, doseq=True).encode()
        url = f"{WEBHOOK}/{metodo}.json"
        try:
            with urllib.request.urlopen(url, data=datos, timeout=60) as r:
                res = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            sys.exit(f"{metodo} devolvió HTTP {e.code}: {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            sys.exit(f"No se pudo llegar a Bitrix: {e.reason}")

        if "error" in res:
            sys.exit(f"{metodo}: {res.get('error')} — {res.get('error_description')}")

        tanda = res.get("result") or []
        if not isinstance(tanda, list):       # métodos que no devuelven lista
            return tanda
        items += tanda

        siguiente = res.get("next")
        if siguiente is None or not tanda:
            return items
        start = siguiente


# ------------------------------------------------------------------ catálogos

def nombres_de_etapa(entity_id):
    """{STATUS_ID: nombre} para una entidad del catálogo de estados."""
    return {s["STATUS_ID"]: s["NAME"]
            for s in llamar("crm.status.list", {"filter[ENTITY_ID]": entity_id})}


def pipelines():
    """{CATEGORY_ID (str): nombre}. El 0 no viene en la lista, se agrega."""
    cats = {"0": "General"}
    for c in llamar("crm.dealcategory.list", {}):
        cats[str(c["ID"])] = c["NAME"]
    return cats


def etapas_de_negociacion(cats):
    """{STAGE_ID: nombre} de todos los pipelines juntos."""
    nombres = dict(nombres_de_etapa("DEAL_STAGE"))
    for cid in cats:
        if cid != "0":
            nombres.update(nombres_de_etapa(f"DEAL_STAGE_{cid}"))
    return nombres


def categoria_de(stage_id):
    """El STAGE_ID trae el pipeline adelante: 'C10:NEW' -> '10'. Sin prefijo es 0."""
    if stage_id.startswith("C") and ":" in stage_id:
        return stage_id[1:].split(":", 1)[0]
    return "0"


def contar(valores):
    cuentas = {}
    for v in valores:
        cuentas[v] = cuentas.get(v, 0) + 1
    return dict(sorted(cuentas.items(), key=lambda kv: -kv[1]))


# --------------------------------------------------------------------- reporte

def por_origen(source_id):
    leads = llamar("crm.lead.list", {
        "filter[SOURCE_ID]": source_id,
        "select[]": ["ID", "STATUS_ID", "TITLE"],
    })
    deals = llamar("crm.deal.list", {
        "filter[SOURCE_ID]": source_id,
        "select[]": ["ID", "STAGE_ID", "CATEGORY_ID", "TITLE"],
    })

    n_lead = nombres_de_etapa("STATUS")
    cats = pipelines()
    n_deal = etapas_de_negociacion(cats)

    etapas = contar(n_lead.get(l["STATUS_ID"], l["STATUS_ID"]) for l in leads)
    derivaciones = sum(1 for l in leads if l["STATUS_ID"] == ETAPA_DERIVADO)
    abiertos = len(leads) - derivaciones

    por_pipeline = contar(
        cats.get(str(d.get("CATEGORY_ID") or categoria_de(d["STAGE_ID"])), "?")
        for d in deals)
    cierres = por_pipeline.get(PIPELINE_CIERRES, 0)

    print(f"Origen: {source_id}\n")
    print(f"Prospectos    {len(leads)}")
    for k, v in etapas.items():
        print(f"    {k:34} {v}")
    print(f"\nNegociaciones {len(deals)}")
    for d in deals:
        cid = str(d.get("CATEGORY_ID") or categoria_de(d["STAGE_ID"]))
        print(f"    {cats.get(cid, '?'):22} {n_deal.get(d['STAGE_ID'], d['STAGE_ID'])}")

    print(f"\nDerivaciones            {derivaciones}   prospectos en «{n_lead.get(ETAPA_DERIVADO, ETAPA_DERIVADO)}»")
    print(f"Prospectos abiertos     {abiertos}")
    print(f"Cierres                 {cierres}   negociaciones en «{PIPELINE_CIERRES}»")

    print("\n--- para el dashboard.json ---")
    print(json.dumps({
        "derivaciones": derivaciones,
        "prospectos_abiertos": abiertos,
        "cierres": cierres,
        "etapas_crm": [{"nombre": k, "n": v} for k, v in etapas.items()],
    }, ensure_ascii=False, indent=2))
    return {"source_id": source_id, "prospectos": len(leads), "negociaciones": len(deals),
            "derivaciones": derivaciones, "prospectos_abiertos": abiertos, "cierres": cierres,
            "etapas_crm": [{"nombre": k, "n": v} for k, v in etapas.items()],
            "ids_prospectos": sorted(str(l["ID"]) for l in leads),
            "ids_negociaciones": sorted(str(d["ID"]) for d in deals)}


def tabla_etapas():
    print("=== Etapas de prospecto ===")
    for k, v in nombres_de_etapa("STATUS").items():
        print(f"  {k:22} {v}")
    print("\n=== Pipelines de negociación ===")
    for k, v in pipelines().items():
        print(f"  {k:4} {v}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "origen" and len(sys.argv) in (3, 5) and (len(sys.argv) == 3 or sys.argv[3] == "--json"):
        r = por_origen(sys.argv[2])
        if len(sys.argv) == 5:      # --json <archivo>: lo lee cursos/monitoreo.py
            with open(sys.argv[4], "w", encoding="utf-8") as f:
                json.dump(r, f, ensure_ascii=False, indent=2)
    elif cmd == "etapas":
        tabla_etapas()
    elif cmd == "llamar" and len(sys.argv) >= 3:
        print(json.dumps(llamar(sys.argv[2]), ensure_ascii=False, indent=2)[:8000])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
