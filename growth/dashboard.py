"""Genera dashboard/index.html (Monitor de Growth) a partir del último snapshot.

El HTML es autocontenido: los datos se embeben como JSON y los gráficos se
dibujan en SVG en el navegador. Así el archivo se publica como artefacto y
se actualiza republicando el mismo archivo, sin backend.

Los números salen de growth/monitor.py, un trimestre por vez.
"""
from __future__ import annotations
import json
from pathlib import Path

from . import ingest, monitor
from .config import Config, RAIZ

SALIDA = RAIZ / "dashboard" / "index.html"


def armar_datos(cfg: Config) -> dict:
    return monitor.armar(ingest.cargar_ultimo(), cfg)


def construir(cfg: Config) -> Path:
    datos = armar_datos(cfg)
    plantilla = (Path(__file__).parent / "plantilla.html").read_text(encoding="utf-8")
    html = plantilla.replace("/*__DATOS__*/null", json.dumps(datos, ensure_ascii=False))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    return SALIDA
