#!/usr/bin/env python3
"""
Convierte las respuestas crudas del MCP de Meta en los CSV con forma de export
del Administrador de anuncios, que es lo que ya sabe leer analizar_meta.py.

Por que este puente existe
--------------------------
El MCP lo llama el AGENTE, no un script: Python no tiene acceso a las
herramientas `mcp__MCP_Meta__*`. Entonces el flujo es en dos tiempos:

  1. El agente llama a `ads_get_ad_entities` (nivel campana, conjunto y anuncio,
     con time_increment="1") y guarda la respuesta TAL CUAL en
     datos/meta-ads/<carpeta>/mcp/<nivel>.json
  2. Este script las traduce a CSV con los nombres de columna del Administrador.

Asi el resto del pipeline (analizar_meta.py, cruzar.py) no se entera de nada y
los CSV siguen siendo la evidencia versionada de cada informe, igual que cuando
los bajaba Joana a mano.

Uso:
    python3 scripts/meta_desde_mcp.py datos/meta-ads/2026-W37/
    python3 scripts/meta_desde_mcp.py <carpeta> --desde 2026-09-01 --hasta 2026-09-07
    python3 scripts/meta_desde_mcp.py --autotest      # prueba el parseo, no toca disco

Entrada: cualquier .json dentro de <carpeta>/mcp/. Cada archivo puede ser:
    - el objeto que devuelve la herramienta: {"ad_entities": "<json string>", ...}
    - una lista de filas ya parseada
    - una lista de varias respuestas (paginas), que se concatenan
"""
import argparse, csv, datetime, glob, json, os, re, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Columnas del export del Administrador de anuncios que consume analizar_meta.py.
# Los nombres van en castellano y con tilde a proposito: son los que trae el CSV
# real de Meta y los que el analizador busca. No renombrar.
COLUMNAS = {
    "campana": [
        "Inicio del informe", "Fin del informe", "Nombre de la campaña",
        "Entrega de la campaña", "Resultados", "Indicador de resultado",
        "Costo por resultados", "Importe gastado (ARS)", "Impresiones",
        "Alcance", "Frecuencia", "CPM (costo por mil impresiones)",
        "CTR (porcentaje de clics en el enlace)", "Clics en el enlace",
        "Objetivo", "Identificador de la campaña",
    ],
    "conjunto": [
        "Inicio del informe", "Fin del informe", "Nombre del conjunto de anuncios",
        "Nombre de la campaña", "Entrega del conjunto de anuncios", "Resultados",
        "Indicador de resultado", "Costo por resultados",
        "Presupuesto del conjunto de anuncios", "Tipo de presupuesto",
        "Importe gastado (ARS)", "Impresiones", "Alcance", "Frecuencia",
        "CPM (costo por mil impresiones)",
        "CTR (porcentaje de clics en el enlace)", "Clics en el enlace",
        "Identificador del conjunto de anuncios",
    ],
    "anuncio": [
        "Inicio del informe", "Fin del informe", "Nombre del anuncio",
        "Nombre del conjunto de anuncios", "Nombre de la campaña",
        "Entrega del anuncio", "Resultados", "Indicador de resultado",
        "Costo por resultados", "Importe gastado (ARS)", "Impresiones",
        "Alcance", "Frecuencia", "CPM (costo por mil impresiones)",
        "CTR (porcentaje de clics en el enlace)", "Clics en el enlace",
        "Identificador del anuncio",
    ],
}

ARCHIVO = {"campana": "campanas", "conjunto": "conjuntos", "anuncio": "anuncios"}


