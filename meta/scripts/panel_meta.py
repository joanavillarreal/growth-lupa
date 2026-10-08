#!/usr/bin/env python3
"""
Arma los datos del panel trimestral de Meta Ads.

Que es el panel
---------------
El artefacto semanal contesta "como fue la semana". Este contesta otra cosa:
**como se viene moviendo el canal a lo largo del trimestre, y que le hicimos.**
Pedido de Joana (2026-09-21), Q calendario (Q3 = julio a septiembre).

Este script NO dibuja: junta. Escribe un JSON con la serie diaria y con los
leads uno por uno, y el HTML filtra del lado del navegador (dia / semana / Q).
Por eso no hace falta precalcular cada combinacion: con ~500 leads por trimestre
el JSON pesa poco y cualquier corte sale al instante.

De donde sale cada cosa
-----------------------
    plataforma  datos/meta-ads/guardia/*/mcp/ lo que trae la guardia de cada dia
                datos/meta-ads/**/*.csv      los CSV del lunes y los historicos
    CRM         datos/crm/**/prospectos*.csv etapa, origen, razon, tipo de negocio
    cambios     memoria/cambios.jsonl        las marcas sobre las curvas
    alertas     memoria/alertas.jsonl        + memoria/guardia.jsonl (las diarias)
    experimentos memoria/experimentos.jsonl

**Las definiciones no se reimplementan.** La clasificacion de etapas, el grupo
de negocio y el bloque de campana se importan de analizar_crm.py y
analizar_meta.py: si el panel calculara la derivacion con su propio criterio,
tendriamos dos numeros distintos con el mismo nombre, que es exactamente el
problema que este repo viene evitando desde el principio.

Uso:
    python3 scripts/panel_meta.py --q 2026-Q3
    python3 scripts/panel_meta.py --q 2026-Q3 --json informes/panel/datos.json
    python3 scripts/panel_meta.py --autotest
"""
import argparse, csv, datetime, glob, json, os, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import analizar_crm as crm
from analizar_meta import CONJUNTOS_DE_EVENTO, bloque_de
from meta_desde_mcp import moneda, entero, porcentaje, desanidar, a_csv, resultado_de

SALIDA = os.path.join(RAIZ, "informes", "panel", "datos.json")
HTML = os.path.join(RAIZ, "informes", "panel-trimestral.html")

# Cuantas semanas hacia atras se consideran inmaduras. Una cohorte reciente
# TODAVIA puede convertir: su derivacion es provisional, no un resultado.
# Sin esta marca, la semana en curso siempre parece un derrumbe y alguien
# reacciona a un fantasma.
SEMANAS_INMADURAS = 2


def trimestre(q):
    """'2026-Q3' -> (inicio, fin). Calendario: Q3 es julio a septiembre."""
    anio, n = q.split("-Q")
    anio, n = int(anio), int(n)
    if not 1 <= n <= 4:
        raise SystemExit(f"Trimestre invalido: {q}")
    ini = datetime.date(anio, 3 * n - 2, 1)
    fin = (datetime.date(anio + (n == 4), (3 * n) % 12 + 1, 1)
           - datetime.timedelta(days=1))
    return ini, fin


def q_de(dia):
    return f"{dia.year}-Q{(dia.month - 1) // 3 + 1}"


# ------------------------------------------------------------------ plataforma

# Familias de resultado que son un lead o una conversacion. Solo las campanas
# que optimizan por esto entran al gasto cruzable: el costo por visita al perfil
# de una campana de awareness no se divide por leads del CRM.
FAMILIA_GENERADORA = ("lead", "mensaje", "onsite_conversion.messaging")


def familia_de(indicador):
    i = (indicador or "").lower()
    if "lead" in i:
        return "lead"
    if "messaging" in i or "mensaje" in i:
        return "mensaje"
    return "otra"


def mapa_conjunto_campana():
    """{conjunto: campana}, juntando TODAS las respuestas crudas del MCP.

    Es el dato que los export del Administrador no traen y sin el cual el
    descuento de conjuntos de evento se aplica mal. El nombre de un conjunto es
    estable, asi que un mapa aprendido en septiembre vale para julio.
    `datos/meta-ads/2026-Q3-mapa-conjuntos/` existe solo para esto.
    """
    mapa = {}
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "datos", "meta-ads", "**",
                                              "mcp", "*.json"), recursive=True)):
        try:
            with open(ruta, encoding="utf-8") as f:
                crudo = json.load(f)
        except Exception:                          # noqa: BLE001
            continue
        for fila in desanidar(crudo):
            nom, camp = fila.get("name"), fila.get("campaign_name")
            # Solo filas de CONJUNTO: las de anuncio tambien traen campaign_name
            # pero su `name` es el del anuncio, y mapearlo seria basura.
            if nom and camp and not fila.get("adset_name"):
                mapa.setdefault(nom, camp)
    return mapa


# Lo que la guardia de las 8:00 guarda cada dia y el panel sabe leer. Solo
# niveles campana y conjunto: `anuncio-diario.json` viene cortado en 200 filas
# (medido el 2026-09-27: del 17/09 en adelante le faltan 1.000 a 5.600 ARS por
# dia) y sumarlo daria un gasto menor al real sin que nada falle.
GUARDIA_NIVELES = (("campana-diario.json", "campana"),
                   ("conjunto-diario.json", "conjunto"))


