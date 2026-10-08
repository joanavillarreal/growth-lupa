"""Orígenes de Bitrix que no están en ningún canal de config/definitions.yaml.

    python3 run.py origenes [--aplicar]

Regla de Joana (08/10/2026):
- Un origen nuevo cuyo nombre empieza con un prefijo de `prefijos_automaticos` de un canal
  (hoy: "Visita Presencial" -> viajes_comerciales) se suma a ese canal sin preguntar.
  Con --aplicar se escribe en definitions.yaml; sin --aplicar solo se muestra.
- Cualquier otro origen sin canal se lista para el mensaje del día: el canal lo decide Joana.

Mira el catálogo completo de orígenes del snapshot (no solo los que ya tienen prospectos), así
un origen recién creado entra a su canal o se avisa antes de traer el primer lead. Al 08/10/2026
todo el catálogo tiene canal o está en origenes_sin_atribuir.
"""
from __future__ import annotations

import re

from .config import RUTA_CONFIG, Config


def detectar(snap: dict, cfg: Config) -> dict:
    conocidos = {str(o) for c in cfg.canales.values() for o in c["origenes"]}
    conocidos |= {str(o) for o in cfg["origenes_sin_atribuir"]}
    prefijos = [(p.lower(), clave) for clave, c in cfg.canales.items()
                for p in c.get("prefijos_automaticos", [])]
    con_leads = {}
    for l in snap["prospectos"]:
        sid = str(l.get("SOURCE_ID") or "")
        if sid:
            con_leads[sid] = con_leads.get(sid, 0) + 1
    automaticos, a_decidir = [], []
    for sid, nombre in sorted(snap.get("catalogo_origenes", {}).items()):
        if sid in conocidos:
            continue
        canal = next((c for p, c in prefijos if (nombre or "").lower().startswith(p)), None)
        item = {"id": sid, "nombre": nombre, "prospectos": con_leads.get(sid, 0)}
        if canal:
            automaticos.append(dict(item, canal=canal))
        else:
            a_decidir.append(item)
    return {"automaticos": automaticos, "a_decidir": a_decidir}


def aplicar(automaticos: list[dict]) -> None:
    """Suma cada origen al final de la lista `origenes` de su canal, sin tocar el resto."""
    texto = RUTA_CONFIG.read_text(encoding="utf-8")
    for a in automaticos:
        bloque = re.search(rf"\n  {a['canal']}:\n(.*?)(?=\n  \w+:\n|\n\S)", texto, re.S)
        lista = re.search(r"origenes: \[(.*?)\]", bloque.group(1), re.S)
        fin = bloque.start(1) + lista.end(1)
        texto = texto[:fin] + f', "{a['id']}"' + texto[fin:]
    RUTA_CONFIG.write_text(texto, encoding="utf-8")
    Config()  # que el archivo siga abriendo
