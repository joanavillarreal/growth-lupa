"""Redacción de los mensajes que van a Slack.


El formato es markdown estándar (**negrita**, [texto](url)), que es lo que
espera el conector de Slack de esta sesión — no la sintaxis mrkdwn nativa.

Dos criterios de escritura:
  - La alarma diaria no se manda si no hay nada. Un canal que recibe "todo ok"
    todos los días deja de leerse en dos semanas.
  - El informe semanal se manda siempre y empieza por la conclusión. Quien lo
    abre en el teléfono tiene que entender el estado en la primera línea.
"""
from __future__ import annotations

from .config import Config

SEMAFORO = {"mejora": "🟢", "estable": "⚪", "empeora": "🔴"}
ICONO_SEV = {"alta": "🔴", "media": "🟠", "baja": "⚪"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(f: str) -> str:
    a, m, d = f.split("-")
    return f"{int(d)} de {MESES[int(m) - 1]}"


def _num(clave: str, v) -> str:
    if v is None:
        return "—"
    if clave.endswith("_usd"):
        return f"${v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if clave.startswith("pct_"):
        return f"{v:.1f}%".replace(".", ",")
    return f"{v:,.0f}".replace(",", ".")


def mensaje_diario(alertas: list[dict], fecha: str) -> str | None:
    """None cuando no hay nada: en ese caso no se manda mensaje."""
    if not alertas:
        return None
    lineas = [f"**Agente Growth · Alarma de adquisición** — {_fecha_larga(fecha)}", ""]
    for a in alertas:
        lineas.append(f"{ICONO_SEV.get(a['severidad'], '⚪')} **{a['titulo']}**")
        lineas.append(f"{a['detalle']}")
        lineas.append(f"_→ {a['accion']}_")
        lineas.append("")
    return "\n".join(lineas).strip()


def mensaje_semanal(informe: dict, cfg: Config, url_dashboard: str = "") -> str:
    s = informe["semana"]
    estado = informe["estado"]
    lineas = [
        f"**Agente Growth · Salud del funnel de adquisición**",
        f"Semana del {_fecha_larga(s['desde'])} al {_fecha_larga(s['hasta'])} · "
        f"{SEMAFORO[estado]} **{estado}** ({informe['mejoran']} mejoran, {informe['empeoran']} empeoran)",
        "",
    ]

    # tabla en monoespaciado: es la única forma de que alinee en Slack
    filas = informe["filas"]
    tabla = ["```", f"{'':<22}{'-2 sem':>9}{'-1 sem':>9}{'esta':>9}"]
    for f in filas:
        vals = "".join(_num(f["metrica"], v).rjust(9) for v in f["valores"])
        marca = {"mejora": " ▲", "empeora": " ▼"}.get(f["direccion"], "")
        tabla.append(f"{f['nombre']:<22}{vals}{marca}")
    tabla.append("```")
    lineas += tabla

    movidas = [f for f in filas if f["direccion"] in ("mejora", "empeora")]
    if movidas:
        lineas.append("**Lo que se movió**")
        for f in movidas:
            verbo = "mejora" if f["direccion"] == "mejora" else "empeora"
            sostenida = " y viene sostenido hace dos semanas" if f["sostenida"] else ""
            detalle = ""
            if f.get("canal"):
                detalle = f" El canal que más lo explica es **{f['canal']}** ({f['canal_detalle']})."
            anterior, actual = f["valores"][-2], f["valores"][-1]
            lineas.append(f"• **{f['nombre']}** {verbo}{sostenida}: "
                          f"{_num(f['metrica'], anterior)} → {_num(f['metrica'], actual)}.{detalle}")
        lineas.append("")

    if informe["alertas"]:
        lineas.append("**Alertas de la semana**")
        for a in informe["alertas"]:
            if a["metrica"] == "gasto_sin_cargar":
                lineas.append(f"{ICONO_SEV[a['severidad']]} Falta inversión de {a['ambito']}: {a['valor_actual']}")
                continue
            crudo = (f" — {a['crudo_actual']} contra {a['crudo_previo']}"
                     if a.get("crudo_actual") else "")
            lineas.append(f"{ICONO_SEV[a['severidad']]} **{a['titulo']}** en {a['ambito']}: "
                          f"{a['variacion']}{crudo}")
        lineas.append("")

    salud = informe["salud"]
    if salud["confiabilidad"] != "alta":
        pendientes = [h["check"] for h in salud["hallazgos"] if h["estado"] == "alerta"]
        lineas.append(f"⚠️ **Confiabilidad del dato: {salud['confiabilidad']}** — "
                      + "; ".join(pendientes[:3]))
        lineas.append("")

    if url_dashboard:
        lineas.append(f"[Ver el dashboard completo]({url_dashboard})")
    return "\n".join(lineas).strip()
