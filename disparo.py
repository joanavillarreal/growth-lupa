#!/usr/bin/env python3
"""Arma y registra los disparos a las rutinas de otros agentes (`disparar_despues`).

Solo se dispara si el análisis está `ok` en el parte de hoy. El disparo en sí lo hace la
sesión con `fire_trigger`; este script dice qué mandar y deja el resultado en el parte.

Uso:
  python3 disparo.py preparar redes_semana --semana 2026-W43
      → por cada agente de `disparar_despues`: trigger_id y texto, o por qué NO se dispara
        (análisis no ok, semana que no es la anterior a hoy, ya disparado hoy).
  python3 disparo.py registrar redes_semana conti --sesion cse_...
  python3 disparo.py registrar redes_semana conti --error "fire_trigger no apareció"
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RAIZ = Path(__file__).resolve().parent
PARTES = RAIZ / "partes" / ("simulacion" if os.environ.get("LUPA_SIMULACION") == "1" else "")


def semana_iso(fecha):
    a, s, _ = fecha.isocalendar()
    return f"{a}-W{s:02d}"


def cargar(fecha):
    ruta = PARTES / f"{fecha.isoformat()}.json"
    parte = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    return ruta, parte


def preparar(agenda, analisis, semana_cerrada, fecha):
    _, parte = cargar(fecha)
    r = parte.get("analisis", {}).get(analisis, {})
    semana_plan = semana_iso(fecha)
    anterior = semana_iso(fecha - dt.timedelta(days=7))
    salida = []
    for agente in agenda["analisis"][analisis].get("disparar_despues", []):
        cfg = agenda["agentes"][agente]
        d = {"agente": agente, "rutina": cfg.get("rutina"), "trigger_id": cfg["trigger_id"]}
        previo = r.get("disparos", {}).get(agente, {})
        if r.get("estado") != "ok":
            d["no_disparar"] = (f"{analisis} no está ok hoy (estado: {r.get('estado', 'sin parte')}): "
                                "no se dispara, avisar en el resumen")
        elif semana_cerrada != anterior:
            d["no_disparar"] = (f"la semana medida ({semana_cerrada}) no es la cerrada anterior a "
                                f"hoy ({anterior}): no se dispara, avisar")
        elif previo.get("estado") == "ok":
            d["no_disparar"] = f"ya se disparó hoy a las {previo['hora']} (sesión {previo['sesion']})"
        else:
            d["texto"] = cfg["texto"].format(semana_plan=semana_plan, semana_cerrada=semana_cerrada)
        salida.append(d)
    return salida


def registrar(agenda, analisis, agente, sesion, error, fecha):
    ruta, parte = cargar(fecha)
    r = parte.get("analisis", {}).get(analisis)
    if r is None:
        sys.exit(f"no hay parte de {analisis} hoy: registrarlo antes con parte.py")
    ahora = dt.datetime.now(ZoneInfo(agenda["zona_horaria"]))
    r.setdefault("disparos", {})[agente] = {
        "estado": "fallido" if error else "ok",
        "hora": ahora.strftime("%H:%M"),
        "trigger_id": agenda["agentes"][agente]["trigger_id"],
        "sesion": sesion,
        "error": error,
    }
    ruta.write_text(json.dumps(parte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"parte actualizado: {analisis} → disparo a {agente}: {'fallido' if error else 'ok'}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("preparar")
    a.add_argument("analisis")
    a.add_argument("--semana", required=True, help="semana cerrada que midió el análisis")
    b = sub.add_parser("registrar")
    b.add_argument("analisis")
    b.add_argument("agente")
    g = b.add_mutually_exclusive_group(required=True)
    g.add_argument("--sesion", help="session_id que devolvió fire_trigger")
    g.add_argument("--error", help="qué pasó si no se pudo disparar")
    for x in (a, b):
        x.add_argument("--fecha", type=dt.date.fromisoformat, help="solo para ensayos")
    args = p.parse_args()

    agenda = yaml.safe_load((RAIZ / "agenda.yaml").read_text(encoding="utf-8"))
    if args.analisis not in agenda["analisis"]:
        p.error(f"'{args.analisis}' no está en agenda.yaml")
    fecha = args.fecha or dt.datetime.now(ZoneInfo(agenda["zona_horaria"])).date()
    if args.cmd == "preparar":
        print(json.dumps(preparar(agenda, args.analisis, args.semana, fecha),
                         ensure_ascii=False, indent=2))
    else:
        if args.agente not in agenda["analisis"][args.analisis].get("disparar_despues", []):
            p.error(f"'{args.agente}' no está en disparar_despues de {args.analisis}")
        registrar(agenda, args.analisis, args.agente, args.sesion, args.error, fecha)


if __name__ == "__main__":
    main()