def fuentes_plataforma():
    """(nivel, fila con forma de CSV del Administrador), la fuente mas fresca primero.

    **Por que el orden importa:** `leer_plataforma` se queda con la PRIMERA
    lectura de cada (nivel, dia, entidad). Meta corrige los numeros de un dia
    durante unos dias despues, asi que la foto mas nueva es la que vale:
    primero la guardia —de la corrida mas nueva a la mas vieja—, despues los
    CSV del lunes y los historicos.

    La guardia es lo que vuelve diario al panel: cubre 14 dias terminando ayer,
    todos los dias, sin esperar al lunes. Una entidad que un dia le falta a la
    guardia (el MCP a veces se come filas, G0) se completa con el CSV, porque
    la deduplicacion es por entidad y no por dia.
    """
    carpetas = sorted(glob.glob(os.path.join(RAIZ, "datos", "meta-ads", "guardia",
                                             "*", "mcp")), reverse=True)
    for carpeta in carpetas:
        for archivo, nivel in GUARDIA_NIVELES:
            ruta = os.path.join(carpeta, archivo)
            if not os.path.isfile(ruta):
                continue
            try:
                with open(ruta, encoding="utf-8") as f:
                    crudo = json.load(f)
            except Exception as e:                  # noqa: BLE001
                print(f"[aviso] {os.path.relpath(ruta, RAIZ)} no se pudo leer ({e}).",
                      file=sys.stderr)
                continue
            for fila in desanidar(crudo):
                # Solo filas de UN dia: un total de ventana sumado como si fuera
                # un dia duplicaria el gasto.
                d = fila.get("date_start")
                if not d or fila.get("date_stop", d) != d:
                    continue
                yield nivel, a_csv(fila, nivel)

    for ruta in sorted(glob.glob(os.path.join(RAIZ, "datos", "meta-ads", "**", "*.csv"),
                                 recursive=True)):
        base = os.path.basename(ruta).lower()
        nivel = ("campana" if base.startswith("campana") else
                 "conjunto" if base.startswith("conjunto") else None)
        if nivel is None:
            continue
        with open(ruta, encoding="utf-8-sig", newline="") as fh:
            for fila in csv.DictReader(fh):
                yield nivel, fila


def leer_plataforma(desde, hasta):
    """Serie diaria del gasto, replicando la definicion de analizar_meta.py.

    **El gasto cruzable NO es el gasto total ni "todo lo que no es evento".**
    Es: campanas de *conversion y remarketing* que optimizan por lead o por
    mensaje, MENOS los conjuntos de evento que corren adentro de ellas. El
    awareness queda afuera aunque sea nucleo — sus visitas al perfil no son
    leads y dividirlas contra el CRM no significa nada.

    Se calcula en dos niveles distintos a proposito:
      - el nucleo sale del nivel CAMPANA, porque el nombre de la campana esta
        en todos los export;
      - el descuento de eventos sale del nivel CONJUNTO, por nombre exacto.

    **Un conjunto de evento se descuenta SOLO si cuelga de una campana nucleo.**
    `CONJUNTOS_DE_EVENTO` tiene nombres que hoy viven en campanas eventuales
    propias (Viajes Presenciales, Webinar Mostrador): restarlos igual descuenta
    plata que el numerador nunca sumo y deflacta el gasto cruzable. Mismo bug
    que la corrida del lunes encontro en `analizar_meta.py` el 2026-09-21.

    Para saber de que campana cuelga cada conjunto hace falta el mapa, y ahi hay
    una trampa: **los export reales del Administrador NO traen la columna
    "Nombre de la campaña" a nivel conjunto** — si la traen los que genera el
    MCP. Verificado el 2026-09-22 sobre los CSV de marzo-septiembre. Entonces el
    mapa se arma con TODOS los archivos que si la tienen y se aplica hacia atras:
    el nombre de un conjunto es estable, asi que lo aprendido en septiembre vale
    para julio. **Un conjunto que no aparece en ningun archivo con campana no se
    descuenta** —no se puede probar que cuelgue de una campana nucleo— y queda
    listado en `sin_mapear` para que se vea.
    """
    dias, vistos, campanas = {}, set(), {}
    filas_campana, filas_conjunto = [], []
    camp_dias = {}
    dias_con_conjunto = set()
    mapa_conjunto = mapa_conjunto_campana()

    def dia(d):
        return dias.setdefault(d, {"d": d, "gasto": 0.0, "gasto_nucleo": 0.0,
                                   "gasto_evento_en_nucleo": 0.0,
                                   "resultados_nucleo": 0, "resultados_evento": 0,
                                   "impresiones": 0, "clics": 0})

    for nivel, fila in fuentes_plataforma():
        d = (fila.get("Inicio del informe") or "").strip()[:10]
        if not d or not (desde.isoformat() <= d <= hasta.isoformat()):
            continue
        # Un CSV de varios dias en una sola fila no es una serie diaria.
        fin = (fila.get("Fin del informe") or "").strip()[:10]
        if fin and fin != d:
            continue
        camp = (fila.get("Nombre de la campaña") or "").strip()
        conj = (fila.get("Nombre del conjunto de anuncios") or "").strip()
        # Una entidad puede venir en varias fuentes (la guardia de dos dias
        # seguidos, el semanal y el de 4 semanas): se deduplica por (nivel,
        # dia, nombre) y gana la primera, que es la mas fresca.
        clave = (nivel, d, conj if nivel == "conjunto" else camp)
        if clave in vistos:
            continue
        vistos.add(clave)
        gasto = moneda(fila.get("Importe gastado (ARS)")) or 0.0
        res = entero(fila.get("Resultados")) or 0
        fam = familia_de(fila.get("Indicador de resultado"))
        reg = dia(d)
        if nivel == "campana":
            imp = entero(fila.get("Impresiones")) or 0
            clics = entero(fila.get("Clics en el enlace")) or 0
            reg["gasto"] += gasto
            reg["impresiones"] += imp
            reg["clics"] += clics
            filas_campana.append((d, camp, gasto, res, fam))
            cd = camp_dias.setdefault((d, camp), {"d": d, "c": camp, "g": 0.0,
                                                  "r": 0, "i": 0, "k": 0})
            cd["g"] += gasto
            cd["r"] += res
            cd["i"] += imp
            cd["k"] += clics
            c = campanas.setdefault(camp, {"nombre": camp, "gasto": 0.0,
                                           "resultados": 0,
                                           "bloque": bloque_de(camp),
                                           "familia": "otra"})
            c["gasto"] += gasto
            c["resultados"] += res
            if fam != "otra":
                c["familia"] = fam
        else:
            if camp:
                mapa_conjunto[conj] = camp     # solo los CSV del MCP lo traen
            filas_conjunto.append((d, conj, gasto, res))
            dias_con_conjunto.add(d)

    # Segunda pasada: la familia de una campana se decide con TODAS sus filas.
    # Un dia sin resultados atribuidos deja el indicador vacio, y clasificar fila
    # por fila mandaria esa campana a "otra" solo por ese dia.
    generadoras = {n for n, c in campanas.items()
                   if c["bloque"] in ("conversion", "remarketing")
                   and c["familia"] in ("lead", "mensaje")}
    for d, camp, gasto, res, _fam in filas_campana:
        if camp in generadoras:
            dias[d]["gasto_nucleo"] += gasto
            dias[d]["resultados_nucleo"] += res

    # Tercera pasada: descontar los conjuntos de evento que cuelgan de una
    # campana generadora, y SOLO esos.
    # Solo avisa de los que tienen plata en juego: un conjunto de evento que
    # figura con gasto cero no cambia ningun numero y el aviso seria ruido.
    sin_mapear = {}
    for d, conj, gasto, res in filas_conjunto:
        if conj not in CONJUNTOS_DE_EVENTO:
            continue
        padre = mapa_conjunto.get(conj)
        if padre is None:
            if gasto > 0:
                sin_mapear[conj] = round(sin_mapear.get(conj, 0) + gasto, 2)
            continue
        if padre in generadoras:
            dias[d]["gasto_evento_en_nucleo"] += gasto
            dias[d]["resultados_evento"] += res
    if sin_mapear:
        print("[aviso] conjuntos de evento CON GASTO y sin campana conocida, que NO "
              "se descontaron del gasto cruzable:", file=sys.stderr)
        for n, g in sorted(sin_mapear.items(), key=lambda x: -x[1]):
            print(f"        {g:>12,.0f} ARS  {n}".replace(",", "."), file=sys.stderr)
        print("      Ningun CSV los trae con su campana. Para mapearlos: una llamada "
              "al MCP a nivel conjunto que cubra esos dias, guardada en "
              "datos/meta-ads/<carpeta>/mcp/conjunto.json.", file=sys.stderr)

    for r in dias.values():
        r["gasto_cruzable"] = round(r["gasto_nucleo"] - r["gasto_evento_en_nucleo"], 2)
        r["resultados_cruzables"] = max(0, r["resultados_nucleo"] - r["resultados_evento"])
        for k in ("gasto", "gasto_nucleo", "gasto_evento_en_nucleo"):
            r[k] = round(r[k], 2)
    for c in campanas.values():
        c["gasto"] = round(c["gasto"], 2)
        c["generadora"] = c["nombre"] in generadoras
    serie_camp = [dict(v, g=round(v["g"], 2))
                  for _, v in sorted(camp_dias.items()) if v["g"] or v["r"]]
    # Serie por CONJUNTO (j) con su campana (c): la usa el panel para decir que
    # publico rinde mejor adentro de cada campana. La campana sale del mapa;
    # un conjunto sin campana conocida queda con c = None y no se dibuja.
    conj_dias = {}
    for d, conj, gasto, res in filas_conjunto:
        r = conj_dias.setdefault((d, conj), {"d": d, "j": conj, "c": mapa_conjunto.get(conj),
                                            "g": 0.0, "r": 0})
        r["g"] += gasto
        r["r"] += res
    serie_conj = [dict(v, g=round(v["g"], 2))
                  for _, v in sorted(conj_dias.items()) if v["g"] or v["r"]]
    return {
        "dias": dias,
        "campanas": sorted(campanas.values(), key=lambda c: -c["gasto"]),
        "camp_dias": serie_camp,
        "conj_dias": serie_conj,
        "sin_mapear": sin_mapear,
        "mapa_conjunto": mapa_conjunto,
        # Hasta que dia hay datos a nivel CONJUNTO: sin ellos no se puede
        # descontar un conjunto de evento que corra adentro de una nucleo.
        "conjuntos_hasta": max(dias_con_conjunto) if dias_con_conjunto else None,
    }


