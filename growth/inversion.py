"""Carga del gasto diario de Meta Ads y Google Ads al SPA 1052 de Bitrix.

Es la versión automática del skill boxer-carga-inversion, para la rutina de
lunes y jueves. Mismas reglas: un registro por día y por canal, montos en USD,
deduplicación por (fecha, tipo de gasto) y nunca por título, los días en cero
no se cargan pero se nombran, y los huecos se dicen.

  Meta   -> lo trae la rutina con el conector MCP (no hay API desde Python) y
            lo pasa en un archivo JSON.
  Google -> se lee acá de la Google Ads API (growth/google_ads.py).

El rango por defecto va desde el día siguiente al último cargado (el más
atrasado de los dos canales) hasta ayer en hora de Buenos Aires: el día de hoy
no terminó y su gasto todavía cambia.
"""
from __future__ import annotations
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from growth import google_ads
from growth.bitrix import Bitrix, BitrixError

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
CATEGORY_ID = 16
CANALES = {
    "meta":   {"enum": 1416, "titulo": "Meta Ads"},
    "google": {"enum": 1418, "titulo": "Google Ads"},
}
ENUM_A_CANAL = {v["enum"]: k for k, v in CANALES.items()}
VENTANA_HUECOS = 60  # días hacia atrás en los que se buscan huecos


# --- Fechas y montos ------------------------------------------------------------
def ayer() -> date:
    return datetime.now(TZ).date() - timedelta(days=1)


def dias(desde: str, hasta: str) -> list[str]:
    d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def titulo(canal: str, iso: str) -> str:
    a, m, d = iso.split("-")
    return f"{CANALES[canal]['titulo']} - {d}/{m}/{a}"


def monto_meta(valor) -> tuple[float, str]:
    """El conector de Meta cambió de formato y hay que aguantar los dos.

    - Desde sept. 2026: {"value": "30340.36", "unit": "ARS"} -> punto decimal.
    - Antes: "$24.736,29 ARS" -> punto miles, coma decimal, y un espacio duro
      (U+00A0) antes de ARS.
    Leer uno con las reglas del otro da montos 100 o 1000 veces corridos.
    """
    if isinstance(valor, dict):
        return float(str(valor["value"]).replace(",", "")), str(valor.get("unit", "")).upper()
    if isinstance(valor, (int, float)):
        return float(valor), ""
    s = str(valor)
    unidad = "ARS" if "ARS" in s.upper() else ""
    s = re.sub(r"[^\d.,]", "", s)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s or 0), unidad


def leer_meta(ruta: str) -> dict[str, float]:
    """Acepta la respuesta de ads_get_ad_entities tal cual, o solo su lista de filas."""
    with open(ruta, encoding="utf-8") as fh:
        crudo = json.load(fh)
    filas = crudo.get("ad_entities", crudo) if isinstance(crudo, dict) else crudo
    if isinstance(filas, str):
        filas = json.loads(filas)
    out: dict[str, float] = {}
    for f in filas:
        ars, unidad = monto_meta(f.get("amount_spent", 0))
        if unidad and unidad != "ARS":
            raise ValueError(f"Meta devolvió el gasto en {unidad}, no en ARS: no convierto a ciegas.")
        d = f["date_start"][:10]
        out[d] = out.get(d, 0.0) + ars
    return out


# --- Bitrix -------------------------------------------------------------------
def cargados(bx: Bitrix, cfg, desde: str, hasta: str) -> dict[tuple[str, str], dict]:
    g = cfg["gasto"]
    items = bx.listar_items(
        g["entity_type_id"],
        select=["id", "title", g["campo_tipo"], g["campo_fecha"], g["campo_monto"]],
        filter={"categoryId": CATEGORY_ID,
                f">={g['campo_fecha']}": desde, f"<={g['campo_fecha']}": hasta})
    idx = {}
    for it in items:
        canal = ENUM_A_CANAL.get(it.get(g["campo_tipo"]))
        # Los primeros 10 caracteres a propósito: convertir de zona horaria
        # puede correr el día, y el día es la clave de la deduplicación.
        f = str(it.get(g["campo_fecha"]) or "")[:10]
        if canal and f:
            idx[(canal, f)] = it
    return idx


