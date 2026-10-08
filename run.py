#!/usr/bin/env python3
"""CLI del agente de growth.

  python3 run.py ingest              # trae Bitrix -> data/snapshots/
  python3 run.py report [--mes AAAA-MM]
  python3 run.py alerts
  python3 run.py dashboard
  python3 run.py daily               # ingest + dashboard + alertas (rutina diaria)
"""
from __future__ import annotations
import argparse
import json
from datetime import date

from growth import anomalies, experiments, health, ingest, metrics
from growth.config import Config


def _mes_completo(etiqueta: str) -> tuple[str, str]:
    y, m = (int(x) for x in etiqueta.split("-"))
    inicio = date(y, m, 1)
    fin = date(y + (m == 12), (m % 12) + 1, 1)
    return inicio.isoformat(), (fin.toordinal() - 1 and date.fromordinal(fin.toordinal() - 1)).isoformat()


def cmd_ingest(args, cfg):
    destino = ingest.correr(cfg)
    datos = json.loads(destino.read_text(encoding="utf-8"))
    print(f"Snapshot {destino.name}: {len(datos['prospectos'])} prospectos, "
          f"{len(datos['negociaciones'])} negociaciones, {len(datos['gastos'])} registros de gasto.")


def cmd_report(args, cfg):
    snap = ingest.cargar_ultimo()
    desde, hasta = _mes_completo(args.mes) if args.mes else (
        snap["ventana"]["desde"], snap["ventana"]["hasta"])
    r = metrics.calcular(snap, cfg, desde, hasta)
    print(f"\nFUNNEL {desde} -> {hasta}  (USD)\n")
    cols = ["Canal", "Gasto", "Prosp", "Deriv", "Presup", "Cierres", "CPL", "CAC", "%Der", "%Pres", "%Conv"]
    print("{:<24}{:>9}{:>7}{:>7}{:>8}{:>9}{:>9}{:>10}{:>8}{:>8}{:>8}".format(*cols))
    filas = [r["general"]] + [r["canales"][c] for c in cfg.canales_activos if c in r["canales"]]
    filas += [v for k, v in r["canales"].items() if k not in cfg.canales_activos and v["prospectos"]]
    for f in filas:
        print("{:<24}{:>9}{:>7}{:>7}{:>8}{:>9}{:>9}{:>10}{:>8}{:>8}{:>8}".format(
            f["nombre"][:23], f"${f['gasto_usd']:,.0f}", f["prospectos"], f["derivados"],
            f["presupuestados"], f["cierres"],
            f"${f['cpl_usd']:.2f}" if f["cpl_usd"] else "—",
            f"${f['cac_usd']:,.0f}" if f["cac_usd"] else "—",
            f"{f['pct_derivacion']}%" if f["pct_derivacion"] is not None else "—",
            f"{f['pct_presupuestado']}%" if f["pct_presupuestado"] is not None else "—",
            f"{f['pct_conversion']}%" if f["pct_conversion"] is not None else "—"))
    g = r["general"]
    print(f"\nMRR cerrado: ${g['mrr_cerrado_usd']:,.0f}  |  presupuestado: ${g['mrr_presupuestado_usd']:,.0f}"
          f"  |  ticket: ${g['ticket_promedio_usd'] or 0:,.0f}")
    print(f"Velocidad: {g['dias_a_derivar_mediana']} días a derivar, "
          f"{g['dias_a_cerrar_mediana']} días de derivado a cierre (medianas)")
    s = health.revisar(snap, cfg, desde, hasta)
    print(f"Confiabilidad del dato: {s['confiabilidad'].upper()} ({s['alertas']} alertas)")


def cmd_alerts(args, cfg):
    snap = ingest.cargar_ultimo()
    hallazgos = anomalies.detectar(snap, cfg)
    if not hallazgos:
        print("Sin anomalías por encima de umbral.")
        return
    for h in hallazgos:
        print(f"[{h['severidad'].upper():>5}] {h['titulo']} — {h['ambito']}: "
              f"{h['valor_previo']} → {h['valor_actual']} ({h['variacion']}) | {h['ventana']}")


def cmd_alarma(args, cfg):
    """La alarma diaria. Sin novedades no imprime mensaje: no se manda nada."""
    from growth import alerts, slack
    snap = ingest.cargar_ultimo()
    msj = slack.mensaje_diario(alerts.diarias(snap, cfg), snap["ventana"]["hasta"])
    print(msj if msj else "Sin novedades: la alarma diaria no manda mensaje.")


def cmd_semanal(args, cfg):
    """El informe semanal. Se manda siempre."""
    from growth import alerts, slack
    snap = ingest.cargar_ultimo()
    informe = alerts.informe_semanal(snap, cfg)
    print(slack.mensaje_semanal(informe, cfg, args.url or ""))


def cmd_contexto_experimento(args, cfg):
    """Números reales del canal para cargar un experimento nuevo."""
    snap = ingest.cargar_ultimo()
    c = experiments.contexto(snap, cfg, args.canal, args.dias)
    nombres = {"generados": "Leads generados", "gasto": "Gasto USD", "cpl": "CPL USD",
               "pct_derivacion": "% derivación (camada)", "costo_por_derivado": "Costo por derivado USD",
               "pct_no_calificacion": "% no calificación", "presupuestados": "Presupuestados (camada)"}
    print(f"Canal {args.canal} · últimos {args.dias} días {c['tramo'][0]} a {c['tramo'][1]} "
          f"(contra {c['tramo_previo'][0]} a {c['tramo_previo'][1]})")
    for k, nombre in nombres.items():
        print(f"  {nombre:<28}{str(c['actual'].get(k)):>10}{str(c['previo'].get(k)):>10}")
    print(f"Ritmo: {c['leads_por_semana']} leads por semana")
    print(f"Experimentos corriendo en el canal: {', '.join(c['corriendo_en_el_canal']) or 'ninguno'}")
    print(f"Próximo id: {c['siguiente_id']}")


def cmd_dashboard(args, cfg):
    from growth.dashboard import construir
    salida = construir(cfg)
    print(f"Dashboard generado: {salida}")


def cmd_daily(args, cfg):
    cmd_ingest(args, cfg)
    cmd_dashboard(args, cfg)
    print()
    cmd_alerts(args, cfg)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    r = sub.add_parser("report"); r.add_argument("--mes", help="AAAA-MM")
    sub.add_parser("alerts")
    sub.add_parser("alarma")
    w = sub.add_parser("semanal"); w.add_argument("--url", help="link al dashboard")
    sub.add_parser("dashboard")
    x = sub.add_parser("contexto-experimento")
    x.add_argument("--canal", required=True, help="clave de canal: meta, google, redes_sociales, general...")
    x.add_argument("--dias", type=int, default=28)
    sub.add_parser("daily")
    args = ap.parse_args()
    cfg = Config()
    {"ingest": cmd_ingest, "report": cmd_report, "alerts": cmd_alerts,
     "dashboard": cmd_dashboard, "daily": cmd_daily,
     "alarma": cmd_alarma, "semanal": cmd_semanal,
     "contexto-experimento": cmd_contexto_experimento}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
