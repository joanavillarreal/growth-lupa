#!/usr/bin/env python3
"""
Procesa los exports del Administrador de anuncios de Meta y calcula el gasto,
el costo por resultado y el estado estructural de la cuenta.

Uso:
    python3 scripts/analizar_meta.py datos/meta-ads/<carpeta>/
    python3 scripts/analizar_meta.py <carpeta> --desde 2026-08-10 --hasta 2026-09-06
    python3 scripts/analizar_meta.py <carpeta> --json informes/<AAAA-Www>/meta.json

Espera en la carpeta los CSV de Campanas, Conjuntos de anuncios y Anuncios
(los reconoce por el nombre del archivo o por sus columnas). Los exports salen
con **una fila por dia y por entidad**, asi que todo se agrega antes de mirar.

Lo que NO hace: cruzar con el CRM. Eso es analizar_crm.py. El cruce de los dos
—cuanto gasto contra cuantos leads llegaron de verdad— se hace en el informe.
"""
import argparse, csv, datetime, glob, json, os, sys
from collections import defaultdict

# Que campanas son "nucleo" del canal y cuales son eventuales.
#
# Decision de Joana (2026-09-08): lo que se mide todos los lunes y jueves contra
# el CRM son las campanas de AWARENESS, CONVERSION y REMARKETING. Las demas
# (webinars, cursos, demos en vivo, visitas presenciales, lead magnets, ferias)
# son fluctuantes, se prenden y se apagan segun lo que haya, y **sus leads caen
# en otros origenes del CRM**, cada uno con el suyo. Mezclarlas rompe el cruce.
#
# Se clasifica por el nombre de la campana. Si aparece una campana nueva que no
# matchea nada, cae en "eventual" y el script lo avisa: revisarla y, si es
# nucleo, agregar su patron aca.
BLOQUES_NUCLEO = [
    ("conversion",  ["conversion", "conversiones", "clientes potenciales",
                     "formulario", "formularios", "whatsapp"]),
    ("remarketing", ["remarketing", "retargeting"]),
    ("awareness",   ["awareness", "seguidores", "reconocimiento", "alcance"]),
]
# Marcadores que ganan sobre lo anterior: si el nombre trae alguno de estos, la
# campana es eventual aunque tambien diga "conversion".
MARCAS_EVENTUAL = [
    "webinar", "curso", "clase", "demo", "presencial", "visita", "evento",
    "automechanika", "feria", "lead magnet", "charla", "conversatorio",
    "black friday", "aniversario", "entrevista", "tienda nube", "guia",
]

# Y ademas: hay conjuntos DE EVENTO viviendo adentro de campanas de conversion.
# Ese es el caso mas traicionero, porque la campana dice "Conversiones" pero sus
# leads caen en otros origenes del CRM (Curso en vivo IA, Demo masiva, Visita
# Presencial...). Si no se descuentan, el CPL del canal sale inflado y parece que
# se pierden leads que en realidad estan en otro lado.
#
# La lista es explicita a proposito: es una decision de negocio, no un patron.
# El script avisa cuando aparece un conjunto nuevo que no esta clasificado.
CONJUNTOS_DE_EVENTO = {
    "Lead Magnet",
    "Campaña Demo Masiva - Luciana - 30JUL",
    "Campaña Demo Masiva - Santiago - 13 AGO",
    "Campaña Demo Masiva - Santiago",
    "Clases de IA en vivo - Joa y Pri",
    "After Automechanika",
    "Campaña Presencialidad Cordoba",
    "Campaña Presencialidad Neuquen",
    "Campaña Presencialidad Rosario",
    "Campaña Presencialidad Adquisicion",
    "Campaña Webinar Marketing",
    "Demo en VIVO Presencial",
    "Entrevista en vivo - Campana Repuestos",
    "Guia | Boxer Taller",
    "Tienda Nube",
    "Conjunto 1 - Frio nacional",          # webinar mostrador
    "Mendoza - Frio - LAL CRM - Video",    # visita presencial
    "San Juan- Frio - LAL CRM - Video",    # visita presencial
}

# El "Indicador de resultado" dice que esta contando cada campana. Dos campanas
# con indicadores distintos NO tienen resultados comparables entre si.
FAMILIA = {
    "actions:lead": ("lead", "Formulario (lead ad)"),
    "onsite_conversion.lead_grouped": ("lead", "Formulario (lead ad)"),
    "actions:onsite_conversion.messaging_conversation_started_7d":
        ("mensaje", "Conversacion de WhatsApp"),
    "profile_visit_view": ("awareness", "Visita al perfil"),
    "actions:post_engagement": ("interaccion", "Interaccion con la publicacion"),
    "actions:link_click": ("trafico", "Clic en el enlace"),
}