def moneda(v):
    """'$20.498,46 ARS' -> 20498.46 · '$0,00 ARS' -> 0.0 · None -> ''.
    {'value': '2418.05', 'unit': 'ARS'} -> 2418.05 (formato nuevo del MCP,
    visto por primera vez el 2026-09-22).

    El MCP devolvia la plata formateada en es-AR (punto de miles, coma
    decimal) como string plano. Parsear eso con float() directo da 20.498
    (veinte pesos) en vez de 20.498,46 — ya paso una vez en el canal de
    Google Ads: el gasto salio /1000 y el CPL parecio genial.

    Sin el desarmado del dict, ese mismo bug vuelve al reves: str({'value':
    '2418.05', 'unit': 'ARS'}) deja "2418.05," (la coma que separa las claves
    del dict sobrevive al regex), y el codigo de abajo la lee como el
    decimal es-AR y borra el punto -> 241805.0. Cien veces mas. Medido en la
    guardia del 2026-09-22: el gasto de la ventana salio inflado de ~380.000
    a ~34.000.000 ARS y disparo un G0 falso ("los datos no cierran").
    """
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return moneda(v.get("value"))
    s = str(v)
    # Saca simbolo, codigo de moneda, espacios finos y no-quebrables.
    s = re.sub(r"[^\d,.\-]", "", s.replace(" ", " ").replace(" ", " "))
    if not s or s in ("-", ".", ","):
        return ""
    if "," in s and "." in s:
        # Formato es-AR: el ultimo separador es el decimal.
        s = s.replace(".", "") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return ""


def entero(v):
    n = moneda(v)
    return "" if n == "" else int(round(n))


def porcentaje(v):
    """website_ctr puede venir numerico o como '1,23%'. Sale siempre numerico."""
    if v is None or v == "":
        return ""
    return moneda(str(v).replace("%", ""))


def resultado_de(res):
    """El campo `results` del MCP cambia de forma segun haya datos o no.

    Con datos:  {"indicator": "actions:lead", "values": [{"value": "3", ...}]}
    Sin datos:  {"indicator": "actions:lead", "value": "Not available"}

    Devuelve (cantidad, indicador). 'Not available' es ausencia de dato, NO un
    cero: se devuelve vacio para que el analizador no lo cuente como resultado.
    """
    if not isinstance(res, dict):
        return "", ""
    ind = res.get("indicator") or ""
    vals = res.get("values")
    if isinstance(vals, list) and vals:
        # Se toma la ventana de atribucion por defecto, que es la que reporta
        # el Administrador de anuncios en su vista normal.
        elegida = next((v for v in vals
                        if "default" in (v.get("attribution_windows") or [])), vals[0])
        return entero(elegida.get("value")), ind
    v = res.get("value")
    if v in (None, "", "Not available"):
        return "", ind
    return entero(v), ind


def costo_de(c):
    """cost_per_result: {'value': '$6.832,82 ARS (Leads)'} -> 6832.82"""
    if not isinstance(c, dict):
        return ""
    v = c.get("value")
    if v in (None, "", "Not available") or (isinstance(v, str) and v.startswith("Not available")):
        return ""
    return moneda(re.sub(r"\(.*?\)", "", str(v)))


def nivel_de(fila):
    """El nivel se deduce de que nombres de padre trae la fila."""
    if "adset_name" in fila:
        return "anuncio"
    if "campaign_name" in fila:
        return "conjunto"
    return "campana"


def desanidar(obj):
    """Saca la lista de filas de cualquiera de las formas que guarda el agente."""
    if isinstance(obj, list):
        filas = []
        for x in obj:
            filas.extend(desanidar(x))
        return filas
    if isinstance(obj, dict):
        for clave in ("ad_entities", "ad_drafts", "data", "entities"):
            if clave in obj:
                v = obj[clave]
                # La herramienta devuelve ad_entities como STRING con JSON adentro.
                return desanidar(json.loads(v) if isinstance(v, str) else v)
        # Un dict suelto que ya parece una fila.
        if "id" in obj or "name" in obj:
            return [obj]
    return []


