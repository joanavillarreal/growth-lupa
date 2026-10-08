#!/usr/bin/env python3
"""
Procesa el snapshot de PROSPECTOS de Bitrix24 y calcula los KPIs de gobierno
del canal de Meta Ads.

Uso:
    python3 scripts/analizar_crm.py datos/crm/2026-W37/prospectos.csv
    python3 scripts/analizar_crm.py <csv> --json informes/2026-W37/kpis.json
    python3 scripts/analizar_crm.py <csv> --desde 2026-08-10 --hasta 2026-09-06
    python3 scripts/analizar_crm.py <csv> --gasto-ars 350000

El CSV sale de scripts/traer_prospectos.py: delimitador ';', BOM UTF-8.

Definiciones (ver config/taxonomia-lead.yaml y referencias/calculos.md):
  resueltos     = etapa != inicial  (Convertido + no util + inactivo)
  no_util_pct   = "Prospecto no util" / resueltos
  derivacion    = "Convertido"       / resueltos
  inactivo_pct  = "Prospecto inactivo" / resueltos

Diferencia clave con el agente de Google Ads: aca el volumen es de ~25
leads/semana, no ~5. La comparacion semana contra semana SI se puede leer.
Lo que no se puede leer es por campana o por creativo: el CRM no guarda ni un
UTM de Meta (0 de 1096 al 2026-09-07).
"""
import argparse, csv, datetime, json, os, sys
from collections import Counter, defaultdict

DELIM = ";"

ETAPA_CONVERTIDO = {"Convertido"}
ETAPA_NO_UTIL = {"Prospecto no util", "Prospecto no útil"}
ETAPA_INACTIVO = {"Prospecto inactivo"}
# Etapas iniciales del canal: el prospecto todavia no se trabajo.
ETAPAS_ABIERTAS = {"Formularios Meta", "Meta Ads", "Redes Sociales"}

# Origenes. "Redes" es organico: entra como contraste, NUNCA en los KPI del canal.
PAGO = {
    "Meta Ads Formulario": "Formulario nativo (lead ad)",
    "Meta Ads": "Clic a WhatsApp",
}
ORGANICO = {"Redes": "Redes organico (contraste)"}
ORIGENES = {**PAGO, **ORGANICO}

COL = {
    "id": "ID", "etapa": "Etapa", "origen": "Origen", "creado": "Creado",
    "razon": "Razon de no derivacion", "tipo": "Tipo de negocio",
    "interes": "Interes en producto", "prioridad": "Prioridad",
    "efectivo": "Contacto efectivo",
    "utm_source": "UTM Source", "utm_medium": "UTM Medium",
    "utm_campaign": "UTM Campaign", "utm_content": "UTM Content",
    "utm_term": "UTM Term",
}

# Segmentacion por tipo de negocio. Es el predictor mas fuerte que tiene el
# canal: ver memoria/baseline.md, Hallazgo 2.
ICP = {
    "Casa de Repuestos de Autos", "Casa de Repuestos de Motos",
    "Casa de Repuestos de Pesados", "Casa de Repuestos de Agrícolas",
    "Casa de Repuestos de Agricolas", "Combinación con Casa de Repuestos",
    "Combinacion con Casa de Repuestos",
    "Combinación con Casa de Repuestos de motos",
    "Combinacion con Casa de Repuestos de motos",
    "Distribuidora", "Autopartes", "Baterias", "Desarmadero",
}
ADYACENTE = {
    "Taller mecánico", "Taller mecanico", "Lubricentro",
    "Combinación sin Casa de Repuestos", "Combinacion sin Casa de Repuestos",
    "concesionario", "Concesionario",
}
SIN_TIPIFICAR = {"A definir", "", "(vacio)"}


def _norm(s):
    tabla = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    return s.translate(tabla).lower().strip()