# ------------------------------------------------------------------ CRM

def grupos_de_razon():
    """{razon: a quien le corresponde el problema}, de config/taxonomia-lead.yaml.

    Es la distincion que evita el error mas caro del panel: "No responde
    mensajes ni llamada" es la razon dominante del canal (425 de 1.494 en la
    linea base) y **no se arregla tocando Meta**. Mostrada en una lista unica
    con las razones de canal, invita a cambiar campanas para resolver un
    problema de seguimiento comercial.
    """
    etiquetas = {"culpa_del_canal": "Del canal (se arregla en Meta)",
                 "culpa_del_seguimiento": "Del seguimiento comercial",
                 "producto_o_precio": "Producto o precio",
                 "timing": "Timing (nutrir, no descartar)"}
    try:
        import yaml
        with open(os.path.join(RAIZ, "config", "taxonomia-lead.yaml"), encoding="utf-8") as f:
            tax = (yaml.safe_load(f) or {}).get("razones_no_derivacion") or {}
    except Exception as e:                        # noqa: BLE001
        print(f"[aviso] no se pudo leer la taxonomia ({e}): las razones van sin agrupar.",
              file=sys.stderr)
        return {}
    return {r: etiquetas.get(k, k) for k, rs in tax.items() for r in (rs or [])}


def _sin_tildes(s):
    tabla = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    return (s or "").translate(tabla).lower().strip()


