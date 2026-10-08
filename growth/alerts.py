"""Alertas de growth: la alarma diaria y el informe semanal.

Dos cadencias con propósitos distintos, y la diferencia es deliberada:

  DIARIA  — es una alarma. Solo habla si algo se rompió. Todas sus reglas son
            estados binarios o umbrales absolutos, nunca tasas: con ~7
            prospectos por día, cualquier porcentaje diario es ruido. El
            objetivo de diseño es que casi siempre no diga nada.

  SEMANAL — es un informe. Llega siempre, haya o no alertas, porque es la
            lectura del estado del funnel. Compara contra las DOS semanas
            anteriores: con una sola no se distingue un rebote de una
            tendencia.
"""
from __future__ import annotations
import collections
import json
from datetime import date, timedelta

from .config import Config, RAIZ
from .health import revisar
from .metrics import calcular, _dia, _en_rango


# --------------------------------------------------------------------------- #
# utilidades de calendario
# --------------------------------------------------------------------------- #
def ultima_semana_completa(hasta: str) -> tuple[date, date]:
    """Lunes a domingo de la última semana cerrada antes de `hasta`."""
    hoy = date.fromisoformat(hasta)
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    fin = lunes_actual - timedelta(days=1)
    return fin - timedelta(days=6), fin


def semanas_hacia_atras(hasta: str, n: int) -> list[tuple[date, date]]:
    """[(lunes, domingo)] de las últimas n semanas completas, de vieja a nueva."""
    ini, fin = ultima_semana_completa(hasta)
    return [(ini - timedelta(days=7 * i), fin - timedelta(days=7 * i)) for i in range(n - 1, -1, -1)]


