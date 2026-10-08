#!/usr/bin/env python3
"""
Campañas de Meta que no están en config/campanas.json: las suma al mapa como "a confirmar".

Uso:
    python3 scripts/campanas_nuevas.py datos/meta-ads/guardia/<hoy>/ [--json salida.json]

Lee el roster de campañas (primera de las tres llamadas de `mcp/roster.json`) y
`mcp/campana-total.json` (las que gastaron en los últimos 14 días aunque hoy estén pausadas).
Cada campaña que no está en el mapa se agrega con:

    origenes_crm: "PENDIENTE"   -> el panel la muestra sin origen confirmado
    a_confirmar: true            -> Joana confirma producto y origen del CRM
    bloque / grupo / destino     -> la clasificación por nombre de analizar_meta.bloque_de;
                                    es una sugerencia, no un dato

Lupa mantiene el mapa (Joana, 08/10/2026), pero el producto y el origen los confirma Joana:
las que quedan `a_confirmar` se listan en el mensaje del día, todos los días, hasta que ella
conteste. Cuando exista Turbo, las campañas nuevas llegan por su parte.

Imprime una línea por campaña nueva y por campaña todavía a confirmar. Código 0 siempre.
"""
import argparse, datetime, json, os, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
from analizar_meta import bloque_de  # noqa: E402

MAPA = os.path.join(RAIZ, "config", "campanas.json")


def entidades(ruta):
    """Las filas de una respuesta de ads_get_ad_entities guardada tal cual."""
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    r = d.get("ad_entities", d) if isinstance(d, dict) else d
    return json.loads(r) if isinstance(r, str) else (r or [])


def en_meta(carpeta):
    """{nombre: {id, estado}} de las campañas del roster y de campana-total."""
    out = {}
    roster = os.path.join(carpeta, "mcp", "roster.json")
    if os.path.isfile(roster):
        with open(roster, encoding="utf-8") as f:
            llamadas = json.load(f)
        if llamadas:
            for c in entidades_de(llamadas[0]):
                out[c["name"]] = {"id": c.get("id"), "estado": c.get("effective_status")}
    total = os.path.join(carpeta, "mcp", "campana-total.json")
    if os.path.isfile(total):
        for c in entidades(total):
            out.setdefault(c["name"], {"id": c.get("id"), "estado": c.get("effective_status")})
    return out


def entidades_de(llamada):
    r = llamada.get("ad_entities", llamada) if isinstance(llamada, dict) else llamada
    return json.loads(r) if isinstance(r, str) else (r or [])


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("carpeta")
    ap.add_argument("--json")
    ap.add_argument("--mapa", default=MAPA)
    a = ap.parse_args()

    with open(a.mapa, encoding="utf-8") as f:
        cfg = json.load(f)
    conocidas = {c["nombre"] for c in cfg["campanas"]}
    hoy = os.path.basename(os.path.normpath(a.carpeta))
    try:
        datetime.date.fromisoformat(hoy)
    except ValueError:
        hoy = datetime.date.today().isoformat()

    nuevas = []
    for nombre, x in sorted(en_meta(a.carpeta).items()):
        if nombre in conocidas:
            continue
        b = bloque_de(nombre)
        nueva = {
            "nombre": nombre, "id_meta": x["id"],
            "grupo": "eventual" if b == "eventual" else "nucleo",
            "bloque": "evento" if b == "eventual" else b,
            "destino": "PENDIENTE",
            "origenes_crm": "PENDIENTE",
            "activa": x["estado"] == "ACTIVE",
            "a_confirmar": True,
            "nota": f"Agregada por Lupa el {hoy}: estaba en Meta y no en el mapa. Bloque sugerido "
                    f"por el nombre. Falta que Joana confirme producto y origen del CRM"
                    + (" (y fecha_evento, si es un evento)." if b == "eventual" else "."),
        }
        cfg["campanas"].append(nueva)
        nuevas.append(nueva)

    if nuevas:
        with open(a.mapa, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")

    pendientes = [c for c in cfg["campanas"] if c.get("a_confirmar")]
    for c in nuevas:
        print(f"NUEVA: {c['nombre']} (id {c['id_meta']}, bloque sugerido {c['bloque']})")
    for c in pendientes:
        if c not in nuevas:
            print(f"A CONFIRMAR: {c['nombre']}")
    if not pendientes:
        print("Mapa de campañas al día: todas las de Meta están confirmadas.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"nuevas": [c["nombre"] for c in nuevas],
                       "a_confirmar": [c["nombre"] for c in pendientes]}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
