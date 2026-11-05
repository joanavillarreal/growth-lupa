#!/usr/bin/env python3
"""Monitoreo de cursos y webinars: qué eventos están abiertos y cómo vienen.

Lee cursos/eventos.yaml, la respuesta exacta del conector de Google Sheets (la planilla
de inscriptos), el resumen de Bitrix (cursos/scripts/bitrix.py --json) y la respuesta
exacta de Meta, y actualiza el dashboard.json del evento. No escribe en ningún lado
más que en el repo: ni Bitrix, ni la planilla, ni mensajes a inscriptos.

Uso:
  python3 cursos/monitoreo.py estado [--fecha AAAA-MM-DD] [--json]
      Estado de cada evento (por_abrir, inscripcion_abierta, realizado, cerrado).

  python3 cursos/monitoreo.py medir <slug> --planilla P.json --bitrix B.json
          [--meta M.json] [--fecha AAAA-MM-DD]
      Valida los crudos (regla 9), calcula stats, ritmo y alertas, actualiza
      cursos/eventos/<slug>/dashboard.json y deja el resumen sin datos personales en
      cursos/datos/<fecha>/<slug>.json. Imprime la tarjeta del evento.

  python3 cursos/monitoreo.py resumen [--fecha AAAA-MM-DD]
      Junta los resúmenes del día: el JSON para `parte.py cursos --datos` y las
      líneas para el resumen de cierre de Slack.

Un número que no se pudo leer queda como estaba y se dice; nunca se estima.
"""
import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CURSOS = RAIZ / "cursos"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")

COLUMNAS = ["Timestamp", "Nombre", "Apellido", "Teléfono", "Email", "Negocio",
            "Tipo de negocio", "¿Cliente Boxer?", "Fuente", "Estado", "Mensaje Enviado",
            "Estado CRM", "Tipo Bitrix", "ID Contacto", "ID Registro", "Asistió",
            "Observaciones"]
ESTADOS_CRM = {"Nuevo — creado en CRM", "Existente — reactivación", "Cliente Boxer",
               "Dice ser cliente — no está en el CRM", "No procesado"}
SI = {"si", "sí", "x", "true", "1", "presente"}
DIAS_RECIEN_PASADO = 15


# ------------------------------------------------------------------ eventos y estado

def hoy():
    return dt.datetime.now(TZ).date()


def cargar_eventos():
    return yaml.safe_load((CURSOS / "eventos.yaml").read_text(encoding="utf-8"))["eventos"]


def _fecha(v):
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def estado(cfg, fecha):
    if cfg.get("cerrado"):
        return "cerrado"
    ultima = max(_fecha(f) for f in cfg["fechas"])
    apertura = _fecha(cfg["apertura"]) if cfg.get("apertura") else None
    if apertura and fecha < apertura:
        return "por_abrir"
    if fecha <= ultima:
        return "inscripcion_abierta"
    return "realizado"


def eventos_abiertos(fecha=None):
    """Lo que usa que_toca_hoy.py: {slug: estado} de los que no están cerrados."""
    fecha = fecha or hoy()
    return {s: e for s, cfg in cargar_eventos().items()
            if (e := estado(cfg, fecha)) != "cerrado"}


# ------------------------------------------------------------------ lectura de crudos

def leer_planilla(ruta):
    """Respuesta exacta de get_values: {"range": ..., "values": [[encabezados], filas...]}."""
    try:
        crudo = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"planilla: el crudo no abre como JSON ({e})")
    valores = crudo.get("values")
    if not valores:
        sys.exit("planilla: la respuesta no trae `values` (¿hoja vacía o rango mal pedido?)")
    encabezados = [h.strip() for h in valores[0]]
    avisos = []
    # n8n y la plantilla madre dependen de los encabezados: se comparan por posición.
    for i, esperado in enumerate(COLUMNAS):
        real = encabezados[i] if i < len(encabezados) else "(falta)"
        if real != esperado:
            avisos.append(f"la columna {chr(65 + i)} dice «{real}» y la plantilla madre "
                          f"dice «{esperado}»")
    filas = []
    for fila in valores[1:]:
        fila = list(fila) + [""] * (len(COLUMNAS) - len(fila))
        if not any(str(c).strip() for c in fila[:4]):
            continue                                  # fila vacía
        filas.append({c: str(fila[i]).strip() for i, c in enumerate(COLUMNAS)})
    if len(valores) - 1 >= 499:
        avisos.append("la planilla llegó al tope del rango pedido (A1:Q500): pedir más filas")
    return filas, avisos


