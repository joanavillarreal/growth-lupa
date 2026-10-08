"""Genera dashboard/viajes.html (Viajes Comerciales) a partir de las visitas.

Las visitas salen de data/viajes.csv, copia de la planilla "Leads visitados -
Artefacto" (ID de negociación, provincia, asesor que viajó). Cada ID se busca
en vivo en Bitrix para traer nombre, responsable, MRR y etapa de hoy.

Los destinos están en data/viajes_destinos.json: estado del viaje, pauta (en la
moneda de moneda_pauta; ARS se pasa a USD con moneda.ars_por_usd) y gastos del
viaje en USD por concepto (pasajes, alojamiento, viáticos). La inversión total
es pauta + gastos. Nada de esto está en el CRM: se carga a mano. Un destino sin
visitas también tiene su solapa.

La agenda la carga SDR en el propio artefacto (db, colección "agenda"). Para
sumarla a las métricas, se copia esa colección a data/viajes_agenda.json y se
vuelve a correr: así sus IDs también se consultan en el CRM.

El panel lo edita todo el equipo, así que la rutina diaria NO lo republica:
`run.py viajes-datos` deja los datos en data/viajes_datos.json y la rutina los
escribe en el documento sistema/crm de la base del artefacto, que la página
lee al abrir. `run.py viajes` arma la página completa y solo se usa cuando se
cambia el código de growth/plantilla_viajes.html.
"""
from __future__ import annotations
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

from .bitrix import Bitrix
from .config import Config, RAIZ

VISITAS = RAIZ / "data" / "viajes.csv"
DESTINOS = RAIZ / "data" / "viajes_destinos.json"
AGENDA = RAIZ / "data" / "viajes_agenda.json"
PLANTILLA = Path(__file__).parent / "plantilla_viajes.html"
SALIDA = RAIZ / "dashboard" / "viajes.html"
# Lo que la rutina diaria escribe en la base del artefacto (documento
# sistema/crm). La página lo lee de ahí, así nunca hace falta republicarla.
SALIDA_DATOS = RAIZ / "data" / "viajes_datos.json"

CAMPOS = ["ID", "TITLE", "STAGE_ID", "CATEGORY_ID", "ASSIGNED_BY_ID",
          "OPPORTUNITY", "CURRENCY_ID"]


def _grupo_etapa(stage: str, cfg: Config) -> str:
    for g in cfg["monitor"]["grupos_etapa"]:
        if stage in g.get("etapas", []) or any(stage.startswith(p) for p in g.get("prefijos", [])):
            return g["nombre"]
    return "Otros embudos"


def _seguimiento(pendientes: list[dict], ahora: datetime, tz: ZoneInfo) -> dict:
    """Estado de seguimiento de una negociación según sus actividades abiertas.

    Al día: tiene al menos una actividad pendiente que todavía no venció.
    Vencida: tiene actividades pendientes, pero todas ya vencieron.
    Sin actividad: no tiene ninguna actividad pendiente.
    """
    if not pendientes:
        return {"estado": "sin_actividad"}
    futuras, vencidas = [], []
    for a in pendientes:
        if not a.get("DEADLINE"):
            futuras.append((None, a))
            continue
        vence = datetime.fromisoformat(a["DEADLINE"]).astimezone(tz)
        (futuras if vence >= ahora else vencidas).append((vence, a))
    if futuras:
        futuras.sort(key=lambda x: (x[0] is None, x[0] or ahora))
        vence, a = futuras[0]
        return {"estado": "al_dia", "fecha": vence.date().isoformat() if vence else "",
                "asunto": (a.get("SUBJECT") or "").strip(), "vencidas": len(vencidas)}
    vencidas.sort(key=lambda x: x[0], reverse=True)
    vence, a = vencidas[0]
    return {"estado": "vencida", "fecha": vence.date().isoformat(),
            "dias": (ahora.date() - vence.date()).days,
            "asunto": (a.get("SUBJECT") or "").strip(), "vencidas": len(vencidas)}


def _ids_validos(valores) -> list[int]:
    return sorted({int(v) for v in valores if str(v).strip().isdigit()})