def campana_del_lead(utm_term, utm_campaign, mapa_conjunto, nombres_campana):
    """La campana de un lead, SOLO si el UTM la dice. Nunca se deduce del origen.

    El workflow de n8n manda el conjunto en `utm_term` y el nombre del
    formulario en `utm_campaign` (verificado el 2026-09-27: 'Formulario
    anuncios 1' en los 55 leads de formulario desde el 08/09). La campana sale
    entonces del mapa conjunto -> campana que ya arma el panel con las
    respuestas del MCP. Si algun dia `utm_campaign` trae el nombre real de una
    campana, se usa directo.

    Un lead sin UTM, o con un conjunto que ningun archivo mapea, queda SIN
    campana. Repartirlo por el origen seria inventar la atribucion.
    """
    if utm_campaign in nombres_campana:
        return utm_campaign
    if not utm_term:
        return None
    if utm_term in mapa_conjunto:
        return mapa_conjunto[utm_term]
    objetivo = _sin_tildes(utm_term)
    for conj, camp in mapa_conjunto.items():
        if _sin_tildes(conj) == objetivo:
            return camp
    return None


def leer_crm(desde, hasta, mapa_conjunto=None, nombres_campana=()):
    """Un registro por lead, con lo minimo para filtrar del lado del navegador.

    Se leen TODOS los snapshots y se deduplica por ID quedandose con la lectura
    mas reciente: la etapa de un lead cambia con el tiempo y la ultima foto es
    la que vale. Los prospectos se borran de Bitrix, asi que el historico se
    arma de los CSV versionados y nunca se le vuelve a pedir a la API.
    """
    grupos = grupos_de_razon()
    por_id, fuentes = {}, []
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "datos", "crm", "*", "prospectos*.csv"))):
        try:
            filas = crm.leer(ruta)
        except SystemExit:
            print(f"[aviso] {os.path.basename(ruta)} no se pudo leer: se saltea.",
                  file=sys.stderr)
            continue
        fuentes.append(os.path.relpath(ruta, RAIZ))
        # El orden alfabetico de los archivos ya deja al final los mas nuevos;
        # igual se prefiere siempre la fila mas reciente por si eso no se cumple.
        for r in filas:
            rid = crm.col(r, "id")
            if rid:
                por_id[rid] = r

    leads = []
    for r in por_id.values():
        f = r.get("_fecha")
        if not f or not (desde <= f.date() <= hasta):
            continue
        origen = r["_origen"]
        if origen not in crm.ORIGENES:
            continue                              # eventos y otros canales, afuera
        term, ucamp = crm.col(r, "utm_term"), crm.col(r, "utm_campaign")
        leads.append({
            "d": f.date().isoformat(),
            "origen": origen,
            "pago": origen in crm.PAGO,
            "bloque": crm.clasificar(r["_etapa"]),
            "grupo": crm.grupo_negocio(r),
            "razon": crm.col(r, "razon") or "",
            "razon_grupo": grupos.get(crm.col(r, "razon"), "Sin clasificar"),
            "utm": bool(crm.col(r, "utm_content")),
            "camp": campana_del_lead(term, ucamp, mapa_conjunto or {},
                                     set(nombres_campana)),
            "conj": term,
            "ad": crm.col(r, "utm_content"),
            # Lo carga la SDR: separa "no lo pude contactar" de "lo contacte y
            # no sirvio". Vacio es que todavia no lo marco.
            "contacto": crm.col(r, "efectivo"),
            # n8n manda el NOMBRE DEL FORMULARIO en utm_campaign (ver n8n.md).
            # Es la unica forma de confirmar a que formulario apunta un anuncio:
            # el MCP de Meta no expone el formulario del creativo.
            "form": ucamp,
        })
    return sorted(leads, key=lambda x: x["d"]), fuentes


# ------------------------------------------------------------------ hoy

# Las tres lecturas que hace la corrida diaria SOLO para el panel (llamadas
# #8 a #10 de referencias/guardia-diaria.md). La guardia no las usa.
HOY_ARCHIVOS = ("anuncio-activos.json", "conjunto-publicos.json", "anuncio-historico.json")

PRODUCTO = {"boxer_taller": "Boxer Taller"}


def _lista(o):
    """El MCP devuelve las listas del targeting como {"0": x, "1": y}."""
    if isinstance(o, dict):
        return [o[k] for k in sorted(o, key=lambda k: int(k) if str(k).isdigit() else 0)]
    return list(o or [])


def resumir_publico(t):
    """El targeting crudo de un conjunto -> lo que una persona lee en 10 segundos.

    Se queda con lo que define A QUIEN se le muestra: edad, pais, los publicos
    que se incluyen (propios y similares), los intereses y cargos, y los que se
    excluyen. Las ubicaciones (feed, reels, audience network) quedan afuera: no
    dicen a quien, dicen donde, y son 30 lineas de ruido.
    """
    t = t or {}
    geo = t.get("geo_locations") or {}
    lugares = [str(x) for x in _lista(geo.get("countries"))]
    for clave in ("regions", "cities"):
        lugares += [x.get("name", "") for x in _lista(geo.get(clave)) if isinstance(x, dict)]
    incluye = [c.get("name", "") for c in _lista(t.get("custom_audiences")) if isinstance(c, dict)]
    intereses = []
    for fs in _lista(t.get("flexible_spec")):
        for k, v in (fs or {}).items():
            for x in _lista(v):
                if not isinstance(x, dict):
                    continue
                if k == "custom_audiences":
                    incluye.append(x.get("name", ""))
                else:
                    intereses.append(x.get("name", ""))
    excluye = [c.get("name", "") for c in _lista(t.get("excluded_custom_audiences"))
               if isinstance(c, dict)]
    auto = t.get("targeting_automation") or {}
    return {
        "edad": f"{t.get('age_min', 18)} a {t.get('age_max', 65)}",
        "lugar": ", ".join(lugares) or "—",
        "incluye": [x for x in incluye if x],
        "intereses": [x for x in intereses if x],
        "excluye": [x for x in excluye if x],
        # Advantage+ encendido: Meta puede salir del publico definido.
        "advantage": bool(auto.get("advantage_audience")),
    }