def _sin_tildes(s):
    return s.translate(str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")).lower()


def bloque_de(nombre):
    """Clasifica el nombre de una CAMPANA. No sirve para conjuntos: para eso
    esta CONJUNTOS_DE_EVENTO, que es una lista explicita.

    'JY | Remarketing' -> 'remarketing'. Lo que no matchea es 'eventual'."""
    n = _sin_tildes(nombre)
    if any(m in n for m in MARCAS_EVENTUAL):
        return "eventual"
    for bloque, claves in BLOQUES_NUCLEO:
        if any(k in n for k in claves):
            return bloque
    return "eventual"


def num(v):
    if v in ("", "-", None):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def leer(carpeta):
    """Devuelve {nivel: (columna_de_nombre, filas)} para los CSV que encuentre."""
    niveles = {
        "campana":  "Nombre de la campaña",
        "conjunto": "Nombre del conjunto de anuncios",
        "anuncio":  "Nombre del anuncio",
    }
    out = {}
    archivos = sorted(f for f in glob.glob(os.path.join(carpeta, "*.csv"))
                      if os.path.isfile(f))
    for path in archivos:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            cols = rd.fieldnames or []
            filas = list(rd)
        # El nivel es el mas fino de los que aparecen como columna de nombre:
        # el export de Anuncios tambien trae el nombre del conjunto.
        for nivel in ("anuncio", "conjunto", "campana"):
            if niveles[nivel] in cols:
                if nivel in out:
                    print(f"[aviso] dos archivos para el nivel '{nivel}'; "
                          f"se usa el ultimo: {os.path.basename(path)}", file=sys.stderr)
                out[nivel] = (niveles[nivel], filas, os.path.basename(path))
                break
        else:
            print(f"[aviso] {os.path.basename(path)}: no se reconocio el nivel, se ignora.",
                  file=sys.stderr)
    return out


def agregar(filas, clave_nombre, desde=None, hasta=None, extra=None):
    """Suma las filas diarias por entidad. Devuelve {nombre: bloque}."""
    agg = defaultdict(lambda: {
        "gasto_ars": 0.0, "resultados": 0.0, "impresiones": 0, "alcance": 0,
        "clics_enlace": 0.0, "dias_con_gasto": set(), "indicadores": set(),
        "entrega": set(), "conjunto": set(), "presupuesto": set(),
    })
    for r in filas:
        dia = r.get("Inicio del informe", "")
        # Sin `time_increment` no hay fecha por fila (la fila ya es el total
        # de la ventana pedida en el MCP): no hay granularidad mas fina para
        # filtrar, asi que esa fila pasa siempre. Filtrarla por desde/hasta
        # comparando contra "" la descartaba entera. Bug corregido 2026-09-21.
        if dia:
            if desde and dia < desde:
                continue
            if hasta and dia > hasta:
                continue
        a = agg[r[clave_nombre]]
        g = num(r.get("Importe gastado (ARS)"))
        imp = int(num(r.get("Impresiones")))
        a["gasto_ars"] += g
        a["resultados"] += num(r.get("Resultados"))
        a["impresiones"] += imp
        a["alcance"] += int(num(r.get("Alcance")))
        # El CTR viene en % por dia: se reconstruyen los clics para poder
        # promediar ponderado en vez de promediar porcentajes.
        a["clics_enlace"] += imp * num(r.get("CTR (porcentaje de clics en el enlace)")) / 100.0
        if g > 0:
            a["dias_con_gasto"].add(dia)
        if r.get("Indicador de resultado"):
            a["indicadores"].add(r["Indicador de resultado"])
        if r.get("Entrega de la campaña") or r.get("Entrega del conjunto de anuncios") \
                or r.get("Entrega del anuncio"):
            a["entrega"].add(r.get("Entrega de la campaña")
                             or r.get("Entrega del conjunto de anuncios")
                             or r.get("Entrega del anuncio"))
        if extra and extra in r and r[extra]:
            a["conjunto"].add(r[extra])
        if r.get("Presupuesto del conjunto de anuncios"):
            a["presupuesto"].add(r["Presupuesto del conjunto de anuncios"])
    salida = {}
    for nombre, a in agg.items():
        dias = sorted(a["dias_con_gasto"])
        ind = sorted(a["indicadores"])
        fam, etiqueta = ("desconocido", "sin indicador")
        for i in ind:
            if i in FAMILIA:
                fam, etiqueta = FAMILIA[i]
                break
        salida[nombre] = {
            "gasto_ars": round(a["gasto_ars"], 2),
            "resultados": round(a["resultados"]),
            "costo_por_resultado_ars": (round(a["gasto_ars"] / a["resultados"])
                                        if a["resultados"] else None),
            "impresiones": a["impresiones"],
            # El alcance es una metrica de personas UNICAS: sumar las filas
            # diarias cuenta varias veces a quien vio el anuncio en mas de un
            # dia, e infla el numero. Con filas diarias el alcance unico del
            # periodo NO se puede reconstruir: hay que leerlo del
            # Administrador de anuncios. Se deja la suma con un nombre que
            # dice lo que es, y el alcance real solo cuando hay un solo dia.
            "alcance": a["alcance"] if len(a["dias_con_gasto"]) <= 1 else None,
            "alcance_sumado_dias": a["alcance"],
            "frecuencia": (round(a["impresiones"] / a["alcance"], 2)
                           if a["alcance"] and len(a["dias_con_gasto"]) <= 1 else None),
            "ctr_enlace_pct": (round(100.0 * a["clics_enlace"] / a["impresiones"], 3)
                               if a["impresiones"] else None),
            "cpm_ars": (round(1000.0 * a["gasto_ars"] / a["impresiones"])
                        if a["impresiones"] else None),
            "primer_dia": dias[0] if dias else None,
            "ultimo_dia": dias[-1] if dias else None,
            "dias_con_gasto": len(dias),
            "indicadores": ind,
            "familia": fam,
            "que_cuenta": etiqueta,
            "entrega": sorted(a["entrega"]),
            "conjuntos": sorted(a["conjunto"]),
            "presupuesto": sorted(a["presupuesto"]),
        }
    return salida


def anuncios_por_conjunto(filas, desde=None, hasta=None):
    """Cuantos anuncios distintos GASTARON en cada conjunto. El problema
    estructural de esta cuenta se mide aca: 1 anuncio por conjunto significa
    que Meta no tiene entre que elegir."""
    m = defaultdict(lambda: defaultdict(float))
    for r in filas:
        dia = r.get("Inicio del informe", "")
        # Sin `time_increment` no hay fecha por fila (la fila ya es el total
        # de la ventana pedida en el MCP): no hay granularidad mas fina para
        # filtrar, asi que esa fila pasa siempre. Filtrarla por desde/hasta
        # comparando contra "" la descartaba entera. Bug corregido 2026-09-21.
        if dia:
            if desde and dia < desde:
                continue
            if hasta and dia > hasta:
                continue
        g = num(r.get("Importe gastado (ARS)"))
        if g > 0:
            m[r["Nombre del conjunto de anuncios"]][r["Nombre del anuncio"]] += g
    out = {}
    for cj, anuncios in m.items():
        out[cj] = {
            "anuncios": len(anuncios),
            "gasto_ars": round(sum(anuncios.values()), 2),
            "detalle": {a: round(g, 2) for a, g in
                        sorted(anuncios.items(), key=lambda kv: -kv[1])},
        }
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["gasto_ars"]))