def rango(cfg, bx: Bitrix | None = None) -> dict:
    """Qué hay que cargar: desde el día siguiente al último cargado hasta ayer."""
    bx = bx or Bitrix()
    hasta = ayer()
    inicio_ventana = (hasta - timedelta(days=VENTANA_HUECOS)).isoformat()
    idx = cargados(bx, cfg, inicio_ventana, hasta.isoformat())
    ultimo = {}
    for c in CANALES:
        fechas = sorted(f for (ch, f) in idx if ch == c)
        ultimo[c] = fechas[-1] if fechas else None
    arranques = [date.fromisoformat(u) + timedelta(days=1) if u else date.fromisoformat(inicio_ventana)
                 for u in ultimo.values()]
    desde = min(arranques)
    # Huecos más viejos que el rango: días sin registro dentro de la ventana.
    huecos = {c: [d for d in dias(inicio_ventana, (desde - timedelta(days=1)).isoformat())
                  if (c, d) not in idx] if desde.isoformat() > inicio_ventana else []
              for c in CANALES}
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "ultimo_cargado": ultimo, "huecos_previos": huecos,
            "al_dia": desde > hasta}


def cargar(cfg, archivo_meta: str | None, desde: str | None = None,
           hasta: str | None = None, dry_run: bool = False) -> str:
    """Hace la carga y devuelve el reporte en markdown."""
    bx = Bitrix()
    r = rango(cfg, bx)
    desde = desde or r["desde"]
    hasta = hasta or r["hasta"]
    if hasta >= datetime.now(TZ).date().isoformat():
        raise ValueError("El rango incluye hoy: el día no terminó y el gasto todavía cambia.")
    if desde > hasta:
        return (f"## Carga de inversión\n\nNada para cargar: los dos canales ya están "
                f"cargados hasta {hasta}.\n" + _huecos_md(r["huecos_previos"], {}))

    cot = float(cfg["gasto"]["meta_api"]["cotizacion_ars_usd"])
    rango_dias = dias(desde, hasta)
    gastos: dict[str, dict[str, float] | None] = {}
    errores: dict[str, str] = {}

    if archivo_meta:
        try:
            gastos["meta"] = leer_meta(archivo_meta)
        except (OSError, ValueError, KeyError) as e:
            errores["meta"] = str(e)
    else:
        errores["meta"] = "la rutina no pasó el gasto de Meta (¿falta el conector?)"

    try:
        mon = google_ads.moneda()
        if mon != "ARS":
            raise google_ads.GoogleAdsError(f"la cuenta está en {mon}, no en ARS")
        g = google_ads.gasto_diario(desde, hasta)
        # La API no devuelve fila para un día sin gasto: ahí es un cero real.
        gastos["google"] = {d: g.get(d, 0.0) for d in rango_dias}
    except (google_ads.GoogleAdsError, OSError, KeyError) as e:
        errores["google"] = str(e)

    ya = cargados(bx, cfg, desde, hasta)
    a_crear, salteados, en_cero, sin_dato = [], [], [], []
    for canal in CANALES:
        if canal not in gastos:
            continue
        for d in rango_dias:
            if d not in gastos[canal]:
                sin_dato.append((canal, d))
                continue
            ars = gastos[canal][d]
            usd = round(ars / cot, 2)
            fila = {"canal": canal, "fecha": d, "ars": round(ars, 2), "usd": usd,
                    "titulo": titulo(canal, d)}
            if (canal, d) in ya:
                fila["id"] = ya[(canal, d)]["id"]
                salteados.append(fila)
            elif usd <= 0:
                en_cero.append(fila)
            else:
                a_crear.append(fila)

    creados, fallo, no_intentados = [], None, []
    g = cfg["gasto"]
    if not dry_run and a_crear:
        # Re-chequeo justo antes de escribir: otra carga pudo entrar entre medio.
        ya = cargados(bx, cfg, desde, hasta)
        for i, f in enumerate(a_crear):
            if (f["canal"], f["fecha"]) in ya:
                f["id"] = ya[(f["canal"], f["fecha"])]["id"]
                salteados.append(f)
                continue
            try:
                res = bx.llamar("crm.item.add", entityTypeId=g["entity_type_id"], fields={
                    "categoryId": CATEGORY_ID,
                    "title": f["titulo"],
                    g["campo_tipo"]: CANALES[f["canal"]]["enum"],
                    g["campo_fecha"]: f["fecha"],
                    g["campo_monto"]: f"{f['usd']:.2f}|USD",
                })
                f["id"] = res["result"]["item"]["id"]
                creados.append(f)
            except (BitrixError, KeyError, TypeError) as e:
                fallo = (f, str(e))
                no_intentados = a_crear[i + 1:]
                break

    return _reporte(desde, hasta, cot, a_crear if dry_run else creados, salteados,
                    en_cero, sin_dato, errores, fallo, no_intentados,
                    r["huecos_previos"], dry_run)