def col(row, clave):
    """Lee una columna tolerando variantes de acento en el header."""
    nombre = COL[clave]
    if nombre in row:
        return (row[nombre] or "").strip()
    objetivo = _norm(nombre)
    for k, v in row.items():
        if k and _norm(k) == objetivo:
            return (v or "").strip()
    return ""


def parse_fecha(s):
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def leer(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=DELIM))
    if rows and len(rows[0]) < 5:
        raise SystemExit(
            f"El CSV parece no usar '{DELIM}' como delimitador "
            f"(se detectaron {len(rows[0])} columnas). Revisar el export.")
    for r in rows:
        r["_fecha"] = parse_fecha(col(r, "creado"))
        r["_etapa"] = col(r, "etapa")
        r["_origen"] = col(r, "origen")
    return rows


def clasificar(etapa):
    if etapa in ETAPA_CONVERTIDO:
        return "convertido"
    if etapa in ETAPA_NO_UTIL:
        return "no_util"
    if etapa in ETAPA_INACTIVO:
        return "inactivo"
    if etapa in ETAPAS_ABIERTAS:
        return "abierta"
    return "otra"      # etapas de otros canales: el lead se reasigno


def grupo_negocio(row):
    t = col(row, "tipo")
    if t in ICP:
        return "ICP (casa de repuestos y afines)"
    if t in ADYACENTE:
        return "Adyacente (taller / lubricentro)"
    return "Sin tipificar"


GRUPOS = ["ICP (casa de repuestos y afines)",
          "Adyacente (taller / lubricentro)",
          "Sin tipificar"]


def pct(num, den):
    return round(100.0 * num / den, 1) if den else None


def kpis(rows):
    c = Counter(clasificar(r["_etapa"]) for r in rows)
    resueltas = c["convertido"] + c["no_util"] + c["inactivo"] + c["otra"]
    con_utm = sum(1 for r in rows if col(r, "utm_source"))
    return {
        "leads": len(rows),
        "abiertos": c["abierta"],
        "resueltos": resueltas,
        "convertido": c["convertido"],
        "no_util": c["no_util"],
        "inactivo": c["inactivo"],
        "no_util_pct": pct(c["no_util"], resueltas),
        "derivacion_pct": pct(c["convertido"], resueltas),
        "inactivo_pct": pct(c["inactivo"], resueltas),
        "con_utm": con_utm,
        "con_utm_pct": pct(con_utm, len(rows)),
    }


# --- umbrales (config/umbrales.yaml) ---
TECHO_NO_UTIL = 15          # heredado del canal de Google Ads, a confirmar
PISO_DERIVACION = 50        # heredado del canal de Google Ads, a confirmar
CPL_OBJETIVO_ARS_BRUTO = 3000   # definido por Joana para Meta, 2026-09-08
CPL_TECHO_USD_DERIVABLE = 200
COTIZACION_ARS_USD = 1500
MIN_LEADS_PARA_DECIDIR = 30   # por segmento, en la ventana de 4 semanas


def cpl(gasto_ars, k):
    """Los tres CPL. El que gobierna es el bruto contra el objetivo operativo."""
    calificados = k["resueltos"] - k["no_util"]
    out = {
        "gasto_ars": round(gasto_ars),
        "cotizacion_ars_por_usd": COTIZACION_ARS_USD,
        "bruto_ars": round(gasto_ars / k["leads"]) if k["leads"] else None,
        "calificado_ars": round(gasto_ars / calificados) if calificados else None,
        "derivable_ars": round(gasto_ars / k["convertido"]) if k["convertido"] else None,
    }
    out["derivable_usd"] = (round(out["derivable_ars"] / COTIZACION_ARS_USD, 1)
                            if out["derivable_ars"] else None)
    out["objetivo_ars_bruto"] = CPL_OBJETIVO_ARS_BRUTO
    out["techo_usd_derivable"] = CPL_TECHO_USD_DERIVABLE
    out["dentro_de_objetivo"] = (out["bruto_ars"] is not None
                                 and out["bruto_ars"] <= CPL_OBJETIVO_ARS_BRUTO)
    out["dentro_del_techo"] = (out["derivable_usd"] is not None
                               and out["derivable_usd"] <= CPL_TECHO_USD_DERIVABLE)
    return out