def relevancia(filas, desde=None, hasta=None):
    """Ultimo valor no vacio de los tres diagnosticos de relevancia por anuncio.
    Meta solo los publica cuando hay volumen suficiente, asi que la mayoria de
    los anuncios no los tiene: eso ya es un dato."""
    ult = {}
    for r in filas:
        dia = r.get("Inicio del informe", "")
        # Sin `time_increment` no hay fecha por fila (la fila ya es el total
        # de la ventana pedida en el MCP): no hay granularidad mas fina para
        # filtrar, asi que esa fila pasa siempre. Filtrarla por desde/hasta
        # comparando contra "" la descartaba entera. Bug corregido 2026-09-21.
        if dia:
            if desde and dia < desde:
                continue
            if hasta and dia > hasta:
                continue
        cal = r.get("Clasificación de calidad", "")
        if cal in ("", "-"):
            continue
        nom = r["Nombre del anuncio"]
        if nom not in ult or dia > ult[nom]["fecha"]:
            ult[nom] = {"fecha": dia, "calidad": cal,
                        "interaccion": r.get("Clasificación del porcentaje de interacción", ""),
                        "conversion": r.get("Clasificación del porcentaje de conversiones", "")}
    return ult


def serie_semanal(filas, clave_nombre, familias, desde=None, hasta=None):
    """Gasto y resultados por semana ISO, SOLO de las campanas que generan leads.

    Mezclar familias aca es el error facil: una visita al perfil y un lead
    sumarian al mismo contador y el costo por resultado semanal saldria sin
    sentido (una semana con mucho awareness "abarata" el lead). El gasto de las
    otras familias se reporta aparte, en `gasto_no_lead_ars`.
    """
    sem = defaultdict(lambda: {"gasto_ars": 0.0, "resultados": 0.0, "impresiones": 0,
                               "alcance": 0, "clics": 0.0, "gasto_no_lead_ars": 0.0})
    for r in filas:
        dia = r.get("Inicio del informe", "")
        if not dia or (desde and dia < desde) or (hasta and dia > hasta):
            continue
        d = datetime.date.fromisoformat(dia)
        y, w, _ = d.isocalendar()
        s = sem[f"{y}-W{w:02d}"]
        imp = int(num(r.get("Impresiones")))
        if familias.get(r[clave_nombre]) not in ("lead", "mensaje"):
            s["gasto_no_lead_ars"] += num(r.get("Importe gastado (ARS)"))
            continue
        s["gasto_ars"] += num(r.get("Importe gastado (ARS)"))
        s["resultados"] += num(r.get("Resultados"))
        s["impresiones"] += imp
        s["alcance"] += int(num(r.get("Alcance")))
        s["clics"] += imp * num(r.get("CTR (porcentaje de clics en el enlace)")) / 100.0
    out = {}
    for k in sorted(sem):
        s = sem[k]
        lunes = datetime.date.fromisocalendar(int(k[:4]), int(k[-2:]), 1)
        out[k] = {
            "rango": f"lun {lunes:%d/%m} a dom {lunes + datetime.timedelta(days=6):%d/%m}",
            "gasto_ars": round(s["gasto_ars"]),
            "gasto_no_lead_ars": round(s["gasto_no_lead_ars"]),
            "resultados": round(s["resultados"]),
            "costo_por_resultado_ars": (round(s["gasto_ars"] / s["resultados"])
                                        if s["resultados"] else None),
            "impresiones": s["impresiones"],
            "ctr_enlace_pct": (round(100.0 * s["clics"] / s["impresiones"], 3)
                               if s["impresiones"] else None),
            "cpm_ars": (round(1000.0 * s["gasto_ars"] / s["impresiones"])
                        if s["impresiones"] else None),
        }
    return out


