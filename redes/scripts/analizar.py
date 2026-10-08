#!/usr/bin/env python3
"""
Procesa las métricas crudas de Metricool de una semana y las compara con el historial.

Uso:
    python3 scripts/analizar.py 2026-W36              # todas las marcas
    python3 scripts/analizar.py 2026-W36 boxer-taller # una marca

Lee   data/raw/<semana>/<marca>.json   (crudo, tal cual lo devuelve Metricool)
Escribe data/<semana>/<marca>.json     (procesado, con comparativa contra la semana anterior)

Toda la aritmética del informe sale de acá. El agente redacta, no calcula.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = json.loads((RAIZ / "config" / "marcas.json").read_text(encoding="utf-8"))
UMBRAL_CHICO = CONFIG.get("umbral_muestra_chica", 200)

# Tipos de IGAC02 que son contenido propio. AD es pauta y se cuenta aparte.
TIPOS_ORGANICOS = ("CAROUSEL_CONTAINER", "POST", "REEL", "STORY")
NOMBRE_TIPO = {
    "CAROUSEL_CONTAINER": "Carrusel",
    "POST": "Post",
    "REEL": "Reel",
    "STORY": "Story",
}


# ---------------------------------------------------------------- utilidades

def num(valor):
    """Metricool manda los números como string ('5009.0') y los faltantes como null."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def n0(valor):
    """Igual que num() pero los faltantes valen 0, para poder sumar."""
    v = num(valor)
    return 0.0 if v is None else v


def filas(datos, bloque):
    """Convierte un bloque crudo en una lista de dicts {fieldId: valor}.

    Metricool respeta el orden de campos que se le pidió, así que el mapeo es posicional.
    Si la respuesta trae columnas de más (la fecha que agrega por su cuenta cuando no se
    la pediste), se ignoran: por eso el skill siempre pide la fecha explícita y primera.
    """
    b = (datos.get("bloques") or {}).get(bloque)
    if not b:
        return []
    campos = b.get("fields") or []
    salida = []
    for fila in b.get("rows") or []:
        salida.append({campo: fila[i] if i < len(fila) else None for i, campo in enumerate(campos)})
    return salida


def pct(parte, total):
    """Porcentaje, redondeado a 1 decimal. None si no se puede dividir."""
    if not total:
        return None
    return round(parte / total * 100, 1)


def variacion(actual, previo):
    """Variación porcentual contra la semana anterior."""
    if previo is None or actual is None or previo == 0:
        return None
    return round((actual - previo) / previo * 100, 1)


def engagement(interacciones, alcance):
    """Engagement como % de interacciones sobre alcance.

    Metricool lo expresa por cada 1000 personas; acá se usa porcentaje porque es
    lo que se lee en el informe. Sobre alcance (personas), no sobre views.
    """
    return pct(interacciones, alcance)


def por_fecha(registros, campo="_fecha"):
    """Ordena cronológicamente.

    Metricool devuelve las filas de `evolution` en orden arbitrario (29, 27, 30, 28...).
    Sin ordenar, el "primer" y "último" día del período salen mal y el crecimiento de
    seguidores queda inventado. El skill declara la fecha como `_fecha` al final de los
    campos de esos bloques, porque ahí es donde Metricool la ubica cuando no se la pide.
    """
    return sorted(registros, key=lambda f: str(f.get(campo) or ""))


# ------------------------------------------------------------------ armadores