def _leer_mcp(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return desanidar(json.load(f))
    except Exception as e:                          # noqa: BLE001
        print(f"[aviso] {os.path.relpath(ruta, RAIZ)} no se pudo leer ({e}).", file=sys.stderr)
        return []


def leer_creativos():
    """{creative_id: creativo}, de TODOS los creativos.json guardados (llamada #11).

    Se busca de la corrida mas nueva a la mas vieja y gana la primera lectura de
    cada creativo. Asi la corrida diaria solo tiene que pedir los creative_id
    que todavia no estan guardados: un creativo no cambia de texto sin cambiar
    de id (Meta crea uno nuevo al editarlo; visto el 2026-10-07 con la placa
    de Bariloche).

    `ads_get_creatives` devuelve {"ad_creatives": [...]}, que desanidar() no
    conoce: se lee aparte.
    """
    out = {}
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "datos", "meta-ads", "guardia", "*",
                                              "mcp", "creativos*.json")), reverse=True):
        try:
            with open(ruta, encoding="utf-8") as f:
                crudo = json.load(f)
        except Exception as e:                      # noqa: BLE001
            print(f"[aviso] {os.path.relpath(ruta, RAIZ)} no se pudo leer ({e}).",
                  file=sys.stderr)
            continue
        filas = crudo.get("ad_creatives", crudo) if isinstance(crudo, dict) else crudo
        for c in (filas or []):
            if isinstance(c, dict) and c.get("id"):
                out.setdefault(str(c["id"]), c)
    return out


def leer_hoy():
    """Lo que esta corriendo hoy, de la corrida diaria mas nueva que lo trajo.

    Tres fuentes, las tres de la misma corrida:
      anuncio-activos.json    los anuncios en ACTIVE ahora (no el roster de las
                              8:00: una campana creada a media manana no estaria)
      conjunto-publicos.json  cada conjunto activo con su targeting y lo que
                              genero desde que se creo (date_preset maximum)
      anuncio-historico.json  cada anuncio con gasto de las campanas activas,
                              desde que se creo: es la base de Tendencias

    **Solo cuenta ACTIVE.** El MCP tambien devuelve WITH_ISSUES de campanas de
    2024-2025 que estan apagadas: contarlas inflaria "lo que corre hoy" con
    cosas que no gastan.
    """
    carpetas = sorted(glob.glob(os.path.join(RAIZ, "datos", "meta-ads", "guardia", "*", "mcp")),
                      reverse=True)
    carpeta = next((c for c in carpetas
                    if all(os.path.isfile(os.path.join(c, a)) for a in HOY_ARCHIVOS)), None)
    if not carpeta:
        return None
    activos, conjuntos, historico = (_leer_mcp(os.path.join(carpeta, a)) for a in HOY_ARCHIVOS)
    creativos = leer_creativos()
    try:
        with open(os.path.join(RAIZ, "config", "campanas.json"), encoding="utf-8") as f:
            cfg = {c["nombre"]: c for c in json.load(f).get("campanas", [])}
    except Exception:                               # noqa: BLE001
        cfg = {}

    def ficha(nombre):
        c = cfg.get(nombre, {})
        bloque = c.get("bloque") or bloque_de(nombre)
        if bloque == "eventual":
            bloque = "evento"
        origenes = c.get("origenes_crm")
        return {"nombre": nombre, "bloque": bloque,
                "producto": PRODUCTO.get(c.get("producto"), "Boxer Gestión"),
                "destino": c.get("destino", ""),
                # A que origen de Bitrix entran sus leads, y que formulario usa
                # segun el mapa. "PENDIENTE" o ausente = sin confirmar.
                "origenes": origenes if isinstance(origenes, list) else None,
                "formulario": c.get("formulario"),
                # Por que no entra a Bitrix, cuando origenes_crm es [] a proposito.
                "motivo": c.get("motivo"),
                "en_config": bool(c)}

    activos = [a for a in activos if a.get("effective_status") == "ACTIVE"]
    campanas = {}
    for a in activos:
        c = campanas.setdefault(a["campaign_name"], dict(ficha(a["campaign_name"]),
                                                         anuncios=[], conjuntos=[]))
        cr = creativos.get(str(a.get("creative_id") or ""), {})
        c["anuncios"].append({
            "nombre": a.get("name", ""), "conjunto": a.get("adset_name", ""),
            "creado": (a.get("created_time") or "")[:10], "id": a.get("id", ""),
            # Lo que vio la persona antes de dejar sus datos: la SDR lo
            # necesita para saber que se le prometio.
            "titulo": cr.get("title") or "", "texto": cr.get("body") or "",
            "descripcion": cr.get("description") or "",
            "cta": cr.get("call_to_action_type") or "", "tipo": cr.get("object_type") or "",
            # pageid_postid: facebook.com/<esto> abre el posteo del anuncio.
            "post": cr.get("effective_object_story_id") or "",
        })
    for x in conjuntos:
        if x.get("effective_status") != "ACTIVE":
            continue
        c = campanas.setdefault(x["campaign_name"], dict(ficha(x["campaign_name"]),
                                                         anuncios=[], conjuntos=[]))
        cant, ind = resultado_de(x.get("results"))
        c["conjuntos"].append({
            "nombre": x.get("name", ""),
            "creado": (x.get("created_time") or "")[:10],
            "presupuesto": moneda(x.get("daily_budget")) or None,
            "publico": resumir_publico(x.get("targeting")),
            "gasto": moneda(x.get("amount_spent")) or 0.0,
            "resultados": cant or 0,
            "indicador": ind,
            "alcance": entero(x.get("reach")) or 0,
        })

    anuncios = []
    for x in historico:
        cant, ind = resultado_de(x.get("results"))
        anuncios.append({
            "nombre": x.get("name", ""), "campana": x.get("campaign_name", ""),
            "conjunto": x.get("adset_name", ""), "estado": x.get("effective_status", ""),
            "creado": (x.get("created_time") or "")[:10],
            "gasto": moneda(x.get("amount_spent")) or 0.0, "resultados": cant or 0,
            "indicador": ind, "impresiones": entero(x.get("impressions")) or 0,
            "clics": entero(x.get("link_click")) or 0,
            "ctr": porcentaje(x.get("website_ctr")) or None,
            "frecuencia": moneda(x.get("frequency")) or None,
        })
    return {
        "foto": os.path.basename(os.path.dirname(carpeta)),
        "con_creativos": bool(creativos),
        # Anuncios activos cuyo creativo no esta en ningun creativos.json:
        # son los que la corrida tiene que pedir con la llamada #11.
        "creativos_faltantes": sorted({a.get("creative_id") for a in activos
                                       if a.get("creative_id")
                                       and str(a.get("creative_id")) not in creativos}),
        "campanas": sorted(campanas.values(), key=lambda c: (c["producto"], c["bloque"], c["nombre"])),
        "anuncios": anuncios,
    }