def mil(n):
    return f"{n:,.0f}".replace(",", ".") if n is not None else "-"


def imprimir(res):
    r = res["rango"]
    print(f"\nRANGO: {r['desde']} a {r['hasta']}")
    t = res["totales"]
    print(f"GASTO TOTAL: {mil(t['gasto_ars'])} ARS   ({mil(t['impresiones'])} impresiones)")

    print("\n== GASTO POR TIPO DE RESULTADO ==")
    print(f"{'':34}{'gasto ARS':>14}{'% del total':>13}{'resultados':>12}{'costo/result':>14}")
    for fam, b in res["por_familia"].items():
        cpr = mil(b["costo_por_resultado_ars"]) if b["costo_por_resultado_ars"] else "-"
        print(f"{b['que_cuenta'][:32]:34}{mil(b['gasto_ars']):>14}"
              f"{b['pct_del_total']:>12}%{b['resultados']:>12}{cpr:>14}")
    print("\n  OJO: los resultados de familias distintas NO son comparables entre si.")
    print("  Un 'resultado' de awareness es una visita al perfil; uno de lead es un lead.")

    print("\n== NUCLEO vs EVENTUAL ==")
    print("  (nucleo = awareness, conversion y remarketing: lo que se mide contra el CRM.")
    print("   eventual = webinars, cursos, demos, presenciales: sus leads caen en otros")
    print("   origenes del CRM, con su propio origen cada uno.)")
    print(f"\n{'':16}{'gasto ARS':>14}{'% total':>10}{'resultados':>12}  campanas")
    for k, b in res["por_bloque"].items():
        print(f"{k:16}{mil(b['gasto_ars']):>14}{b['pct_del_total']:>9}%{b['resultados']:>12}"
              f"  {len(b['campanas'])}")
    ev = res.get("conjuntos_de_evento", {})
    g = res["gasto_cruzable_con_crm"]
    print(f"\n  Nucleo que genera leads          {mil(g['gasto_bruto_nucleo_ars']):>12} ARS")
    print(f"  menos conjuntos de evento        {mil(ev.get('gasto_ars', 0)):>12} ARS "
          f"({ev.get('resultados', 0)} resultados, {len(ev.get('detalle', {}))} conjuntos)")
    print(f"  = GASTO CRUZABLE CON EL CRM      {mil(g['gasto_ars']):>12} ARS  ·  "
          f"{g['resultados_que_cobra_meta']} resultados que cobra Meta")
    print(f"    Dividir por los leads que llegaron al CRM (analizar_crm.py) = CPL real.")
    if ev.get("sin_clasificar"):
        print(f"\n  [!] conjuntos que parecen de evento y NO estan en la lista:")
        for n in ev["sin_clasificar"]:
            print(f"        {n}")
        print(f"      Revisarlos y agregarlos a CONJUNTOS_DE_EVENTO si corresponde.")

    print("\n== CAMPANAS ==")
    print(f"{'':46}{'gasto ARS':>13}{'result':>8}{'costo/r':>10}  periodo")
    for nom, b in res["campanas"].items():
        cpr = mil(b["costo_por_resultado_ars"]) if b["costo_por_resultado_ars"] else "-"
        per = (f"{b['primer_dia'][5:]}->{b['ultimo_dia'][5:]} ({b['dias_con_gasto']}d)"
               if b["primer_dia"] else "sin gasto")
        print(f"{nom[:44]:46}{mil(b['gasto_ars']):>13}{b['resultados']:>8}{cpr:>10}  {per}")
        print(f"{'':46}{b['bloque']} · {b['que_cuenta']}")

    print("\n== ANUNCIOS ACTIVOS POR CONJUNTO  <- el problema estructural ==")
    print(f"{'':52}{'anuncios':>10}{'gasto ARS':>14}")
    flacos = 0
    for cj, b in res["anuncios_por_conjunto"].items():
        marca = "  <- 1 solo anuncio" if b["anuncios"] == 1 else ""
        if b["anuncios"] < res["minimo_anuncios"]:
            flacos += 1
        print(f"{cj[:50]:52}{b['anuncios']:>10}{mil(b['gasto_ars']):>14}{marca}")
    print(f"\n  {flacos} de {len(res['anuncios_por_conjunto'])} conjuntos por debajo del "
          f"minimo de {res['minimo_anuncios']} anuncios.")

    print("\n== ANUNCIOS (por gasto) ==")
    print(f"{'':46}{'gasto ARS':>13}{'result':>8}{'costo/r':>10}{'frec':>7}{'CTR%':>8}")
    for nom, b in list(res["anuncios"].items())[:25]:
        cpr = mil(b["costo_por_resultado_ars"]) if b["costo_por_resultado_ars"] else "-"
        print(f"{nom[:44]:46}{mil(b['gasto_ars']):>13}{b['resultados']:>8}{cpr:>10}"
              f"{b['frecuencia'] if b['frecuencia'] is not None else '-':>7}"
              f"{b['ctr_enlace_pct'] if b['ctr_enlace_pct'] is not None else '-':>8}")
    if len(res["anuncios"]) > 25:
        print(f"  ... y {len(res['anuncios']) - 25} anuncios mas (estan en el JSON)")

    if res["relevancia"]:
        print("\n== DIAGNOSTICOS DE RELEVANCIA (ultimo valor publicado) ==")
        for nom, v in sorted(res["relevancia"].items(), key=lambda kv: kv[1]["fecha"], reverse=True):
            print(f"  {v['fecha']}  {nom[:36]:38} calidad={v['calidad'][:34]}")
            print(f"{'':14}interaccion={v['interaccion'][:34]:36} conversion={v['conversion'][:34]}")
    print(f"\n  Solo {len(res['relevancia'])} de {len(res['anuncios'])} anuncios tienen "
          f"diagnostico publicado. Meta los publica recien con volumen suficiente:")
    print("  que falten en la mayoria ya dice que los anuncios no juntan datos.")

    print("\n== POR SEMANA ==")
    print(f"{'':32}{'gasto ARS':>13}{'result':>8}{'costo/r':>10}{'CPM':>9}{'CTR%':>8}")
    for k, s in res["por_semana"].items():
        cpr = mil(s["costo_por_resultado_ars"]) if s["costo_por_resultado_ars"] else "-"
        print(f"{k + ' (' + s['rango'] + ')':32}{mil(s['gasto_ars']):>13}{s['resultados']:>8}"
              f"{cpr:>10}{mil(s['cpm_ars']):>9}"
              f"{s['ctr_enlace_pct'] if s['ctr_enlace_pct'] is not None else '-':>8}")

    print("\n== ALERTAS ==")
    for a in res["alertas"]:
        print(f"  [!] {a}")
    print()


