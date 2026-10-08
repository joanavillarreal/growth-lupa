#!/usr/bin/env python3
"""Compara un panel generado por Lupa contra el publicado en su link oficial.

Se usa en modo ensayo: Lupa genera el panel en el repo, lee el oficial con la
herramienta Artifact (`action: read`, `path: index.html`) y compara los datos
embebidos, no el HTML (el servicio agrega su propio envoltorio al publicar).

Uso:
  python3 comparar.py monitor_growth <html_oficial_leido>
  python3 comparar.py panel_meta_ads <html_oficial_leido> --json salida.json

Sale con código 0 si los datos coinciden y 1 si hay diferencias (las lista).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent

# Cómo encontrar los datos dentro del HTML de cada panel.
EXTRACTORES = {
    "monitor_growth": r"const D = (\{.*?\});\n",
    "panel_meta_ads": r'<script type="application/json" id="datos">(.*?)</script>',
}


def datos(html, patron):
    m = re.search(patron, html, re.S)
    if not m:
        raise SystemExit("no encontré el bloque de datos en el HTML")
    return json.loads(m.group(1))


def diferencias(a, b, ruta=""):
    if type(a) is not type(b):
        yield ruta or "/", a, b
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                yield f"{ruta}/{k}", a.get(k, "<falta>"), b.get(k, "<falta>")
            else:
                yield from diferencias(a[k], b[k], f"{ruta}/{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            yield f"{ruta} (largo)", len(a), len(b)
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diferencias(x, y, f"{ruta}[{i}]")
    elif a != b:
        yield ruta, a, b


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("panel", choices=EXTRACTORES)
    p.add_argument("oficial", type=Path, help="HTML leído del link oficial")
    p.add_argument("--json", type=Path, help="guarda el resultado para el parte")
    args = p.parse_args()

    panel = yaml.safe_load((RAIZ / "paneles.yaml").read_text(encoding="utf-8"))["paneles"][args.panel]
    propio = datos((RAIZ / panel["archivo"]).read_text(encoding="utf-8"), EXTRACTORES[args.panel])
    oficial = datos(args.oficial.read_text(encoding="utf-8"), EXTRACTORES[args.panel])

    difs = [{"ruta": r, "lupa": a, "oficial": b} for r, a, b in diferencias(propio, oficial)]
    resultado = {"panel": args.panel, "coincide": not difs, "n_diferencias": len(difs),
                 "diferencias": difs[:200]}
    if args.json:
        args.json.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str) + "\n",
                             encoding="utf-8")
    if not difs:
        print(f"{panel['nombre']}: los datos coinciden con el oficial.")
        return
    print(f"{panel['nombre']}: {len(difs)} diferencias con el oficial (Lupa → oficial):")
    for d in difs[:40]:
        print(f"  {d['ruta']}: {str(d['lupa'])[:70]} → {str(d['oficial'])[:70]}")
    sys.exit(1)


if __name__ == "__main__":
    main()
