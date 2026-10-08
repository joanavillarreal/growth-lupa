"""Detección de anomalías de la última semana.

Dos decisiones que evitan que esto se vuelva ruido:
  1. Nunca se alerta por debajo de `n_minimo_para_alertar`. Con 12 cierres por
     mes, una caída del 50% semanal en conversión puede ser un solo negocio.
  2. El CAC y las conversiones se comparan a 28 días corridos, no a 7:
     el ciclo mediano hasta el cierre ronda los 70 días y una semana no alcanza
     para que un cierre aparezca.
"""
from __future__ import annotations
from datetime import date, timedelta

from .config import Config
from .health import revisar
from .metrics import calcular

ETIQUETAS = {
    "cpl": "CPL", "cac": "CAC", "prospectos": "Generación de prospectos",
    "pct_derivacion": "% de derivación", "pct_presupuestado": "% de presupuestados",
    "pct_conversion": "% de conversión", "costo_por_derivado": "costo por derivado",
}
CLAVE_METRICA = {"cpl": "cpl_usd", "cac": "cac_usd", "prospectos": "prospectos",
                 "costo_por_derivado": "costo_por_derivado_usd"}

# Sobre qué se calcula cada métrica. Define cuál es el n que hay que exigir
# antes de alertar: al CAC no lo protege tener muchos prospectos, lo protege
# tener suficientes cierres.
BASE = {
    "cpl": "prospectos", "prospectos": "prospectos",
    "pct_derivacion": "prospectos", "pct_presupuestado": "prospectos",
    "cac": "cierres", "pct_conversion": "cierres", "costo_por_derivado": "prospectos",
}


def _crudo(metrica: str, fila: dict) -> str:
    """El cálculo detrás del número, para que la alerta se pueda auditar de un vistazo."""
    if metrica == "cac":
        return f"${fila['gasto_usd']:,.0f} ÷ {fila['cierres']} cierre" + ("s" if fila["cierres"] != 1 else "")
    if metrica == "costo_por_derivado":
        return f"${fila['gasto_usd']:,.0f} ÷ {fila['derivados']} derivados"
    if metrica == "cpl":
        return f"${fila['gasto_usd']:,.0f} ÷ {fila['prospectos']} prospectos"
    if metrica == "pct_derivacion":
        return f"{fila['derivados']} de {fila['prospectos']} prospectos"
    if metrica == "pct_presupuestado":
        return f"{fila['presupuestados']} de {fila['prospectos']} prospectos"
    if metrica == "pct_conversion":
        return f"{fila['cierres']} de {fila['prospectos']} prospectos"
    return f"{fila['prospectos']} prospectos"


def detectar(snapshot: dict, cfg: Config, hasta: str | None = None) -> list[dict]:
    """Evalúa las reglas semanales, cada una sobre su propia ventana."""
    a = cfg["alertas"]
    hasta = hasta or snapshot["ventana"]["hasta"]
    fin = date.fromisoformat(hasta)
    ambitos = ["general"] + cfg.canales_activos
    cache: dict[int, tuple[dict, dict, tuple, tuple]] = {}
    hallazgos: list[dict] = []

    for regla in a["semanales"]:
        if regla["metrica"] in ("gasto_sin_cargar", "pct_no_calificacion"):
            continue                      # se resuelven aparte, no por umbral relativo
        dias = regla["ventana_dias"]
        if dias not in cache:
            v = (fin - timedelta(days=dias - 1), fin)
            b = (fin - timedelta(days=dias * 2 - 1), fin - timedelta(days=dias))
            cache[dias] = (calcular(snapshot, cfg, v[0].isoformat(), v[1].isoformat()),
                           calcular(snapshot, cfg, b[0].isoformat(), b[1].isoformat()), v, b)
        actual, previo, ventana, base = cache[dias]

        for ambito in ambitos:
            ahora = actual["general"] if ambito == "general" else actual["canales"].get(ambito)
            antes = previo["general"] if ambito == "general" else previo["canales"].get(ambito)
            if not ahora or not antes:
                continue
            # El umbral se aplica sobre lo que la métrica realmente cuenta.
            base_n = BASE.get(regla["metrica"], "prospectos")
            minimo = (a.get("n_minimo_cierres", 3) if base_n == "cierres"
                      else a["n_minimo_para_alertar"])
            if ahora.get(base_n, 0) < minimo or antes.get(base_n, 0) < minimo:
                continue

            clave = CLAVE_METRICA.get(regla["metrica"], regla["metrica"])
            v_ahora, v_antes = ahora.get(clave), antes.get(clave)
            if v_ahora is None or v_antes in (None, 0):
                continue

            if "umbral_pp" in regla:
                delta = v_ahora - v_antes
                supera = (delta <= -regla["umbral_pp"]) if regla["direccion"] == "baja" else (delta >= regla["umbral_pp"])
                magnitud = f"{delta:+.1f} pp"
            else:
                delta = (v_ahora - v_antes) / v_antes * 100
                supera = (delta <= -regla["umbral_pct"]) if regla["direccion"] == "baja" else (delta >= regla["umbral_pct"])
                magnitud = f"{delta:+.0f}%"

            if supera:
                hallazgos.append({
                    "metrica": regla["metrica"],
                    "titulo": ETIQUETAS.get(regla["metrica"], regla["metrica"]),
                    "ambito": "General" if ambito == "general" else cfg.nombre_canal(ambito),
                    "severidad": regla["severidad"], "direccion": regla["direccion"],
                    "valor_actual": v_ahora, "valor_previo": v_antes, "variacion": magnitud,
                    "ventana": f"últimos {dias} días vs. los {dias} anteriores",
                    "desde": ventana[0].isoformat(), "hasta": ventana[1].isoformat(),
                    "base_desde": base[0].isoformat(), "base_hasta": base[1].isoformat(),
                    "crudo_actual": _crudo(regla["metrica"], ahora),
                    "crudo_previo": _crudo(regla["metrica"], antes),
                    "n": ahora["prospectos"],
                })

    # El gasto sin cargar invalida el CPL, así que viaja con las alertas.
    largo = max((r["ventana_dias"] for r in a["semanales"] if "ventana_dias" in r), default=28)
    salud = revisar(snapshot, cfg, (fin - timedelta(days=largo - 1)).isoformat(), hasta)
    for h in salud["hallazgos"]:
        if h["estado"] == "alerta" and h["check"].startswith("Inversión de"):
            hallazgos.append({
                "metrica": "gasto_sin_cargar", "titulo": "Gasto sin cargar",
                "ambito": h["check"].replace("Inversión de ", ""), "severidad": "alta",
                "direccion": "n/a", "valor_actual": h["valor"], "valor_previo": None,
                "variacion": "—", "ventana": "carga del SPA", "n": None,
            })

    orden = {"alta": 0, "media": 1, "baja": 2}
    return sorted(hallazgos, key=lambda h: orden.get(h["severidad"], 9))
