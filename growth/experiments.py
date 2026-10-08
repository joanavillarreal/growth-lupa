"""Registro de experimentos de adquisición.

Cada experimento es un .md en experiments/ con frontmatter YAML. Se versiona
con el repo a propósito: el historial de qué probamos y qué decidimos vale
tanto como el número, y sobrevive a cualquier dashboard.
"""
from __future__ import annotations
from pathlib import Path
import yaml

from .config import RAIZ

DIR = RAIZ / "experiments"
ESTADOS = ("propuesto", "corriendo", "concluido", "descartado")


def cargar() -> list[dict]:
    salida = []
    for archivo in sorted(DIR.glob("EXP-*.md")):
        texto = archivo.read_text(encoding="utf-8")
        if not texto.startswith("---"):
            continue
        _, frente, cuerpo = texto.split("---", 2)
        datos = yaml.safe_load(frente) or {}
        datos["cuerpo"] = cuerpo.strip()
        datos["archivo"] = archivo.name
        salida.append(datos)
    return sorted(salida, key=lambda e: str(e.get("id", "")), reverse=True)


def activos() -> list[dict]:
    return [e for e in cargar() if e.get("estado") == "corriendo"]


def marcas_para_serie(experimentos: list[dict]) -> list[dict]:
    """Experimentos con fecha de inicio, para dibujarlos sobre las series."""
    return [
        {"id": e["id"], "titulo": e.get("titulo", ""), "canal": e.get("canal", ""),
         "inicio": str(e["inicio"]), "fin": str(e.get("fin") or "")}
        for e in experimentos if e.get("inicio")
    ]


def siguiente_id() -> str:
    existentes = [e.get("id", "") for e in cargar()]
    numeros = [int(x.split("-")[1]) for x in existentes if str(x).startswith("EXP-")]
    return f"EXP-{max(numeros, default=0) + 1:03d}"


# --------------------------------------------------------------------------- #
# resultado en métricas, para la solapa Experimentos del Monitor
# --------------------------------------------------------------------------- #
# Qué se mide de cada experimento y para qué lado es mejor. Todo sobre la
# CAMADA del tramo (los prospectos creados entre lanzamiento y fin), porque un
# cambio en la generación solo puede mover lo que entra a partir de él.
METRICAS = {
    "generados": ("Leads generados", "sube"),
    "cpl": ("Costo por lead", "baja"),
    "pct_derivacion": ("% de derivación", "sube"),
    "costo_por_derivado": ("Costo por derivado", "baja"),
    "pct_no_calificacion": ("% de no calificación", "baja"),
    "presupuestados": ("Presupuestados de la camada", "sube"),
}


def _fecha(v) -> str:
    return str(v or "")[:10]


def _medir(snap, cfg, canal: str, desde: str, hasta: str) -> dict:
    from . import metrics
    r = metrics.calcular(snap, cfg, desde, hasta)
    f = r["general"] if canal in ("", "general") else r["canales"].get(canal)
    if not f:
        return {k: None for k in METRICAS} | {"gasto": 0.0}
    der = f["derivados_cohorte"]
    return {
        "gasto": f["gasto_usd"],
        "generados": f["prospectos"],
        "cpl": f["cpl_usd"],
        "pct_derivacion": f["pct_derivacion_cohorte"],
        "costo_por_derivado": round(f["gasto_usd"] / der, 2) if der and f["gasto_usd"] else None,
        "pct_no_calificacion": f["pct_no_calificacion"],
        "presupuestados": f["presupuestados_cohorte"],
    }


def _conjunto(cfg, exp: dict, ini: str, corte: str) -> dict | None:
    """El conjunto de anuncios de Meta que el experimento tiene que mover.

    Sale de data/meta_adsets.json, que refresca la corrida diaria con el
    conector de Meta. Los leads son los que reporta Meta.
    """
    import json
    from datetime import date, timedelta
    adset = str(exp.get("conjunto_meta") or "")
    if not adset:
        return None
    ruta = RAIZ / "data" / "meta_adsets.json"
    doc = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    c = (doc.get("conjuntos") or {}).get(adset, {})
    tc = (cfg["gasto"].get("meta_api") or {}).get("cotizacion_ars_usd") or 1
    meta = exp.get("meta_leads_dia")
    serie, d = [], date.fromisoformat(ini)
    while d.isoformat() <= corte:
        x = (c.get("dias") or {}).get(d.isoformat())
        serie.append({"fecha": d.isoformat(), "leads": None if x is None else int(x.get("leads") or 0),
                      "gasto_usd": None if x is None else round((x.get("gasto_ars") or 0) / tc, 2)})
        d += timedelta(days=1)
    con_dato = [x for x in serie if x["leads"] is not None]
    leads = sum(x["leads"] for x in con_dato)
    gasto = round(sum(x["gasto_usd"] for x in con_dato), 2)
    por_dia = round(leads / len(con_dato), 1) if con_dato else None
    return {
        "id": adset, "nombre": c.get("nombre") or adset,
        "dias_con_dato": len(con_dato), "dias": len(serie),
        "ultimo_dato": con_dato[-1]["fecha"] if con_dato else None,
        "leads": leads, "leads_por_dia": por_dia, "meta_por_dia": meta,
        "gasto_usd": gasto, "gasto_ars_por_dia": round(sum(
            ((c.get("dias") or {}).get(x["fecha"]) or {}).get("gasto_ars", 0) for x in con_dato) / len(con_dato))
            if con_dato else None,
        "cpl_usd": round(gasto / leads, 2) if leads else None,
        "ok": None if por_dia is None or not meta else por_dia >= meta,
        "serie": serie,
    }


