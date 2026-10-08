#!/usr/bin/env python3
"""Decide qué análisis le tocan hoy a Lupa.

Lee agenda.yaml y la fecha en hora de Argentina, y descuenta lo que ya salió
bien hoy según partes/AAAA-MM-DD.json (un análisis fallido se puede reintentar).

Uso:
  python3 que_toca_hoy.py                    # hoy
  python3 que_toca_hoy.py --fecha 2026-10-12 # simular otra fecha
  python3 que_toca_hoy.py --json             # salida para la rutina
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RAIZ = Path(__file__).resolve().parent
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def normalizar(dia):
    return dia.lower().replace("é", "e").replace("á", "a")


def toca(dias, dia_semana):
    if dias == "todos":
        return True
    if isinstance(dias, str):
        dias = [dias]
    return dia_semana in {normalizar(d) for d in dias}


def leer_parte(fecha):
    ruta = RAIZ / "partes" / f"{fecha.isoformat()}.json"
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8")).get("analisis", {})


def calcular(fecha=None):
    agenda = yaml.safe_load((RAIZ / "agenda.yaml").read_text(encoding="utf-8"))
    if fecha is None:
        fecha = dt.datetime.now(ZoneInfo(agenda["zona_horaria"])).date()
    dia_semana = DIAS[fecha.weekday()]
    parte = leer_parte(fecha)

    pendientes, ya_hechos, no_tocan = [], [], []
    for nombre, cfg in agenda["analisis"].items():
        if not toca(cfg["dias"], dia_semana):
            no_tocan.append(nombre)
        elif parte.get(nombre, {}).get("estado") == "ok":
            ya_hechos.append(nombre)
        else:
            pendientes.append(nombre)

    return {
        "fecha": fecha.isoformat(),
        "dia": dia_semana,
        "pendientes": pendientes,
        "ya_hechos": ya_hechos,
        "no_tocan": no_tocan,
        "detalle": {n: agenda["analisis"][n] for n in pendientes},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fecha", type=dt.date.fromisoformat, help="AAAA-MM-DD (simulación)")
    p.add_argument("--json", action="store_true", help="salida JSON completa")
    args = p.parse_args()

    r = calcular(args.fecha)
    if args.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return
    print(f"{r['fecha']} ({r['dia']})")
    print("  toca hoy:  " + (", ".join(r["pendientes"]) or "nada"))
    if r["ya_hechos"]:
        print("  ya hecho:  " + ", ".join(r["ya_hechos"]))
    if r["no_tocan"]:
        print("  no toca:   " + ", ".join(r["no_tocan"]))


if __name__ == "__main__":
    main()