BLOQUES = [("00-08 madrugada", 0, 8), ("08-13 manana", 8, 13),
           ("13-18 tarde", 13, 18), ("18-24 noche", 18, 24)]
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def por_momento(rows):
    bloques, dias = {}, {}
    for nom, a, b in BLOQUES:
        sub = [r for r in rows if r["_fecha"] and a <= r["_fecha"].hour < b]
        if sub:
            bloques[nom] = kpis(sub)
    for i, nom in enumerate(DIAS):
        sub = [r for r in rows if r["_fecha"] and r["_fecha"].weekday() == i]
        if sub:
            dias[nom] = kpis(sub)
    fds = [r for r in rows if r["_fecha"] and r["_fecha"].weekday() >= 5]
    fuera = [r for r in rows if r["_fecha"] and
             (r["_fecha"].hour < 8 or r["_fecha"].hour >= 20 or r["_fecha"].weekday() >= 5)]
    return {
        "por_bloque": bloques, "por_dia": dias,
        "fin_de_semana": kpis(fds) if fds else None,
        "fuera_de_horario": {"leads": len(fuera), "pct": pct(len(fuera), len(rows))},
    }


def semana(fecha):
    y, w, _ = fecha.isocalendar()
    return f"{y}-W{w:02d}"


def rango_semana(etiqueta):
    """'2026-W36' -> 'lun 31/08 a dom 06/09'. La etiqueta ISO sola no le dice
    nada a nadie: siempre acompanarla con las fechas reales."""
    y, w = etiqueta.split("-W")
    lunes = datetime.date.fromisocalendar(int(y), int(w), 1)
    return f"lun {lunes.strftime('%d/%m')} a dom {(lunes + datetime.timedelta(days=6)).strftime('%d/%m')}"


