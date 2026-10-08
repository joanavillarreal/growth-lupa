#!/usr/bin/env python3
"""Redes · general: los números de las cuentas al día de hoy (corre todos los días).

Uso:
    python3 redes/scripts/general.py [--fecha AAAA-MM-DD]     (por defecto, hoy en Argentina)

Lee   redes/general/raw/<fecha>/<marca>.json  — Metricool, los 30 días que terminan AYER:
        ig_evolucion (IGEV01, IGEV37, IGEV16, IGEV05, IGEV06, IGEV11 + _fecha)
        ig_por_tipo  (IGAC01, IGAC02, IGAC05, IGAC06, IGAC11)
        fb_evolucion (FBEV17, FBEV33, FBEV34, FBEV49, FBEV21, FBEV22 + _fecha)
        li_evolucion (LIEV01, LIEV27, LIEV22, LIEV28, LIEV21, LIEV23, LIEV20, LIEV24 + _fecha), solo Gestión
Escribe redes/general/<fecha>.json:
        últimos 7 días (hasta ayer) contra los 7 anteriores, y la serie diaria de 30 días.

Todas las cuentas salen de las funciones de analizar.py (resumen_instagram, etc.), aplicadas a
una ventana de días en vez de a una semana ISO: mismos criterios que el análisis semanal.
El día de hoy nunca entra: todavía no cerró.
"""
import argparse
import copy
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REDES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REDES / "scripts"))
import analizar  # noqa: E402

MARCAS = [("boxer-gestion", "Boxer Gestión"), ("boxer-taller", "Boxer Taller")]


def fecha_de(bloque, fila):
    """La fecha de una fila: primer campo en ig_por_tipo, `_fecha` en las evoluciones."""
    campos = bloque["fields"]
    i = campos.index("_fecha") if "_fecha" in campos else 0
    return str(fila[i] or "")


def recorte(crudo, desde, hasta):
    """Copia del crudo con solo las filas entre desde y hasta (AAAA-MM-DD, inclusive)."""
    d, h = desde.replace("-", ""), hasta.replace("-", "")
    out = copy.deepcopy(crudo)
    out["desde"], out["hasta"] = desde, hasta
    for b in out["bloques"].values():
        b["rows"] = [r for r in b["rows"] if d <= fecha_de(b, r)[:8] <= h]
    return out


def resumen(crudo):
    ig = analizar.resumen_instagram(crudo)
    org, pauta = ig.get("organico") or {}, ig.get("pauta") or {}
    r = {"seguidores": (ig.get("seguidores") or {}).get("fin"),
         "seguidores_delta": (ig.get("seguidores") or {}).get("delta"),
         "alcance_organico": org.get("alcance"), "alcance_pago": pauta.get("alcance"),
         "alcance_total": ig.get("alcance_total_cuenta"),
         "views_organicas": org.get("views"), "pct_views_pauta": ig.get("pct_views_de_pauta"),
         "interacciones": org.get("interacciones"), "engagement_pct": org.get("engagement_pct"),
         "muestra_chica": ig.get("muestra_chica"),
         "engagement_no_confiable": any((f.get("engagement_pct") or 0) > 100
                                        for f in ig.get("formatos") or [])}
    if fb := analizar.resumen_facebook(crudo):
        r["fb"] = {"seguidores": fb["seguidores"]["fin"], "seguidores_delta": fb["seguidores"]["delta"],
                   "views": fb.get("views_contenido")}
    if li := analizar.resumen_linkedin(crudo):
        r["li"] = {"seguidores": li["seguidores"]["fin"], "seguidores_delta": li["seguidores"]["delta"],
                   "impresiones": li.get("impresiones")}
    return r


def construir(hoy: date):
    ayer = hoy - timedelta(days=1)
    v_desde = (ayer - timedelta(days=6)).isoformat()
    p_hasta = (ayer - timedelta(days=7)).isoformat()
    p_desde = (ayer - timedelta(days=13)).isoformat()
    s_desde = ayer - timedelta(days=29)
    salida = {"fecha": hoy.isoformat(), "datos_hasta": ayer.isoformat(),
              "ventana": {"desde": v_desde, "hasta": ayer.isoformat()},
              "previa": {"desde": p_desde, "hasta": p_hasta}, "marcas": {}}
    for clave, nombre in MARCAS:
        ruta = REDES / "general" / "raw" / hoy.isoformat() / f"{clave}.json"
        if not ruta.exists():
            salida["marcas"][clave] = {"nombre": nombre, "sin_dato": f"falta el crudo {ruta.name}"}
            continue
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        act = resumen(recorte(crudo, v_desde, ayer.isoformat()))
        prev = resumen(recorte(crudo, p_desde, p_hasta))
        var = {k: analizar.variacion(act.get(k), prev.get(k))
               for k in ("alcance_organico", "alcance_pago", "alcance_total", "interacciones")}
        var["engagement_pp"] = (round(act["engagement_pct"] - prev["engagement_pct"], 1)
                                if act.get("engagement_pct") is not None
                                and prev.get("engagement_pct") is not None else None)
        serie = []
        for i in range(30):
            d = (s_desde + timedelta(days=i)).isoformat()
            r = resumen(recorte(crudo, d, d))
            serie.append({"fecha": d, "seguidores": r["seguidores"],
                          "alcance_organico": r["alcance_organico"], "alcance_pago": r["alcance_pago"]})
        seg30 = [p["seguidores"] for p in serie if p["seguidores"] is not None]
        salida["marcas"][clave] = {
            "nombre": nombre, "ultimos_7": act, "previos_7": prev, "variacion_pct": var,
            "seguidores_delta_30d": (seg30[-1] - seg30[0]) if len(seg30) > 1 else None,
            "serie_30d": serie}
    destino = REDES / "general" / f"{hoy.isoformat()}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for clave, m in salida["marcas"].items():
        if "sin_dato" in m:
            print(f"{m['nombre']}: SIN DATO ({m['sin_dato']})")
            continue
        u = m["ultimos_7"]
        print(f"{m['nombre']}: {u['seguidores']} seguidores ({u['seguidores_delta']:+d} en 7 días) · "
              f"alcance 7d {u['alcance_total']} (orgánico {u['alcance_organico']}, pauta {u['alcance_pago']}) · "
              f"engagement orgánico {u['engagement_pct']}%")
    print(f"-> {destino.relative_to(REDES.parent)}")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fecha", type=date.fromisoformat)
    a = ap.parse_args()
    construir(a.fecha or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date())
