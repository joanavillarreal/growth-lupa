"""Monitor de Growth: los números del dashboard, un trimestre por vez.

Cuatro solapas que siguen el camino del prospecto: el funnel general del Q,
y después cada paso por separado (generación, derivación, ventas). Todo sale
del snapshot, igual que el resto del agente.

Convención de corte, la misma para todos los hitos:
  - generados:      prospectos con fecha de creación en el Q.
  - derivados:      negociaciones con Fecha de derivación en el Q.
  - presupuestados: negociaciones con Fecha de Presupuestado en el Q.
  - cerrados:       negociaciones con Fecha de cierre en el Q.
A los tres hitos de negociación se les suma cuántos vienen de prospectos
ingresados en el mismo Q (vínculo LEAD_ID), que es la parte del resultado que
explica la generación del propio trimestre.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import experiments, health, metrics
from .config import Config
from .metrics import _dia, _dias_entre, _en_rango, _mrr_usd

N_MINIMO = 15   # prospectos, para comparar tasas entre canales


def _prom(v):
    return round(sum(v) / len(v), 1) if v else None


def _pct(a, b):
    return round(a / b * 100, 1) if b else None


# Las semanas van de sábado a viernes: lo que entra el sábado lo trabaja SDR
# en la semana que sigue, así que pertenece a esa semana.
INICIO_SEMANA = 5   # date.weekday(): lunes 0 … sábado 5


def _inicio_semana(d: date) -> date:
    return d - timedelta(days=(d.weekday() - INICIO_SEMANA) % 7)


def _semanal(fechas: list[str], desde: str, hasta: str, tope: str) -> dict:
    """Conteo por semana de sábado a viernes dentro del Q.

    La primera y la última semana quedan recortadas por los bordes del Q. La
    semana N de un Q se compara con la semana N del Q anterior.
    """
    ini_q, fin_q = date.fromisoformat(desde), date.fromisoformat(hasta)
    corte = min(fin_q, date.fromisoformat(tope))
    semanas = []
    s0 = _inicio_semana(ini_q)
    while s0 <= fin_q:
        semanas.append((max(s0, ini_q), min(s0 + timedelta(days=6), fin_q)))
        s0 += timedelta(days=7)
    cuentas = [0] * len(semanas)
    for f in fechas:
        d = _dia(f)
        if not d or not (desde <= d <= hasta):
            continue
        i = (_inicio_semana(date.fromisoformat(d)) - _inicio_semana(ini_q)).days // 7
        cuentas[i] += 1
    visibles = [i for i, (a, _) in enumerate(semanas) if a <= corte]
    n = len(visibles)
    ultima_parcial = bool(n) and semanas[n - 1][1] > corte
    return {
        "valores": cuentas[:n],
        "ultima_parcial": ultima_parcial,
        "rangos": [[a.isoformat(), min(b, corte).isoformat()] for a, b in semanas[:n]],
        "primera_parcial": bool(semanas) and semanas[0][0].weekday() != INICIO_SEMANA,
    }


class _Ctx:
    """Índices del snapshot que todas las solapas comparten."""

    def __init__(self, snap: dict, cfg: Config):
        self.snap, self.cfg = snap, cfg
        f, m = cfg["funnel"], cfg["monitor"]
        self.c_deriv = f["derivado"]["campo_fecha_deal"]
        self.c_presu = f["presupuestado"]["campo_fecha"]
        self.c_cierre = f["cierre"]["campo_fecha"]
        self.c_razon = f["no_derivacion"]["campo"]
        self.c_tn_lead = m["campos"]["tipo_negocio_lead"]
        self.c_tn_deal = m["campos"]["tipo_negocio_deal"]
        self.c_plan = m["campos"]["plan_deal"]
        self.futuro = m["etapas_a_futuro"]
        # Nombres: los del CRM si el webhook puede leer usuarios; si no, los del YAML.
        self.asesores = {str(k): v for k, v in (m.get("asesores") or {}).items()}
        self.asesores.update({k: v for k, v in ((snap.get("catalogos") or {}).get("usuarios") or {}).items() if v})
        cat = snap.get("catalogos") or {}
        self.cat_tn = cat.get("tipo_negocio", {})
        self.cat_plan = cat.get("plan", {})
        self.cat_etapas = cat.get("etapas", {})
        self.cat_razones = snap.get("catalogo_razones", {})
        self.leads = {str(l["ID"]): l for l in snap["prospectos"]}
        self.deals = snap["negociaciones"]
        self.deals_por_lead = defaultdict(list)
        for d in self.deals:
            if d.get("LEAD_ID"):
                self.deals_por_lead[str(d["LEAD_ID"])].append(d)
        self.act_lead = defaultdict(list)
        for owner, creada in (snap.get("actividades") or {}).get("prospectos", []):
            self.act_lead[str(owner)].append(creada)
        self.pendientes = defaultdict(list)
        for owner, vence in (snap.get("actividades") or {}).get("pendientes_negociacion", []):
            self.pendientes[str(owner)].append(vence)
        self.grupos = []
        for g in m["grupos_etapa"]:
            self.grupos.append((g["nombre"], set(g.get("etapas", [])), tuple(g.get("prefijos", []))))

    def canal(self, source_id) -> str:
        return self.cfg.canal_de_origen(source_id)

    def nombre_canal(self, clave) -> str:
        return self.cfg.nombre_canal(clave)

    def asesor(self, uid) -> str:
        uid = str(uid or "")
        return self.asesores.get(uid, f"Usuario #{uid}" if uid else "Sin asignar")

    def razon(self, rid) -> str:
        return self.cat_razones.get(str(rid), "(sin razón cargada)") if rid else "(sin razón cargada)"

    def tipo_negocio_deal(self, d) -> str:
        v = d.get(self.c_tn_deal)
        if not v and d.get("LEAD_ID"):
            v = (self.leads.get(str(d["LEAD_ID"])) or {}).get(self.c_tn_lead)
        return self.cat_tn.get(str(v), "Sin cargar") if v else "Sin cargar"

    def tipo_negocio_lead(self, l) -> str:
        v = l.get(self.c_tn_lead)
        return self.cat_tn.get(str(v), "Sin cargar") if v else "Sin cargar"

    def grupo_etapa(self, d) -> str:
        if _dia(d.get(self.c_cierre)):
            return "Cliente"
        st = d.get("STAGE_ID") or ""
        for nombre, etapas, prefijos in self.grupos:
            if st in etapas or (prefijos and st.startswith(prefijos)):
                return nombre
        return "Otros embudos"


def _ranking(counter: Counter, n=None) -> list:
    return [[k, v] for k, v in counter.most_common(n)]


def _podio(res: dict, ctx: _Ctx) -> dict:
    """Cuatro criterios, 3-2-1 puntos por puesto en cada uno."""
    canales = {k: v for k, v in res["canales"].items()
               if k != "sin_atribuir" and (v["prospectos"] or v["derivados"] or v["cierres"])}
    criterios = [
        ("derivados", "Más derivó", False, None),
        ("cierres", "Más cierres", False, None),
        ("presupuestados", "Más presupuestos", False, None),
        ("pct_no_calificacion", "Menos no calificados", True, N_MINIMO),
    ]
    puntos = Counter()
    detalle = []
    for clave, titulo, menor_mejor, n_min in criterios:
        cand = [(k, v[clave]) for k, v in canales.items()
                if v[clave] is not None and (n_min is None or v["prospectos"] >= n_min)]
        if not menor_mejor:
            cand = [c for c in cand if c[1] > 0]
        cand.sort(key=lambda kv: kv[1], reverse=not menor_mejor)
        for i, (k, _) in enumerate(cand[:3]):
            puntos[k] += 3 - i
        detalle.append({
            "criterio": titulo, "clave": clave, "pct": clave.startswith("pct"),
            "top": [[ctx.nombre_canal(k), v] for k, v in cand[:3]],
        })
    orden = sorted(puntos.items(), key=lambda kv: (-kv[1], -canales[kv[0]]["cierres"],
                                                   -canales[kv[0]]["derivados"]))
    return {
        "podio": [{"canal": ctx.nombre_canal(k), "puntos": p,
                   "derivados": canales[k]["derivados"], "cierres": canales[k]["cierres"],
                   "presupuestados": canales[k]["presupuestados"],
                   "pct_no_calificacion": canales[k]["pct_no_calificacion"]} for k, p in orden[:3]],
        "criterios": detalle,
        "n_minimo": N_MINIMO,
    }


def calcular_q(ctx: _Ctx, etiqueta: str, desde: str, hasta: str, previo: tuple | None) -> dict:
    snap, cfg = ctx.snap, ctx.cfg
    tope = snap["ventana"]["hasta"]
    hoy = tope
    base = metrics.calcular(snap, cfg, desde, min(hasta, tope))
    gen = base["general"]

    # ---------------- prospectos del Q ----------------
    leads_q = [l for l in snap["prospectos"] if _en_rango(l.get("DATE_CREATE"), desde, hasta)]
    ids_q = {str(l["ID"]) for l in leads_q}
    inactivos = [l for l in leads_q if l.get("STATUS_ID") == "UC_LG671J"]
    no_utiles = [l for l in leads_q if l.get("STATUS_ID") == "JUNK"]

    def resumen_descarte(grupo, n_razones):
        razones = Counter(ctx.razon(l.get(ctx.c_razon)) for l in grupo)
        canales = Counter(ctx.nombre_canal(ctx.canal(l.get("SOURCE_ID"))) for l in grupo)
        return {"n": len(grupo), "pct": _pct(len(grupo), len(leads_q)),
                "razones": _ranking(razones, n_razones), "canales": _ranking(canales, 3)}

    # a futuro: prospectos del Q con alguna negociación hoy en una columna a futuro
    fut_ventas, fut_presu = set(), set()
    for lid in ids_q:
        for d in ctx.deals_por_lead.get(lid, []):
            st = d.get("STAGE_ID") or ""
            if st in ctx.futuro:
                (fut_ventas if st.startswith("C10:") else fut_presu).add(lid)
    a_futuro = fut_ventas | fut_presu

    # ---------------- hitos de negociación del Q ----------------
    derivados = [d for d in ctx.deals if _en_rango(d.get(ctx.c_deriv), desde, hasta)]
    presupuestados = [d for d in ctx.deals if _en_rango(d.get(ctx.c_presu), desde, hasta)]
    cerrados = [d for d in ctx.deals if _en_rango(d.get(ctx.c_cierre), desde, hasta)]

    def del_q(grupo):
        return sum(1 for d in grupo if str(d.get("LEAD_ID") or "") in ids_q)

    mrr = round(sum(_mrr_usd(d, cfg) for d in cerrados), 2)
    dias_cierre = [x for d in cerrados if (x := _dias_entre(d.get(ctx.c_deriv), d.get(ctx.c_cierre))) is not None]

    gasto_medios = round(sum(v["gasto_usd"] for v in base["canales"].values()), 2)
    cac_canal = []
    for k, v in sorted(base["canales"].items(), key=lambda kv: -kv[1]["gasto_usd"]):
        if v["gasto_usd"] > 0:
            cac_canal.append({"canal": v["nombre"], "gasto": v["gasto_usd"], "cierres": v["cierres"],
                              "cac": v["cac_usd"], "cobertura": v["cobertura_gasto"]})

    tab1 = {
        "tabla": {
            "gasto": round(gasto_medios + base["overhead_usd"], 2),
            "gasto_medios": gasto_medios, "gasto_overhead": base["overhead_usd"],
            "generados": len(leads_q),
            "no_calificados": len(no_utiles),
            "derivados": len(derivados), "derivados_mismo_q": del_q(derivados),
            "presupuestados": len(presupuestados), "presupuestados_mismo_q": del_q(presupuestados),
            "a_futuro": len(a_futuro), "a_futuro_ventas": len(fut_ventas),
            "a_futuro_presupuestos": len(fut_presu - fut_ventas),
            "cerrados": len(cerrados), "cerrados_mismo_q": del_q(cerrados),
            "mrr": mrr,
        },
        "inactivo": resumen_descarte(inactivos, 3),
        "no_calificado": resumen_descarte(no_utiles, 1),
        "win_rate": _pct(len(cerrados), len(leads_q)),
        "pct_a_futuro": _pct(len(a_futuro), len(leads_q)),
        "dias_cierre": {"promedio": _prom(dias_cierre), "n": len(dias_cierre), "de": len(cerrados)},
        "cac": {"general": round(gasto_medios / len(cerrados), 2) if cerrados else None,
                "canales": cac_canal},
    }

    # ---------------- generación ----------------
    rango_prev = previo[1:] if previo else None

    def semanal_de(fechas_fn, lista_fn):
        act = _semanal(fechas_fn(lista_fn(desde, hasta)), desde, hasta, tope)
        prev = _semanal(fechas_fn(lista_fn(*rango_prev)), *rango_prev, tope) if rango_prev else None
        return {"actual": act, "previo": prev, "previo_etiqueta": previo[0] if previo else None}

    def leads_en(a, b):
        return [l for l in snap["prospectos"] if _en_rango(l.get("DATE_CREATE"), a, b)]

    def deals_en(campo):
        return lambda a, b: [d for d in ctx.deals if _en_rango(d.get(campo), a, b)]

    por_canal = []
    for k, v in sorted(base["canales"].items(), key=lambda kv: -kv[1]["prospectos"]):
        if v["prospectos"] or v["gasto_usd"]:
            por_canal.append({"canal": v["nombre"], "clave": k, "generados": v["prospectos"],
                              "gasto": v["gasto_usd"], "cpl": v["cpl_usd"],
                              "cobertura": v["cobertura_gasto"]})
    tab2 = {
        "gasto": gasto_medios,
        "semanal": semanal_de(lambda ls: [l["DATE_CREATE"] for l in ls], leads_en),
        "generados": len(leads_q),
        "por_canal": por_canal,
        "podio": _podio(base, ctx),
        "cpl": gen["cpl_usd"],
        "por_tipo_negocio": _ranking(Counter(ctx.tipo_negocio_lead(l) for l in leads_q)),
    }

    # ---------------- derivación ----------------
    convertidos = [l for l in snap["prospectos"]
                   if l.get("STATUS_ID") == "CONVERTED" and _en_rango(l.get("DATE_CLOSED"), desde, hasta)]
    acts, dias_der = [], []
    for l in convertidos:
        corte = _dia(l.get("DATE_CLOSED"))
        acts.append(sum(1 for c in ctx.act_lead.get(str(l["ID"]), []) if c and c <= corte))
        if (x := _dias_entre(l.get("DATE_CREATE"), l.get("DATE_CLOSED"))) is not None:
            dias_der.append(x)
    tab3 = {
        "derivados": len(derivados),
        "derivados_mismo_q": del_q(derivados),
        "por_asesor": _ranking(Counter(ctx.asesor(d.get("ASSIGNED_BY_ID")) for d in derivados)),
        "por_canal": _ranking(Counter(ctx.nombre_canal(ctx.canal(d.get("SOURCE_ID"))) for d in derivados)),
        "semanal": semanal_de(lambda ds: [d[ctx.c_deriv] for d in ds], deals_en(ctx.c_deriv)),
        "por_tipo_negocio": _ranking(Counter(ctx.tipo_negocio_deal(d) for d in derivados)),
        "actividades": {"promedio": _prom(acts), "n": len(acts),
                        "sin_actividad": sum(1 for a in acts if a == 0)},
        "dias_derivacion": {"promedio": _prom(dias_der), "mediana": metrics._mediana(dias_der),
                            "n": len(dias_der)},
    }

    # ---------------- ventas ----------------
    asesores = defaultdict(lambda: {"presupuestos": 0, "mrr_presupuestado": 0.0, "cierres": 0,
                                    "mrr": 0.0, "_dias": [], "recibido": Counter()})
    for d in presupuestados:
        a = asesores[ctx.asesor(d.get("ASSIGNED_BY_ID"))]
        a["presupuestos"] += 1
        a["mrr_presupuestado"] += _mrr_usd(d, cfg)
    for d in cerrados:
        a = asesores[ctx.asesor(d.get("ASSIGNED_BY_ID"))]
        a["cierres"] += 1
        a["mrr"] += _mrr_usd(d, cfg)
        if (x := _dias_entre(d.get(ctx.c_deriv), d.get(ctx.c_cierre))) is not None:
            a["_dias"].append(x)
    for d in derivados:
        asesores[ctx.asesor(d.get("ASSIGNED_BY_ID"))]["recibido"][ctx.grupo_etapa(d)] += 1
    filas_asesor = []
    for nombre, a in asesores.items():
        filas_asesor.append({
            "asesor": nombre, "presupuestos": a["presupuestos"],
            "mrr_presupuestado": round(a["mrr_presupuestado"], 2),
            "cierres": a["cierres"], "mrr": round(a["mrr"], 2),
            "dias_cierre": _prom(a["_dias"]), "dias_cierre_n": len(a["_dias"]),
            "recibido": dict(a["recibido"]), "recibido_total": sum(a["recibido"].values()),
        })
    filas_asesor.sort(key=lambda f: (-f["recibido_total"], -f["cierres"]))

    grupos_orden = [g[0] for g in ctx.grupos] + ["Otros embudos"]

    tab4 = {
        "semanal": semanal_de(lambda ds: [d[ctx.c_presu] for d in ds], deals_en(ctx.c_presu)),
        "presupuestos": len(presupuestados),
        "asesores": filas_asesor,
        "grupos": [g for g in grupos_orden if any(f["recibido"].get(g) for f in filas_asesor)],
        "clientes": {
            "n": len(cerrados),
            "planes": _ranking(Counter(ctx.cat_plan.get(str(d.get(ctx.c_plan)), "Sin cargar")
                                       if d.get(ctx.c_plan) else "Sin cargar" for d in cerrados)),
            "vendedores": _ranking(Counter(ctx.asesor(d.get("ASSIGNED_BY_ID")) for d in cerrados)),
            "tipos": _ranking(Counter(ctx.tipo_negocio_deal(d) for d in cerrados)),
        },
    }

    return {
        "etiqueta": etiqueta, "desde": desde, "hasta": hasta,
        "parcial": hasta > tope, "corte": min(hasta, tope),
        "previo": previo[0] if previo else None,
        "funnel": tab1, "generacion": tab2, "derivacion": tab3, "ventas": tab4,
        "salud": health.revisar(snap, cfg, desde, min(hasta, tope)),
        "comparacion": comparar(ctx, desde, min(hasta, tope), previo),
        "objetivos": objetivos_q(ctx, etiqueta, desde, hasta, min(hasta, tope), base,
                                 leads_q, len(no_utiles), cerrados),
    }


def _objetivos_de(cfg: Config, etiqueta: str) -> dict | None:
    """Los objetivos que rigen para un Q: la última clave que no lo supera."""
    tabla = (cfg["monitor"].get("objetivos") or {})
    vigentes = [k for k in tabla if k <= etiqueta]
    return tabla[max(vigentes)] if vigentes else None


def objetivos_q(ctx: "_Ctx", etiqueta: str, desde: str, hasta: str, corte: str, base: dict,
                leads_q: list[dict], no_utiles: int, cerrados: list[dict]) -> dict | None:
    """Cada objetivo con su valor, su meta y si viene bien.

    Los ratios (CAC, ROAS, %) se juzgan contra la meta tal cual. Los leads se
    acumulan durante el Q, así que se juzgan por ritmo: lo generado hasta hoy
    proyectado a los días del trimestre.
    """
    obj = _objetivos_de(ctx.cfg, etiqueta)
    if not obj:
        return None
    m = ctx.cfg["monitor"]
    dias_q = _dias_entre(desde, hasta) + 1
    dias = _dias_entre(desde, corte) + 1
    gasto_total = sum(v["gasto_usd"] for v in base["canales"].values()) + base["overhead_usd"]
    n_cierres = len(cerrados)
    salida = []

    # CAC
    cac = round(gasto_total / n_cierres, 2) if n_cierres else None
    salida.append({"clave": "cac", "nombre": "CAC", "valor": cac, "meta": obj["cac_max_usd"],
                   "sentido": "max", "formato": "usd",
                   "ok": None if cac is None else cac <= obj["cac_max_usd"],
                   "provisorio": n_cierres < 5,
                   "detalle": {"gasto": round(gasto_total, 2), "overhead": base["overhead_usd"], "cierres": n_cierres}})

    # ROAS de pauta
    pauta = m.get("canales_pauta", [])
    g_pauta = sum(base["canales"].get(k, {}).get("gasto_usd", 0) for k in pauta)
    mrr_pauta = sum(base["canales"].get(k, {}).get("mrr_cerrado_usd", 0) for k in pauta)
    c_pauta = sum(base["canales"].get(k, {}).get("cierres", 0) for k in pauta)
    roas = round(mrr_pauta / g_pauta, 2) if g_pauta else None
    salida.append({"clave": "roas", "nombre": "ROAS de pauta", "valor": roas, "meta": obj["roas_min"],
                   "sentido": "min", "formato": "x",
                   "ok": None if roas is None else roas >= obj["roas_min"],
                   "provisorio": c_pauta < 5,
                   "detalle": {"mrr": round(mrr_pauta, 2), "gasto": round(g_pauta, 2), "cierres": c_pauta,
                               "canales": [ctx.nombre_canal(k) for k in pauta]}})

    # % no calificados
    gen = len(leads_q)
    pnc = _pct(no_utiles, gen)
    salida.append({"clave": "no_calificados", "nombre": "Leads no calificados", "valor": pnc,
                   "meta": obj["pct_no_calificados_max"], "sentido": "max", "formato": "pct",
                   "ok": None if pnc is None else pnc <= obj["pct_no_calificados_max"],
                   "provisorio": gen < 30, "detalle": {"n": no_utiles, "generados": gen}})

    # leads del Q, por ritmo
    proy = round(gen / dias * dias_q) if dias else None
    salida.append({"clave": "leads", "nombre": "Leads generados", "valor": gen, "meta": obj["leads_q"],
                   "sentido": "acumulado", "formato": "n",
                   "ok": None if proy is None else proy >= obj["leads_q"],
                   "provisorio": dias < 14,
                   "detalle": {"proyeccion": proy, "dias": dias, "dias_q": dias_q,
                               "esperado_hoy": round(obj["leads_q"] * dias / dias_q)}})

    # % casas de repuestos
    tipos = Counter(ctx.tipo_negocio_lead(l) for l in leads_q)
    sin_def = sum(tipos.get(t, 0) for t in m.get("tipos_sin_definir", []))
    casas = sum(tipos.get(t, 0) for t in m.get("tipos_casa_repuestos", []))
    definidos = gen - sin_def
    pcr = _pct(casas, definidos)
    salida.append({"clave": "casas_repuestos", "nombre": "Casas de repuestos", "valor": pcr,
                   "meta": obj["pct_casas_repuestos_min"], "sentido": "min", "formato": "pct",
                   "ok": None if pcr is None else pcr >= obj["pct_casas_repuestos_min"],
                   "provisorio": definidos < 30,
                   "detalle": {"casas": casas, "definidos": definidos, "sin_definir": sin_def}})

    # win rate
    wr = _pct(n_cierres, gen)
    salida.append({"clave": "win_rate", "nombre": "Win rate", "valor": wr, "meta": obj["win_rate_min"],
                   "sentido": "min", "formato": "pct",
                   "ok": None if wr is None else wr >= obj["win_rate_min"],
                   "provisorio": n_cierres < 5, "detalle": {"cierres": n_cierres, "generados": gen}})

    # MRR, con sus dos capas
    mrr = None
    if obj.get("mrr_q_usd"):
        por_canal = {k: v.get("mrr_cerrado_usd", 0) for k, v in base["canales"].items()}
        total = round(sum(por_canal.values()), 2)
        prefijos = tuple(x.lower() for x in m.get("prefijos_en_vivo", []))
        extra = {x.lower() for x in m.get("origenes_en_vivo", [])}
        cat_origenes = ctx.snap.get("catalogo_origenes", {})

        def es_vivo(d):
            nombre = cat_origenes.get(str(d.get("SOURCE_ID")), "").lower()
            return bool(nombre) and (nombre.startswith(prefijos) or nombre in extra)

        origenes_vivo = sorted({cat_origenes.get(str(d.get("SOURCE_ID")), "") for d in cerrados if es_vivo(d)})
        en_vivo = round(sum(_mrr_usd(d, ctx.cfg) for d in cerrados if es_vivo(d)), 2)
        pagos = round(sum(por_canal.get(k, 0) for k in m.get("canales_pagos_mrr", [])), 2)
        sin_atr = round(por_canal.get("sin_atribuir", 0), 2)
        no_pago = round(total - pagos - sin_atr, 2)
        pnp = _pct(no_pago, total)
        proy = round(total / dias * dias_q) if dias else None
        proy_vivo = round(en_vivo / dias * dias_q) if dias else None
        grupos = [
            {"nombre": " + ".join(ctx.nombre_canal(k) for k in m.get("canales_pagos_mrr", [])), "tipo": "pago", "mrr": pagos},
            {"nombre": "Acciones en vivo", "tipo": "vivo", "mrr": en_vivo},
            {"nombre": "Otros no pagos", "tipo": "otro", "mrr": round(no_pago - en_vivo, 2)},
            {"nombre": "Sin atribuir", "tipo": "sin", "mrr": sin_atr},
        ]
        canales = sorted(([ctx.nombre_canal(k), round(v, 2)] for k, v in por_canal.items() if v), key=lambda x: -x[1])
        mrr = {
            "valor": total, "meta": obj["mrr_q_usd"], "proyeccion": proy,
            "esperado_hoy": round(obj["mrr_q_usd"] * dias / dias_q), "dias": dias, "dias_q": dias_q,
            "ok": None if proy is None else proy >= obj["mrr_q_usd"],
            "provisorio": n_cierres < 5 or dias < 14, "cierres": n_cierres,
            "ticket": round(total / n_cierres, 2) if n_cierres else None,
            "en_vivo": {"valor": en_vivo, "meta": obj["mrr_en_vivo_usd"], "proyeccion": proy_vivo,
                        "esperado_hoy": round(obj["mrr_en_vivo_usd"] * dias / dias_q),
                        "ok": None if proy_vivo is None else proy_vivo >= obj["mrr_en_vivo_usd"],
                        "prefijos": m.get("prefijos_en_vivo", []),
                        "extra": m.get("origenes_en_vivo", []), "origenes": origenes_vivo},
            "no_pago": {"valor": pnp, "mrr": no_pago, "meta": obj["pct_mrr_no_pago_min"],
                        "ok": None if pnp is None else pnp > obj["pct_mrr_no_pago_min"]},
            "grupos": grupos, "canales": canales,
        }
    return {"metas": salida, "mrr": mrr}


def cartera_a_futuro(ctx: _Ctx) -> dict:
    """Foto de HOY: negociaciones en columnas a futuro y su agenda, por asesor.

    No depende del Q elegido: la cartera estacionada es la de hoy, entre
    cuando haya entrado.
    """
    hoy = ctx.snap["ventana"]["hasta"]
    filas = defaultdict(lambda: {"total": 0, "sin_actividad": 0, "vencidas": 0, "al_dia": 0,
                                 "por_columna": Counter()})
    for d in ctx.deals:
        st = d.get("STAGE_ID") or ""
        if st not in ctx.futuro:
            continue
        f = filas[ctx.asesor(d.get("ASSIGNED_BY_ID"))]
        f["total"] += 1
        f["por_columna"][ctx.futuro[st]] += 1
        pend = ctx.pendientes.get(str(d["ID"]), [])
        if not pend:
            f["sin_actividad"] += 1
        elif any(v and v < hoy for v in pend):
            f["vencidas"] += 1
        else:
            f["al_dia"] += 1
    salida = [{"asesor": k, **{kk: vv for kk, vv in v.items() if kk != "por_columna"},
               "por_columna": _ranking(v["por_columna"])} for k, v in filas.items()]
    salida.sort(key=lambda f: -(f["sin_actividad"] + f["vencidas"]))
    return {"fecha": hoy, "asesores": salida,
            "total": sum(f["total"] for f in salida),
            "sin_actividad": sum(f["sin_actividad"] for f in salida),
            "vencidas": sum(f["vencidas"] for f in salida)}


# --------------------------------------------------------------------------- #
# comparación contra el mismo tramo del Q anterior
# --------------------------------------------------------------------------- #
def _kpis(ctx: "_Ctx", desde: str, hasta: str) -> dict:
    """Los números que se comparan entre trimestres, sobre un tramo cualquiera."""
    snap, cfg = ctx.snap, ctx.cfg
    base = metrics.calcular(snap, cfg, desde, hasta)
    leads = [l for l in snap["prospectos"] if _en_rango(l.get("DATE_CREATE"), desde, hasta)]
    gen = len(leads)
    cerr = [d for d in ctx.deals if _en_rango(d.get(ctx.c_cierre), desde, hasta)]
    gasto = sum(v["gasto_usd"] for v in base["canales"].values())
    dias = [x for d in cerr if (x := _dias_entre(d.get(ctx.c_deriv), d.get(ctx.c_cierre))) is not None]
    return {
        "_n_leads": gen, "_n_cierres": len(cerr),
        "gasto": round(gasto, 2),
        "generados": gen,
        "cpl": round(gasto / gen, 2) if gen else None,
        "pct_no_calificacion": _pct(sum(1 for l in leads if l.get("STATUS_ID") == "JUNK"), gen),
        "pct_inactivo": _pct(sum(1 for l in leads if l.get("STATUS_ID") == "UC_LG671J"), gen),
        "derivados": sum(1 for d in ctx.deals if _en_rango(d.get(ctx.c_deriv), desde, hasta)),
        "presupuestados": sum(1 for d in ctx.deals if _en_rango(d.get(ctx.c_presu), desde, hasta)),
        "cerrados": len(cerr),
        "mrr": round(sum(_mrr_usd(d, cfg) for d in cerr), 2),
        "win_rate": _pct(len(cerr), gen),
        "cac": round(gasto / len(cerr), 2) if cerr else None,
        "dias_cierre": _prom(dias),
    }


def _n_de(clave: str, k: dict) -> int:
    """Sobre cuántos casos se apoya cada métrica, para exigirle un mínimo."""
    if clave in ("cerrados", "mrr", "win_rate", "cac", "dias_cierre"):
        return k["_n_cierres"]
    if clave in ("derivados", "presupuestados"):
        return k[clave]
    return k["_n_leads"]


def comparar(ctx: "_Ctx", desde: str, corte: str, previo: tuple | None) -> dict:
    """Cada número del tramo contra el mismo tramo del Q anterior.

    estado: "desmejora" si empeoró más que su umbral, "mejora" si mejoró más
    que su umbral, "estable" si no, y "sin_lectura" cuando todavía no hay
    volumen o días suficientes para decir nada.
    """
    conf = ctx.cfg["monitor"]["desmejora"]
    actual = _kpis(ctx, desde, corte)
    largo = _dias_entre(desde, corte)
    salida = {"tramo": {"desde": desde, "hasta": corte, "dias": largo + 1}, "previo": None, "metricas": {}}
    prev = None
    if previo:
        p_desde, p_fin = previo[1], previo[2]
        p_hasta = min((date.fromisoformat(p_desde) + timedelta(days=largo)).isoformat(), p_fin)
        prev = _kpis(ctx, p_desde, p_hasta)
        salida["previo"] = {"etiqueta": previo[0], "desde": p_desde, "hasta": p_hasta}
    for clave, m in conf["metricas"].items():
        a = actual.get(clave)
        b = prev.get(clave) if prev else None
        fila = {"nombre": m["nombre"], "actual": a, "previo": b, "mejor": m["mejor"],
                "delta_pct": None, "delta_pp": None, "estado": "sin_lectura"}
        if a is not None and b is not None:
            if "umbral_pp" in m:
                fila["delta_pp"] = round(a - b, 1)
                cambio, umbral = fila["delta_pp"], m["umbral_pp"]
            else:
                fila["delta_pct"] = round((a - b) / b * 100, 1) if b else None
                cambio, umbral = fila["delta_pct"], m["umbral_pct"]
            con_volumen = min(_n_de(clave, actual), _n_de(clave, prev)) >= m.get("n_min", 0)
            if cambio is not None and con_volumen and largo + 1 >= conf["dias_minimos_q"]:
                peor = cambio < 0 if m["mejor"] == "sube" else cambio > 0
                if abs(cambio) < umbral:
                    fila["estado"] = "estable"
                else:
                    fila["estado"] = "desmejora" if peor else "mejora"
        salida["metricas"][clave] = fila
    return salida


def estado_actual(snap: dict, cfg: Config) -> dict:
    """La comparación del Q en curso, sola: la usa la alarma diaria."""
    ctx = _Ctx(snap, cfg)
    hasta = snap["ventana"]["hasta"]
    qs = _trimestres_completos(snap)
    for i, (etiqueta, ini, fin) in enumerate(qs):
        if ini <= hasta <= fin:
            comp = comparar(ctx, ini, hasta, qs[i - 1] if i else None)
            comp["etiqueta"] = etiqueta
            return comp
    return {"etiqueta": None, "metricas": {}}


def _trimestres_completos(snap: dict) -> list[tuple[str, str, str]]:
    hasta = snap["ventana"]["hasta"]
    qs = []
    for etiqueta, ini, fin in metrics.trimestres(snap["ventana"]["desde"], hasta):
        y, q = int(etiqueta[:4]), int(etiqueta[-1])
        fin_real = (date(y + (q == 4), (q * 3) % 12 + 1, 1) - timedelta(days=1)).isoformat()
        qs.append((etiqueta, ini, fin_real))
    return qs


def gasto_meta_atrasado(cfg: Config, hasta: str) -> dict | None:
    """El gasto de Meta tiene que llegar hasta el día anterior al snapshot.

    Si el refresco no corrió (Meta no conectó), los días que faltan cuentan
    como inversión cero y el CPL, el CAC y el ROAS salen baratos. En ese caso
    el Monitor lo dice arriba de todo, en todas las solapas.
    """
    fechas = sorted(metrics.cargar_gasto_meta(cfg))
    esperado = (date.fromisoformat(hasta) - timedelta(days=1)).isoformat()
    ultimo = fechas[-1] if fechas else None
    if ultimo and ultimo >= esperado:
        return None
    return {"hasta": ultimo, "esperado": esperado,
            "dias_faltantes": _dias_entre(ultimo, esperado) if ultimo else None}


def armar(snap: dict, cfg: Config) -> dict:
    ctx = _Ctx(snap, cfg)
    hasta = snap["ventana"]["hasta"]
    # Los Q se listan completos: el Q en curso muestra su avance hasta hoy.
    qs = _trimestres_completos(snap)
    salida = []
    for i, (etiqueta, ini, fin) in enumerate(qs):
        salida.append(calcular_q(ctx, etiqueta, ini, fin, qs[i - 1] if i else None))
    extra = {}
    if (atraso := gasto_meta_atrasado(cfg, hasta)):
        extra["gasto_meta_atrasado"] = atraso
    return {
        "generado_en": snap["generado_en"],
        "actualizado": hasta,
        "trimestres": salida,
        "cartera_a_futuro": cartera_a_futuro(ctx),
        "tiene_actividades": bool(snap.get("actividades")),
        "experimentos": experiments.para_monitor(snap, cfg),
        # La solapa Experimentos arranca acá: los Q anteriores no tienen registro.
        "experimentos_desde": "2026-Q4",
        **extra,
    }