def resumen_instagram(datos):
    """Todo lo de Instagram: separa orgánico de pago y compara formatos."""
    ig = {}

    # --- Desglose por tipo de contenido (IGAC02) -------------------------
    por_tipo = {}
    pauta = {"views": 0.0, "alcance": 0.0}
    for f in filas(datos, "ig_por_tipo"):
        tipo = (f.get("IGAC02") or "").strip()
        if not tipo:
            continue  # filas agregadas sin dimensión: Metricool las incluye, no son un tipo
        destino = pauta if tipo == "AD" else por_tipo.setdefault(
            tipo, {"views": 0.0, "alcance": 0.0, "interacciones": 0.0}
        )
        destino["views"] += n0(f.get("IGAC05"))
        destino["alcance"] += n0(f.get("IGAC06"))
        if tipo != "AD":
            destino["interacciones"] += n0(f.get("IGAC11"))

    formatos = []
    for tipo in TIPOS_ORGANICOS:
        if tipo not in por_tipo:
            continue
        d = por_tipo[tipo]
        # Metricool no atribuye interacciones al contenedor de carrusel en este connector:
        # vienen siempre nulas. Marcar 0% haría parecer que el carrusel no engancha, que es
        # falso. Cuando no hay dato se deja en None y el informe lo dice, en vez de inventar
        # un cero. El engagement real del carrusel sale de las piezas individuales (IGPO).
        sin_dato = d["interacciones"] == 0 and d["views"] > 0
        formatos.append({
            "formato": NOMBRE_TIPO[tipo],
            "views": int(d["views"]),
            "alcance": int(d["alcance"]),
            "interacciones": None if sin_dato else int(d["interacciones"]),
            "engagement_pct": None if sin_dato else engagement(d["interacciones"], d["alcance"]),
            "sin_datos_interaccion": sin_dato,
        })
    formatos.sort(key=lambda x: x["engagement_pct"] if x["engagement_pct"] is not None else -1,
                  reverse=True)
    ig["formatos"] = formatos

    views_org = sum(f["views"] for f in formatos)
    alcance_org = sum(f["alcance"] for f in formatos)
    inter_org = sum(f["interacciones"] or 0 for f in formatos)
    views_tot = views_org + pauta["views"]

    ig["organico"] = {
        "views": int(views_org),
        "alcance": int(alcance_org),
        "interacciones": int(inter_org),
        "engagement_pct": engagement(inter_org, alcance_org),
    }
    ig["pauta"] = {"views": int(pauta["views"]), "alcance": int(pauta["alcance"])}
    ig["pct_views_de_pauta"] = pct(pauta["views"], views_tot)
    ig["alcance_total_cuenta"] = int(alcance_org + pauta["alcance"])

    # --- Seguidores vs no seguidores (IGAC03) ---------------------------
    # OJO: esta dimensión no se puede cruzar con la de tipo de contenido, así que
    # el número incluye la pauta. Cuando la pauta pesa, hay que decirlo en el informe.
    audiencia = {}
    for f in filas(datos, "ig_por_audiencia"):
        quien = (f.get("IGAC03") or "").strip()
        if not quien:
            continue
        a = audiencia.setdefault(quien, {"views": 0.0, "alcance": 0.0})
        a["views"] += n0(f.get("IGAC05"))
        a["alcance"] += n0(f.get("IGAC06"))

    v_seg = audiencia.get("FOLLOWER", {}).get("views", 0.0)
    v_no = audiencia.get("NON_FOLLOWER", {}).get("views", 0.0)
    v_total_aud = v_seg + v_no + audiencia.get("UNKNOWN", {}).get("views", 0.0)
    ig["audiencia"] = {
        "views_seguidores": int(v_seg),
        "views_no_seguidores": int(v_no),
        "pct_seguidores": pct(v_seg, v_total_aud),
        "pct_no_seguidores": pct(v_no, v_total_aud),
        "incluye_pauta": True,
        "advertencia": (
            "Incluye pauta: Metricool no permite cruzar audiencia con tipo de contenido. "
            "Con pauta alta, el % de no seguidores mide la campaña, no el alcance del contenido."
        ),
    }

    # --- Evolución de la cuenta -----------------------------------------
    ev = por_fecha(filas(datos, "ig_evolucion"))
    seguidores = [num(f.get("IGEV01")) for f in ev]
    seguidores = [s for s in seguidores if s is not None]
    if seguidores:
        # IGEV43/44 (ganados/perdidos) vienen vacíos: el crecimiento es delta del total.
        ig["seguidores"] = {
            "inicio": int(seguidores[0]),
            "fin": int(seguidores[-1]),
            "delta": int(seguidores[-1] - seguidores[0]),
            "delta_pct": variacion(seguidores[-1], seguidores[0]),
        }
    ig["publicaciones"] = int(sum(n0(f.get("IGEV37")) for f in ev))
    ig["stories_publicadas"] = int(sum(n0(f.get("IGEV16")) for f in ev))

    # --- Piezas individuales: cuáles trajeron seguidores -----------------
    piezas = []
    for f in filas(datos, "ig_posts"):
        alcance = n0(f.get("IGPO14"))
        piezas.append({
            "tipo": f.get("IGPO07") or "Post",
            "fecha": f.get("IGPO01"),
            "url": f.get("IGPO06"),
            "texto": (f.get("IGPO03") or "")[:180],
            "views": int(n0(f.get("IGPO28"))),
            "alcance": int(alcance),
            "interacciones": int(n0(f.get("IGPO12"))),
            "guardados": int(n0(f.get("IGPO15"))),
            "compartidos": int(n0(f.get("IGPO27"))),
            "follows": int(n0(f.get("IGPO29"))),
            "engagement_pct": engagement(n0(f.get("IGPO12")), alcance),
        })
    for f in filas(datos, "ig_reels"):
        alcance = n0(f.get("IGRE11"))
        piezas.append({
            "tipo": "Reel",
            "fecha": f.get("IGRE01"),
            "url": f.get("IGRE06"),
            "texto": (f.get("IGRE03") or "")[:180],
            "views": int(n0(f.get("IGRE23"))),
            "alcance": int(alcance),
            "interacciones": int(n0(f.get("IGRE09"))),
            "guardados": int(n0(f.get("IGRE12"))),
            "compartidos": int(n0(f.get("IGRE21"))),
            "follows": None,  # los reels no exponen follows por pieza
            "retencion_pct": num(f.get("IGRE27")),
            "view_rate_pct": num(f.get("IGRE28")),
            "engagement_pct": engagement(n0(f.get("IGRE09")), alcance),
        })

    piezas.sort(key=lambda p: p.get("engagement_pct") or -1, reverse=True)
    ig["piezas"] = piezas
    ig["top_por_engagement"] = piezas[:5]
    con_follows = [p for p in piezas if p.get("follows")]
    con_follows.sort(key=lambda p: p["follows"], reverse=True)
    ig["top_por_seguidores_ganados"] = con_follows[:5]
    ig["guardados_totales"] = sum(p["guardados"] for p in piezas)
    ig["compartidos_totales"] = sum(p["compartidos"] for p in piezas)

    # Señal de que los porcentajes son ruido y no hay que sacar conclusiones de ellos.
    ig["muestra_chica"] = alcance_org < UMBRAL_CHICO

    return ig