def analizar(rows, desde=None, hasta=None, gasto_ars=None):
    rows = [r for r in rows if r["_origen"] in ORIGENES]
    if desde:
        rows = [r for r in rows if r["_fecha"] and r["_fecha"].date() >= desde]
    if hasta:
        rows = [r for r in rows if r["_fecha"] and r["_fecha"].date() <= hasta]
    if not rows:
        raise SystemExit("No quedaron prospectos despues de filtrar. Revisar rango y origenes.")

    # El canal es SOLO lo pago. El organico entra aparte, como contraste.
    pagos = [r for r in rows if r["_origen"] in PAGO]
    organicos = [r for r in rows if r["_origen"] in ORGANICO]
    if not pagos:
        raise SystemExit("No quedo ningun lead de Meta Ads pago en el rango.")

    fechas = [r["_fecha"] for r in pagos if r["_fecha"]]
    res = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "rango": {"desde": str(min(fechas).date()), "hasta": str(max(fechas).date()),
                  "dias": (max(fechas) - min(fechas)).days},
        "global": kpis(pagos),
        "organico_contraste": kpis(organicos) if organicos else None,
        "por_origen": {}, "por_tipo_negocio": {}, "por_origen_y_tipo": {},
        "por_semana": {}, "momento": {}, "razones_no_util": {},
        "razones_inactivo": {}, "tipo_negocio_conteo": {},
        "campanas_utm": [], "alertas": [],
    }
    dias = max(res["rango"]["dias"], 1)
    res["global"]["leads_por_semana"] = round(len(pagos) / (dias / 7), 1)

    for origen, etiqueta in PAGO.items():
        sub = [r for r in pagos if r["_origen"] == origen]
        if sub:
            res["por_origen"][etiqueta] = kpis(sub)

    for g in GRUPOS:
        sub = [r for r in pagos if grupo_negocio(r) == g]
        if sub:
            res["por_tipo_negocio"][g] = kpis(sub)

    for origen, etiqueta in PAGO.items():
        for g in GRUPOS:
            sub = [r for r in pagos if r["_origen"] == origen and grupo_negocio(r) == g]
            if sub:
                res["por_origen_y_tipo"][f"{etiqueta} | {g}"] = kpis(sub)

    res["momento"] = por_momento(pagos)

    porsem = defaultdict(list)
    for r in pagos:
        if r["_fecha"]:
            porsem[semana(r["_fecha"])].append(r)
    for k in sorted(porsem):
        res["por_semana"][k] = kpis(porsem[k])
        res["por_semana"][k]["rango"] = rango_semana(k)

    for origen, etiqueta in PAGO.items():
        sub = [r for r in pagos if r["_origen"] == origen]
        res["razones_no_util"][etiqueta] = dict(Counter(
            col(r, "razon") or "(sin razon)" for r in sub
            if clasificar(r["_etapa"]) == "no_util").most_common())
        res["razones_inactivo"][etiqueta] = dict(Counter(
            col(r, "razon") or "(sin razon)" for r in sub
            if clasificar(r["_etapa"]) == "inactivo").most_common())
        res["tipo_negocio_conteo"][etiqueta] = dict(Counter(
            col(r, "tipo") or "(vacio)" for r in sub).most_common())

    agg = defaultdict(lambda: {"leads": 0, "convertido": 0, "no_util": 0})
    for r in pagos:
        camp = col(r, "utm_campaign")
        if not camp:
            continue
        a = agg[(camp, col(r, "utm_content"))]
        a["leads"] += 1
        cl = clasificar(r["_etapa"])
        if cl in ("convertido", "no_util"):
            a[cl] += 1
    for (camp, cont), a in sorted(agg.items(), key=lambda kv: -kv[1]["leads"]):
        res["campanas_utm"].append({"utm_campaign": camp, "utm_content": cont, **a})

    if gasto_ars:
        res["cpl"] = cpl(gasto_ars, res["global"])
    else:
        res["cpl"] = None

    res["alertas"] = alertas(res, pagos)
    return res