# ------------------------------------------------------------------ memoria

def leer_jsonl(ruta):
    if not os.path.isfile(ruta):
        return []
    out = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            try:
                out.append(json.loads(linea))
            except json.JSONDecodeError:
                print(f"[aviso] linea invalida en {os.path.basename(ruta)}, se saltea.",
                      file=sys.stderr)
    return out


def leer_memoria(desde, hasta):
    m = os.path.join(RAIZ, "memoria")
    en_rango = lambda d: bool(d) and desde.isoformat() <= d[:10] <= hasta.isoformat()

    # Lupa (08/10/2026): los cambios salen del registro de actividad de Meta
    # (scripts/cambios_desde_actividad.py), las alertas solo de la guardia propia, y los
    # experimentos de la solapa Experimentos del Monitor (scripts/experimentos_desde_monitor.py).
    # Lo que escribía agente-meta-ads quedó en memoria/archivo/ y ya no se lee.
    cambios = [c for c in leer_jsonl(os.path.join(m, "cambios-actividad.jsonl"))
               if en_rango(c.get("fecha"))]

    alertas = []   # las del análisis semanal son de Turbo: llegarán por su parte
    # Las de la guardia diaria entran como alertas tambien: son del mismo canal
    # y Joana las quiere ver en el mismo lugar.
    for g in leer_jsonl(os.path.join(m, "guardia.jsonl")):
        alertas.append({
            "id": g.get("clave", ""), "abierta": g.get("primer_aviso"),
            "cerrada": g.get("resuelta_el"), "severidad": "media",
            "titulo": g.get("titulo", ""), "entidad": g.get("entidad", ""),
            "estado": g.get("estado", "abierta"), "origen_alerta": "guardia diaria",
        })
    # Una alerta cuenta en el trimestre si estuvo VIVA en algun momento de el:
    # abierta antes y todavia sin cerrar tambien cuenta.
    vivas = [a for a in alertas
             if (a.get("abierta") or "") <= hasta.isoformat()
             and (not a.get("cerrada") or a["cerrada"] >= desde.isoformat())]

    exps = [e for e in leer_jsonl(os.path.join(m, "experimentos-monitor.jsonl"))
            if (e.get("abierto") or "") <= hasta.isoformat()]
    return cambios, vivas, exps


# ------------------------------------------------------------------ armado

def construir(q, hoy=None):
    hoy = hoy or datetime.date.today()
    desde, hasta = trimestre(q)
    # El trimestre anterior entra entero para poder comparar: julio contra
    # junio, y el Q contra el mismo tramo del Q anterior. El HTML lo usa solo
    # como base de comparacion y como trimestre elegible.
    q_ant = q_de(desde - datetime.timedelta(days=1))
    desde_ant, _ = trimestre(q_ant)
    # Nunca mas alla de ayer: el dia en curso esta a medio cargar en Meta.
    tope = min(hasta, hoy - datetime.timedelta(days=1))
    plat = leer_plataforma(desde_ant, tope)
    dias = plat["dias"]
    leads, fuentes = leer_crm(desde_ant, tope, plat["mapa_conjunto"],
                              [c["nombre"] for c in plat["campanas"]])
    cambios, alertas, exps = leer_memoria(desde, hasta)

    serie = [dias[d] for d in sorted(dias)]
    en_q = [x["d"] for x in serie if x["d"] >= desde.isoformat()]
    dias_con_leads = sorted({l["d"] for l in leads if l["d"] >= desde.isoformat()})
    corte_inmaduro = (hoy - datetime.timedelta(weeks=SEMANAS_INMADURAS)).isoformat()

    return {
        "generado": hoy.isoformat(),
        "q": {"id": q, "desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "q_anterior": {"id": q_ant, "desde": desde_ant.isoformat(),
                       "hasta": (desde - datetime.timedelta(days=1)).isoformat()},
        "cobertura": {
            "plataforma_desde": en_q[0] if en_q else None,
            "plataforma_hasta": en_q[-1] if en_q else None,
            "conjuntos_hasta": plat["conjuntos_hasta"],
            "crm_desde": dias_con_leads[0] if dias_con_leads else None,
            "crm_hasta": dias_con_leads[-1] if dias_con_leads else None,
            "fuentes_crm": fuentes,
        },
        # Todo lo que el navegador necesita para recortar cualquier ventana.
        # Incluye el trimestre anterior: el HTML recorta.
        "dias": serie,
        "leads": leads,
        "campanas": plat["campanas"],
        "camp_dias": plat["camp_dias"],
        "conj_dias": plat["conj_dias"],
        "cambios": cambios,
        "alertas": alertas,
        "experimentos": exps,
        "cohorte_inmadura_desde": corte_inmaduro,
        # La vista "Dia a dia" y Tendencias. None si ninguna corrida lo trajo.
        "hoy": leer_hoy(),
        "conjuntos_evento_sin_mapear": plat["sin_mapear"],   # {conjunto: gasto no descontado}
        "limites": {
            "atribucion_por_anuncio_desde": "2026-09-08",
            "nota_atribucion": (
                "Antes del 08/09 el CRM no guardaba ni un UTM: para esas fechas "
                "NO se puede saber que anuncio trajo un lead, y el panel no lo "
                "muestra. Inventarlo esta prohibido."),
            "nota_cambios": (
                "Las marcas de cambios salen del registro de actividad de Meta, desde el "
                "2026-09-21: dicen qué cambió, quién y cuándo, no el porqué."),
            "nota_cohorte": (
                f"Los leads de las ultimas {SEMANAS_INMADURAS} semanas todavia "
                f"pueden convertir: su derivacion es PROVISIONAL."),
        },
    }