def fecha_de(timestamp):
    """'3/11/2026, 03:47:44' -> 2026-11-03. La hora viene en 12 h sin AM/PM: solo se usa el día."""
    try:
        d, m, a = timestamp.split(",")[0].strip().split("/")
        return dt.date(int(a), int(m), int(d))
    except ValueError:
        return None


def leer_meta(ruta, campanas):
    """Respuesta exacta de ads_get_ad_entities; devuelve (gasto ARS, detalle)."""
    try:
        crudo = json.loads(Path(ruta).read_text(encoding="utf-8"))
        entidades = crudo["ad_entities"]
        if isinstance(entidades, str):
            entidades = json.loads(entidades)
    except (OSError, KeyError, json.JSONDecodeError) as e:
        sys.exit(f"meta: el crudo no abre o no trae ad_entities ({e})")
    por_id = {str(e["id"]): e for e in entidades}
    faltan = [c["id"] for c in campanas if str(c["id"]) not in por_id]
    if faltan:
        sys.exit(f"meta: la respuesta no trae las campañas {faltan}: volver a pedir")
    total, detalle = 0.0, []
    for c in campanas:
        gasto = por_id[str(c["id"])]["amount_spent"]
        if gasto.get("unit") != "ARS":
            sys.exit(f"meta: la campaña {c['id']} viene en {gasto.get('unit')}, no en ARS")
        total += float(gasto["value"])
        detalle.append({"id": c["id"], "nombre": por_id[str(c["id"])].get("name"),
                        "gasto": float(gasto["value"])})
    return round(total, 2), detalle


# ------------------------------------------------------------------ cálculo

def es_si(v):
    return v.strip().lower() in SI


