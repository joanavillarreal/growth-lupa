#!/usr/bin/env python3
"""
Cambios en la cuenta desde el registro de actividad de Meta (reemplaza a memoria/cambios.jsonl
de agente-meta-ads, que Lupa ya no lee).

Uso:
    python3 scripts/cambios_desde_actividad.py <respuesta de ads_account_get_activity_logs> \
            [--desde 2026-09-21] [--salida memoria/cambios-actividad.jsonl]

Entra la respuesta TAL CUAL de `ads_account_get_activity_logs` (cuenta 725901852075382), y sale
una línea por cambio con lo que dibuja el panel: fecha, nivel, entidad, antes, despues, quien.

Qué cuenta como cambio: lo que hizo una persona (no Meta) sobre campañas, conjuntos y anuncios:
estado, presupuesto, puja, público, objetivo de optimización, y altas de campañas, conjuntos y
anuncios. No cuentan los públicos personalizados, la facturación ni la biblioteca de imágenes.

Lo que el registro NO dice es el porqué ni a qué experimento responde: eso es de Turbo. Los
cambios salen con `que` vacío y `origen: "registro de actividad de Meta"`.

Las horas del registro vienen en la zona de la cuenta (Argentina: el 07/10 "9:35 AM" es la
pausa de DemoLu que agente-meta-ads anotó a las 09:35 ART).
"""
import argparse, datetime, json, os, re, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NIVEL = {"Ad": "anuncio", "Ad set": "conjunto", "Campaign": "campana"}
TIPOS = {   # event_type del registro -> qué se cambió
    "Ad status updated": "estado", "Ad set status updated": "estado",
    "Campaign status updated": "estado",
    "Ad set budget updated": "presupuesto", "Campaign budget updated": "presupuesto",
    "Ad set bidding updated": "puja", "Ad set bid strategy updated": "puja",
    "Ad set targeting updated": "publico",
    "Ad set optimization goal updated": "optimizacion",
    "Ad created": "alta", "Ad set created": "alta", "Campaign created": "alta",
}
INTERMEDIOS = {"Pending Process", "Pending Review", "In Process"}


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        crudo = json.load(f)
    r = crudo.get("result", crudo) if isinstance(crudo, dict) else crudo
    return json.loads(r) if isinstance(r, str) else r


def fecha_hora(texto):
    """'10/7/2026 at 9:35 AM' -> datetime (hora de la cuenta)."""
    return datetime.datetime.strptime(texto.replace(" at ", " "), "%m/%d/%Y %I:%M %p")


def nivel_de(tipo):
    for k in ("Ad set", "Campaign", "Ad"):
        if tipo.startswith(k):
            return NIVEL[k]
    return None


VENTANA = datetime.timedelta(minutes=15)


def monto(v):
    """Presupuesto: {'type': 'payment_amount', 'currency': 'ARS', 'old_value': 1000000} -> '10.000 ARS/dia'."""
    if isinstance(v, dict) and isinstance(v.get("old_value", v.get("new_value")), (int, float)):
        n = v.get("old_value", v.get("new_value")) / 100
        return f"{n:,.0f}".replace(",", ".") + f" {v.get('currency', '')}/dia".replace(" /", "/")
    return v


