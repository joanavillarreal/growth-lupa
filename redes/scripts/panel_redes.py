#!/usr/bin/env python3
"""Arma el Panel de redes de Lupa: redes/panel/datos.json y redes/panel/index.html.

Uso:
    python3 redes/scripts/panel_redes.py        (desde la raíz de growth-lupa)

El panel tiene tres partes:
  1. Las cuentas al día de hoy   <- redes/general/<fecha>.json más reciente (general.py, diario)
  2. Leads de redes del trimestre <- data/snapshots/ (el último: el mismo snapshot del Monitor)
  3. La última semana cerrada     <- redes/data/<semana>/ (analizar.py, cruce_crm.py, lectura.json)
     Solo la última: cada lunes se reemplaza. El histórico semanal queda en el repo, no en el panel.

Además deja un bloque legible por máquina para Conti (y cualquier agente que lea el panel sin
entrar al repo): <script type="application/json" id="datos-redes">, también en
redes/panel/datos-redes.json. Se arma SOLO con --semana (lo corre redes · semana, los lunes):
la última semana cerrada, los leads de redes del trimestre a esa fecha y, de
redes/memoria/conclusiones.md, "Descartado" y "En prueba" de cada marca. Los demás días el panel
se reconstruye con el bloque guardado, sin tocarlo.

No recalcula lo que ya calcularon analizar.py o general.py. Lo único nuevo son las alertas
automáticas de la semana (reglas fijas, cada una con su número) y los leads por trimestre.
Donde un número no existe va null ("sin dato"), nunca cero.
"""
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REDES = Path(__file__).resolve().parent.parent
RAIZ = REDES.parent
sys.path.insert(0, str(RAIZ))

from growth import ingest            # noqa: E402  (snapshot normalizado a hora argentina)
from growth.config import Config     # noqa: E402

MARCAS = [("boxer-gestion", "Boxer Gestión"), ("boxer-taller", "Boxer Taller")]
TIPO = {"FEED_CAROUSEL_ALBUM": "Carrusel", "FEED_IMAGE": "Post", "FEED_VIDEO": "Video",
        "REELS": "Reel", "REEL": "Reel"}
UMBRAL_CAIDA_ALCANCE = -30.0   # % contra la semana anterior
UMBRAL_PAUTA = 90.0            # % de las views de Instagram que son pauta


def leer(semana, nombre):
    ruta = REDES / "data" / semana / f"{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def semanas():
    return sorted(p.name for p in (REDES / "data").iterdir() if re.match(r"\d{4}-W\d{2}$", p.name))


def pieza(p):
    if not p:
        return None
    return {"tipo": TIPO.get(p.get("tipo"), p.get("tipo")), "fecha": p.get("fecha"), "url": p.get("url"),
            "texto": (p.get("texto") or "").split("\n")[0][:160],
            "alcance": p.get("alcance"), "interacciones": p.get("interacciones"),
            "engagement_pct": p.get("engagement_pct"), "guardados": p.get("guardados"),
            "compartidos": p.get("compartidos"), "follows": p.get("follows"),
            "view_rate_pct": p.get("view_rate_pct")}


def resumen_marca(d):
    ig, fb, li = d.get("instagram") or {}, d.get("facebook") or {}, d.get("linkedin")
    org, pauta, seg = ig.get("organico") or {}, ig.get("pauta") or {}, ig.get("seguidores") or {}
    comp = (d.get("comparativa") or {}).get("instagram") or {}
    return {
        "desde": d.get("desde"), "hasta": d.get("hasta"), "modo_lectura": d.get("modo_lectura"),
        "ig": {
            "seguidores": seg.get("fin"), "seguidores_delta": seg.get("delta"),
            "alcance_organico": org.get("alcance"), "alcance_pago": pauta.get("alcance"),
            "alcance_total": ig.get("alcance_total_cuenta"),
            "views_organicas": org.get("views"), "views_pago": pauta.get("views"),
            "pct_views_pauta": ig.get("pct_views_de_pauta"),
            "engagement_pct": org.get("engagement_pct"), "interacciones": org.get("interacciones"),
            "publicaciones": ig.get("publicaciones"), "stories": ig.get("stories_publicadas"),
            "guardados": ig.get("guardados_totales"), "compartidos": ig.get("compartidos_totales"),
            "muestra_chica": ig.get("muestra_chica"),
            "formatos": ig.get("formatos") or [],
            "var_alcance_organico": comp.get("alcance_organico"),
            "var_engagement": comp.get("engagement_pct"),
        },
        "fb": {"seguidores": (fb.get("seguidores") or {}).get("fin"),
               "seguidores_delta": (fb.get("seguidores") or {}).get("delta"),
               "views": fb.get("views_contenido"), "publicaciones": fb.get("publicaciones")},
        "li": None if not li else {"seguidores": (li.get("seguidores") or {}).get("fin"),
                                   "seguidores_delta": (li.get("seguidores") or {}).get("delta"),
                                   "impresiones": li.get("impresiones"),
                                   "publicaciones": li.get("publicaciones"),
                                   "engagement_pct": li.get("engagement_pct_sobre_impresiones")},
        "top_engagement": [pieza(p) for p in (ig.get("top_por_engagement") or [])[:3]],
        "top_seguidores": [pieza(p) for p in (ig.get("top_por_seguidores_ganados") or [])[:3]],
    }