def alertas(res, pagos):
    out = []
    g = res["global"]

    if g["con_utm"] == 0:
        out.append(
            f"ATRIBUCION EN CERO: 0 de {g['leads']} leads de Meta traen UTM. No se "
            f"puede saber que campana, conjunto ni anuncio genero cada lead. Todo "
            f"analisis por creativo es imposible hoy: es el bloqueante numero uno "
            f"del canal (informes/setup-pendiente.md, B3).")
    elif g["con_utm_pct"] is not None and g["con_utm_pct"] < 90:
        out.append(
            f"ATRIBUCION PARCIAL: solo {g['con_utm_pct']}% de los leads trae UTM "
            f"({g['con_utm']} de {g['leads']}).")

    if g["no_util_pct"] is not None and g["no_util_pct"] > TECHO_NO_UTIL:
        out.append(f"NO CALIFICADOS: {g['no_util_pct']}% ({g['no_util']} de "
                   f"{g['resueltos']}) supera el techo de {TECHO_NO_UTIL}%.")
    if g["derivacion_pct"] is not None and g["derivacion_pct"] < PISO_DERIVACION:
        out.append(f"DERIVACION: {g['derivacion_pct']}% ({g['convertido']} de "
                   f"{g['resueltos']}) esta por debajo del piso de {PISO_DERIVACION}%.")

    # El bloque inactivo es el mas grande del canal y NO se arregla en Meta.
    if g["inactivo_pct"] is not None and g["inactivo_pct"] > 45:
        out.append(
            f"SEGUIMIENTO COMERCIAL: {g['inactivo_pct']}% ({g['inactivo']} de "
            f"{g['resueltos']}) quedo en 'Prospecto inactivo'. Son leads que "
            f"servian y se perdieron despues del contacto. Ese bloque NO se "
            f"arregla tocando Meta Ads: no proponer cambios de campana por esto.")

    for etiqueta, k in res["por_origen"].items():
        if k["no_util_pct"] is not None and k["no_util_pct"] > TECHO_NO_UTIL:
            out.append(f"[{etiqueta}] no calificados {k['no_util_pct']}% "
                       f"({k['no_util']} de {k['resueltos']}) supera el techo.")

    # Tipo de negocio: el hallazgo mas accionable del canal.
    t = res["por_tipo_negocio"]
    icp = t.get("ICP (casa de repuestos y afines)")
    ady = t.get("Adyacente (taller / lubricentro)")
    sin = t.get("Sin tipificar")
    fuera = sum(x["leads"] for x in (ady, sin) if x)
    if icp and fuera:
        out.append(
            f"MEZCLA DE PUBLICO: {fuera} de {g['leads']} leads "
            f"({pct(fuera, g['leads'])}%) NO son ICP (adyacentes o sin tipificar). "
            f"ICP deriva {icp['derivacion_pct']}% ({icp['convertido']}/{icp['resueltos']}) "
            f"contra " + " y ".join(
                f"{x['derivacion_pct']}% ({x['convertido']}/{x['resueltos']})"
                for x in (ady, sin) if x) + ". Es el hallazgo mas accionable: se "
            f"trabaja con segmentacion, exclusiones y copy que filtre.")
    if ady and ady["leads"] >= MIN_LEADS_PARA_DECIDIR and ady["derivacion_pct"] is not None \
            and ady["derivacion_pct"] < 15:
        out.append(
            f"ADYACENTES: talleres y lubricentros derivan {ady['derivacion_pct']}% "
            f"({ady['convertido']} de {ady['resueltos']}) y quedan inactivos "
            f"{ady['inactivo_pct']}%. Es un segmento distinto, no ICP central.")
    if sin and sin["no_util_pct"] is not None and sin["no_util_pct"] > 25:
        out.append(
            f"SIN TIPIFICAR: {sin['leads']} leads sin tipo de negocio cargado, con "
            f"{sin['no_util_pct']}% de no calificados. 'No se pudo tipificar' es "
            f"sintoma de lead flojo, no una categoria.")

    # Deterioro semana a semana. Aca SI se puede leer: hay ~25 leads/semana.
    sem = [(k, v) for k, v in sorted(res["por_semana"].items())
           if v["resueltos"] >= 10]
    if len(sem) >= 6:
        prev = [v for _, v in sem[:-3]]
        ult = [v for _, v in sem[-3:]]
        def tasa(bloque, campo):
            n = sum(v[campo] for v in bloque)
            d = sum(v["resueltos"] for v in bloque)
            return pct(n, d), n, d
        d_ult, cn, cd = tasa(ult, "convertido")
        d_pre, pn, pd = tasa(prev, "convertido")
        if d_ult is not None and d_pre is not None and d_ult < d_pre - 8:
            out.append(
                f"TENDENCIA: la derivacion de las ultimas 3 semanas es {d_ult}% "
                f"({cn}/{cd}) contra {d_pre}% ({pn}/{pd}) en las semanas previas. "
                f"OJO: las cohortes recientes son mas jovenes y todavia pueden "
                f"convertir. Confirmar el proximo lunes antes de tratarlo como caida.")

    if res.get("cpl"):
        c = res["cpl"]
        mil = lambda n: f"{n:,}".replace(",", ".")
        if not c["dentro_de_objetivo"]:
            out.append(f"CPL BRUTO: {mil(c['bruto_ars'])} ARS por lead supera el "
                       f"objetivo de {mil(CPL_OBJETIVO_ARS_BRUTO)} ARS.")
        if c["derivable_usd"] is not None and not c["dentro_del_techo"]:
            out.append(f"CPL DERIVABLE: {c['derivable_usd']} USD por lead Convertido "
                       f"supera el techo de negocio de {CPL_TECHO_USD_DERIVABLE} USD.")
        elif c["derivable_usd"] is not None and not c["dentro_de_objetivo"]:
            out.append(f"MATIZ: el CPL esta fuera de objetivo pero dentro del techo de "
                       f"negocio ({c['derivable_usd']} USD por Convertido, techo "
                       f"{CPL_TECHO_USD_DERIVABLE}). Es decision de Joana, no una alarma.")
    else:
        out.append("SIN GASTO: no se paso --gasto-ars. Ningun CPL es calculable. "
                   "Nunca estimarlo.")

    org = res.get("organico_contraste")
    if org and org["resueltos"] >= 30 and org["derivacion_pct"] and g["derivacion_pct"] \
            and org["derivacion_pct"] > g["derivacion_pct"] + 10:
        out.append(
            f"CONTRASTE: el organico de redes deriva {org['derivacion_pct']}% "
            f"({org['convertido']}/{org['resueltos']}) contra {g['derivacion_pct']}% "
            f"del pago. No es comparable directo (el organico ya conoce la marca), "
            f"pero marca el techo al que puede aspirar el canal pago.")
    return out


