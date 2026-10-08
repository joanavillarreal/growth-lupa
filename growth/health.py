"""Panel de salud de datos.

Un dashboard que miente es peor que no tener dashboard. Esto mide cuánto
hay que creerle al resto de los números, con foco en prospectos, que es
donde se carga a mano y donde se rompe la atribución.
"""
from __future__ import annotations
from collections import Counter
from datetime import date, timedelta

from .config import Config
from . import metrics
from .metrics import _dia, _en_rango, _monto_usd


_CFG: list = []


def revisar(snapshot: dict, cfg: Config, desde: str, hasta: str) -> dict:
    _CFG[:] = [cfg]
    f = cfg["funnel"]
    catalogo = snapshot.get("catalogo_origenes", {})
    hallazgos: list[dict] = []

    # --- prospectos ---------------------------------------------------------
    leads = [l for l in snapshot["prospectos"] if _en_rango(l.get("DATE_CREATE"), desde, hasta)]
    total = len(leads)
    sin_origen = [l for l in leads if not l.get("SOURCE_ID")]
    sin_atribuir = [l for l in leads if cfg.canal_de_origen(l.get("SOURCE_ID")) == "sin_atribuir"]
    sin_contacto = [l for l in leads if l.get("HAS_PHONE") == "N" and l.get("HAS_EMAIL") == "N"]

    # orígenes que existen en Bitrix y nadie mapeó a un canal en definitions.yaml
    conocidos = set()
    for canal in cfg.canales.values():
        conocidos.update(str(o) for o in canal["origenes"])
    conocidos.update(str(o) for o in cfg["origenes_sin_atribuir"])
    huerfanos = Counter()
    for l in leads:
        sid = str(l.get("SOURCE_ID") or "")
        if sid and sid not in conocidos:
            huerfanos[sid] += 1

    if total:
        hallazgos.append(_check(
            "Prospectos sin canal atribuido", len(sin_atribuir), total,
            umbral_pct=10, severidad="alta",
            detalle="Sus prospectos no entran en ningún CPL ni % por canal.",
        ))
        # La contactabilidad se mide POR CANAL y contra el período anterior.
        # En los canales pagos, el prospecto entra a Bitrix sin teléfono ni mail
        # porque el contacto vive en la conversación (Hyperflow): eso es
        # estructural, no un error de carga. Lo que sí importa es que empeore.
        hallazgos.extend(_contactabilidad(snapshot, cfg, leads, desde, hasta))
    if sin_origen:
        hallazgos.append({
            "check": "Prospectos con origen vacío", "estado": "alerta", "severidad": "alta",
            "valor": len(sin_origen), "detalle": "SOURCE_ID sin cargar en Bitrix.",
        })
    for sid, n in huerfanos.most_common():
        hallazgos.append({
            "check": f"Origen nuevo sin mapear: {catalogo.get(sid, sid)}",
            "estado": "alerta", "severidad": "media", "valor": n,
            "detalle": f"Agregar '{sid}' a un canal en config/definitions.yaml.",
        })

    # --- negociaciones ------------------------------------------------------
    campo_cierre = f["cierre"]["campo_fecha"]
    campo_presu = f["presupuestado"]["campo_fecha"]
    cerradas = [d for d in snapshot["negociaciones"] if _en_rango(d.get(campo_cierre), desde, hasta)]
    presupuestadas = [d for d in snapshot["negociaciones"] if _en_rango(d.get(campo_presu), desde, hasta)]
    sin_mrr = [d for d in cerradas if not float(d.get("OPPORTUNITY") or 0)]
    if cerradas:
        hallazgos.append(_check(
            "Cierres sin MRR cargado", len(sin_mrr), len(cerradas),
            umbral_pct=5, severidad="alta",
            detalle="Sin MRR no hay ticket promedio, ni payback, ni LTV/CAC.",
        ))
    sin_presu_fecha = [d for d in cerradas if not _dia(d.get(campo_presu))]
    if cerradas:
        hallazgos.append(_check(
            "Cierres sin fecha de presupuestado", len(sin_presu_fecha), len(cerradas),
            umbral_pct=20, severidad="baja",
            detalle="Saltean una etapa del funnel: el % presupuestado→cierre queda sesgado.",
        ))

    # --- gasto --------------------------------------------------------------
    # Un solo renglón por canal. Meta y Redes se controlan contra la API, que
    # es de donde sale su inversión; el resto, contra el SPA.
    g = cfg["gasto"]
    hoy = date.fromisoformat(hasta)
    dias_periodo = (hoy - date.fromisoformat(desde)).days + 1
    regla_gasto = next((r for r in cfg["alertas"]["semanales"]
                        if r["metrica"] == "gasto_sin_cargar"), {})
    conf_meta = g.get("meta_api") or {}
    desde_api = metrics.cargar_gasto_meta(cfg)

    def renglon(nombre, fechas, fuente, cadencia):
        """Un canal está al día si cubre hasta `hoy - cadencia`.

        No se le puede exigir a una carga semanal que tenga el dato de ayer.
        """
        if not fechas:
            return {"check": f"Inversión de {nombre}", "estado": "alerta", "severidad": "alta",
                    "valor": f"sin ningún registro en {fuente}",
                    "detalle": "Sin inversión no hay CPL ni CAC para este canal."}
        ultimo = max(fechas)
        atraso = (hoy - date.fromisoformat(ultimo)).days
        # Solo se consideran los días que ya deberían estar cargados.
        corte_exigible = (hoy - timedelta(days=cadencia)).isoformat()
        exigibles = [(date.fromisoformat(desde) + timedelta(days=i)).isoformat()
                     for i in range(dias_periodo)
                     if (date.fromisoformat(desde) + timedelta(days=i)).isoformat() <= corte_exigible]
        faltantes = [d for d in exigibles if d not in set(fechas)]
        problemas = []
        if faltantes:
            muestra = ", ".join(faltantes[:4]) + ("…" if len(faltantes) > 4 else "")
            problemas.append(f"faltan {len(faltantes)} de {len(exigibles)} días: {muestra}")
        return {"check": f"Inversión de {nombre}",
                "estado": "alerta" if problemas else "ok", "severidad": "alta",
                "valor": "; ".join(problemas) if problemas
                         else f"al día hasta {ultimo}, vía {fuente} ({len(exigibles)} días del período)",
                "detalle": "Con días sin dato, el CPL y el CAC del período salen más baratos de lo real."
                           if problemas else ""}

    for clave in cfg.canales_activos:
        nombre = cfg.nombre_canal(clave)
        if clave in conf_meta.get("canales", {}):
            fechas = sorted(f for f, v in desde_api.items() if (v.get(clave) or 0) > 0)
            # Una campaña puede no haber corrido nunca todavía: eso no es un hueco.
            if not fechas:
                continue
            hallazgos.append(renglon(nombre, fechas, "la API de Meta",
                                     regla_gasto.get("cadencia_api_dias", 1)))
            continue
        tipos = set(cfg.canales[clave]["tipos_gasto"])
        fechas = sorted({_dia(i.get(g["campo_fecha"])) for i in snapshot["gastos"]
                         if i.get(g["campo_tipo"]) in tipos and _dia(i.get(g["campo_fecha"]))})
        hallazgos.append(renglon(nombre, fechas, "el SPA",
                                 regla_gasto.get("cadencia_spa_dias", 7)))

    # Conciliación: lo que la carga semanal dejó en el SPA contra lo que dice
    # Meta. No afecta las métricas —el dashboard usa la API— pero un desvío
    # avisa que a Bitrix le faltan días y que el resto de la empresa está
    # mirando un número distinto.
    espejo = conf_meta.get("tipo_gasto_espejo")
    if espejo is not None and desde_api:
        tc = conf_meta.get("cotizacion_ars_usd") or 1
        fechas_spa = sorted({_dia(i.get(g["campo_fecha"])) for i in snapshot["gastos"]
                             if i.get(g["campo_tipo"]) == espejo and _dia(i.get(g["campo_fecha"]))})
        if fechas_spa:
            # Se comparan solo los días que el SPA alcanzó a cubrir: como la carga
            # es semanal, siempre va a ir algunos días atrás y eso no es un error
            # de monto. El atraso se reporta aparte.
            corte = min(max(fechas_spa), hasta)
            en_spa = sum(_monto(i, g) for i in snapshot["gastos"]
                         if i.get(g["campo_tipo"]) == espejo and _en_rango(i.get(g["campo_fecha"]), desde, corte))
            en_api = sum(sum(v.values()) for f, v in desde_api.items() if desde <= f <= corte)
            atraso_spa = (hoy - date.fromisoformat(max(fechas_spa))).days
            problemas = []
            if en_api and abs((en_spa - en_api) / en_api * 100) > 3:
                problemas.append(f"los montos no coinciden: SPA ${en_spa:,.0f} vs Meta ${en_api:,.0f}")
            if atraso_spa > regla_gasto.get("cadencia_spa_dias", 7) + 1:
                problemas.append(f"última carga {max(fechas_spa)}, {atraso_spa} días atrás")
            hallazgos.append({
                "check": "Bitrix al día con Meta",
                "estado": "alerta" if problemas else "ok", "severidad": "media",
                "valor": "; ".join(problemas) if problemas
                         else f"coinciden hasta {corte} (${en_api:,.0f})",
                "detalle": "El dashboard usa la API, así que sus métricas están bien; lo que queda "
                           "desactualizado es el número que ve el resto de la empresa en el CRM."
                           if problemas else "",
            })

    alertas = [h for h in hallazgos if h["estado"] == "alerta"]
    return {
        "periodo": {"desde": desde, "hasta": hasta},
        "total_prospectos": total,
        "hallazgos": hallazgos,
        "alertas": len(alertas),
        "confiabilidad": _confiabilidad(alertas),
    }