def coma(v):
    return f"{v:.1f}".replace(".", ",")


def alertas_auto(r, nombre):
    """Reglas fijas. Cada alerta dice el número que la dispara."""
    ig, out = r["ig"], []
    if ig["publicaciones"] == 0:
        out.append(f"{nombre} no publicó nada en Instagram esta semana.")
    if ig["muestra_chica"]:
        out.append(f"{nombre}: alcance orgánico de {ig['alcance_organico']} personas. Con tan poco "
                   "alcance los % de engagement son ruido: no se sacan conclusiones de ellos.")
    raros = [f for f in ig["formatos"] if (f.get("engagement_pct") or 0) > 100]
    if raros:
        out.append(f"{nombre}: el engagement de {', '.join(f['formato'] for f in raros)} da más de 100% "
                   "(interacciones de piezas de semanas anteriores). El % orgánico de la cuenta no es "
                   "confiable esta semana: vale el ranking pieza por pieza.")
    if ig["seguidores_delta"] is not None and ig["seguidores_delta"] < 0:
        out.append(f"{nombre} perdió {-ig['seguidores_delta']} seguidores en Instagram.")
    if ig["var_alcance_organico"] is not None and ig["var_alcance_organico"] <= UMBRAL_CAIDA_ALCANCE:
        out.append(f"{nombre}: el alcance orgánico cayó {coma(ig['var_alcance_organico'])}% contra la "
                   "semana anterior.")
    if ig["pct_views_pauta"] is not None and ig["pct_views_pauta"] >= UMBRAL_PAUTA:
        out.append(f"{nombre}: el {coma(ig['pct_views_pauta'])}% de las views de Instagram fueron pauta. "
                   "Lo que se dice del contenido sale del orgánico.")
    if ig["publicaciones"] and not r["top_seguidores"]:
        sin_dato = [p for p in r["top_engagement"] if p and p["follows"] is None]
        if sin_dato:
            out.append(f"{nombre}: ningún post o carrusel trajo seguidores (0 follows); los reels "
                       "no informan follows (sin dato, no cero).")
        else:
            out.append(f"{nombre}: ninguna pieza de la semana trajo seguidores (0 follows por pieza).")
    return out


def leads_por_trimestre(hoy):
    cfg = Config()
    origenes = set(cfg["canales"]["redes_sociales"]["origenes"])
    snap = ingest.cargar_ultimo()
    corte = snap["ventana"]["hasta"]
    leads = [p for p in snap["prospectos"] if p.get("SOURCE_ID") in origenes]

    def q_de(d):
        return d.year, (d.month - 1) // 3 + 1

    def limites(y, q):
        ini = date(y, 3 * q - 2, 1)
        fin = date(y + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1)
        return ini, fin

    y, q = q_de(date.fromisoformat(corte))
    actual = (y, q)
    previo = (y, q - 1) if q > 1 else (y - 1, 4)
    out = []
    for (yy, qq) in (actual, previo):
        ini, fin = limites(yy, qq)
        tope = min(fin, date.fromisoformat(corte))
        del_q = [p for p in leads if ini.isoformat() <= p["DATE_CREATE"][:10] <= tope.isoformat()]
        sem = Counter()
        for p in del_q:
            iy, iw, _ = date.fromisoformat(p["DATE_CREATE"][:10]).isocalendar()
            sem[f"{iy}-W{iw:02d}"] += 1
        # todas las semanas del Q, también las que no trajeron nada (0 real, el CRM respondió)
        semanas_q, d = [], ini
        while d <= tope:
            iy, iw, _ = d.isocalendar()
            k = f"{iy}-W{iw:02d}"
            if k not in semanas_q:
                semanas_q.append(k)
            d += timedelta(days=1)
        estados = Counter(p.get("STATUS_ID") for p in del_q)
        out.append({
            "etiqueta": f"Q{qq} {yy}", "desde": ini.isoformat(), "hasta": tope.isoformat(),
            "en_curso": tope < fin, "total": len(del_q),
            "por_semana": [{"semana": k, "leads": sem.get(k, 0)} for k in semanas_q],
            "derivados": estados.get("CONVERTED", 0),
            "no_utiles": estados.get("JUNK", 0), "inactivos": estados.get("UC_LG671J", 0),
            "en_gestion": len(del_q) - estados.get("CONVERTED", 0) - estados.get("JUNK", 0)
            - estados.get("UC_LG671J", 0),
        })
    # mismo tramo del Q anterior: del día 1 al mismo día del trimestre
    dias = (date.fromisoformat(out[0]["hasta"]) - date.fromisoformat(out[0]["desde"])).days
    ini_prev = date.fromisoformat(out[1]["desde"])
    tramo_fin = (ini_prev + timedelta(days=dias)).isoformat()
    out[1]["mismo_tramo"] = {"hasta": tramo_fin, "total": sum(
        1 for p in leads if out[1]["desde"] <= p["DATE_CREATE"][:10] <= tramo_fin)}
    return {"corte_snapshot": corte, "trimestres": out,
            "fuente": "Bitrix24, prospectos con origen del canal Redes Sociales "
                      "(config/definitions.yaml), snapshot diario del funnel"}