def medir(slug, cfg, filas, avisos_planilla, bitrix, meta, fecha):
    st = estado(cfg, fecha)
    ultima = max(_fecha(f) for f in cfg["fechas"])
    primera = min(_fecha(f) for f in cfg["fechas"])

    total = len(filas)
    cliente = Counter(f["¿Cliente Boxer?"].strip().lower().replace("í", "i") for f in filas)
    clientes_si = cliente.get("si", 0)
    clientes_no = cliente.get("no", 0)
    estado_crm = Counter(f["Estado CRM"] for f in filas)
    tipo_bitrix = Counter(f["Tipo Bitrix"] for f in filas)
    fuente = Counter(f["Fuente"] for f in filas)
    asistentes = sum(1 for f in filas if es_si(f["Asistió"]))

    por_dia = Counter()
    sin_fecha = 0
    for f in filas:
        d = fecha_de(f["Timestamp"])
        if d:
            por_dia[d] += 1
        else:
            sin_fecha += 1
    signups, acumulado = [], 0
    for d in sorted(por_dia):
        acumulado += por_dia[d]
        signups.append({"fecha": d.isoformat(), "nuevos": por_dia[d], "acumulado": acumulado})

    stats = {
        "total": total, "clientes_si": clientes_si, "clientes_no": clientes_no,
        "asistentes": asistentes, "meta_leads": fuente.get("Meta", 0),
        "derivaciones": bitrix["derivaciones"], "cierres": bitrix["cierres"],
        "leads_prospecto": tipo_bitrix.get("Prospecto", 0),
        "leads_negociacion": tipo_bitrix.get("Negociación", 0),
        "prospectos_abiertos": bitrix["prospectos_abiertos"],
    }
    inversion = meta[0] if meta else None

    # ---- ritmo
    obj = (cfg.get("objetivos") or {}).get("inscriptos_min")
    ritmo = None
    if obj and st in ("por_abrir", "inscripcion_abierta"):
        apertura = _fecha(cfg["apertura"]) if cfg.get("apertura") else (min(por_dia) if por_dia else fecha)
        dias_corridos = max((fecha - apertura).days + 1, 1)
        faltan_dias = (primera - fecha).days
        por_dia_hoy = total / dias_corridos
        faltan = max(obj + 1 - total, 0)           # "más de 40" = 41
        ritmo = {"objetivo": f"más de {obj}", "dias_corridos": dias_corridos,
                 "faltan_dias": faltan_dias, "por_dia": round(por_dia_hoy, 1),
                 "faltan_inscriptos": faltan,
                 "necesario_por_dia": round(faltan / faltan_dias, 1) if faltan_dias > 0 else None}

    # ---- alertas (solo las que se pueden afirmar con lo leído)
    alertas = []
    inval = [f for f in filas if f["Estado"] == "Teléfono inválido"]
    if inval:
        alertas.append(f"{len(inval)} teléfono(s) inválido(s): no recibieron la confirmación "
                       "ni entraron al CRM (corregir a mano)")
    no_env = [f for f in filas if f["Mensaje Enviado"] == "No enviado"]
    if no_env:
        alertas.append(f"{len(no_env)} con «Mensaje Enviado» = No enviado (mirar el historial de n8n)")
    sin_crm = [f for f in filas if not f["Estado CRM"] and f["Estado"] != "Teléfono inválido"]
    if sin_crm:
        alertas.append(f"{len(sin_crm)} sin «Estado CRM»: el flujo se cortó después de la confirmación")
    raros = {k: v for k, v in estado_crm.items() if k and k not in ESTADOS_CRM}
    if raros:
        alertas.append("valores de «Estado CRM» fuera de la lista (quedan sin mensaje de cosecha): "
                       + ", ".join(f"«{k}» ({v})" for k, v in raros.items()))
    dice = estado_crm.get("Dice ser cliente — no está en el CRM", 0)
    if dice and st == "realizado":
        alertas.append(f"{dice} «Dice ser cliente — no está en el CRM»: revisar a mano antes de la cosecha")
    otros = cliente.keys() - {"si", "no"}
    if otros:
        alertas.append(f"{sum(cliente[k] for k in otros)} sin «¿Cliente Boxer?» Si/No")
    if sin_fecha:
        alertas.append(f"{sin_fecha} fila(s) con Timestamp que no se pudo leer (no entran en la curva)")
    if st == "realizado" and total and asistentes == 0:
        alertas.append("el evento pasó y «Asistió» está vacía: sin eso no hay show rate ni cosecha")
    if ritmo and ritmo["faltan_dias"] <= 3 and total < obj / 2:
        alertas.append(f"ritmo de inscripción bajo: {total} inscriptos a {ritmo['faltan_dias']} días "
                       f"(menos de la mitad del objetivo de más de {obj})")
    if total >= 10 and clientes_si / total > 0.6:
        alertas.append(f"{clientes_si} de {total} son clientes Boxer ({clientes_si / total:.0%}): "
                       "el evento no está trayendo datos nuevos")
    ids_planilla = {f["ID Registro"] for f in filas if f["Tipo Bitrix"] == "Prospecto" and f["ID Registro"]}
    fuera = [i for i in bitrix.get("ids_prospectos", []) if i not in ids_planilla]
    if fuera:
        alertas.append(f"{len(fuera)} prospecto(s) con el origen del evento en Bitrix que no están "
                       f"en la planilla (IDs {', '.join(fuera)}): entraron por otro lado; avisar, no tocar")
    if st == "realizado" and (fecha - ultima).days > DIAS_RECIEN_PASADO:
        alertas.append(f"pasó hace {(fecha - ultima).days} días y sigue sin cerrar: falta que Vent lo cierre")
    if meta is None and cfg.get("meta", {}).get("campanas"):
        alertas.append("no se pudo leer la inversión en Meta: queda la del último monitoreo")
    alertas += [f"planilla: {a}" for a in avisos_planilla]

    return {
        "slug": slug, "nombre": cfg["nombre"], "estado": st, "fecha": fecha.isoformat(),
        "evento": [f.isoformat() if isinstance(f, dt.date) else str(f) for f in cfg["fechas"]],
        "stats": stats, "inversion_total": inversion,
        "inversion_detalle": meta[1] if meta else None,
        "signups_por_dia": signups, "etapas_crm": bitrix["etapas_crm"],
        "composicion": {"estado_crm": dict(estado_crm), "tipo_bitrix": dict(tipo_bitrix),
                        "fuente": dict(fuente),
                        "asistentes_por_estado_crm": dict(Counter(
                            f["Estado CRM"] for f in filas if es_si(f["Asistió"])))},
        "bitrix": {k: bitrix[k] for k in ("prospectos", "negociaciones", "derivaciones",
                                          "prospectos_abiertos", "cierres")},
        "ritmo": ritmo, "alertas": alertas,
    }


