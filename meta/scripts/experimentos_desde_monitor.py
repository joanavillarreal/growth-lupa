#!/usr/bin/env python3
"""
Experimentos del Panel Meta Ads desde la solapa Experimentos del Monitor de Growth (reemplaza a
memoria/experimentos.jsonl de agente-meta-ads, que Lupa ya no lee).

Uso (desde la raíz de growth-lupa):
    python3 meta/scripts/experimentos_desde_monitor.py

Lee experiments/EXP-*.md con el mismo lector del Monitor (growth.experiments.cargar), se queda con
los del canal Meta y escribe meta/memoria/experimentos-monitor.jsonl con los campos que usa el
panel. Cuando exista Turbo, sus experimentos de Meta llegan por su parte, no por su repo.
"""
import json, os, sys

META = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(META))
from growth import experiments  # noqa: E402

iso = lambda v: v.isoformat() if hasattr(v, "isoformat") else (v or None)
salida = os.path.join(META, "memoria", "experimentos-monitor.jsonl")
filas = []
for e in experiments.cargar():
    if e.get("canal") != "meta":
        continue
    filas.append({
        "id": e.get("id"), "abierto": iso(e.get("lanzamiento")), "revisar_en": iso(e.get("fin_analisis")),
        "estado": e.get("estado"), "nivel": "conjunto" if e.get("conjunto_meta") else "canal",
        "hipotesis": " ".join(str(e.get("hipotesis") or "").split()),
        "cambio": " ".join(str(e.get("solucion") or "").split()),
        "metrica": e.get("metrica_primaria"), "objetivo": e.get("efecto_esperado"),
        "n_base": e.get("n_minimo"), "valor_base": None,
        "veredicto": e.get("decision") or None, "notas": " ".join(str(e.get("nombre") or "").split()),
        "origen": "Monitor de Growth · solapa Experimentos",
    })
with open(salida, "w", encoding="utf-8") as f:
    f.write("# Experimentos de Meta desde la solapa Experimentos del Monitor (experiments/EXP-*.md).\n")
    for x in filas:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")
print(f"{len(filas)} experimentos de Meta -> meta/memoria/experimentos-monitor.jsonl")