def ultima_general(hoy):
    archivos = sorted(p for p in (REDES / "general").glob("????-??-??.json")
                      if p.stem <= hoy.isoformat()) if (REDES / "general").exists() else []
    if not archivos:
        return None
    g = json.loads(archivos[-1].read_text(encoding="utf-8"))
    g["al_dia"] = g["fecha"] == hoy.isoformat()
    return g


def ultima_semana():
    for s in reversed(semanas()):
        if all(leer(s, clave) for clave, _ in MARCAS):
            return s
    return None


FORMATO_BLOQUE = 1   # subir si cambia la forma del bloque datos-redes


def memoria_conti():
    """De la Parte 1 de conclusiones.md: Descartado (tabla) y En prueba (preguntas) por marca."""
    texto = (REDES / "memoria" / "conclusiones.md").read_text(encoding="utf-8")
    parte1 = texto.split("# Parte 2")[0]
    out = {}
    for clave, nombre in MARCAS:
        m = re.search(rf"^## {re.escape(nombre)}\n(.*?)(?=^## |\Z)", parte1, re.S | re.M)
        if not m:
            out[clave] = {"descartado": None, "en_prueba": None}
            continue
        secciones = dict(re.findall(r"^### (.+?)\n(.*?)(?=^### |\Z)", m.group(1), re.S | re.M))
        desc = next((v for k, v in secciones.items() if k.startswith("Descartado")), "")
        prueba = next((v for k, v in secciones.items() if k.startswith("En prueba")), "")
        filas = []
        for linea in desc.splitlines():
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            if linea.startswith("|") and len(celdas) == 2 and not set(celdas[0]) <= set("-: ") \
                    and celdas[0] != "Mecanismo":
                filas.append({"mecanismo": celdas[0].replace("**", ""), "evidencia": celdas[1]})
        items = []
        bloques = re.split(r"\n(?=\*\*¿)", prueba.strip().split("\n---")[0])
        for b in bloques:
            q = re.match(r"\*\*(¿.+?\?)\*\*\s*(.*)", b.strip(), re.S)
            if q:
                items.append({"pregunta": q.group(1), "estado_y_evidencia": " ".join(q.group(2).split())})
        out[clave] = {"descartado": filas, "en_prueba": items}
    return out


def piezas_conti(ig):
    """Mejores y peores piezas de Instagram por engagement orgánico, con formato y tema."""
    def ficha(p):
        return {"formato": TIPO.get(p.get("tipo"), p.get("tipo")), "fecha": p.get("fecha"),
                "url": p.get("url"),
                # Metricool no clasifica el tema: va la primera línea del caption, tal cual.
                "tema": (p.get("texto") or "").split("\n")[0][:200] or None,
                "alcance": p.get("alcance"), "interacciones": p.get("interacciones"),
                "engagement_pct": p.get("engagement_pct"), "guardados": p.get("guardados"),
                "compartidos": p.get("compartidos"), "follows": p.get("follows"),
                "views": p.get("views"), "view_rate_pct": p.get("view_rate_pct")}
    con_dato = [p for p in (ig.get("piezas") or []) if p.get("engagement_pct") is not None]
    orden = sorted(con_dato, key=lambda p: p["engagement_pct"], reverse=True)
    n = min(3, len(orden) // 2)          # con menos de 2 piezas no hay "mejor" contra "peor"
    return ([ficha(p) for p in orden[:max(n, 1)]] if orden else [],
            [ficha(p) for p in orden[::-1][:n]])


def bloque_conti(semana, fila, leads):
    marcas = {}
    for clave, nombre in MARCAS:
        d = leer(semana, clave)
        r = resumen_marca(d)
        mejores, peores = piezas_conti(d.get("instagram") or {})
        ig = {k: v for k, v in r["ig"].items() if k != "formatos"}
        ig["formatos"] = r["ig"]["formatos"]
        marcas[clave] = {"nombre": nombre, "instagram": ig, "facebook": r["fb"], "linkedin": r["li"],
                         "mejores_piezas": mejores, "peores_piezas": peores}
    lectura = fila.get("lectura") or {}
    return {
        "formato": FORMATO_BLOQUE,
        "generado": datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).isoformat(timespec="minutes"),
        "fuente": "Lupa (growth-lupa), análisis redes · semana. Orgánico y pago van separados; "
                  "null = sin dato, nunca cero.",
        "semana": {"semana": semana, "desde": fila.get("desde"), "hasta": fila.get("hasta"),
                   "marcas": marcas,
                   "titular": lectura.get("titular"), "funciono": lectura.get("funciono") or [],
                   "no_funciono": lectura.get("no_funciono") or [], "alertas": fila.get("alertas") or [],
                   "prospectos_redes_semana": fila.get("crm")},
        "leads_trimestre": leads,
        "memoria": memoria_conti(),
    }