def a_csv(fila, nivel):
    dia = fila.get("date_start") or ""
    fin = fila.get("date_stop") or dia
    cant, ind = resultado_de(fila.get("results"))
    base = {
        "Inicio del informe": dia,
        "Fin del informe": fin,
        "Resultados": cant,
        "Indicador de resultado": ind,
        "Costo por resultados": costo_de(fila.get("cost_per_result")),
        "Importe gastado (ARS)": moneda(fila.get("amount_spent")),
        "Impresiones": entero(fila.get("impressions")),
        "Alcance": entero(fila.get("reach")),
        "Frecuencia": moneda(fila.get("frequency")),
        "CPM (costo por mil impresiones)": moneda(fila.get("cpm")),
        "CTR (porcentaje de clics en el enlace)": porcentaje(fila.get("website_ctr")),
        "Clics en el enlace": entero(fila.get("link_click")),
    }
    estado = fila.get("effective_status") or ""
    if nivel == "campana":
        base.update({
            "Nombre de la campaña": fila.get("name", ""),
            "Entrega de la campaña": estado,
            "Objetivo": fila.get("objective", ""),
            "Identificador de la campaña": fila.get("id", ""),
        })
    elif nivel == "conjunto":
        base.update({
            "Nombre del conjunto de anuncios": fila.get("name", ""),
            "Nombre de la campaña": fila.get("campaign_name", ""),
            "Entrega del conjunto de anuncios": estado,
            "Presupuesto del conjunto de anuncios": moneda(fila.get("daily_budget")
                                                          or fila.get("lifetime_budget")),
            "Tipo de presupuesto": ("Diario" if fila.get("daily_budget")
                                    else ("Total" if fila.get("lifetime_budget") else "")),
            "Identificador del conjunto de anuncios": fila.get("id", ""),
        })
    else:
        base.update({
            "Nombre del anuncio": fila.get("name", ""),
            "Nombre del conjunto de anuncios": fila.get("adset_name", ""),
            "Nombre de la campaña": fila.get("campaign_name", ""),
            "Entrega del anuncio": estado,
            "Identificador del anuncio": fila.get("id", ""),
        })
    return {c: base.get(c, "") for c in COLUMNAS[nivel]}


def convertir(carpeta, desde=None, hasta=None, con_gasto_cero=False):
    origen = os.path.join(carpeta, "mcp")
    if not os.path.isdir(origen):
        print(f"[error] no existe {origen}/ — ahi van los JSON crudos del MCP.",
              file=sys.stderr)
        return 1
    archivos = sorted(glob.glob(os.path.join(origen, "*.json")))
    if not archivos:
        print(f"[error] {origen}/ esta vacio.", file=sys.stderr)
        return 1

    por_nivel, vistos = {}, {}
    for path in archivos:
        with open(path, encoding="utf-8") as fh:
            try:
                crudo = json.load(fh)
            except json.JSONDecodeError as e:
                print(f"[error] {os.path.basename(path)}: JSON invalido ({e}).",
                      file=sys.stderr)
                return 1
        filas = desanidar(crudo)
        if not filas:
            print(f"[aviso] {os.path.basename(path)}: sin filas, se ignora.",
                  file=sys.stderr)
            continue
        for f in filas:
            nivel = nivel_de(f)
            dia = f.get("date_start") or ""
            if desde and dia and dia < desde:
                continue
            if hasta and dia and dia > hasta:
                continue
            gasto = moneda(f.get("amount_spent"))
            if not con_gasto_cero and (gasto == "" or gasto == 0.0):
                continue
            # Una misma entidad y dia puede venir repetida entre paginas: la
            # paginacion del MCP no garantiza cortes limpios. Se deduplica por
            # (id, dia) para no duplicar gasto, que es el error mas caro posible.
            clave = (nivel, f.get("id"), dia)
            if clave in vistos:
                continue
            vistos[clave] = True
            por_nivel.setdefault(nivel, []).append(a_csv(f, nivel))

    if not por_nivel:
        print("[error] no quedo ninguna fila con gasto. Revisar el rango de fechas.",
              file=sys.stderr)
        return 1

    for nivel, filas in sorted(por_nivel.items()):
        dias = sorted({f["Inicio del informe"] for f in filas if f["Inicio del informe"]})
        d0 = desde or (dias[0] if dias else "sin-fecha")
        d1 = hasta or (dias[-1] if dias else "sin-fecha")
        destino = os.path.join(carpeta, f"{ARCHIVO[nivel]}_{d0}_{d1}.csv")
        filas.sort(key=lambda f: (f["Inicio del informe"], f.get("Nombre de la campaña", "")))
        with open(destino, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNAS[nivel])
            w.writeheader()
            w.writerows(filas)
        gasto = sum(f["Importe gastado (ARS)"] for f in filas
                    if isinstance(f["Importe gastado (ARS)"], float))
        entidades = len({f[[c for c in COLUMNAS[nivel] if c.startswith("Nombre del")
                            or c == "Nombre de la campaña"][0]] for f in filas})
        print(f"{os.path.relpath(destino, RAIZ)}")
        print(f"  {len(filas)} filas · {entidades} entidades · "
              f"{len(dias)} dias · {gasto:,.0f} ARS")

    faltan = [n for n in ("campana", "conjunto", "anuncio") if n not in por_nivel]
    if faltan:
        print(f"\n[aviso] sin datos para: {', '.join(faltan)}. "
              "Volver a llamar al MCP en ese nivel antes de analizar.", file=sys.stderr)
    return 0