def resumen(datos):
    """Lo que se imprime en consola. El panel calcula lo suyo en el navegador;
    esto es para que la corrida vea que trajo sin abrir el HTML."""
    q = datos["q"]
    d = [x for x in datos["dias"] if x["d"] >= q["desde"]]
    gasto = sum(x["gasto"] for x in d)
    cruz = sum(x["gasto_cruzable"] for x in d)
    res = sum(x["resultados_cruzables"] for x in d)
    pagos = [l for l in datos["leads"] if l["pago"] and l["d"] >= q["desde"]]
    resueltos = [l for l in pagos if l["bloque"] in ("convertido", "no_util", "inactivo", "otra")]
    conv = [l for l in resueltos if l["bloque"] == "convertido"]
    print(f"Panel {q['id']} ({q['desde']} a {q['hasta']}) · generado {datos['generado']}")
    print(f"  dias con datos de plataforma : {len(d)}")
    print(f"  gasto total                  : {gasto:,.0f} ARS".replace(",", "."))
    print(f"  gasto cruzable (nucleo - ev.): {cruz:,.0f} ARS".replace(",", "."))
    print(f"  resultados cruzables (Meta)  : {res}")
    print(f"  leads pagos en el CRM        : {len(pagos)}")
    if res:
        print(f"  ubicados Meta -> CRM         : {len(pagos) / res * 100:.0f}%")
    if cruz and len(pagos):
        print(f"  CPL real                     : {cruz / len(pagos):,.0f} ARS"
              .replace(",", "."))
    if resueltos:
        print(f"  derivacion                   : {len(conv) / len(resueltos) * 100:.1f}% "
              f"({len(conv)} de {len(resueltos)} resueltos)")
    if cruz and conv:
        print(f"  costo por Convertido         : {cruz / len(conv):,.0f} ARS"
              .replace(",", "."))
    con_camp = sum(1 for l in pagos if l["camp"])
    print(f"  leads con campana (UTM)      : {con_camp} de {len(pagos)}")
    cob = datos["cobertura"]
    if cob["conjuntos_hasta"] and cob["plataforma_hasta"] \
            and cob["conjuntos_hasta"] < cob["plataforma_hasta"]:
        print(f"  [aviso] hay datos de conjunto solo hasta {cob['conjuntos_hasta']}: "
              f"despues de esa fecha no se descuentan conjuntos de evento dentro "
              f"de campanas nucleo. Falta conjunto-diario.json en la guardia.")
    h = datos.get("hoy")
    if h:
        n = sum(len(c["anuncios"]) for c in h["campanas"])
        print(f"  hoy ({h['foto']})              : {len(h['campanas'])} campanas activas, "
              f"{n} anuncios activos, {len(h['anuncios'])} anuncios en Tendencias")
    else:
        print("  [aviso] no hay anuncio-activos / conjunto-publicos / anuncio-historico en "
              "ninguna corrida: la vista Dia a dia sale vacia.")
    print(f"  cambios marcados             : {len(datos['cambios'])}")
    print(f"  alertas vivas en el Q        : {len(datos['alertas'])}")


def main():
    ap = argparse.ArgumentParser(description="Datos del panel trimestral de Meta Ads.")
    ap.add_argument("--q", default=None, help="2026-Q3. Por defecto, el trimestre de hoy.")
    ap.add_argument("--json", default=SALIDA)
    ap.add_argument("--html", default=HTML,
                    help="HTML donde se reinyectan los datos. Por defecto, el panel.")
    ap.add_argument("--sin-html", action="store_true",
                    help="Solo escribe el JSON, no toca el HTML.")
    ap.add_argument("--hoy", help="AAAA-MM-DD, para pruebas.")
    ap.add_argument("--autotest", action="store_true")
    a = ap.parse_args()
    if a.autotest:
        return autotest()

    hoy = datetime.date.fromisoformat(a.hoy) if a.hoy else datetime.date.today()
    datos = construir(a.q or q_de(hoy), hoy)
    os.makedirs(os.path.dirname(a.json), exist_ok=True)
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    resumen(datos)
    print(f"\n  -> {os.path.relpath(a.json, RAIZ)} "
          f"({os.path.getsize(a.json) / 1024:.0f} KB)")
    if not a.sin_html:
        inyectar(a.html, datos)
        print(f"  -> {os.path.relpath(a.html, RAIZ)} (datos reinyectados)")
    if not datos["dias"]:
        print("\n[!] No hay datos de plataforma en el trimestre. El panel saldria vacio.")
        return 1
    return 0


def inyectar(html, datos):
    """Mete el JSON adentro de <script type="application/json" id="datos">.

    Antes esto era un paso a mano, y si se olvidaba el panel quedaba mostrando
    los datos viejos sin que nada fallara. Ahora lo hace el script siempre.
    `</` se escapa para que un texto con "</script>" no corte el bloque.
    """
    import re
    with open(html, encoding="utf-8") as f:
        txt = f.read()
    carga = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    patron = re.compile(r'(<script type="application/json" id="datos">)(.*?)(</script>)', re.S)
    if not patron.search(txt):
        raise SystemExit(f"[error] {html} no tiene el bloque <script id=\"datos\">.")
    nuevo = patron.sub(lambda m: m.group(1) + carga + m.group(3), txt, count=1)
    with open(html, "w", encoding="utf-8") as f:
        f.write(nuevo)