def construir(semanal=False):
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    ahora = datetime.now(tz)
    hoy = ahora.date()
    datos = {"generado": ahora.isoformat(timespec="minutes"), "hoy": hoy.isoformat(),
             "general": ultima_general(hoy), "leads": leads_por_trimestre(hoy), "semana": None}
    s = ultima_semana()
    if s:
        fila = {"semana": s, "alertas": [], "crm": None, "lectura": leer(s, "lectura"), "marcas": {}}
        for clave, nombre in MARCAS:
            r = resumen_marca(leer(s, clave))
            fila["desde"], fila["hasta"] = r["desde"], r["hasta"]
            fila["alertas"] += alertas_auto(r, nombre)
            fila["marcas"][clave] = {"nombre": nombre, "top_engagement": r["top_engagement"],
                                     "top_seguidores": r["top_seguidores"],
                                     "publicaciones": r["ig"]["publicaciones"]}
        crm = leer(s, "crm")
        if crm:
            fila["crm"] = {"prospectos_redes": crm.get("prospectos_redes"),
                           "inversion_redes_ars": crm.get("inversion_redes"),
                           "costo_por_prospecto_ars": crm.get("costo_por_prospecto"),
                           "var_pct": (crm.get("comparativa") or {}).get("prospectos_redes_var_pct")}
            if crm.get("prospectos_redes") == 0:
                fila["alertas"].append("Las redes no trajeron ningún prospecto al CRM esta semana.")
        datos["semana"] = fila

    ruta_bloque = REDES / "panel" / "datos-redes.json"
    if semanal and s:
        conti = bloque_conti(s, fila, datos["leads"])
        ruta_bloque.write_text(json.dumps(conti, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    conti = json.loads(ruta_bloque.read_text(encoding="utf-8")) if ruta_bloque.exists() else None

    destino = REDES / "panel"
    destino.mkdir(exist_ok=True)
    (destino / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n",
                                        encoding="utf-8")
    plantilla = (destino / "plantilla.html").read_text(encoding="utf-8")
    bloque = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    html = re.sub(r'(<script type="application/json" id="datos">).*?(</script>)',
                  lambda m: m.group(1) + bloque + m.group(2), plantilla, count=1, flags=re.S)
    bloque_c = json.dumps(conti, ensure_ascii=False).replace("</", "<\\/")
    html = re.sub(r'(<script type="application/json" id="datos-redes">).*?(</script>)',
                  lambda m: m.group(1) + bloque_c + m.group(2), html, count=1, flags=re.S)
    (destino / "index.html").write_text(html, encoding="utf-8")
    g = datos["general"]
    print(f"Panel de redes: cuentas al {g['datos_hasta'] if g else 'SIN DATO'}"
          f"{'' if not g or g['al_dia'] else ' (ATRASADO: no es de hoy)'} · "
          f"leads {datos['leads']['trimestres'][0]['etiqueta']}: {datos['leads']['trimestres'][0]['total']} · "
          f"semana {s or 'ninguna'} · bloque datos-redes: "
          f"{(conti or {}).get('semana', {}).get('semana', 'NO HAY') if conti else 'NO HAY'}"
          f"{' (rearmado)' if semanal else ' (el guardado del lunes)'}")
    print(f"  -> {destino / 'index.html'}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--semana", action="store_true",
                    help="rearmar el bloque datos-redes (solo redes · semana, los lunes)")
    construir(ap.parse_args().semana)