def aplicar(slug, r):
    """Actualiza el dashboard.json con lo medido y devuelve los cambios (antes → después)."""
    ruta = CURSOS / "eventos" / slug / "dashboard.json"
    d = json.loads(ruta.read_text(encoding="utf-8"))
    cambios = []
    for k, v in r["stats"].items():
        if d["stats"].get(k) != v:
            cambios.append(f"{k}: {d['stats'].get(k)} → {v}")
        d["stats"][k] = v
    if r["inversion_total"] is not None:
        if d.get("inversion_total") != r["inversion_total"]:
            cambios.append(f"inversion_total: {d.get('inversion_total')} → {r['inversion_total']}")
        d["inversion_total"] = r["inversion_total"]
    for k in ("signups_por_dia", "etapas_crm"):
        if d.get(k) != r[k]:
            cambios.append(f"{k}: actualizado")
        d[k] = r[k]
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cambios


def plata(n):
    return "$ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tarjeta(r, cfg):
    s = r["stats"]
    primera = min(_fecha(f) for f in cfg["fechas"])
    dias = (primera - _fecha(r["fecha"])).days
    cuando = (f"faltan {dias} días" if dias > 0 else "es hoy" if dias == 0
              else f"pasó hace {-dias} días")
    l = [f"{r['nombre']} · {cfg['tipo']} · {primera.strftime('%d/%m/%Y')} — {cuando} ({r['estado']})"]
    t = s["total"]
    pct = lambda n: f"{n / t:.0%}" if t else "—"
    rit = r["ritmo"]
    linea = f"Inscriptos    {t}"
    if rit:
        linea += f" · objetivo {rit['objetivo']} · {str(rit['por_dia']).replace('.', ',')} por día"
        if rit["necesario_por_dia"] is not None and rit["faltan_inscriptos"]:
            linea += (f" · hacen falta {str(rit['necesario_por_dia']).replace('.', ',')} por día "
                      f"en los {rit['faltan_dias']} que quedan")
    l.append(linea)
    l.append(f"Clientes      {s['clientes_si']} ({pct(s['clientes_si'])}) · no clientes {s['clientes_no']} ({pct(s['clientes_no'])})")
    if r["estado"] == "realizado":
        l.append(f"Asistieron    {s['asistentes']} ({pct(s['asistentes'])})")
    obj_d = (cfg.get("objetivos") or {}).get("derivacion_pct_min")
    l.append(f"Derivaciones  {s['derivaciones']} ({pct(s['derivaciones'])} de los inscriptos"
             + (f"; objetivo más del {obj_d}%" if obj_d else "") + f") · cierres {s['cierres']}"
             + f" · prospectos abiertos {s['prospectos_abiertos']}")
    if r["inversion_total"] is not None:
        cpl = (f" · {plata(r['inversion_total'] / s['meta_leads'])} por inscripto de Meta ({s['meta_leads']})"
               if s["meta_leads"] else "")
        l.append(f"Pauta Meta    {plata(r['inversion_total'])}{cpl}")
    l.append("Alertas       " + ("sin alertas" if not r["alertas"] else ""))
    l += [f"  · {a}" for a in r["alertas"]]
    return "\n".join(l)


# ------------------------------------------------------------------ comandos