def resultado(snap: dict, cfg, exp: dict) -> dict:
    """El canal durante la prueba contra el mismo largo de tiempo justo antes."""
    from datetime import date, timedelta
    hoy = snap["ventana"]["hasta"]
    ini = _fecha(exp.get("lanzamiento") or exp.get("inicio"))
    fin = _fecha(exp.get("fin_analisis") or exp.get("fin"))
    if not ini:
        return {"estado_lectura": "sin_fechas"}
    if ini > hoy:
        return {"estado_lectura": "por_lanzar", "desde": ini, "hasta": fin}
    corte = min(fin or hoy, hoy)
    largo = (date.fromisoformat(corte) - date.fromisoformat(ini)).days + 1
    b_hasta = (date.fromisoformat(ini) - timedelta(days=1)).isoformat()
    b_desde = (date.fromisoformat(ini) - timedelta(days=largo)).isoformat()
    canal = str(exp.get("canal") or "general")
    durante = _medir(snap, cfg, canal, ini, corte)
    antes = _medir(snap, cfg, canal, b_desde, b_hasta)
    filas = []
    for clave, (nombre, mejor) in METRICAS.items():
        a, d = antes.get(clave), durante.get(clave)
        cambio, tipo, juicio = None, None, None
        if a is not None and d is not None:
            if clave.startswith("pct"):
                cambio, tipo = round(d - a, 1), "pp"
            elif a:
                cambio, tipo = round((d - a) / a * 100, 1), "pct"
            if cambio is not None:
                juicio = "igual" if cambio == 0 else (
                    "mejora" if (cambio > 0) == (mejor == "sube") else "empeora")
        filas.append({"clave": clave, "nombre": nombre, "antes": a, "durante": d,
                      "cambio": cambio, "tipo": tipo, "juicio": juicio,
                      "primaria": clave == exp.get("metrica_primaria")})
    n_min = exp.get("n_minimo") or 0
    terminado = bool(fin) and fin < hoy
    conjunto = _conjunto(cfg, exp, ini, corte)
    if conjunto:
        # Se juzga por el ritmo diario del conjunto: hace falta una semana de
        # datos para que un día flojo o un día bueno no decidan.
        if conjunto["dias_con_dato"] < 7:
            lectura = "faltan_datos"
        else:
            lectura = "lista" if terminado else "en_curso"
    elif durante.get("generados", 0) < n_min:
        lectura = "faltan_datos"
    else:
        lectura = "lista" if terminado else "en_curso"
    return {
        "estado_lectura": lectura,
        "desde": ini, "hasta": corte, "fin_analisis": fin, "dias": largo,
        "base": {"desde": b_desde, "hasta": b_hasta},
        "n_actual": durante.get("generados"), "n_minimo": n_min,
        "gasto": {"antes": antes.get("gasto"), "durante": durante.get("gasto")},
        "metricas": filas,
        "conjunto": conjunto,
    }


def para_monitor(snap: dict, cfg) -> list[dict]:
    """Los experimentos listos para pintar: sus campos más el resultado."""
    salida = []
    for e in cargar():
        datos = e.get("datos") or []
        if isinstance(datos, str):
            datos = [datos]
        salida.append({
            "id": str(e.get("id", "")),
            "nombre": e.get("nombre") or e.get("titulo") or "",
            "canal": str(e.get("canal") or "general"),
            "canal_nombre": "General" if str(e.get("canal") or "general") == "general"
                            else cfg.nombre_canal(str(e.get("canal"))),
            "estado": e.get("estado", "propuesto"),
            "descripcion": e.get("descripcion") or "",
            "problema": e.get("problema") or "",
            "hipotesis": e.get("hipotesis") or "",
            "datos": [str(d) for d in datos],
            "solucion": e.get("solucion") or "",
            "metrica_primaria": e.get("metrica_primaria") or "",
            "efecto_esperado": str(e.get("efecto_esperado") or ""),
            "n_minimo": e.get("n_minimo") or 0,
            "lanzamiento": _fecha(e.get("lanzamiento") or e.get("inicio")),
            "fin_analisis": _fecha(e.get("fin_analisis") or e.get("fin")),
            "responsable": e.get("responsable") or "",
            "conclusion": e.get("resultado") or "",
            "decision": e.get("decision") or "",
            "notas": e.get("cuerpo") or "",
            "resultado": resultado(snap, cfg, e),
        })
    return salida


def contexto(snap: dict, cfg, canal: str, dias: int = 28) -> dict:
    """Los números del canal en los últimos `dias` días cerrados y en los
    `dias` anteriores: la base para escribir el problema y la hipótesis, y
    para estimar cuánto tarda en juntarse el n mínimo."""
    from datetime import date, timedelta
    hoy = date.fromisoformat(snap["ventana"]["hasta"])
    fin = hoy - timedelta(days=1)
    ini = fin - timedelta(days=dias - 1)
    p_fin = ini - timedelta(days=1)
    p_ini = p_fin - timedelta(days=dias - 1)
    actual = _medir(snap, cfg, canal, ini.isoformat(), fin.isoformat())
    previo = _medir(snap, cfg, canal, p_ini.isoformat(), p_fin.isoformat())
    por_semana = round((actual.get("generados") or 0) / dias * 7, 1)
    activos = [e["id"] + " " + str(e.get("nombre") or e.get("titulo") or "")
               for e in cargar() if e.get("estado") == "corriendo" and str(e.get("canal")) == canal]
    return {"canal": canal, "tramo": [ini.isoformat(), fin.isoformat()],
            "tramo_previo": [p_ini.isoformat(), p_fin.isoformat()],
            "actual": actual, "previo": previo, "leads_por_semana": por_semana,
            "corriendo_en_el_canal": activos, "siguiente_id": siguiente_id()}