def resumen_facebook(datos):
    ev = por_fecha(filas(datos, "fb_evolucion"))
    if not ev:
        return None
    seguidores = [num(f.get("FBEV17")) for f in ev]
    seguidores = [s for s in seguidores if s is not None]
    interacciones = sum(n0(f.get("FBEV34")) for f in ev)
    fb = {
        "views_contenido": int(sum(n0(f.get("FBEV49")) for f in ev)),
        "publicaciones": int(sum(n0(f.get("FBEV33")) for f in ev)),
        "interacciones": int(interacciones),
        "reels_publicados": int(sum(n0(f.get("FBEV21")) for f in ev)),
        "views_reels": int(sum(n0(f.get("FBEV22")) for f in ev)),
    }
    if seguidores:
        fb["seguidores"] = {
            "inicio": int(seguidores[0]),
            "fin": int(seguidores[-1]),
            "delta": int(seguidores[-1] - seguidores[0]),
        }
    return fb


def resumen_linkedin(datos):
    ev = por_fecha(filas(datos, "li_evolucion"))
    if not ev:
        return None
    seguidores = [num(f.get("LIEV01")) for f in ev]
    seguidores = [s for s in seguidores if s is not None]
    impresiones = sum(n0(f.get("LIEV22")) for f in ev)
    interacciones = sum(n0(f.get("LIEV28")) for f in ev)
    li = {
        "impresiones": int(impresiones),
        "publicaciones": int(sum(n0(f.get("LIEV27")) for f in ev)),
        "interacciones": int(interacciones),
        "reacciones": int(sum(n0(f.get("LIEV21")) for f in ev)),
        "comentarios": int(sum(n0(f.get("LIEV23")) for f in ev)),
        "compartidos": int(sum(n0(f.get("LIEV20")) for f in ev)),
        "clics": int(sum(n0(f.get("LIEV24")) for f in ev)),
        # En LinkedIn el engagement va sobre impresiones, no sobre alcance:
        # no es comparable con el de Instagram o Facebook.
        "engagement_pct_sobre_impresiones": pct(interacciones, impresiones),
    }
    if seguidores:
        li["seguidores"] = {
            "inicio": int(seguidores[0]),
            "fin": int(seguidores[-1]),
            "delta": int(seguidores[-1] - seguidores[0]),
        }
    return li


