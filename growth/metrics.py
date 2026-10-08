"""Cálculo del funnel: general y por canal de adquisición.

Convenciones de corte (definidas con el equipo, ver config/definitions.yaml):
  - PROSPECTOS: prospectos creados dentro del período.
  - DERIVADOS: dos lecturas, porque no son lo mismo y conviene ver las dos.
      * cohorte   -> prospectos CREADOS en el período que hoy están Convertido.
                     Responde "de lo que entró este mes, cuánto derivó",
                     pero se sigue moviendo hasta que la cohorte madura.
      * actividad -> negociaciones con Fecha de derivación en el período.
                     Responde "cuánto derivó el equipo este mes". Es el que
                     usamos de numerador por defecto, para que los tres hitos
                     de negociación se lean con el mismo criterio.
  - PRESUPUESTADOS: negociaciones con Fecha de Presupuestado en el período.
  - CIERRES: negociaciones con Fecha de cierre en el período. Son los clientes.

Además del funnel de actividad se calcula el FUNNEL DE INGRESADOS: se toman
los prospectos creados en el período y se los sigue hasta donde hayan llegado
hoy, sin importar en qué mes ocurrió cada hito. Responde una pregunta que el
otro funnel no puede responder —de lo que entró, cuánto terminó comprando—
a cambio de que la camada se sigue moviendo hasta que madura.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from . import stats
from .config import Config, RAIZ


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _dia(valor) -> str:
    """Normaliza cualquier fecha de Bitrix a 'YYYY-MM-DD'."""
    return (valor or "")[:10]


def _en_rango(valor, desde: str, hasta: str) -> bool:
    d = _dia(valor)
    return bool(d) and desde <= d <= hasta


def _div(num, den):
    """División que no explota: sin denominador no hay métrica, hay None."""
    return (num / den) if den else None


def _pct(num, den):
    v = _div(num, den)
    return round(v * 100, 1) if v is not None else None


def _monto_usd(crudo: str, cfg: Config) -> float:
    """El SPA guarda el monto como '123.45|USD'."""
    if not crudo:
        return 0.0
    monto, _, moneda = str(crudo).partition("|")
    try:
        valor = float(monto)
    except ValueError:
        return 0.0
    if moneda == "ARS":
        return valor / cfg["moneda"]["ars_por_usd"]
    return valor


def _mrr_usd(deal: dict, cfg: Config) -> float:
    try:
        valor = float(deal.get(cfg["funnel"]["mrr"]["campo"]) or 0)
    except (TypeError, ValueError):
        return 0.0
    if deal.get(cfg["funnel"]["mrr"]["campo_moneda"]) == "ARS":
        return valor / cfg["moneda"]["ars_por_usd"]
    return valor


def _dias_entre(desde_valor, hasta_valor) -> int | None:
    a, b = _dia(desde_valor), _dia(hasta_valor)
    if not a or not b:
        return None
    try:
        d = (date.fromisoformat(b) - date.fromisoformat(a)).days
    except ValueError:
        return None
    return d if d >= 0 else None


def cargar_gasto_meta(cfg: Config) -> dict[str, dict[str, float]]:
    """Gasto diario de Meta en dólares, ya separado por canal.

    Devuelve {fecha: {clave_de_canal: usd}}. Sale del conector de Meta y no
    del SPA porque el SPA guarda un solo monto por día para toda la cuenta:
    adentro de ese número no se puede distinguir awareness de performance.
    """
    import json
    conf = cfg["gasto"].get("meta_api") or {}
    ruta = RAIZ / conf.get("archivo", "")
    if not conf or not ruta.exists():
        return {}
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    tc = conf.get("cotizacion_ars_usd") or 1
    salida: dict[str, dict[str, float]] = {}
    for fecha, valores in doc.get("dias", {}).items():
        salida[fecha] = {
            canal: (valores.get(f"{grupo}_ars", 0.0) or 0.0) / tc
            for canal, grupo in conf.get("canales", {}).items()
        }
    return salida


def _promedio(valores: list[int]) -> float | None:
    """El promedio dice algo distinto que la mediana y por eso van los dos.

    La mediana describe el caso típico; el promedio incluye la cola de los
    casos que tardaron muchísimo. Cuando el promedio es varias veces la
    mediana, eso no es un defecto del número: es la señal de que hay un grupo
    de prospectos que quedaron olvidados y arrastran el total.
    """
    return round(sum(valores) / len(valores), 1) if valores else None


def _mediana(valores: list[int]) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    n = len(v)
    medio = n // 2
    return float(v[medio]) if n % 2 else round((v[medio - 1] + v[medio]) / 2, 1)


# --------------------------------------------------------------------------- #
# cálculo principal
# --------------------------------------------------------------------------- #
def calcular(snapshot: dict, cfg: Config, desde: str, hasta: str) -> dict:
    """Funnel del período, desagregado por canal más el total general."""
    f = cfg["funnel"]
    campo_deriv = f["derivado"]["campo_fecha_deal"]
    campo_presu = f["presupuestado"]["campo_fecha"]
    campo_cierre = f["cierre"]["campo_fecha"]
    campo_razon = f["no_derivacion"]["campo"]
    campo_cierre_lead = f["derivado"].get("campo_fecha_lead", "DATE_CLOSED")
    estados_no_deriv = f["no_derivacion"]["estados"]

    # fecha de creación del prospecto, para medir velocidad cuando hay vínculo
    creacion_lead = {l["ID"]: _dia(l.get("DATE_CREATE")) for l in snapshot["prospectos"]}

    filas: dict[str, dict] = defaultdict(lambda: {
        "prospectos": 0, "derivados_cohorte": 0, "descartados": 0,
        "presupuestados_cohorte": 0, "cierres_cohorte": 0,
        "mrr_cohorte_usd": 0.0, "_cohorte_con_deal": set(),
        "derivados": 0, "presupuestados": 0, "cierres": 0,
        "gasto_usd": 0.0, "mrr_cerrado_usd": 0.0, "mrr_presupuestado_usd": 0.0,
        "_dias_a_derivar": [], "_dias_a_cerrar": [], "_dias_lead_a_cierre": [],
        "razones": Counter(), "por_estado": Counter(), "no_derivados": 0, "no_calificados": 0,
        "_con_vinculo": 0, "_sin_vinculo": 0, "_convertidos_medidos": 0,
        "_dias_con_gasto": set(),
    })

    # --- prospectos ---------------------------------------------------------
    cohorte: dict[str, str] = {}
    for lead in snapshot["prospectos"]:
        if not _en_rango(lead.get("DATE_CREATE"), desde, hasta):
            continue
        canal = cfg.canal_de_origen(lead.get("SOURCE_ID"))
        cohorte[str(lead["ID"])] = canal
        fila = filas[canal]
        fila["prospectos"] += 1
        estado = lead.get("STATUS_ID")
        if estado == f["derivado"]["status_convertido"]:
            fila["derivados_cohorte"] += 1
        elif estado in estados_no_deriv:
            fila["descartados"] += 1
            fila["no_derivados"] += 1
            # "No calificado" es solo el descarte por calidad (Prospecto no
            # útil); el inactivo es otra cosa y no entra en esta tasa.
            if estado == "JUNK":
                fila["no_calificados"] += 1
            fila["por_estado"][estados_no_deriv[estado]] += 1
            razon = lead.get(campo_razon)
            fila["razones"][str(razon) if razon else "(sin razón cargada)"] += 1

    # --- velocidad de derivación, medida sobre el prospecto -----------------
    # De su fecha de creación a su fecha de conversión. Ambas viven en el mismo
    # registro, así que se mide el 100% de los convertidos del período y no hace
    # falta que la negociación tenga el prospecto vinculado.
    for lead in snapshot["prospectos"]:
        if lead.get("STATUS_ID") != f["derivado"]["status_convertido"]:
            continue
        cerrado = lead.get(campo_cierre_lead)
        if not _en_rango(cerrado, desde, hasta):
            continue
        fila = filas[cfg.canal_de_origen(lead.get("SOURCE_ID"))]
        fila["_convertidos_medidos"] += 1
        d = _dias_entre(lead.get("DATE_CREATE"), cerrado)
        if d is not None:
            fila["_dias_a_derivar"].append(d)

    # --- hitos de negociación ----------------------------------------------
    for deal in snapshot["negociaciones"]:
        canal = cfg.canal_de_origen(deal.get("SOURCE_ID"))
        fila = filas[canal]
        # Solo se mide velocidad desde el prospecto cuando la negociación está
        # vinculada a uno. Sin vínculo, la fecha más temprana disponible es la
        # creación de la propia negociación, que en el 80% de los casos coincide
        # con la derivación: meterla en la mediana la aplasta contra cero.
        origen_fecha = creacion_lead.get(deal.get("LEAD_ID"))

        # Funnel de ingresados: la negociación cuenta para el canal del
        # PROSPECTO que la originó, y su hito cuenta sin importar la fecha.
        # Preguntamos hasta dónde llegó esta camada, no qué pasó este mes.
        canal_cohorte = cohorte.get(str(deal.get("LEAD_ID") or ""))
        if canal_cohorte:
            coh = filas[canal_cohorte]
            coh["_cohorte_con_deal"].add(str(deal["LEAD_ID"]))
            if _dia(deal.get(campo_presu)):
                coh["presupuestados_cohorte"] += 1
            if _dia(deal.get(campo_cierre)):
                coh["cierres_cohorte"] += 1
                coh["mrr_cohorte_usd"] += _mrr_usd(deal, cfg)

        if _en_rango(deal.get(campo_deriv), desde, hasta):
            fila["derivados"] += 1
            fila["_con_vinculo" if origen_fecha else "_sin_vinculo"] += 1

        if _en_rango(deal.get(campo_presu), desde, hasta):
            fila["presupuestados"] += 1
            fila["mrr_presupuestado_usd"] += _mrr_usd(deal, cfg)

        if _en_rango(deal.get(campo_cierre), desde, hasta):
            fila["cierres"] += 1
            fila["mrr_cerrado_usd"] += _mrr_usd(deal, cfg)
            d = _dias_entre(deal.get(campo_deriv), deal.get(campo_cierre))
            if d is not None:
                fila["_dias_a_cerrar"].append(d)
            if origen_fecha:
                d = _dias_entre(origen_fecha, deal.get(campo_cierre))
                if d is not None:
                    fila["_dias_lead_a_cierre"].append(d)

    # --- gasto --------------------------------------------------------------
    g = cfg["gasto"]
    conf_meta = g.get("meta_api") or {}
    espejo = conf_meta.get("tipo_gasto_espejo")
    overhead = 0.0

    # Meta y Redes Sociales: de la API, día por día.
    for fecha, por_canal in cargar_gasto_meta(cfg).items():
        if not (desde <= fecha <= hasta):
            continue
        for canal, monto in por_canal.items():
            if monto <= 0:
                continue
            filas[canal]["gasto_usd"] += monto
            filas[canal]["_dias_con_gasto"].add(fecha)
    for item in snapshot["gastos"]:
        if not _en_rango(item.get(g["campo_fecha"]), desde, hasta):
            continue
        monto = _monto_usd(item.get(g["campo_monto"]), cfg)
        if cfg.es_overhead(item.get(g["campo_tipo"])):
            overhead += monto
            continue
        # Lo cargado en el SPA para Meta es el espejo de lo que ya trajimos de
        # la API: sumarlo sería contar el mismo gasto dos veces.
        try:
            if espejo is not None and int(item.get(g["campo_tipo"])) == int(espejo):
                continue
        except (TypeError, ValueError):
            pass
        canal = cfg.canal_de_tipo_gasto(item.get(g["campo_tipo"]))
        if not canal:
            continue
        dia = _dia(item.get(g["campo_fecha"]))
        filas[canal]["gasto_usd"] += monto
        filas[canal]["_dias_con_gasto"].add(dia)

    # --- derivar métricas ---------------------------------------------------
    dias_periodo = max(_dias_entre(desde, hasta) or 0, 0) + 1
    resultado = {"periodo": {"desde": desde, "hasta": hasta}, "canales": {}, "overhead_usd": round(overhead, 2)}
    for clave, fila in filas.items():
        resultado["canales"][clave] = _cerrar_fila(clave, fila, cfg, dias_periodo)

    total = _sumar(filas.values())
    total["gasto_usd"] += overhead * 0  # el overhead no entra en el CAC por canal
    resultado["general"] = _cerrar_fila("general", total, cfg, dias_periodo)
    resultado["general"]["cac_full_usd"] = round(
        v, 2) if (v := _div(total["gasto_usd"] + overhead, total["cierres"])) else None
    return resultado


def _sumar(filas) -> dict:
    total = {
        "prospectos": 0, "derivados_cohorte": 0, "descartados": 0, "derivados": 0,
        "presupuestados_cohorte": 0, "cierres_cohorte": 0,
        "mrr_cohorte_usd": 0.0, "_cohorte_con_deal": set(),
        "presupuestados": 0, "cierres": 0, "gasto_usd": 0.0,
        "mrr_cerrado_usd": 0.0, "mrr_presupuestado_usd": 0.0,
        "_dias_a_derivar": [], "_dias_a_cerrar": [], "_dias_lead_a_cierre": [],
        "razones": Counter(), "por_estado": Counter(), "no_derivados": 0, "no_calificados": 0,
        "_con_vinculo": 0, "_sin_vinculo": 0, "_convertidos_medidos": 0,
        "_dias_con_gasto": set(),
    }
    for fila in filas:
        for k, v in fila.items():
            if isinstance(v, set):
                total[k].update(v)
            elif isinstance(v, Counter):
                total[k].update(v)
            elif isinstance(v, list):
                total[k].extend(v)
            else:
                total[k] += v
    return total


def _cerrar_fila(clave: str, fila: dict, cfg: Config, dias_periodo: int = 0) -> dict:
    p, der, pre, cie = fila["prospectos"], fila["derivados"], fila["presupuestados"], fila["cierres"]
    gasto = round(fila["gasto_usd"], 2)

    # Qué proporción de los días del período tiene gasto cargado en el SPA.
    # Un mes con la carga a medias produce un CPL y un CAC artificialmente
    # buenos: hay que poder distinguir "salió barato" de "falta cargar".
    cobertura = round(len(fila["_dias_con_gasto"]) / dias_periodo, 2) if dias_periodo else None
    return {
        "cobertura_gasto": cobertura,
        "dias_con_gasto": len(fila["_dias_con_gasto"]),
        "dias_periodo": dias_periodo,
        "canal": clave,
        "nombre": "General" if clave == "general" else cfg.nombre_canal(clave),
        "gasto_usd": gasto,
        "prospectos": p,
        "derivados": der,
        "derivados_cohorte": fila["derivados_cohorte"],
        "descartados": fila["descartados"],
        "presupuestados": pre,
        "cierres": cie,
        # funnel de ingresados: la misma camada seguida hasta hoy
        "presupuestados_cohorte": fila["presupuestados_cohorte"],
        "cierres_cohorte": fila["cierres_cohorte"],
        "mrr_cohorte_usd": round(fila["mrr_cohorte_usd"], 2),
        "pct_conversion_cohorte": _pct(fila["cierres_cohorte"], p),
        "pct_cohorte_derivado_a_presupuestado": _pct(
            fila["presupuestados_cohorte"], fila["derivados_cohorte"]),
        "pct_cohorte_presupuestado_a_cierre": _pct(
            fila["cierres_cohorte"], fila["presupuestados_cohorte"]),
        # Qué proporción de los derivados de la camada tiene su negociación
        # vinculada al prospecto. Sin vínculo no hay forma de seguirlo, así
        # que esto es el techo de lo que el funnel de ingresados puede ver.
        "cohorte_vinculada": round(
            len(fila["_cohorte_con_deal"]) / fila["derivados_cohorte"], 2)
            if fila["derivados_cohorte"] else None,
        "cohorte_con_deal": len(fila["_cohorte_con_deal"]),
        # las cuatro métricas pedidas
        "cpl_usd": round(v, 2) if (v := _div(gasto, p)) else None,
        "cac_usd": round(v, 2) if (v := _div(gasto, cie)) else None,
        "pct_conversion": _pct(cie, p),
        # Rango en el que está de verdad la conversión de este canal. Con pocos
        # eventos el porcentaje observado es una foto movida; esto dice cuánto.
        "ic_conversion": [round(v * 100, 1) if v is not None else None
                          for v in stats.wilson(cie, p)],
        "piso_conversion": round(v * 100, 2) if (v := stats.piso_confiable(cie, p)) is not None else None,
        "pct_derivacion": _pct(der, p),
        # lectura paso a paso: dónde se rompe realmente el funnel
        "pct_presupuestado": _pct(pre, p),
        "pct_derivado_a_presupuestado": _pct(pre, der),
        "pct_presupuestado_a_cierre": _pct(cie, pre),
        "pct_derivacion_cohorte": _pct(fila["derivados_cohorte"], p),
        # costos intermedios: el CPL barato que no deriva se ve acá
        "costo_por_derivado_usd": round(v, 2) if (v := _div(gasto, der)) else None,
        "costo_por_presupuesto_usd": round(v, 2) if (v := _div(gasto, pre)) else None,
        # plata
        "mrr_cerrado_usd": round(fila["mrr_cerrado_usd"], 2),
        "mrr_presupuestado_usd": round(fila["mrr_presupuestado_usd"], 2),
        "ticket_promedio_usd": round(v, 2) if (v := _div(fila["mrr_cerrado_usd"], cie)) else None,
        "payback_meses": round(v, 1) if (v := _div(gasto, fila["mrr_cerrado_usd"])) else None,
        # velocidad
        "dias_a_derivar_mediana": _mediana(fila["_dias_a_derivar"]),
        "dias_a_derivar_promedio": _promedio(fila["_dias_a_derivar"]),
        "dias_a_derivar_n": len(fila["_dias_a_derivar"]),
        "dias_a_cerrar_mediana": _mediana(fila["_dias_a_cerrar"]),
        "dias_a_cerrar_promedio": _promedio(fila["_dias_a_cerrar"]),
        "dias_a_cerrar_n": len(fila["_dias_a_cerrar"]),
        "dias_lead_a_cierre_mediana": _mediana(fila["_dias_lead_a_cierre"]),
        "dias_lead_a_cierre_promedio": _promedio(fila["_dias_lead_a_cierre"]),
        "dias_lead_a_cierre_n": len(fila["_dias_lead_a_cierre"]),
        "no_derivados": fila["no_derivados"],
        "no_calificados": fila["no_calificados"],
        "pct_no_calificacion": _pct(fila["no_calificados"], p),
        # Lista y no diccionario: los IDs de razón son numéricos y JavaScript
        # reordena las claves enteras de un objeto, perdiendo el orden por
        # frecuencia que es justamente lo que hay que mostrar.
        "razones": [[clave, n] for clave, n in fila["razones"].most_common()],
        "no_derivacion_por_estado": dict(fila["por_estado"]),
        # Qué proporción de las derivaciones se pudo medir de punta a punta.
        "cobertura_velocidad": round(
            fila["_con_vinculo"] / (fila["_con_vinculo"] + fila["_sin_vinculo"]), 2)
            if (fila["_con_vinculo"] + fila["_sin_vinculo"]) else None,
        "convertidos_medidos": fila["_convertidos_medidos"],
        "derivaciones_medidas": fila["_con_vinculo"],
        "derivaciones_sin_vinculo": fila["_sin_vinculo"],
    }


# --------------------------------------------------------------------------- #
# series temporales
# --------------------------------------------------------------------------- #
def meses(desde: str, hasta: str) -> list[tuple[str, str, str]]:
    """[(etiqueta, desde, hasta)] por mes calendario."""
    salida = []
    cursor = date.fromisoformat(desde).replace(day=1)
    fin = date.fromisoformat(hasta)
    while cursor <= fin:
        siguiente = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        ultimo = min(siguiente - timedelta(days=1), fin)
        salida.append((cursor.strftime("%Y-%m"), cursor.isoformat(), ultimo.isoformat()))
        cursor = siguiente
    return salida


def semanas(desde: str, hasta: str) -> list[tuple[str, str, str]]:
    """[(etiqueta, desde, hasta)] por semana ISO (lunes a domingo)."""
    salida = []
    fin = date.fromisoformat(hasta)
    cursor = date.fromisoformat(desde)
    cursor -= timedelta(days=cursor.weekday())
    while cursor <= fin:
        ultimo = min(cursor + timedelta(days=6), fin)
        salida.append((cursor.isoformat(), cursor.isoformat(), ultimo.isoformat()))
        cursor += timedelta(days=7)
    return salida


def mejor_canal(resultado: dict, n_minimo: int = 15) -> dict | None:
    """El mejor canal, sin dejarse engañar por los canales chicos.

    El % de conversión ya es el producto de todos los pases del funnel, así
    que sigue siendo el criterio. Lo que cambia es que NO se ordena por el
    porcentaje observado sino por su piso de confianza: la tasa que el canal
    sostiene incluso siendo pesimistas. Un canal con 1 cierre sobre 17
    prospectos muestra 5,9% pero su piso es 1,0%; uno con 2 sobre 45 muestra
    4,4% con un piso de 1,2%. El segundo es la apuesta más firme aunque su
    número se vea peor, y esa es exactamente la trampa que hay que evitar.

    Además devuelve contra quiénes la ventaja es concluyente (los rangos no
    se superponen) y contra quiénes todavía no, para poder decirlo en vez de
    presentar un ganador como si estuviera decidido.
    """
    # "Sin atribuir" no es un canal sino los prospectos cuyo origen no mapea a
    # ninguno: no se puede invertir en él ni compararlo con los demás.
    candidatos = [
        (clave, fila) for clave, fila in resultado["canales"].items()
        if clave != "sin_atribuir"
        and fila["prospectos"] >= n_minimo
        and fila["piso_conversion"] is not None
    ]
    if not candidatos:
        return None

    clave, fila = max(candidatos, key=lambda kv: (kv[1]["piso_conversion"],
                                                  kv[1]["pct_conversion"] or 0))
    lider = (fila["cierres"], fila["prospectos"])

    concluyente, empatados = [], []
    for otra_clave, otra in candidatos:
        if otra_clave == clave:
            continue
        rival = (otra["cierres"], otra["prospectos"])
        (concluyente if stats.distinguibles(lider, rival) else empatados).append(otra_clave)

    # ¿Cuánto volumen haría falta para desempatar con el rival más cercano?
    falta = None
    if empatados:
        cercano = max((c for c in empatados),
                      key=lambda c: resultado["canales"][c]["pct_conversion"] or 0)
        rival = resultado["canales"][cercano]
        falta = {
            "canal": cercano,
            "prospectos": stats.n_necesario(
                (rival["pct_conversion"] or 0) / 100, (fila["pct_conversion"] or 0) / 100),
        }

    return {
        "canal": clave,
        "pct_conversion": fila["pct_conversion"],
        "ic": fila["ic_conversion"],
        "prospectos": fila["prospectos"],
        "cierres": fila["cierres"],
        "concluyente": concluyente,
        "empatados": empatados,
        "para_desempatar": falta,
        "n_minimo": n_minimo,
    }


def trimestres(desde: str, hasta: str) -> list[tuple[str, str, str]]:
    """[(etiqueta, desde, hasta)] por trimestre calendario."""
    salida = []
    ini = date.fromisoformat(desde)
    fin = date.fromisoformat(hasta)
    cursor = date(ini.year, (ini.month - 1) // 3 * 3 + 1, 1)
    while cursor <= fin:
        mes_fin = cursor.month + 2
        siguiente = date(cursor.year + (mes_fin >= 12), (mes_fin % 12) + 1, 1)
        ultimo = min(siguiente - timedelta(days=1), fin)
        salida.append((f"{cursor.year}-Q{(cursor.month - 1) // 3 + 1}", cursor.isoformat(), ultimo.isoformat()))
        cursor = siguiente
    return salida


def serie_rango(snapshot: dict, cfg: Config, desde: str, hasta: str,
                granularidad: str = "semana") -> list[dict]:
    """Serie acotada a un rango: se usa para ver el detalle dentro de un Q."""
    tramos = semanas(desde, hasta) if granularidad == "semana" else meses(desde, hasta)
    tope = snapshot["ventana"]["hasta"]
    # Se corta en el último tramo completo. Una semana de dos días tiene los
    # prospectos de dos días pero las derivaciones de negociaciones viejas:
    # da ratios de 300% y arruina la escala de todo el gráfico.
    # semanas() ya recorta el último tramo contra `hasta`, así que su fecha de
    # fin no delata que está truncado: hay que comparar contra la duración real.
    def entero(t):
        largo = 7 if granularidad == "semana" else 28
        return (date.fromisoformat(t[1]) + timedelta(days=largo - 1)).isoformat() <= tope

    completos = [t for t in tramos if entero(t)]
    if not completos:
        completos = [(tramos[0][0], tramos[0][1], min(tramos[0][2], tope))] if tramos else []
    salida = []
    for etiqueta, ini, fin in completos:
        punto = calcular(snapshot, cfg, ini, fin)
        punto["etiqueta"] = etiqueta
        punto["parcial"] = False
        salida.append(punto)
    return salida


def serie(snapshot: dict, cfg: Config, granularidad: str = "mes") -> list[dict]:
    desde = snapshot["ventana"]["desde"]
    hasta = snapshot["ventana"]["hasta"]
    tramos = meses(desde, hasta) if granularidad == "mes" else semanas(desde, hasta)
    salida = []
    for etiqueta, ini, fin in tramos:
        punto = calcular(snapshot, cfg, ini, fin)
        punto["etiqueta"] = etiqueta
        punto["parcial"] = fin >= hasta      # el último tramo está incompleto
        salida.append(punto)
    return salida