def fila_kpi(etiqueta, k, ancho=38):
    f = lambda n: (f"{pct(n, k['resueltos'])}% ({n}/{k['resueltos']})"
                   if k["resueltos"] else "-")
    return (f"{etiqueta:{ancho}}{k['leads']:>7}{f(k['convertido']):>18}"
            f"{f(k['no_util']):>18}{f(k['inactivo']):>18}")


def cabecera(ancho=38):
    return (f"{'':{ancho}}{'leads':>7}{'derivacion':>18}{'no util':>18}{'inactivo':>18}")


def imprimir(res):
    r = res["rango"]
    fmt = lambda s: datetime.date.fromisoformat(s).strftime("%d/%m/%Y")
    print(f"\nRANGO ANALIZADO: {fmt(r['desde'])} a {fmt(r['hasta'])}  ({r['dias']} dias)")
    g = res["global"]
    print(f"LEADS DE META ADS (pago): {g['leads']}  ({g['leads_por_semana']}/semana)   "
          f"resueltos {g['resueltos']} | abiertos {g['abiertos']}")
    print(f"CON UTM: {g['con_utm']} de {g['leads']} "
          f"({g['con_utm_pct']}%)  <- atribucion a campana/anuncio")

    print("\n== POR ORIGEN ==")
    print(cabecera())
    for etiqueta, k in res["por_origen"].items():
        print(fila_kpi(etiqueta, k))
    print(fila_kpi("TOTAL META PAGO", g))
    if res.get("organico_contraste"):
        print(fila_kpi("(contraste) Redes organico", res["organico_contraste"]))

    print("\n== POR TIPO DE NEGOCIO  <- el predictor mas fuerte del canal ==")
    print(cabecera())
    for etiqueta, k in res["por_tipo_negocio"].items():
        print(fila_kpi(etiqueta, k))

    if res["por_origen_y_tipo"]:
        print("\n== ORIGEN x TIPO DE NEGOCIO ==")
        print(cabecera(46))
        for etiqueta, k in res["por_origen_y_tipo"].items():
            print(fila_kpi(etiqueta, k, 46))

    print("\n== POR SEMANA ISO ==")
    print(cabecera(28))
    for k, v in res["por_semana"].items():
        print(fila_kpi(f"{k} ({v['rango']})", v, 28))

    m = res.get("momento") or {}
    if m.get("por_bloque"):
        print("\n== SEGUN CUANDO ENTRO EL LEAD ==")
        print(cabecera(20))
        for nom, k in m["por_bloque"].items():
            print(fila_kpi(nom, k, 20))
        print()
        for nom, k in m["por_dia"].items():
            print(fila_kpi(nom, k, 20))
        fh = m.get("fuera_de_horario", {})
        print(f"\n  Fuera de horario comercial: {fh.get('leads')} de {g['leads']} "
              f"({fh.get('pct')}%)")

    print("\n== RAZONES: NO CALIFICADOS (se arreglan en Meta) ==")
    for etiqueta, d in res["razones_no_util"].items():
        if d:
            print(f"  -- {etiqueta} --")
            for k, v in list(d.items())[:10]:
                print(f"     {v:>4}  {k}")
    print("\n== RAZONES: INACTIVOS (se arreglan en el seguimiento comercial) ==")
    for etiqueta, d in res["razones_inactivo"].items():
        if d:
            print(f"  -- {etiqueta} --")
            for k, v in list(d.items())[:8]:
                print(f"     {v:>4}  {k}")

    if res["campanas_utm"]:
        print("\n== CAMPANAS CON ATRIBUCION (via UTM) ==")
        for c in res["campanas_utm"]:
            print(f"  campaign={c['utm_campaign']} content={c['utm_content']}  "
                  f"leads {c['leads']} | convertido {c['convertido']} | no util {c['no_util']}")
    else:
        print("\n== CAMPANAS CON ATRIBUCION ==")
        print("  Ninguna. El CRM no guarda UTM de Meta: no se puede cruzar un lead")
        print("  con la campana, el conjunto ni el anuncio que lo genero.")

    print("\n== COSTO POR LEAD ==")
    if res.get("cpl"):
        c = res["cpl"]
        mil = lambda n: f"{n:,}".replace(",", ".") if n is not None else "-"
        print(f"  gasto del periodo      {mil(c['gasto_ars'])} ARS")
        print(f"  CPL bruto              {mil(c['bruto_ars'])} ARS"
              f"   (objetivo <= {mil(c['objetivo_ars_bruto'])})"
              f"  {'OK' if c['dentro_de_objetivo'] else 'FUERA'}")
        print(f"  CPL calificado         {mil(c['calificado_ars'])} ARS   (excluye no utiles)")
        print(f"  CPL derivable          {mil(c['derivable_ars'])} ARS = {c['derivable_usd']} USD"
              f"   (techo <= {c['techo_usd_derivable']} USD)"
              f"  {'OK' if c['dentro_del_techo'] else 'FUERA'}")
    else:
        print("  Sin cifra de gasto: no calculable. Pasar --gasto-ars <ARS> del periodo")
        print("  (sale del export de Campanas de Meta Ads). Nunca estimarlo.")

    print("\n== ALERTAS ==")
    if res["alertas"]:
        for a in res["alertas"]:
            print(f"  [!] {a}")
    else:
        print("  Sin alertas: todos los umbrales dentro de rango.")
    print()


def main():
    ap = argparse.ArgumentParser(
        description="KPIs del canal Meta Ads desde el snapshot de prospectos de Bitrix24.")
    ap.add_argument("csv", help="Ruta al snapshot de prospectos")
    ap.add_argument("--json", help="Escribir el resultado como JSON en esta ruta")
    ap.add_argument("--desde", help="Fecha inicial YYYY-MM-DD")
    ap.add_argument("--hasta", help="Fecha final YYYY-MM-DD")
    ap.add_argument("--gasto-ars", type=float, dest="gasto_ars",
                    help="Gasto total en ARS del periodo (export de Campanas de Meta). "
                         "Sin esto, ningun CPL se calcula.")
    a = ap.parse_args()
    fecha = lambda s: datetime.date.fromisoformat(s) if s else None
    res = analizar(leer(a.csv), fecha(a.desde), fecha(a.hasta), a.gasto_ars)
    imprimir(res)
    if a.json:
        os.makedirs(os.path.dirname(a.json) or ".", exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
        print(f"JSON escrito en {a.json}\n")


if __name__ == "__main__":
    main()
