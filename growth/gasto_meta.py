"""Preparación `gasto_meta`: de las respuestas de Meta guardadas tal cual a data/meta_spend.json
y data/meta_adsets.json. Nadie escribe estos montos a mano (regla 9 de CLAUDE.md).

    python3 run.py gasto-meta rango              # qué pedirle a Meta hoy (ids, desde, hasta)
    python3 run.py gasto-meta cargar <carpeta>   # valida las respuestas y actualiza los archivos

La carpeta es meta/datos/meta-ads/gasto/<hoy>/ y tiene las respuestas EXACTAS de
`ads_get_ad_entities` (copiando el archivo de resultado si es grande, o el texto tal cual):

    cuenta-diario.json    level ad_account, time_increment 1, desde..hasta
    cuenta-total.json     lo mismo SIN time_increment: el total del rango, para cuadrar
    redes-diario.json     level campaign, object_ids = campanas_redes, time_increment 1
    cursos-diario.json    (solo si meta_spend.json tiene campanas_cursos / conjuntos_cursos)
    conjunto-<id>.json    level adset, object_ids [id], fields amount_spent y lead, time_increment 1

Antes de escribir nada se valida: todo abre como JSON, cada fila es un solo día dentro del rango,
no hay días repetidos ni el día en curso, la suma diaria de la cuenta es igual al total (±1 ARS)
y lo de redes y cursos no supera el total del día. Si algo falla no se escribe nada y el error
dice qué: la preparación se vuelve a pedir y, si sigue, queda fallida.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import experiments
from .config import RAIZ

SPEND = RAIZ / "data" / "meta_spend.json"
ADSETS = RAIZ / "data" / "meta_adsets.json"
TOLERANCIA_ARS = 1.0


class NoCuadra(Exception):
    pass


def _hoy() -> date:
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def _leer(ruta: Path) -> list[dict]:
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        r = d.get("ad_entities", d) if isinstance(d, dict) else d
        filas = json.loads(r) if isinstance(r, str) else r
    except (OSError, ValueError, TypeError) as e:
        raise NoCuadra(f"{ruta.name}: no abre como JSON ({e})")
    if not isinstance(filas, list):
        raise NoCuadra(f"{ruta.name}: no trae una lista de filas")
    return filas


def _monto(v) -> float:
    v = v.get("value") if isinstance(v, dict) else v
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _por_dia(filas, nombre, desde: str, hasta: str, una_por_dia=True) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for f in filas:
        d0, d1 = f.get("date_start"), f.get("date_stop")
        if not d0 or d0 != d1:
            raise NoCuadra(f"{nombre}: una fila no es de un solo día ({d0} a {d1}); falta time_increment 1")
        if not desde <= d0 <= hasta:
            raise NoCuadra(f"{nombre}: trae el {d0}, fuera del rango {desde} a {hasta}")
        out[d0].append(f)
    if una_por_dia:
        rep = [d for d, fs in out.items() if len(fs) > 1]
        if rep:
            raise NoCuadra(f"{nombre}: días repetidos {rep}")
    return out


def rango(hoy: date | None = None) -> dict:
    """Qué hay que pedirle a Meta: desde el día siguiente al último cargado hasta ayer."""
    hoy = hoy or _hoy()
    ayer = (hoy - timedelta(days=1)).isoformat()
    doc = json.loads(SPEND.read_text(encoding="utf-8"))
    ultimo = max(doc["dias"]) if doc.get("dias") else None
    desde = (date.fromisoformat(ultimo) + timedelta(days=1)).isoformat() if ultimo else ayer
    out = {"cuenta": doc["cuenta"], "desde": desde, "hasta": ayer, "al_dia": desde > ayer,
           "redes": [c["id"] for c in doc.get("campanas_redes", [])],
           "cursos_campanas": [c["id"] if isinstance(c, dict) else c for c in doc.get("campanas_cursos", [])],
           "cursos_conjuntos": [c["id"] if isinstance(c, dict) else c for c in doc.get("conjuntos_cursos", [])],
           "conjuntos": {}}
    ads = json.loads(ADSETS.read_text(encoding="utf-8"))
    ids = {i: c.get("nombre", "") for i, c in ads.get("conjuntos", {}).items()}
    for e in experiments.activos():
        if e.get("conjunto_meta"):
            ids.setdefault(str(e["conjunto_meta"]), e.get("titulo") or "")
    for i in ids:
        dias = (ads.get("conjuntos", {}).get(i) or {}).get("dias") or {}
        u = max(dias) if dias else None
        d = (date.fromisoformat(u) + timedelta(days=1)).isoformat() if u else desde
        if d <= ayer:
            out["conjuntos"][i] = {"desde": d, "hasta": ayer}
    return out


def calcular(carpeta: Path, hoy: date | None = None) -> tuple[dict, dict]:
    """Valida la carpeta y devuelve (días nuevos de meta_spend, días nuevos por conjunto)."""
    carpeta = Path(carpeta)
    r = rango(hoy)
    nuevos_spend: dict[str, dict] = {}
    if not r["al_dia"]:
        desde, hasta = r["desde"], r["hasta"]
        cuenta = _por_dia(_leer(carpeta / "cuenta-diario.json"), "cuenta-diario", desde, hasta)
        total = sum(_monto(f[0].get("amount_spent")) for f in cuenta.values())
        filas_tot = _leer(carpeta / "cuenta-total.json")
        if len(filas_tot) != 1:
            raise NoCuadra(f"cuenta-total: trae {len(filas_tot)} filas, se espera 1 (sin time_increment)")
        t0 = filas_tot[0]
        # Meta no siempre trae las fechas en el total; si las trae, tienen que ser las pedidas.
        if t0.get("date_start") and (t0.get("date_start"), t0.get("date_stop")) != (desde, hasta):
            raise NoCuadra(f"cuenta-total: es del {t0.get('date_start')} al {t0.get('date_stop')}, "
                           f"se pidió del {desde} al {hasta}")
        if abs(total - _monto(t0.get("amount_spent"))) > TOLERANCIA_ARS:
            raise NoCuadra(f"la suma diaria de la cuenta ({total:,.2f} ARS) no da el total del rango "
                           f"({_monto(t0.get('amount_spent')):,.2f} ARS): respuesta cortada o de otro rango")
        grupos = {"redes": ["redes-diario.json"] if r["redes"] else [],
                  "cursos": ["cursos-diario.json"] if (r["cursos_campanas"] or r["cursos_conjuntos"]) else []}
        sumas = {}
        for grupo, archivos in grupos.items():
            s = defaultdict(float)
            for a in archivos:
                for d, fs in _por_dia(_leer(carpeta / a), a, desde, hasta, una_por_dia=False).items():
                    s[d] += sum(_monto(f.get("amount_spent")) for f in fs)
            sumas[grupo] = s
        d = date.fromisoformat(desde)
        while d.isoformat() <= hasta:
            k = d.isoformat()
            tot = _monto(cuenta[k][0].get("amount_spent")) if k in cuenta else 0.0
            dia = {"total_ars": round(tot, 2), "redes_ars": round(sumas["redes"].get(k, 0.0), 2)}
            if grupos["cursos"]:
                dia["cursos_ars"] = round(sumas["cursos"].get(k, 0.0), 2)
            perf = tot - dia["redes_ars"] - dia.get("cursos_ars", 0.0)
            if perf < -TOLERANCIA_ARS:
                raise NoCuadra(f"{k}: redes y cursos ({tot - perf:,.2f} ARS) superan el total de la cuenta ({tot:,.2f} ARS)")
            dia["performance_ars"] = round(max(perf, 0.0), 2)
            nuevos_spend[k] = dia
            d += timedelta(days=1)

    nuevos_ads: dict[str, dict] = {}
    for i, rg in r["conjuntos"].items():
        filas = _por_dia(_leer(carpeta / f"conjunto-{i}.json"), f"conjunto-{i}", rg["desde"], rg["hasta"])
        nombre = next((f[0].get("name") for f in filas.values() if f[0].get("name")), None)
        dias = {}
        for k, fs in sorted(filas.items()):
            dias[k] = {"gasto_ars": round(_monto(fs[0].get("amount_spent")), 2),
                       "leads": int(_monto(fs[0].get("lead")))}
        nuevos_ads[i] = {"nombre": nombre, "dias": dias}
    return nuevos_spend, nuevos_ads


def cargar(carpeta: Path, hoy: date | None = None) -> str:
    spend, ads = calcular(carpeta, hoy)       # NoCuadra -> no se escribe nada
    doc = json.loads(SPEND.read_text(encoding="utf-8"))
    doc["dias"].update(spend)
    doc["dias"] = dict(sorted(doc["dias"].items()))
    if spend:
        doc["generado_en"] = (hoy or _hoy()).isoformat()
    SPEND.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    a = json.loads(ADSETS.read_text(encoding="utf-8"))
    for i, x in ads.items():
        c = a.setdefault("conjuntos", {}).setdefault(i, {"nombre": x["nombre"] or "", "dias": {}})
        c["dias"].update(x["dias"])
        c["dias"] = dict(sorted(c["dias"].items()))
    ADSETS.write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ult = max(doc["dias"]) if doc["dias"] else "—"
    return (f"OK: meta_spend.json +{len(spend)} días (hasta {ult}); "
            f"meta_adsets.json: " + (", ".join(f"{i} +{len(x['dias'])} días" for i, x in ads.items()) or "nada nuevo"))