# --- Reporte ------------------------------------------------------------------
def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _huecos_md(huecos: dict, errores: dict) -> str:
    lineas = [f"- {CANALES[c]['titulo']}: " + ", ".join(_dm(d) for d in ds)
              for c, ds in huecos.items() if ds]
    if not lineas:
        return ""
    return ("\n**Huecos anteriores al rango** (días sin registro en los últimos "
            f"{VENTANA_HUECOS}; pueden ser días en $0, revisar):\n" + "\n".join(lineas) + "\n")


def _reporte(desde, hasta, cot, creados, salteados, en_cero, sin_dato, errores,
             fallo, no_intentados, huecos, dry_run) -> str:
    verbo = "a crear (DRY RUN, no se escribió nada)" if dry_run else "creados"
    out = [f"## Carga de inversión — {_dm(desde)} a {_dm(hasta)}", "",
           f"Cotización: {cot:g} ARS = 1 USD", ""]
    total = 0.0
    for c in CANALES:
        fs = [f for f in creados if f["canal"] == c]
        t = sum(f["usd"] for f in fs)
        total += t
        if c in errores:
            out.append(f"- **{CANALES[c]['titulo']}**: PENDIENTE — {errores[c]}")
        else:
            out.append(f"- **{CANALES[c]['titulo']}**: {len(fs)} registros {verbo}, USD {t:,.2f}")
    out.append(f"- **Total**: USD {total:,.2f}")
    if creados:
        out += ["", "| Día | Canal | ARS | USD | ID |", "|---|---|---:|---:|---|"]
        for f in sorted(creados, key=lambda x: (x["fecha"], x["canal"])):
            out.append(f"| {_dm(f['fecha'])} | {CANALES[f['canal']]['titulo']} | "
                       f"{f['ars']:,.2f} | {f['usd']:,.2f} | {f.get('id', '—')} |")
    if salteados:
        out.append("\n**Salteados** (ya estaban cargados): " + ", ".join(
            f"{CANALES[f['canal']]['titulo']} {_dm(f['fecha'])} (id {f['id']})" for f in salteados))
    if en_cero:
        out.append("\n**Días sin gasto** (no se creó registro, es un $0 real): " + ", ".join(
            f"{CANALES[f['canal']]['titulo']} {_dm(f['fecha'])}" for f in en_cero))
    if sin_dato:
        out.append("\n**Sin dato de origen** (hueco, no es $0): " + ", ".join(
            f"{CANALES[c]['titulo']} {_dm(d)}" for c, d in sin_dato))
    if fallo:
        f, e = fallo
        out.append(f"\n**FALLÓ** {CANALES[f['canal']]['titulo']} {_dm(f['fecha'])}: {e}. "
                   "Corté ahí. Quedaron sin intentar: " + (", ".join(
                       f"{CANALES[x['canal']]['titulo']} {_dm(x['fecha'])}" for x in no_intentados)
                       or "ninguno") + ". Se puede volver a correr: lo ya creado se saltea.")
    h = _huecos_md(huecos, errores)
    if h:
        out.append(h)
    return "\n".join(out) + "\n"