MINIMO_ANUNCIOS = 3          # config/umbrales.yaml -> creativos
FRECUENCIA_MAXIMA = 2.5


def alertas(res):
    out = []
    conj = res["anuncios_por_conjunto"]
    flacos = {c: b for c, b in conj.items() if b["anuncios"] < MINIMO_ANUNCIOS}
    if flacos:
        gasto = sum(b["gasto_ars"] for b in flacos.values())
        pct = round(100.0 * gasto / res["totales"]["gasto_ars"], 1) if res["totales"]["gasto_ars"] else 0
        out.append(
            f"CREATIVOS: {len(flacos)} de {len(conj)} conjuntos corren con menos de "
            f"{MINIMO_ANUNCIOS} anuncios, y concentran {mil(gasto)} ARS ({pct}% del gasto). "
            f"Con un solo anuncio Meta no tiene entre que elegir y no hay aprendizaje "
            f"de creativo posible.")
    solos = [c for c, b in conj.items() if b["anuncios"] == 1]
    if len(solos) >= 3:
        out.append(f"FRAGMENTACION: {len(conj)} conjuntos activos, {len(solos)} de ellos con "
                   f"un unico anuncio. Con este volumen de leads, repartir en muchos "
                   f"conjuntos chicos hace que ninguno junte los ~50 eventos que necesita "
                   f"para salir de la fase de aprendizaje. Consolidar.")
    for nom, b in res["anuncios"].items():
        if b.get("frecuencia") and b["frecuencia"] > FRECUENCIA_MAXIMA:
            out.append(f"FATIGA: '{nom[:45]}' acumula frecuencia {b['frecuencia']} "
                       f"(techo {FRECUENCIA_MAXIMA}).")
    # OJO: que una campana figure con 0 resultados NO alcanza para alertar. El
    # export de Campanas a veces sale sin la columna de indicador para una
    # campana entera, y entonces sus resultados vienen vacios aunque a nivel
    # conjunto si esten. Solo se alerta cuando el indicador SI esta y aun asi
    # no hubo ni un resultado.
    for nom, b in res["campanas"].items():
        if b["gasto_ars"] > 50000 and not b["resultados"]:
            if b["indicadores"]:
                out.append(f"SIN RESULTADOS: '{nom[:45]}' gasto {mil(b['gasto_ars'])} ARS "
                           f"optimizando por {b['que_cuenta']} y no registro ni un "
                           f"resultado. Revisar la configuracion.")
            else:
                out.append(f"EXPORT INCOMPLETO: '{nom[:45]}' gasto {mil(b['gasto_ars'])} ARS "
                           f"y el export no trae su indicador de resultado, asi que sus "
                           f"resultados salen en cero. NO concluir que no rindio: buscar "
                           f"sus conjuntos en el export de Conjuntos.")
    ev = res.get("por_bloque", {}).get("eventual")
    if ev and ev["pct_del_total"] > 15:
        out.append(f"REPARTO NUCLEO/EVENTUAL: {ev['pct_del_total']}% del gasto "
                   f"({mil(ev['gasto_ars'])} ARS) esta en campanas eventuales "
                   f"(webinars, cursos, demos, presenciales). Sus leads caen en otros "
                   f"origenes del CRM: NO se cruzan con los KPI de este canal.")
    fams = res["por_familia"]
    no_lead = sum(b["gasto_ars"] for f, b in fams.items() if f not in ("lead", "mensaje"))
    if res["totales"]["gasto_ars"]:
        pct = round(100.0 * no_lead / res["totales"]["gasto_ars"], 1)
        out.append(f"REPARTO: {pct}% del gasto ({mil(no_lead)} ARS) fue a objetivos que no "
                   f"generan leads (awareness, trafico, interaccion). No esta mal por si "
                   f"solo — es una decision de embudo — pero tiene que ser deliberada.")
    if not out:
        out.append("Sin alertas de plataforma.")
    return out