def cmd_estado(args):
    fecha = args.fecha or hoy()
    res = {s: estado(c, fecha) for s, c in cargar_eventos().items()}
    if args.json:
        print(json.dumps({"fecha": fecha.isoformat(), "eventos": res,
                          "abiertos": [s for s, e in res.items() if e != "cerrado"]},
                         ensure_ascii=False, indent=2))
        return
    for s, e in res.items():
        print(f"  {e:20} {s}")


def cmd_medir(args):
    fecha = args.fecha or hoy()
    eventos = cargar_eventos()
    if args.slug not in eventos:
        sys.exit(f"{args.slug} no está en cursos/eventos.yaml")
    cfg = eventos[args.slug]
    filas, avisos = leer_planilla(args.planilla)
    try:
        bitrix = json.loads(Path(args.bitrix).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"bitrix: el resumen no abre ({e})")
    if bitrix.get("source_id") != cfg["source_id"]:
        sys.exit(f"bitrix: el resumen es de {bitrix.get('source_id')}, no de {cfg['source_id']}")
    meta = None
    if args.meta:
        meta = leer_meta(args.meta, cfg["meta"]["campanas"])
    r = medir(args.slug, cfg, filas, avisos, bitrix, meta, fecha)
    r["cambios"] = aplicar(args.slug, r)
    salida = CURSOS / "datos" / fecha.isoformat() / f"{args.slug}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(tarjeta(r, cfg))
    print("\nCambios en el dashboard.json: " + ("; ".join(r["cambios"]) or "ninguno"))
    print(f"Resumen: {salida.relative_to(RAIZ)}")


def cmd_resumen(args):
    fecha = args.fecha or hoy()
    carpeta = CURSOS / "datos" / fecha.isoformat()
    abiertos = eventos_abiertos(fecha)
    medidos = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(carpeta.glob("*.json"))
               if p.stem != "parte"} if carpeta.exists() else {}
    sin_medir = [s for s in abiertos if s not in medidos]
    datos = {
        "eventos": {s: {"estado": r["estado"], "inscriptos": r["stats"]["total"],
                        "asistentes": r["stats"]["asistentes"],
                        "derivaciones": r["stats"]["derivaciones"], "cierres": r["stats"]["cierres"],
                        "inversion_total": r["inversion_total"], "ritmo": r["ritmo"]}
                    for s, r in medidos.items()},
        "alertas": [f"{r['nombre']}: {a}" for r in medidos.values() for a in r["alertas"]],
        "sin_medir": sin_medir,
    }
    (carpeta / "parte.json").parent.mkdir(parents=True, exist_ok=True)
    (carpeta / "parte.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    print(f"datos para parte.py: {(carpeta / 'parte.json').relative_to(RAIZ)}")
    print("--- líneas para el resumen de cierre ---")
    for s, r in medidos.items():
        st = r["stats"]
        rit = r["ritmo"]
        extra = (f", {str(rit['por_dia']).replace('.', ',')}/día, faltan {rit['faltan_dias']} días"
                 if rit else f", {st['asistentes']} asistieron, {st['derivaciones']} derivados, "
                             f"{st['cierres']} cierre(s)")
        print(f"🎓 {r['nombre']}: {st['total']} inscriptos{extra}")
        for a in r["alertas"]:
            print(f"   ⚠️ {a}")
    for s in sin_medir:
        print(f"🎓 {s}: no se midió hoy")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estado")
    e.add_argument("--fecha", type=dt.date.fromisoformat)
    e.add_argument("--json", action="store_true")
    m = sub.add_parser("medir")
    m.add_argument("slug")
    m.add_argument("--planilla", required=True, type=Path)
    m.add_argument("--bitrix", required=True, type=Path)
    m.add_argument("--meta", type=Path)
    m.add_argument("--fecha", type=dt.date.fromisoformat)
    r = sub.add_parser("resumen")
    r.add_argument("--fecha", type=dt.date.fromisoformat)
    a = p.parse_args()
    {"estado": cmd_estado, "medir": cmd_medir, "resumen": cmd_resumen}[a.cmd](a)


if __name__ == "__main__":
    main()