# ------------------------------------------------------------------ autotest

def autotest():
    fallas = []

    def chequear(nombre, ok):
        print(("  ok   " if ok else "  FALLA") + f" {nombre}")
        if not ok:
            fallas.append(nombre)

    chequear("Q3 es julio a septiembre",
             trimestre("2026-Q3") == (datetime.date(2026, 7, 1), datetime.date(2026, 9, 30)))
    chequear("Q1 es enero a marzo",
             trimestre("2026-Q1") == (datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)))
    chequear("Q4 cierra el 31 de diciembre",
             trimestre("2026-Q4") == (datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)))
    chequear("Q2 cierra el 30 de junio",
             trimestre("2026-Q2")[1] == datetime.date(2026, 6, 30))
    chequear("el trimestre de una fecha de septiembre es Q3",
             q_de(datetime.date(2026, 9, 22)) == "2026-Q3")
    chequear("el 1 de julio ya es Q3", q_de(datetime.date(2026, 7, 1)) == "2026-Q3")

    chequear("conversiones y remarketing son bloques generadores",
             bloque_de("JY | Conversiones") == "conversion"
             and bloque_de("JY | Remarketing") == "remarketing")
    chequear("un webinar es eventual aunque no lo diga el config",
             bloque_de("JY | Webinar Mostrador - 17 SEPT") == "eventual")
    chequear("awareness NO es bloque generador: sus visitas no son leads",
             bloque_de("JY | Awareness") == "awareness")
    chequear("la familia sale del indicador de resultado",
             familia_de("actions:lead") == "lead"
             and familia_de("actions:onsite_conversion.messaging_conversation_started_7d") == "mensaje"
             and familia_de("profile_visit_view") == "otra")

    chequear("las definiciones del CRM se importan, no se reescriben",
             crm.clasificar("Convertido") == "convertido"
             and crm.clasificar("Prospecto inactivo") == "inactivo"
             and crm.clasificar("Formularios Meta") == "abierta")

    # Una alerta abierta antes del trimestre y todavia sin cerrar cuenta en el Q.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        global RAIZ
        real = RAIZ
        os.makedirs(os.path.join(tmp, "memoria"))
        # Las alertas salen solo de la guardia de Lupa (memoria/guardia.jsonl).
        with open(os.path.join(tmp, "memoria", "guardia.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"clave": "VIEJA", "primer_aviso": "2026-05-01", "resuelta_el": None,
                                "estado": "abierta", "titulo": "x"}) + "\n")
            f.write(json.dumps({"clave": "CERRADA-ANTES", "primer_aviso": "2026-04-01",
                                "resuelta_el": "2026-05-02", "estado": "resuelta",
                                "titulo": "y"}) + "\n")
            f.write(json.dumps({"clave": "FUTURA", "primer_aviso": "2026-11-01", "resuelta_el": None,
                                "estado": "abierta", "titulo": "z"}) + "\n")
        RAIZ = tmp
        try:
            _, vivas, _ = leer_memoria(datetime.date(2026, 7, 1), datetime.date(2026, 9, 30))
        finally:
            RAIZ = real
        ids = {a["id"] for a in vivas}
        chequear("una alerta abierta antes del Q y sin cerrar cuenta en el Q",
                 "VIEJA" in ids)
        chequear("una cerrada antes del Q no cuenta", "CERRADA-ANTES" not in ids)
        chequear("una abierta despues del Q no cuenta", "FUTURA" not in ids)

    # El bug que la corrida del lunes encontro el 2026-09-21: un conjunto de
    # evento que vive en su PROPIA campana eventual no se descuenta del nucleo.
    generadoras = {"JY | Conversiones"}
    mapa = {"Conjunto 1 - Frio nacional": "JY | Webinar Mostrador - 17 SEPT 2026",
            "Lead Magnet": "JY | Conversiones"}
    def descuenta(conj):
        padre = mapa.get(conj)
        return padre is not None and padre in generadoras
    chequear("un conjunto de evento dentro de una campana nucleo SI se descuenta",
             descuenta("Lead Magnet"))
    chequear("un conjunto de evento en su propia campana eventual NO se descuenta",
             not descuenta("Conjunto 1 - Frio nacional"))
    chequear("un conjunto sin campana conocida NO se descuenta",
             not descuenta("Campana Presencialidad Cordoba"))

    mapa = {"Conversión segmentación similar": "JY | Conversiones",
            "Remarketing": "JY | Remarketing"}
    chequear("la campana de un lead sale del conjunto del UTM",
             campana_del_lead("Remarketing", "Formulario anuncios 1", mapa, set())
             == "JY | Remarketing")
    chequear("el conjunto del UTM se encuentra aunque venga sin tildes",
             campana_del_lead("Conversion segmentacion similar", "", mapa, set())
             == "JY | Conversiones")
    chequear("un lead sin UTM queda sin campana: no se reparte por el origen",
             campana_del_lead("", "", mapa, {"JY | Conversiones"}) is None)
    chequear("un conjunto que ningun archivo mapea queda sin campana",
             campana_del_lead("Conjunto nuevo", "Formulario anuncios 1", mapa, set()) is None)
    chequear("si utm_campaign trae el nombre real de la campana, se usa",
             campana_del_lead("", "JY | Conversiones", mapa, {"JY | Conversiones"})
             == "JY | Conversiones")

    g = grupos_de_razon()
    chequear("la razon dominante del canal se clasifica como seguimiento, no como pauta",
             g.get("No responde mensajes ni llamada") == "Del seguimiento comercial")
    chequear("una razon de rubro equivocado si es del canal",
             g.get("No tiene negocio, negocio de otro rubro") == "Del canal (se arregla en Meta)")
    chequear("la plata en es-AR se lee bien", moneda("$20.498,46 ARS") == 20498.46)
    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