# ---------------------------------------------------------------- comparativa

def semana_anterior(semana):
    """'2026-W36' -> '2026-W35', cruzando el cambio de año correctamente."""
    anio, num_sem = semana.split("-W")
    lunes = date.fromisocalendar(int(anio), int(num_sem), 1) - timedelta(days=7)
    iso = lunes.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def comparar(actual, previo):
    """Variaciones contra la semana anterior en las métricas que van al informe."""
    if not previo:
        return {"hay_semana_previa": False}

    comp = {"hay_semana_previa": True, "semana_previa": previo.get("semana")}

    ig_a, ig_p = actual.get("instagram") or {}, previo.get("instagram") or {}
    if ig_a and ig_p:
        org_a = ig_a.get("organico") or {}
        org_p = ig_p.get("organico") or {}
        comp["instagram"] = {
            "views_organicas": variacion(org_a.get("views"), org_p.get("views")),
            "alcance_organico": variacion(org_a.get("alcance"), org_p.get("alcance")),
            "interacciones": variacion(org_a.get("interacciones"), org_p.get("interacciones")),
            "engagement_pct": variacion(org_a.get("engagement_pct"), org_p.get("engagement_pct")),
            "seguidores": variacion(
                (ig_a.get("seguidores") or {}).get("fin"),
                (ig_p.get("seguidores") or {}).get("fin"),
            ),
            "publicaciones": variacion(ig_a.get("publicaciones"), ig_p.get("publicaciones")),
            "guardados": variacion(ig_a.get("guardados_totales"), ig_p.get("guardados_totales")),
        }

    for red, campo in (("facebook", "views_contenido"), ("linkedin", "impresiones")):
        a, p = actual.get(red), previo.get(red)
        if a and p:
            comp[red] = {
                campo: variacion(a.get(campo), p.get(campo)),
                "interacciones": variacion(a.get("interacciones"), p.get("interacciones")),
                "seguidores": variacion(
                    (a.get("seguidores") or {}).get("fin"),
                    (p.get("seguidores") or {}).get("fin"),
                ),
            }

    return comp


# --------------------------------------------------------------------- salida