def _contactabilidad(snapshot, cfg, leads_periodo, desde, hasta) -> list[dict]:
    """% de prospectos sin teléfono ni mail, por canal, contra el período previo."""
    from datetime import date, timedelta, timedelta

    largo = (date.fromisoformat(hasta) - date.fromisoformat(desde)).days + 1
    ini_previo = (date.fromisoformat(desde) - timedelta(days=largo)).isoformat()
    fin_previo = (date.fromisoformat(desde) - timedelta(days=1)).isoformat()
    previos = [l for l in snapshot["prospectos"] if _en_rango(l.get("DATE_CREATE"), ini_previo, fin_previo)]

    def tasa(grupo):
        por_canal = {}
        for l in grupo:
            canal = cfg.canal_de_origen(l.get("SOURCE_ID"))
            n, sin = por_canal.get(canal, (0, 0))
            falta = l.get("HAS_PHONE") == "N" and l.get("HAS_EMAIL") == "N"
            por_canal[canal] = (n + 1, sin + int(falta))
        return {c: (n, sin, round(sin / n * 100, 1)) for c, (n, sin) in por_canal.items() if n}

    ahora, antes = tasa(leads_periodo), tasa(previos)
    salida = []
    for canal in cfg.canales_activos:
        if canal not in ahora:
            continue
        n, sin, pct = ahora[canal]
        pct_antes = antes.get(canal, (0, 0, None))[2]
        empeoro = pct_antes is not None and (pct - pct_antes) > 15
        salida.append({
            "check": f"Contactabilidad: {cfg.nombre_canal(canal)}",
            "estado": "alerta" if empeoro else "ok",
            "severidad": "media",
            "valor": f"{sin}/{n} sin teléfono ni mail ({pct}%)",
            "detalle": f"Empeoró {pct - pct_antes:+.1f} pp contra el período anterior ({pct_antes}%)."
                       if empeoro else "",
        })
    return salida


def _monto(item, g):
    return _monto_usd(item.get(g["campo_monto"]), _CFG[0]) if _CFG else 0.0


def _check(nombre, cantidad, total, umbral_pct, severidad, detalle) -> dict:
    pct = round(cantidad / total * 100, 1) if total else 0.0
    return {
        "check": nombre,
        "estado": "alerta" if pct > umbral_pct else "ok",
        "severidad": severidad,
        "valor": f"{cantidad}/{total} ({pct}%)",
        "pct": pct,
        "detalle": detalle if pct > umbral_pct else "",
    }


def _confiabilidad(alertas: list[dict]) -> str:
    graves = sum(1 for a in alertas if a["severidad"] == "alta")
    if graves >= 2:
        return "baja"
    if graves == 1 or len(alertas) >= 3:
        return "media"
    return "alta"