# --------------------------------------------------------------------------- #
# ALARMA DIARIA
# --------------------------------------------------------------------------- #
def diarias(snapshot: dict, cfg: Config, hasta: str | None = None) -> list[dict]:
    hasta = hasta or snapshot["ventana"]["hasta"]
    hoy = date.fromisoformat(hasta)
    # El día de referencia es AYER: el día en curso todavía no terminó y
    # siempre parecería una caída.
    ayer = hoy - timedelta(days=1)
    reglas = {r["regla"]: r for r in cfg["alertas"]["diarias"]}
    salida: list[dict] = []

    def agregar(regla, titulo, detalle, accion):
        salida.append({"regla": regla, "titulo": titulo, "detalle": detalle,
                       "accion": accion, "severidad": reglas.get(regla, {}).get("severidad", "media")})

    # prospectos por día y canal
    por_dia: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for lead in snapshot["prospectos"]:
        f = _dia(lead.get("DATE_CREATE"))
        if f:
            por_dia[f][cfg.canal_de_origen(lead.get("SOURCE_ID"))] += 1
            por_dia[f]["_total"] += 1

    # 1. ningún prospecto en todo el día
    if "sin_prospectos" in reglas and por_dia.get(ayer.isoformat(), collections.Counter())["_total"] == 0:
        agregar("sin_prospectos", "No entró ningún prospecto ayer",
                f"{ayer.isoformat()} cerró con 0 prospectos de todos los canales.",
                "Revisar formularios, Hyperflow y la integración con Bitrix.")

    # 2. un canal callado varios días seguidos (una regla por canal)
    for r in cfg["alertas"]["diarias"]:
        if r["regla"] != "canal_mudo":
            continue
        canal = r["canal"]
        dias = [(ayer - timedelta(days=i)).isoformat() for i in range(r["dias"])]
        if all(por_dia.get(d, collections.Counter())[canal] == 0 for d in dias):
            tramo = "ayer" if r["dias"] == 1 else f"{r['dias']} días seguidos"
            rango = dias[0] if r["dias"] == 1 else f"entre {dias[-1]} y {dias[0]}"
            salida.append({"regla": "canal_mudo", "severidad": r.get("severidad", "media"),
                           "titulo": f"{cfg.nombre_canal(canal)} sin prospectos {tramo}",
                           "detalle": f"Sin un solo prospecto {rango}.",
                           "accion": "Revisar si la campaña está activa y si el formulario sigue enviando a Bitrix."})

    # 3. inversión sin cargar en el SPA, Meta y Google en una sola alerta
    r = reglas.get("spa_sin_cargar")
    if r:
        g = cfg["gasto"]
        atrasados = []
        for canal, tipo in r["tipos"].items():
            fechas = [_dia(i.get(g["campo_fecha"])) for i in snapshot["gastos"]
                      if str(i.get(g["campo_tipo"])) == str(tipo) and _dia(i.get(g["campo_fecha"]))]
            ultimo = max(fechas) if fechas else None
            atraso = (ayer - date.fromisoformat(ultimo)).days if ultimo else None
            if atraso is None or atraso > r["dias"]:
                atrasados.append(f"{cfg.nombre_canal(canal)}: " +
                                 (f"último día cargado {ultimo} ({atraso} días de atraso)" if ultimo
                                  else "sin ningún día cargado"))
        if atrasados:
            agregar("spa_sin_cargar", f"La inversión del SPA tiene más de {r['dias']} días sin cargar",
                    " · ".join(atrasados) + ". Mientras falte, el CPL y el CAC salen más baratos de lo real.",
                    "Correr la carga de inversión (skill boxer-carga-inversion) con el export de Google Ads.")

    # 5 y 6. calidad de la atribución, el mismo día en que se rompe
    de_ayer = [l for l in snapshot["prospectos"] if _dia(l.get("DATE_CREATE")) == ayer.isoformat()]
    if "prospecto_sin_origen" in reglas:
        sin_origen = [l for l in de_ayer if not l.get("SOURCE_ID")]
        if sin_origen:
            agregar("prospecto_sin_origen", f"{len(sin_origen)} prospectos entraron sin origen",
                    "Sin origen no entran en ningún CPL ni en ningún porcentaje por canal.",
                    "Cargarles el origen hoy, mientras se sabe de dónde vinieron.")
    if "origen_sin_mapear" in reglas:
        conocidos = {str(o) for c in cfg.canales.values() for o in c["origenes"]}
        conocidos |= {str(o) for o in cfg["origenes_sin_atribuir"]}
        nuevos = collections.Counter(str(l.get("SOURCE_ID")) for l in de_ayer
                                     if l.get("SOURCE_ID") and str(l.get("SOURCE_ID")) not in conocidos)
        for sid, n in nuevos.items():
            nombre = snapshot.get("catalogo_origenes", {}).get(sid, sid)
            agregar("origen_sin_mapear", f"Origen sin mapear: {nombre}",
                    f"{n} prospectos ayer con un origen que no pertenece a ningún canal.",
                    "Asignarlo a un canal en config/definitions.yaml.")

    # 7. un número del Monitor de Growth pasó a rojo
    if "monitor_desmejora" in reglas:
        for a in _desmejoras_nuevas(snapshot, cfg, hasta):
            agregar("monitor_desmejora", a["titulo"], a["detalle"], a["accion"])

    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(salida, key=lambda a: orden.get(a["severidad"], 9))


SOLAPA_DESMEJORA = {
    "generados": "Mirar Generación en el Monitor: qué canal cayó.",
    "cpl": "Mirar Generación en el Monitor: costo por lead por canal.",
    "pct_no_calificacion": "Mirar Funnel general en el Monitor: canal y razón principal de los no útiles.",
    "pct_inactivo": "Mirar Funnel general en el Monitor: razones y canal de los inactivos.",
    "derivados": "Mirar Derivación en el Monitor: por canal y por asesor.",
    "presupuestados": "Mirar Ventas en el Monitor: presupuestos por asesor.",
    "cerrados": "Mirar Ventas en el Monitor: cierres por asesor y cartera a futuro sin agenda.",
    "mrr": "Mirar Ventas en el Monitor: cierres y MRR por asesor.",
    "win_rate": "Mirar Funnel general en el Monitor.",
    "cac": "Mirar Funnel general en el Monitor: CAC por canal.",
    "dias_cierre": "Mirar Ventas en el Monitor: tiempo de cierre por asesor.",
}


