#!/usr/bin/env python3
"""Registra el resultado de un análisis en el parte del día.

Escribe/actualiza partes/AAAA-MM-DD.json (fecha de Argentina). No pushea:
eso lo hace la rutina después de cada análisis.

Uso:
  python3 parte.py funnel ok --resumen "..." --datos datos.json
  python3 parte.py meta fallido --error "ads_get_ad_accounts no apareció tras 3 búsquedas"
  python3 parte.py gasto_meta ok --datos gasto.json      # preparación compartida

--herramientas: nombres completos con los que cargaron (ej. mcp__abc123__getBrandSettings).
Cada llamada suma un intento del día para ese análisis.

--datos es un JSON con lo encontrado (hallazgos, alertas, métricas clave, etc.).
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RAIZ = Path(__file__).resolve().parent
# Con LUPA_SIMULACION=1 los partes van a partes/simulacion/: una corrida simulada nunca
# deja un parte que una corrida real lea como "ya hecho".
PARTES = RAIZ / "partes" / ("simulacion" if os.environ.get("LUPA_SIMULACION") == "1" else "")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("analisis")
    p.add_argument("estado", choices=["ok", "fallido"])
    p.add_argument("--resumen", default="")
    p.add_argument("--error", default=None)
    p.add_argument("--herramientas", nargs="*", default=[], help="nombres completos cargados")
    p.add_argument("--datos", type=Path, help="JSON con hallazgos/alertas/métricas")
    p.add_argument("--fecha", type=dt.date.fromisoformat, help="solo para ensayos")
    args = p.parse_args()

    agenda = yaml.safe_load((RAIZ / "agenda.yaml").read_text(encoding="utf-8"))
    paneles = yaml.safe_load((RAIZ / "paneles.yaml").read_text(encoding="utf-8"))
    preparaciones = agenda.get("preparaciones", {})
    if args.analisis not in agenda["analisis"] and args.analisis not in preparaciones:
        p.error(f"'{args.analisis}' no está en agenda.yaml")
    es_prep = args.analisis in preparaciones
    if args.estado == "fallido" and not args.error:
        p.error("un análisis fallido necesita --error con lo que realmente pasó")

    tz = ZoneInfo(agenda["zona_horaria"])
    ahora = dt.datetime.now(tz)
    fecha = args.fecha or ahora.date()
    ruta = PARTES / f"{fecha.isoformat()}.json"
    parte = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {
        "fecha": fecha.isoformat(), "modo": paneles["modo"], "analisis": {}}
    seccion = parte.setdefault("preparacion" if es_prep else "analisis", {})

    if es_prep:
        cfg = preparaciones[args.analisis]
        artefacto = None
        # una preparación avisa donde avisan los análisis que la usan
        cfg = {**cfg, "slack": ", ".join(sorted({a["slack"] for a in agenda["analisis"].values()
                                              if args.analisis in a.get("necesita", [])}))}
    else:
        cfg = agenda["analisis"][args.analisis]
    if not es_prep and not cfg.get("artefacto"):
        artefacto = None          # análisis sin panel (ej. inversion)
    elif not es_prep:
        panel = paneles["paneles"][cfg["artefacto"]]
        publica = paneles["modo"] == "oficial" or panel.get("en_ensayo") == "publicar"
        # En ensayo, los paneles "comparar" se generan en el repo y no se publican.
        artefacto = panel["link"] if publica else f"no publicado (ensayo): {panel.get('archivo')}"
    previo = seccion.get(args.analisis, {})
    seccion[args.analisis] = {
        "estado": args.estado,
        "intentos": previo.get("intentos", 0) + 1,
        "hora": ahora.strftime("%H:%M"),
        "resumen": args.resumen,
        "error": args.error,
        "herramientas": args.herramientas,
        "artefacto": artefacto,
        "datos": json.loads(args.datos.read_text(encoding="utf-8")) if args.datos else {},
        "para": cfg.get("disparar_despues", []),
    }
    if previo:
        seccion[args.analisis]["intentos_previos"] = previo.get("intentos_previos", []) + [
            {k: previo.get(k) for k in ("estado", "hora", "error", "herramientas")}]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(parte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = seccion[args.analisis]
    print(f"parte actualizado: {ruta.relative_to(RAIZ)} → {args.analisis}: {args.estado} (intento {r['intentos']})")
    if args.estado == "fallido" and r["intentos"] >= agenda.get("max_intentos_por_dia", 3):
        print(f"TOPE ALCANZADO: avisar por Slack ({cfg['slack']}) que {args.analisis} "
              "no se reintenta hasta mañana")


if __name__ == "__main__":
    main()