def analizar(carpeta, desde=None, hasta=None):
    datos = leer(carpeta)
    faltan = [n for n in ("campana", "conjunto", "anuncio") if n not in datos]
    if "campana" not in datos:
        raise SystemExit("Falta el export de Campanas: sin el no hay cifra de gasto.")
    if faltan:
        print(f"[aviso] faltan los exports de: {', '.join(faltan)}. "
              f"Los bloques que dependen de ellos quedan sin cubrir.", file=sys.stderr)

    camp_col, camp_filas, camp_arch = datos["campana"]
    campanas = agregar(camp_filas, camp_col, desde, hasta)
    dias = [r["Inicio del informe"] for r in camp_filas if r.get("Inicio del informe")]
    dias = [d for d in dias if (not desde or d >= desde) and (not hasta or d <= hasta)]

    res = {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "carpeta": carpeta,
        "archivos": {k: v[2] for k, v in datos.items()},
        # Sin `time_increment` (ventanas largas, regla de volumen) no hay fecha
        # por fila: `dias` queda vacio y el rango no se puede derivar de los
        # datos. En ese caso, usar el rango que pidio quien llamo al script
        # (--desde/--hasta) en vez de dejarlo en null — sin esto, cruzar.py
        # corta con "el JSON de Meta no trae rango" aunque el caller SI lo haya
        # dado. Bug encontrado y corregido 2026-09-21.
        "rango": {"desde": (min(dias) if dias else desde),
                  "hasta": (max(dias) if dias else hasta)},
        "minimo_anuncios": MINIMO_ANUNCIOS,
        "campanas": dict(sorted(campanas.items(), key=lambda kv: -kv[1]["gasto_ars"])),
        "conjuntos": {}, "anuncios": {}, "anuncios_por_conjunto": {}, "relevancia": {},
    }
    if "conjunto" in datos:
        col, filas, _ = datos["conjunto"]
        res["conjuntos"] = dict(sorted(
            agregar(filas, col, desde, hasta, extra="Nombre de la campaña").items(),
            key=lambda kv: -kv[1]["gasto_ars"]))
    if "anuncio" in datos:
        col, filas, _ = datos["anuncio"]
        res["anuncios"] = dict(sorted(
            agregar(filas, col, desde, hasta, extra="Nombre del conjunto de anuncios").items(),
            key=lambda kv: -kv[1]["gasto_ars"]))
        res["anuncios_por_conjunto"] = anuncios_por_conjunto(filas, desde, hasta)
        res["relevancia"] = relevancia(filas, desde, hasta)

    total_g = sum(b["gasto_ars"] for b in campanas.values())
    res["totales"] = {
        "gasto_ars": round(total_g, 2),
        "impresiones": sum(b["impresiones"] for b in campanas.values()),
        "campanas_con_gasto": sum(1 for b in campanas.values() if b["gasto_ars"] > 0),
    }

    # --- nucleo vs eventual (decision de Joana, 2026-09-08) ---
    bloq = defaultdict(lambda: {"gasto_ars": 0.0, "resultados": 0, "campanas": []})
    for nom, b in campanas.items():
        b["bloque"] = bloque_de(nom)
        x = bloq[b["bloque"]]
        x["gasto_ars"] += b["gasto_ars"]
        x["resultados"] += b["resultados"]
        x["campanas"].append(nom)
    for x in bloq.values():
        x["gasto_ars"] = round(x["gasto_ars"], 2)
        x["pct_del_total"] = round(100.0 * x["gasto_ars"] / total_g, 1) if total_g else 0
    orden = ["conversion", "remarketing", "awareness", "eventual"]
    res["por_bloque"] = {k: bloq[k] for k in orden if k in bloq}

    # El gasto que se cruza con el CRM: campanas nucleo que generan leads,
    # MENOS los conjuntos de evento que viven ADENTRO DE ESAS MISMAS campanas.
    # Ojo: CONJUNTOS_DE_EVENTO tiene nombres que hoy cuelgan de campanas
    # eventuales propias (Viajes Presenciales, Webinar Mostrador), no de
    # conversion/remarketing. Si se restan de gasto_gen igual, se descuenta
    # plata que gasto_gen nunca conto: por eso el filtro de abajo exige que
    # el conjunto cuelgue de una campana nucleo. Bug encontrado y corregido
    # 2026-09-21 (ver memoria/aprendizajes.md) — hasta esa fecha el gasto
    # cruzable salia deflactado cuando estos conjuntos vivian en campanas
    # eventuales.
    nombres_campanas_nucleo = {
        n for n, b in campanas.items()
        if b["bloque"] in ("conversion", "remarketing") and b["familia"] in ("lead", "mensaje")
    }
    gen = [campanas[n] for n in nombres_campanas_nucleo]
    gasto_gen = sum(b["gasto_ars"] for b in gen)
    res_gen = sum(b["resultados"] for b in gen)

    ev_g = ev_r = 0.0
    ev_detalle, sin_clasificar = {}, []
    for nom, b in res.get("conjuntos", {}).items():
        campanas_del_conjunto = set(b.get("conjuntos", []))
        if nom in CONJUNTOS_DE_EVENTO and campanas_del_conjunto & nombres_campanas_nucleo:
            ev_g += b["gasto_ars"]
            ev_r += b["resultados"]
            ev_detalle[nom] = {"gasto_ars": b["gasto_ars"], "resultados": b["resultados"],
                                "campana": sorted(campanas_del_conjunto)}
        elif b["gasto_ars"] > 0 and any(m in _sin_tildes(nom) for m in MARCAS_EVENTUAL):
            sin_clasificar.append(nom)

    res["conjuntos_de_evento"] = {
        "gasto_ars": round(ev_g, 2),
        "resultados": round(ev_r),
        "detalle": ev_detalle,
        "sin_clasificar": sin_clasificar,
        "nota": ("Conjuntos de evento (cursos, demos, presenciales, lead magnets) que "
                 "corren adentro de campanas de conversion. Sus leads caen en OTROS "
                 "origenes del CRM, con su propio origen cada uno, asi que se descuentan "
                 "del cruce del canal. Ver referencias/calculos.md."),
    }
    res["gasto_cruzable_con_crm"] = {
        "gasto_ars": round(gasto_gen - ev_g, 2),
        "resultados_que_cobra_meta": round(res_gen - ev_r),
        "gasto_bruto_nucleo_ars": round(gasto_gen, 2),
        "descontado_conjuntos_de_evento_ars": round(ev_g, 2),
        "nota": ("Campanas nucleo (conversion y remarketing) que optimizan por lead o "
                 "por mensaje, menos los conjuntos de evento. Es el numerador del CPL "
                 "real: se divide por los leads que efectivamente llegaron al CRM con "
                 "origen 'Meta Ads' o 'Meta Ads Formulario' (analizar_crm.py), no por "
                 "los resultados que reporta Meta."),
    }

    fam = defaultdict(lambda: {"gasto_ars": 0.0, "resultados": 0, "que_cuenta": ""})
    for b in campanas.values():
        f = fam[b["familia"]]
        f["gasto_ars"] += b["gasto_ars"]
        f["resultados"] += b["resultados"]
        f["que_cuenta"] = b["que_cuenta"]
    for f, b in fam.items():
        b["gasto_ars"] = round(b["gasto_ars"], 2)
        b["pct_del_total"] = round(100.0 * b["gasto_ars"] / total_g, 1) if total_g else 0
        b["costo_por_resultado_ars"] = (round(b["gasto_ars"] / b["resultados"])
                                        if b["resultados"] else None)
    res["por_familia"] = dict(sorted(fam.items(), key=lambda kv: -kv[1]["gasto_ars"]))
    familias = {n: b["familia"] for n, b in campanas.items()}
    res["por_semana"] = serie_semanal(camp_filas, camp_col, familias, desde, hasta)
    if "anuncio" in datos and "Nombre de la campaña" not in (datos["anuncio"][1][0].keys()
                                                             if datos["anuncio"][1] else {}):
        res.setdefault("limitaciones", []).append(
            "El export de Anuncios no trae la columna 'Nombre de la campana', asi que no "
            "se puede reconstruir campana -> conjunto -> anuncio. Pedir esa columna en el "
            "proximo export (ver referencias/meta-exports.md).")
    res.setdefault("limitaciones", []).append(
        "ALCANCE Y FRECUENCIA: con filas diarias no se puede reconstruir el alcance "
        "unico de un periodo (sumar los alcances diarios cuenta varias veces a la misma "
        "persona). Por eso 'alcance' y 'frecuencia' vienen en null cuando el periodo "
        "tiene mas de un dia, y la suma queda en 'alcance_sumado_dias' solo como cota "
        "superior. Para la frecuencia real hay que leerla del Administrador de anuncios. "
        "Corregido el 2026-09-10: antes se reportaba la suma como si fuera alcance unico, "
        "lo que SUBESTIMABA la frecuencia (caso medido: 1,23 reportado contra 2,12 real).")
    res["alertas"] = alertas(res)
    return res


def main():
    ap = argparse.ArgumentParser(description="KPIs de plataforma desde los exports de Meta Ads.")
    ap.add_argument("carpeta", help="Carpeta con los CSV del Administrador de anuncios")
    ap.add_argument("--desde", help="Fecha inicial YYYY-MM-DD")
    ap.add_argument("--hasta", help="Fecha final YYYY-MM-DD")
    ap.add_argument("--json", help="Escribir el resultado como JSON en esta ruta")
    a = ap.parse_args()
    res = analizar(a.carpeta, a.desde, a.hasta)
    imprimir(res)
    if a.json:
        os.makedirs(os.path.dirname(a.json) or ".", exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
        print(f"JSON escrito en {a.json}\n")


if __name__ == "__main__":
    main()