def _snapshot_anterior(hasta: str) -> dict | None:
    from .config import DIR_SNAPSHOTS
    previos = sorted(p for p in DIR_SNAPSHOTS.glob("*.json") if p.stem < hasta)
    from .ingest import cargar
    return cargar(previos[-1]) if previos else None


def _desmejoras_nuevas(snapshot: dict, cfg: Config, hasta: str) -> list[dict]:
    """Los números del Monitor que HOY están en desmejora y en el snapshot
    anterior no lo estaban.

    Avisa el día del cambio y nada más: si un número sigue en rojo una semana,
    la alarma no lo repite todos los días (la tarjeta del Monitor sí lo sigue
    mostrando). Si el snapshot anterior es de otro Q, cuenta como que antes no
    había nada en rojo.
    """
    from . import monitor
    from .slack import _num
    hoy = monitor.estado_actual(snapshot, cfg)
    if not hoy.get("metricas"):
        return []
    antes_rojo = set()
    anterior = _snapshot_anterior(hasta)
    if anterior:
        ayer = monitor.estado_actual(anterior, cfg)
        if ayer.get("etiqueta") == hoy["etiqueta"]:
            antes_rojo = {k for k, v in ayer["metricas"].items() if v["estado"] == "desmejora"}
    q = hoy["etiqueta"][5:] + " " + hoy["etiqueta"][:4]
    qp = hoy["previo"]["etiqueta"] if hoy.get("previo") else ""
    qp = qp[5:] + " " + qp[:4] if qp else "el Q anterior"
    salida = []
    for clave, m in hoy["metricas"].items():
        if m["estado"] != "desmejora" or clave in antes_rojo:
            continue
        fmt = lambda v: _num("pct_" if clave.startswith(("pct", "win")) else
                             ("x_usd" if clave in ("cpl", "cac", "mrr") else ""), v)
        cambio = (f"{m['delta_pp']:+.1f} pp".replace(".", ",") if m["delta_pp"] is not None
                  else f"{m['delta_pct']:+.0f}%")
        if clave == "dias_cierre":
            fmt = lambda v: f"{v:.0f} días".replace(".", ",")
        salida.append({
            "titulo": f"{m['nombre']} en desmejora: {cambio}",
            "detalle": (f"{q} a {hoy['tramo']['dias']} días: {fmt(m['actual'])}, contra "
                        f"{fmt(m['previo'])} en el mismo tramo de {qp}."),
            "accion": SOLAPA_DESMEJORA.get(clave, "Mirar el Monitor de Growth."),
        })
    return salida


# --------------------------------------------------------------------------- #
# INFORME SEMANAL
# --------------------------------------------------------------------------- #
ETIQUETAS = {
    "prospectos": "Prospectos generados",
    "cpl_usd": "CPL",
    "pct_derivacion": "% de derivación",
    "costo_por_derivado_usd": "Costo por derivado",
    "pct_no_calificacion": "% de no calificación",
    "presupuestados": "Presupuestados",
    "cierres": "Clientes nuevos",
}
# Para cada métrica, si subir es bueno. None = es solo contexto, sin juicio.
SUBIR_ES_BUENO = {
    "prospectos": True, "cpl_usd": False, "pct_derivacion": True,
    "costo_por_derivado_usd": False, "pct_no_calificacion": False,
    "presupuestados": True,
    # Los cierres van a la tabla como contexto pero sin juicio: con 1 a 4 por
    # semana, pasar de 4 a 1 no distingue un problema de la suerte. Su lectura
    # es mensual, donde el número tiene con qué sostenerse.
    "cierres": None,
}
ES_PORCENTAJE = {"pct_derivacion", "pct_no_calificacion"}