def armar_datos(cfg: Config, bx: Bitrix | None = None) -> dict:
    bx = bx or Bitrix()
    with VISITAS.open(encoding="utf-8") as f:
        planilla = list(csv.DictReader(f))
    agenda = json.loads(AGENDA.read_text(encoding="utf-8")) if AGENDA.exists() else []
    dest = json.loads(DESTINOS.read_text(encoding="utf-8"))
    tc = cfg["moneda"]["ars_por_usd"] if dest["moneda_pauta"] == "ARS" else 1
    destinos = {}
    for p, d in dest["destinos"].items():
        pauta_usd = round(d["pauta"] / tc, 2) if d.get("pauta") is not None else None
        gastos = {k: float(v) for k, v in (d.get("gastos_usd") or {}).items() if v is not None}
        viaje_usd = round(sum(gastos.values()), 2) if gastos else None
        hay = pauta_usd is not None or viaje_usd is not None
        destinos[p] = {"estado": d.get("estado", "finalizado"),
                       "pauta": d.get("pauta"), "pauta_usd": pauta_usd,
                       "gastos_usd": gastos, "viaje_usd": viaje_usd,
                       "inversion_usd": round((pauta_usd or 0) + (viaje_usd or 0), 2) if hay else None}

    ids = _ids_validos([v["id_negociacion"] for v in planilla] + [a.get("id_negociacion") for a in agenda])
    campo_cierre = cfg["funnel"]["cierre"]["campo_fecha"]
    deals = {d["ID"]: d for d in bx.listar("crm.deal.list", filter={"ID": ids}, select=CAMPOS + [campo_cierre])} if ids else {}

    embudos = {str(c["ID"]): c["NAME"] for c in bx.llamar("crm.dealcategory.list")["result"]}
    embudos.setdefault("0", "General")
    etapas: dict[str, str] = {}
    for cat in {d["CATEGORY_ID"] for d in deals.values()}:
        for s in bx.llamar("crm.dealcategory.stage.list", id=int(cat))["result"]:
            etapas[s["STATUS_ID"]] = s["NAME"]

    pendientes: dict[str, list[dict]] = {}
    if deals:
        for a in bx.listar("crm.activity.list",
                           filter={"OWNER_TYPE_ID": 2, "OWNER_ID": list(deals), "COMPLETED": "N"},
                           select=["ID", "OWNER_ID", "DEADLINE", "SUBJECT"]):
            pendientes.setdefault(a["OWNER_ID"], []).append(a)
    tz = ZoneInfo(cfg["notificaciones"]["timezone"])
    ahora = datetime.now(tz)
    asesores = {str(k): v for k, v in cfg["monitor"]["asesores"].items()}

    # Lo que el CRM dice hoy de cada negociación; null = el ID no existe.
    crm: dict[str, dict | None] = {}
    for i in ids:
        d = deals.get(str(i))
        if not d:
            crm[str(i)] = None
            continue
        crm[d["ID"]] = {
            "nombre": d["TITLE"].strip(),
            "responsable": asesores.get(d["ASSIGNED_BY_ID"], f"Usuario #{d['ASSIGNED_BY_ID']}"),
            "embudo": embudos.get(d["CATEGORY_ID"], f"Embudo {d['CATEGORY_ID']}"),
            "etapa": etapas.get(d["STAGE_ID"], d["STAGE_ID"]),
            "grupo": _grupo_etapa(d["STAGE_ID"], cfg),
            "cerrado": bool(d.get(campo_cierre)),
            "fecha_cierre": (d.get(campo_cierre) or "")[:10],
            "mrr": float(d.get("OPPORTUNITY") or 0),
            "moneda": d.get("CURRENCY_ID") or "USD",
            "actividad": _seguimiento(pendientes.get(d["ID"], []), ahora, tz),
        }

    return {
        "generado_en": ahora.isoformat(timespec="minutes"),
        "portal": urlparse(bx.base).netloc,
        "provincias": list(dict.fromkeys([v["provincia"] for v in planilla] + list(destinos))),
        "destinos": destinos,
        "moneda_inversion": dest["moneda_pauta"],
        "conceptos": dest.get("conceptos", {}),
        "tc": tc,
        "planilla": [{"id": v["id_negociacion"], "provincia": v["provincia"],
                      "asesor_viaje": v["asesor_viaje"]} for v in planilla],
        "agenda": agenda,
        "crm": crm,
    }


def exportar_datos(cfg: Config) -> Path:
    """Solo los datos, sin la agenda (la página la lee en vivo de la base)."""
    datos = {k: v for k, v in armar_datos(cfg).items() if k != "agenda"}
    SALIDA_DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return SALIDA_DATOS


def construir(cfg: Config) -> Path:
    """Página completa con los datos embebidos. Solo para cambios de código:
    el día a día va por exportar_datos y la base del artefacto."""
    datos = armar_datos(cfg)
    html = PLANTILLA.read_text(encoding="utf-8").replace(
        "/*__DATOS__*/null", json.dumps(datos, ensure_ascii=False))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(html, encoding="utf-8")
    return SALIDA