def autotest():
    """Prueba el parseo contra las formas reales que devuelve el MCP."""
    casos = [
        ("moneda es-AR",      moneda("$20.498,46 ARS"), 20498.46),
        ("moneda cero",       moneda("$0,00 ARS"),      0.0),
        ("moneda millon",     moneda("$3.057.742,00 ARS"),   3057742.0),
        ("moneda numerica",   moneda(1234.5),                1234.5),
        ("moneda nula",       moneda(None),                  ""),
        ("moneda dict nuevo", moneda({"value": "2418.05", "unit": "ARS"}), 2418.05),
        ("ctr con coma",      porcentaje("1,23%"),           1.23),
        ("costo por result",  costo_de({"value": "$6.832,82 ARS (Leads)"}), 6832.82),
        ("costo no disp",     costo_de({"value": "Not available (Leads)"}), ""),
        ("result con datos",  resultado_de({"indicator": "actions:lead",
                                            "values": [{"attribution_windows": ["default"],
                                                        "value": "3"}]}), (3, "actions:lead")),
        ("result no disp",    resultado_de({"indicator": "actions:lead",
                                            "value": "Not available"}), ("", "actions:lead")),
        ("nivel anuncio",     nivel_de({"adset_name": "x", "campaign_name": "y"}), "anuncio"),
        ("nivel conjunto",    nivel_de({"campaign_name": "y"}),  "conjunto"),
        ("nivel campana",     nivel_de({"name": "y"}),           "campana"),
        ("desanidar string",  len(desanidar({"ad_entities": '[{"id":"1","name":"a"}]'})), 1),
    ]
    fallos = 0
    for nombre, obtenido, esperado in casos:
        ok = obtenido == esperado
        fallos += not ok
        print(f"  {'ok  ' if ok else 'FALLA'} {nombre}: {obtenido!r}"
              + ("" if ok else f"  (esperado {esperado!r})"))
    print(f"\n{len(casos) - fallos}/{len(casos)} bien.")
    return 1 if fallos else 0


def main():
    ap = argparse.ArgumentParser(
        description="Traduce las respuestas del MCP de Meta a CSV del Administrador.")
    ap.add_argument("carpeta", nargs="?", help="datos/meta-ads/<AAAA-Www>/")
    ap.add_argument("--desde", help="YYYY-MM-DD, recorta las filas")
    ap.add_argument("--hasta", help="YYYY-MM-DD, recorta las filas")
    ap.add_argument("--con-gasto-cero", action="store_true",
                    help="Conserva las filas sin gasto (por defecto se descartan: "
                         "el MCP devuelve todas las entidades historicas de la cuenta).")
    ap.add_argument("--autotest", action="store_true", help="Prueba el parseo y sale.")
    a = ap.parse_args()
    if a.autotest:
        return autotest()
    if not a.carpeta:
        ap.error("falta la carpeta (o usar --autotest)")
    return convertir(os.path.join(RAIZ, a.carpeta) if not os.path.isabs(a.carpeta)
                     else a.carpeta, a.desde, a.hasta, a.con_gasto_cero)


if __name__ == "__main__":
    sys.exit(main())