def _direccion(clave: str, actual, previo) -> str:
    """mejora / empeora / estable, ya interpretado según qué conviene."""
    if actual is None or previo is None or previo == 0:
        return "sin_base"
    if clave in ES_PORCENTAJE:
        delta = actual - previo
        if abs(delta) < 2:                       # menos de 2 pp no es un movimiento
            return "estable"
        sube = delta > 0
    else:
        delta = (actual - previo) / abs(previo) * 100
        if abs(delta) < 10:                      # menos de 10% es ruido semanal
            return "estable"
        sube = delta > 0
    bueno = SUBIR_ES_BUENO.get(clave)
    if bueno is None:
        return "estable"
    return "mejora" if sube == bueno else "empeora"


def _contribucion(clave: str, actual: dict, previo: dict, cfg: Config) -> tuple[str, str] | None:
    """Qué canal explica mejor el cambio de una métrica general.

    Para los conteos alcanza con la diferencia por canal. Para las tasas se usa
    un contrafáctico: se recalcula el agregado dejando a ese canal como estaba
    la semana anterior; el canal cuyo congelamiento más acerca el resultado al
    valor previo es el que explica el movimiento.
    """
    canales = [c for c in cfg.canales_activos if c in actual["canales"] or c in previo["canales"]]
    if not canales:
        return None

    if clave in ("prospectos", "presupuestados", "cierres"):
        deltas = [(c, (actual["canales"].get(c, {}).get(clave, 0) or 0)
                   - (previo["canales"].get(c, {}).get(clave, 0) or 0)) for c in canales]
        clave_canal, delta = max(deltas, key=lambda x: abs(x[1]))
        if delta == 0:
            return None
        signo = "+" if delta > 0 else ""
        return clave_canal, f"{signo}{delta:g} prospectos" if clave == "prospectos" else f"{signo}{delta:g}"

    if clave in ("cpl_usd", "costo_por_derivado_usd"):
        divisor = "prospectos" if clave == "cpl_usd" else "derivados"
        def agregado(congelar: str | None):
            gasto = suma = 0.0
            for c in canales:
                fuente = previo if c == congelar else actual
                fila = fuente["canales"].get(c, {})
                gasto += fila.get("gasto_usd", 0) or 0
                suma += fila.get(divisor, 0) or 0
            return (gasto / suma) if suma else None
        base, objetivo = agregado(None), None
        objetivo = actual["general"].get(clave)
        if base is None:
            return None
        mejor, mejor_dif = None, 0.0
        for c in canales:
            alt = agregado(c)
            if alt is None:
                continue
            dif = abs(base - alt)
            if dif > mejor_dif:
                mejor, mejor_dif = c, dif
        if not mejor:
            return None
        antes = previo["canales"].get(mejor, {}).get(clave)
        ahora = actual["canales"].get(mejor, {}).get(clave)
        if antes is None or ahora is None:
            return None
        fmt = lambda v: f"${v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
        return mejor, f"{fmt(antes)} → {fmt(ahora)}"

    # tasas del funnel: el canal cuyo porcentaje más se movió, con peso suficiente
    candidatos = []
    for c in canales:
        fa, fb = actual["canales"].get(c, {}), previo["canales"].get(c, {})
        va, vb = fa.get(clave), fb.get(clave)
        if va is None or vb is None:
            continue
        if (fa.get("prospectos", 0) or 0) < cfg["alertas"]["n_minimo_para_alertar"]:
            continue
        candidatos.append((c, va - vb, vb, va))
    if not candidatos:
        return None
    c, delta, vb, va = max(candidatos, key=lambda x: abs(x[1]))
    return c, f"{vb:.1f}% → {va:.1f}%".replace(".", ",")