def avance_objetivo(marca, ig):
    """Avance contra el objetivo de trimestre y ritmo necesario para llegar.

    Solo para las marcas que tienen `objetivo_trimestre` en config/marcas.json.
    El ritmo semanal se toma del delta de la semana: si no creció, no hay ETA
    que estimar y se devuelve None en vez de un número inventado.
    """
    obj = marca.get("objetivo_trimestre")
    if not obj or obj.get("metrica") != "seguidores_instagram":
        return None
    seg = ig.get("seguidores") or {}
    actual = seg.get("fin")
    if actual is None:
        return None
    meta = obj["valor"]
    faltan = meta - actual
    ritmo = seg.get("delta")
    semanas = None
    if ritmo and ritmo > 0 and faltan > 0:
        semanas = int(-(-faltan // ritmo))  # redondeo hacia arriba
    return {
        "meta": meta,
        "actual": actual,
        "faltan": faltan,
        "avance_pct": pct(actual, meta),
        "ritmo_semanal": ritmo,
        "semanas_a_este_ritmo": semanas,
        "ritmo_necesario_13_semanas": int(-(-faltan // 13)) if faltan > 0 else 0,
    }


def procesar(semana, clave_marca):
    marca = CONFIG["marcas"][clave_marca]
    crudo_path = RAIZ / "data" / "raw" / semana / f"{clave_marca}.json"
    if not crudo_path.exists():
        raise SystemExit(f"Falta el crudo: {crudo_path}\nEl skill tiene que extraerlo de Metricool primero.")

    crudo = json.loads(crudo_path.read_text(encoding="utf-8"))

    salida = {
        "semana": semana,
        "marca": clave_marca,
        "nombre": marca["nombre"],
        "modo_lectura": marca["modo_lectura"],
        "desde": crudo.get("desde"),
        "hasta": crudo.get("hasta"),
        "instagram": resumen_instagram(crudo),
    }
    if fb := resumen_facebook(crudo):
        salida["facebook"] = fb
    if li := resumen_linkedin(crudo):
        salida["linkedin"] = li
    if obj := avance_objetivo(marca, salida["instagram"]):
        salida["objetivo_trimestre"] = obj

    previo_path = RAIZ / "data" / semana_anterior(semana) / f"{clave_marca}.json"
    previo = json.loads(previo_path.read_text(encoding="utf-8")) if previo_path.exists() else None
    salida["comparativa"] = comparar(salida, previo)

    destino = RAIZ / "data" / semana / f"{clave_marca}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    return salida, destino


def imprimir(r):
    ig = r.get("instagram") or {}
    org = ig.get("organico") or {}
    print(f"\n=== {r['nombre']} — {r['semana']} ({r['modo_lectura']}) ===")
    print(f"Instagram orgánico: {org.get('views')} views · {org.get('alcance')} alcance "
          f"· engagement {org.get('engagement_pct')}%")
    if ig.get("pct_views_de_pauta"):
        print(f"Pauta: {ig['pct_views_de_pauta']}% de las views de la cuenta")
    if seg := ig.get("seguidores"):
        print(f"Seguidores: {seg['inicio']} -> {seg['fin']} ({seg['delta']:+d})")
    if obj := r.get("objetivo_trimestre"):
        eta = f"{obj['semanas_a_este_ritmo']} semanas a este ritmo" if obj["semanas_a_este_ritmo"] else "sin ritmo positivo esta semana"
        print(f"Objetivo trimestre: {obj['actual']}/{obj['meta']} ({obj['avance_pct']}%) · faltan {obj['faltan']} "
              f"· {eta} · harian falta {obj['ritmo_necesario_13_semanas']}/semana para 13 semanas")
    if ig.get("muestra_chica"):
        print(f"[!] Alcance orgánico bajo el umbral ({UMBRAL_CHICO}): los % son ruido estadístico.")
    for f in ig.get("formatos", []):
        eng = "sin dato" if f["sin_datos_interaccion"] else f"{f['engagement_pct']}%"
        print(f"  {f['formato']:<9} {f['views']:>7} views · {f['alcance']:>6} alcance · eng {eng}")
    comp = r.get("comparativa") or {}
    if comp.get("hay_semana_previa"):
        print(f"vs {comp['semana_previa']}: {comp.get('instagram')}")
    else:
        print("Sin semana previa en el historial: esta corrida sienta la línea de base.")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    semana = sys.argv[1]
    marcas = [sys.argv[2]] if len(sys.argv) > 2 else list(CONFIG["marcas"])
    for clave in marcas:
        resultado, destino = procesar(semana, clave)
        imprimir(resultado)
        print(f"-> {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
