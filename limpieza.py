#!/usr/bin/env python3
"""Limpieza del histórico (análisis `limpieza`, los lunes). Por defecto solo muestra el plan.

Uso:
  python3 limpieza.py                  # qué borraría hoy (no toca nada)
  python3 limpieza.py --aplicar        # borra
  python3 limpieza.py --fecha 2026-12-14   # simular otro día

Reglas (Joana, 08/10/2026):
  - Resúmenes semanales, lecturas y conclusiones: se guardan siempre.
  - Crudos de Metricool y de Meta: 8 semanas, y después se borran.
      Excepción: los crudos de Meta que el Panel Meta Ads todavía usa (desde el inicio del
      trimestre anterior, porque el panel compara contra el Q anterior entero), y los mapas
      conjunto -> campaña y los exports históricos, que no son de un día sino de referencia.
  - Fotos diarias del CRM: todas las de los últimos 90 días; las más viejas se reducen a una por
    semana ISO (la última de cada semana). Las fotos semanales del CRM no se borran nunca.
"""
import argparse
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent
CRUDO_DIAS = 56          # 8 semanas
CRM_DIARIO_DIAS = 90


def fin_semana(etiqueta):
    """'2026-W40...' -> el domingo que cierra esa semana."""
    m = re.match(r"(\d{4})-W(\d{2})", etiqueta)
    return date.fromisocalendar(int(m.group(1)), int(m.group(2)), 7) if m else None


def inicio_q_anterior(hoy):
    q = (hoy.month - 1) // 3
    ini_actual = date(hoy.year, 3 * q + 1, 1)
    ant = ini_actual - timedelta(days=1)
    return date(ant.year, 3 * ((ant.month - 1) // 3) + 1, 1)


def plan(hoy):
    corte_crudo = hoy - timedelta(days=CRUDO_DIAS)
    corte_meta = min(corte_crudo, inicio_q_anterior(hoy))
    corte_crm = hoy - timedelta(days=CRM_DIARIO_DIAS)
    borrar = []   # (ruta, motivo)

    # 1. Metricool semanal: se borran los crudos de Metricool y de Meta; crm.json es la foto
    #    semanal del CRM y se queda.
    for d in sorted((RAIZ / "redes" / "data" / "raw").glob("????-W??")):
        fin = fin_semana(d.name)
        if fin and fin < corte_crudo:
            for f in sorted(d.glob("*.json")):
                if f.name != "crm.json":
                    borrar.append((f, f"crudo de {d.name} (terminó el {fin}), más de 8 semanas"))

    # 2. Metricool diario (redes · general)
    for d in sorted((RAIZ / "redes" / "general" / "raw").glob("????-??-??")):
        if date.fromisoformat(d.name) < corte_crudo:
            borrar.append((d, "crudo diario de Metricool, más de 8 semanas"))

    # 3. Meta: carpetas con fecha. Nunca los mapas de conjuntos ni los históricos.
    base = RAIZ / "meta" / "datos" / "meta-ads"
    # la última carpeta de guardia de cada semana conserva su foto del CRM aunque tenga +90 días
    ultima_de_semana = {}
    for d in sorted(base.glob("guardia/????-??-??")):
        ultima_de_semana[date.fromisoformat(d.name).isocalendar()[:2]] = d
    for d in sorted([*base.glob("guardia/????-??-??"), *base.glob("????-W??*"), *base.glob("????-??-??-*"),
                     *base.glob("actividad/????-??-??.json"), *base.glob("gasto/????-??-??")]):
        if "mapa" in d.name or "historico" in d.name:
            continue
        if d.parent.name in ("guardia", "actividad", "gasto") or re.match(r"\d{4}-\d{2}-\d{2}-", d.name):
            dia = date.fromisoformat(d.name[:10])
        else:
            dia = fin_semana(d.name)
        if dia and dia < corte_meta:
            # la foto diaria del CRM que guarda la guardia sigue la regla de 90 días
            conserva_crm = (d / "crm").exists() and (
                dia >= corte_crm or ultima_de_semana.get(dia.isocalendar()[:2]) == d)
            if conserva_crm:
                for sub in sorted(p for p in d.iterdir() if p.name != "crm"):
                    borrar.append((sub, f"crudo de Meta del {dia}, más de 8 semanas y fuera del Q anterior"))
            else:
                borrar.append((d, f"crudo de Meta del {dia}, más de 8 semanas y fuera del Q anterior"))

    # 4. Fotos diarias del CRM (snapshots del funnel): 90 días enteras, después una por semana.
    viejas = {}
    for f in sorted((RAIZ / "data" / "snapshots").glob("????-??-??.json")):
        dia = date.fromisoformat(f.stem)
        if dia < corte_crm:
            viejas.setdefault(dia.isocalendar()[:2], []).append(f)
    for semana, fs in viejas.items():
        for f in fs[:-1]:   # se queda la última de cada semana
            borrar.append((f, f"foto diaria del CRM de más de 90 días; queda {fs[-1].name} para la semana {semana[0]}-W{semana[1]:02d}"))
    return borrar, {"crudo": corte_crudo, "meta": corte_meta, "crm": corte_crm}


def tamano(p):
    return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--fecha", type=date.fromisoformat)
    a = ap.parse_args()
    hoy = a.fecha or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    borrar, cortes = plan(hoy)
    print(f"Limpieza al {hoy}: crudos antes del {cortes['crudo']} · Meta antes del {cortes['meta']} "
          f"· fotos diarias del CRM antes del {cortes['crm']}")
    total = 0
    for ruta, motivo in borrar:
        total += tamano(ruta)
        print(f"  {'BORRO' if a.aplicar else 'borraría'} {ruta.relative_to(RAIZ)} — {motivo}")
        if a.aplicar:
            shutil.rmtree(ruta) if ruta.is_dir() else ruta.unlink()
    print(f"{len(borrar)} elementos, {total / 1e6:.1f} MB{'' if a.aplicar else ' (no se borró nada: falta --aplicar)'}")


if __name__ == "__main__":
    main()