def informe_semanal(snapshot: dict, cfg: Config, hasta: str | None = None) -> dict:
    hasta = hasta or snapshot["ventana"]["hasta"]
    conf = cfg["alertas"]["informe_semanal"]
    n = conf["semanas_de_referencia"] + 1
    rangos = semanas_hacia_atras(hasta, n)
    puntos = [calcular(snapshot, cfg, a.isoformat(), b.isoformat()) for a, b in rangos]
    actual, previo = puntos[-1], puntos[-2]

    filas = []
    for clave in conf["metricas"]:
        valores = [p["general"].get(clave) for p in puntos]
        direccion = _direccion(clave, valores[-1], valores[-2])
        # Sostenida = se movió igual en las dos comparaciones. Es lo que
        # distingue una tendencia de un rebote.
        anterior = _direccion(clave, valores[-2], valores[-3]) if len(valores) > 2 else "sin_base"
        fila = {
            "metrica": clave, "nombre": ETIQUETAS.get(clave, clave),
            "valores": valores, "direccion": direccion,
            "sostenida": direccion == anterior and direccion in ("mejora", "empeora"),
            "es_porcentaje": clave in ES_PORCENTAJE,
        }
        if direccion in ("mejora", "empeora"):
            resp = _contribucion(clave, actual, previo, cfg)
            if resp:
                fila["canal"] = cfg.nombre_canal(resp[0])
                fila["canal_detalle"] = resp[1]
        filas.append(fila)

    mejoran = [f for f in filas if f["direccion"] == "mejora"]
    empeoran = [f for f in filas if f["direccion"] == "empeora"]
    if len(empeoran) > len(mejoran):
        estado = "empeora"
    elif len(mejoran) > len(empeoran):
        estado = "mejora"
    else:
        estado = "estable"

    return {
        "semana": {"desde": rangos[-1][0].isoformat(), "hasta": rangos[-1][1].isoformat()},
        "referencia": [{"desde": a.isoformat(), "hasta": b.isoformat()} for a, b in rangos[:-1]],
        "estado": estado,
        "filas": filas,
        "mejoran": len(mejoran), "empeoran": len(empeoran),
        "alertas": _alertas_semanales(snapshot, cfg, puntos, rangos, hasta),
        "salud": revisar(snapshot, cfg, rangos[-1][0].isoformat(), hasta),
    }


def _alertas_semanales(snapshot, cfg, puntos, rangos, hasta) -> list[dict]:
    """Las reglas con umbral, evaluadas sobre su propia ventana."""
    from .anomalies import detectar
    salida = [a for a in detectar(snapshot, cfg, hasta)]

    # % de no calificación: sostenido por encima de la referencia, o un salto.
    regla = next((r for r in cfg["alertas"]["semanales"]
                  if r["metrica"] == "pct_no_calificacion"), None)
    if regla:
        valores = [p["general"].get("pct_no_calificacion") for p in puntos]
        ultimos = [v for v in valores[-regla["semanas_seguidas"]:] if v is not None]
        actual = valores[-1]
        motivo = None
        if actual is not None and actual >= regla["umbral_salto"]:
            motivo = f"saltó a {actual:.1f}% en la semana"
        elif (len(ultimos) == regla["semanas_seguidas"]
              and all(v > regla["umbral_referencia"] for v in ultimos)):
            motivo = (f"lleva {regla['semanas_seguidas']} semanas por encima del "
                      f"{regla['umbral_referencia']}%: " + ", ".join(f"{v:.1f}%" for v in ultimos))
        if motivo:
            salida.append({
                "metrica": "pct_no_calificacion", "titulo": "% de no calificación",
                "ambito": "General", "severidad": regla["severidad"], "direccion": "sube",
                "valor_actual": actual, "valor_previo": valores[-2],
                "variacion": motivo, "ventana": "semana",
                "desde": rangos[-1][0].isoformat(), "hasta": rangos[-1][1].isoformat(),
                "base_desde": rangos[-2][0].isoformat(), "base_hasta": rangos[-2][1].isoformat(),
                "crudo_actual": "", "crudo_previo": "", "n": None,
            })
    return salida
