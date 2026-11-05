#!/usr/bin/env python3
"""Arma el dashboard de cursos y webinars para publicar como artefacto.

Junta el `dashboard.json` de cada carpeta de `cursos/eventos/`, lo mete dentro
de `cursos/panel/index.html` y deja el archivo listo en
`cursos/panel/dist/index.html`. Ese es el archivo que se publica con la
herramienta Artifact, siempre a la misma URL (panel `cursos_en_vivo` de
paneles.yaml).

    python3 cursos/panel/build.py

Copiado de growth-vent (dashboard/build.py) el 05/11/2026; desde ese día los
datos del panel viven en el repo de Lupa.

El panel agrupa los eventos por trimestre (según su primera fecha) y abre en
el calendario del trimestre en curso. Un evento con `"oculto": true` en su
dashboard.json no entra.
"""

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
CURSOS = RAIZ / "cursos"
PLANTILLA = CURSOS / "panel" / "index.html"
SALIDA = CURSOS / "panel" / "dist" / "index.html"
MARCADOR = "__DATA__"


def cargar_eventos():
    eventos = []
    for archivo in sorted((CURSOS / "eventos").glob("*/dashboard.json")):
        if archivo.parent.name.startswith("_"):
            continue  # _plantilla y cualquier otra carpeta auxiliar
        try:
            evento = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"{archivo.relative_to(RAIZ)}: JSON inválido — {e}")
        if evento.pop("oculto", False):
            continue
        faltan = [c for c in ("id", "titulo", "tag", "kind", "fechas", "stats")
                  if c not in evento]
        if faltan:
            sys.exit(f"{archivo.relative_to(RAIZ)}: faltan campos {faltan}")
        eventos.append(evento)
    if not eventos:
        sys.exit("No hay ningún cursos/eventos/*/dashboard.json para publicar.")
    eventos.sort(key=lambda e: (e["fechas"] or [""])[0], reverse=True)
    return eventos


def main():
    eventos = cargar_eventos()
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    if MARCADOR not in plantilla:
        sys.exit(f"{PLANTILLA.name} perdió el marcador {MARCADOR}.")

    datos = json.dumps(eventos, ensure_ascii=False, separators=(", ", ": "))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(plantilla.replace(MARCADOR, datos), encoding="utf-8")

    print(f"{SALIDA.relative_to(RAIZ)} · {SALIDA.stat().st_size / 1024:.1f} KB")
    for e in eventos:
        inscriptos = e["stats"].get("total", 0)
        print(f"  {e['fechas'][0]}  {e['titulo'][:46]:46}  {inscriptos:>4} inscriptos")


if __name__ == "__main__":
    main()