def cambios(eventos, desde=None):
    utiles = []
    for e in eventos:
        tipo = e.get("event_type", "")
        if tipo == "Updated status of ad after it finishes Ad Review":
            tipo = "Ad status updated"     # es el estado que queda después de la revisión
        if tipo not in TIPOS:
            continue
        cuando = fecha_hora(e["datetime"])
        if desde and cuando.date().isoformat() < desde:
            continue
        extra = json.loads(e["extra_data"]) if e.get("extra_data") else {}
        a, d = extra.get("old_value"), extra.get("new_value")
        if TIPOS[tipo] == "presupuesto":
            a, d = monto(a), monto(d)
        utiles.append({"cuando": cuando, "tipo": tipo, "e": e, "meta": str(e.get("actor_id")) == "0",
                       "antes": a, "despues": d})
    utiles.sort(key=lambda u: u["cuando"])

    # Un cambio de estado llega en varios pasos (Activo -> Procesando -> En revisión -> Inactivo),
    # a veces a lo largo de unos minutos y con el último paso hecho por Meta al terminar la
    # revisión. Se junta en uno: lo arranca una persona y lo cierra el último paso dentro de
    # 15 minutos. Lo que hace Meta sin que nadie lo haya pedido no es un cambio en la cuenta.
    cadenas, abierta = [], {}
    for u in utiles:
        k = (u["e"]["object_id"], TIPOS[u["tipo"]])
        c = abierta.get(k)
        if c and u["cuando"] - c["ultimo"] <= VENTANA:
            c["pasos"].append(u); c["ultimo"] = u["cuando"]
        elif not u["meta"]:
            c = {"pasos": [u], "ultimo": u["cuando"]}
            abierta[k] = c; cadenas.append(c)

    # El armado de algo nuevo no es un cambio en la cuenta: lo que se le hace a un objeto en la
    # hora siguiente a crearlo (puja, público, objetivo, primer estado) queda adentro de su alta.
    # Y el alta de un anuncio suelto tampoco se marca: se marcan campañas y conjuntos nuevos.
    altas = {}
    for c in cadenas:
        u = c["pasos"][0]
        if TIPOS[u["tipo"]] == "alta":
            altas.setdefault(u["e"]["object_id"], u["cuando"])
    def es_armado(u):
        t0 = altas.get(u["e"]["object_id"])
        return t0 is not None and TIPOS[u["tipo"]] != "alta" and datetime.timedelta(0) <= u["cuando"] - t0 <= datetime.timedelta(hours=1)
    cadenas = [c for c in cadenas
               if not es_armado(c["pasos"][0])
               and not (TIPOS[c["pasos"][0]["tipo"]] == "alta" and nivel_de(c["pasos"][0]["tipo"]) == "anuncio")]

    salida = []
    for c in cadenas:
        u0, pasos = c["pasos"][0], c["pasos"]
        firmes = lambda vs: [v for v in vs if v is not None and not (isinstance(v, str) and v in INTERMEDIOS)]
        a = (firmes([p["antes"] for p in pasos]) or [None])[0]
        d = (firmes([p["despues"] for p in pasos]) or [None])[-1]
        if isinstance(a, (dict, list)) or isinstance(d, (dict, list)):
            a = d = None   # público o puja: el registro trae la spec entera; se marca el cambio sin detalle
        if a is not None and a == d:
            continue
        tipo = TIPOS[u0["tipo"]]
        if tipo == "alta":
            a, d = None, "creado"
        elif a is None and d is None:
            d = {"publico": "cambió el público", "puja": "cambió la puja",
                 "optimizacion": "cambió el objetivo de optimización"}.get(tipo)
        salida.append({
            "fecha": u0["cuando"].date().isoformat(),
            "hora": u0["cuando"].strftime("%H:%M"),
            "nivel": nivel_de(u0["tipo"]),
            "entidad": u0["e"].get("object_name") or u0["e"].get("object_id"),
            "entidad_id": u0["e"].get("object_id"),
            "cambio": TIPOS[u0["tipo"]],
            "que": "",
            "antes": a, "despues": d,
            "quien": u0["e"].get("actor_name"),
            "origen": "registro de actividad de Meta",
        })
    return salida


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("respuesta")
    ap.add_argument("--desde", default="2026-09-21")
    ap.add_argument("--salida", default=os.path.join(RAIZ, "memoria", "cambios-actividad.jsonl"))
    a = ap.parse_args()
    cs = cambios(leer(a.respuesta), a.desde)
    # Se acumula: el registro de Meta guarda 3 meses; el archivo guarda todo. Sin duplicados.
    previos = []
    if os.path.isfile(a.salida):
        with open(a.salida, encoding="utf-8") as f:
            previos = [json.loads(l) for l in f if l.strip() and not l.startswith("#")]
    clave = lambda c: (c["entidad_id"], c["cambio"], c["fecha"], c["hora"])
    vistos = {clave(c) for c in previos}
    nuevos = [c for c in cs if clave(c) not in vistos]
    todos = sorted(previos + nuevos, key=lambda c: (c["fecha"], c["hora"]))
    with open(a.salida, "w", encoding="utf-8") as f:
        f.write("# Cambios en la cuenta desde el registro de actividad de Meta "
                "(scripts/cambios_desde_actividad.py). Una línea por cambio.\n")
        for c in todos:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"{len(cs)} cambios en la respuesta, {len(nuevos)} nuevos -> {os.path.relpath(a.salida, RAIZ)} ({len(todos)} en total)")


if __name__ == "__main__":
    main()
