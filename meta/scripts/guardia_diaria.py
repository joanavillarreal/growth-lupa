#!/usr/bin/env python3
"""
La guardia diaria del canal de Meta Ads. Corre todos los dias a las 8:00 ART y
**calla si no hay nada que decir**.

Para que existe
---------------
Joana no tiene que entrar al Administrador de anuncios a buscar si algo se
rompio. La guardia entra por ella todos los dias, mira cuatro cosas y solo
escribe a Slack cuando encuentra algo NUEVO:

  G0  la cuenta dejo de gastar, o los datos que trajo el MCP no cierran
  G1  errores de entrega en entidades que estan ACTIVAS hoy
  G2  un anuncio activo que gasta y no trae ningun resultado hace N dias
  G3  el CPL subiendo o el CTR cayendo N dias seguidos
  G4  plata que se esta yendo sin volver: un evento que ya paso y sigue
      gastando, un anuncio quemando al mismo publico, y cuanto de la ventana
      se fue a anuncios que no trajeron nada

No hace analisis de negocio: eso es la corrida del lunes, que cruza con el CRM.
La guardia mira solo la plataforma y solo busca deterioro.

El silencio es el estado normal
-------------------------------
Una alerta que se manda todos los dias deja de leerse. Por eso el estado vive en
memoria/guardia.jsonl y una alerta ya avisada no se repite: solo vuelve si
**escala** (el problema crece) o si pasaron los dias de recordatorio.

Uso
---
    python3 scripts/guardia_diaria.py datos/meta-ads/guardia/<AAAA-MM-DD>/
    python3 scripts/guardia_diaria.py <carpeta> --hoy 2026-09-15 --dry-run
    python3 scripts/guardia_diaria.py --autotest      # prueba las reglas, no toca disco

Entra por <carpeta>/mcp/ (lo que dejo el agente al llamar al MCP):
    anuncio-diario.json    nivel ad,       ventana, time_increment "1"
    anuncio-total.json     nivel ad,       ventana, SIN time_increment   (control)
    campana-diario.json    nivel campaign, ventana, time_increment "1"
    campana-total.json     nivel campaign, ventana, SIN time_increment   (control)
    errores.json           ads_get_errors sobre la cuenta
    roster.json            las TRES llamadas de roster (campana, conjunto,
                           anuncio) por effective_status, en un mismo archivo
Las llamadas exactas estan en referencias/guardia-diaria.md. No improvisarlas.

Codigos de salida:
    0 = corrio bien (haya o no alertas; mirar SIN NOVEDADES / MENSAJE DE SLACK)
    1 = faltan insumos o estan rotos -> no se puede opinar, avisar y cortar
"""
import argparse, datetime, json, os, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

from meta_desde_mcp import moneda, entero, porcentaje, resultado_de, desanidar
# G5 cruza con el CRM y necesita saber que resultados de Meta DEBERIAN aparecer
# ahi. Esas definiciones ya existen y no se reimplementan: el bloque de una
# campana y la lista de conjuntos de evento salen de analizar_meta, igual que
# en el panel. Si el criterio cambia, cambia en un solo lugar.
from analizar_meta import FAMILIA, CONJUNTOS_DE_EVENTO, bloque_de

ESTADO_POR_DEFECTO = os.path.join(RAIZ, "memoria", "guardia.jsonl")
UMBRALES_YAML = os.path.join(RAIZ, "config", "umbrales.yaml")
CAMPANAS_JSON = os.path.join(RAIZ, "config", "campanas.json")

# Estados en los que una entidad TODAVIA le importa a la guardia. Un error sobre
# algo pausado o archivado es historia: la cuenta arrastra decenas y ahogan lo
# que si pasa hoy.
ESTADOS_VIVOS = {"ACTIVE", "WITH_ISSUES", "PENDING_REVIEW", "DISAPPROVED",
                 "PENDING_BILLING_INFO", "IN_PROCESS", "PREAPPROVED"}

# OJO: el estado propio del anuncio NO alcanza para saber si esta corriendo.
# Medido el 2026-09-15 en esta cuenta: 70 anuncios devolvieron effective_status
# WITH_ISSUES y 57 de ellos cuelgan de campanas apagadas hace meses
# ("Hot Sale Mayo 2025", "Campana de Mensajes - Publico Similar 3%"). El estado
# del hijo no hereda la pausa del padre. Por eso una entidad esta viva solo si
# SU CAMPANA esta viva, y por eso el roster se pide en tres niveles.

# Indicadores de resultado que son un lead. Solo sobre estos tiene sentido
# hablar de CPL: el costo por visita al perfil de una campana de awareness no se
# compara contra el objetivo de 3.000 ARS.
INDICADORES_LEAD = ("actions:lead", "lead", "onsite_conversion.lead_grouped",
                    "offsite_conversion.fb_pixel_lead")

DEFAULTS = {
    "ventana_dias": 14,
    "gasto_minimo_diario_ars": 1000,
    "sin_resultados": {"dias_seguidos": 2, "gasto_dia_1_ars": 6000},
    "ctr": {"caida_pct": 25, "impresiones_minimas_por_dia": 1500,
            "dias_seguidos": 3, "impresiones_minimas_base": 3000},
    "cpl": {"suba_pct": 30, "resultados_minimos_dia_base": 3,
            "dias_seguidos": 3, "resultados_minimos_base": 5},
    "gasto_innecesario": {
        "evento_vencido_dias_gracia": 1,
        "frecuencia_maxima_ventana": 5.0,
        "gasto_sin_resultado_pct": 10,
        "gasto_sin_resultado_minimo_ars": 20000,
    },
    "conciliacion_crm": {
        "minimo_leads_meta": 4,
        "ventana_conciliacion_dias": 7,
        "piso_conciliacion_pct": 25,
        "minimo_leads_meta_ventana": 10,
    },
    "dia_sin_leads": {"gasto_minimo_ars": 5000},
    "repeticion": {"recordar_cada_dias": 7, "escalada_dias": 3},
    "control_totales_tolerancia_pct": 1.0,
}


# ---------------------------------------------------------------- umbrales

def cargar_umbrales(ruta=UMBRALES_YAML):
    """Lee config/umbrales.yaml -> guardia_diaria. Sin el, usa los defaults.

    La guardia no se cae por una dependencia que falta: un dia sin guardia es
    un dia sin mirar la cuenta.
    """
    u = json.loads(json.dumps(DEFAULTS))          # copia profunda
    try:
        import yaml
        with open(ruta, encoding="utf-8") as f:
            bloque = (yaml.safe_load(f) or {}).get("guardia_diaria") or {}
    except Exception as e:                        # noqa: BLE001
        print(f"[aviso] no se pudo leer {os.path.basename(ruta)} ({e}). "
              f"Se usan los umbrales por defecto del script.", file=sys.stderr)
        return u
    for k, v in bloque.items():
        if isinstance(v, dict) and isinstance(u.get(k), dict):
            u[k].update(v)
        else:
            u[k] = v
    return u


# ---------------------------------------------------------------- lectura

def fechas_de_evento(ruta=CAMPANAS_JSON):
    """{nombre de campana: fecha del evento} desde config/campanas.json.

    El campo `fecha_evento` es opcional y lo carga Joana cuando da de alta una
    campana de evento. Sin el, G4a no puede opinar sobre esa campana — y eso es
    correcto: adivinar la fecha del nombre ("17 SEPT 2026") funciona hasta que
    una campana se llama distinto y el agente apaga plata por una corazonada.
    """
    try:
        with open(ruta, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:                        # noqa: BLE001
        print(f"[aviso] no se pudo leer campanas.json ({e}): G4a no corre.",
              file=sys.stderr)
        return {}
    return {c["nombre"]: c["fecha_evento"] for c in cfg.get("campanas", [])
            if c.get("fecha_evento")}


def leer(carpeta, nombre, obligatorio=True, sub="mcp"):
    ruta = os.path.join(carpeta, sub, nombre)
    if not os.path.isfile(ruta):
        if obligatorio:
            raise FileNotFoundError(ruta)
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def filas(obj):
    """Normaliza una respuesta del MCP a una lista de filas comparables."""
    salida = []
    for f in desanidar(obj or []):
        cant, ind = resultado_de(f.get("results"))
        salida.append({
            "id": str(f.get("id") or ""),
            "nombre": f.get("name") or "",
            "campana": f.get("campaign_name") or "",
            "conjunto": f.get("adset_name") or "",
            "dia": f.get("date_start") or "",
            "gasto": moneda(f.get("amount_spent")) or 0.0,
            "impresiones": entero(f.get("impressions")) or 0,
            "clics": entero(f.get("link_click")) or 0,
            "ctr": porcentaje(f.get("website_ctr")),
            "frecuencia": moneda(f.get("frequency")),
            "resultados": cant,
            "indicador": ind,
            "estado": f.get("effective_status") or "",
        })
    return salida


def ars(n):
    """37709.4 -> '37.709'. Formato es-AR, que es como reporta la cuenta.

    Escribir '37,709 ARS' en un aviso invita a leerlo como treinta y siete pesos.
    Es la misma trampa que el parseo al reves, del otro lado.
    """
    return f"{n:,.0f}".replace(",", ".")


def dias_de(hasta, cantidad):
    """[hasta-cantidad+1 ... hasta] como texto AAAA-MM-DD, del mas viejo al mas nuevo."""
    return [(hasta - datetime.timedelta(days=i)).isoformat()
            for i in range(cantidad - 1, -1, -1)]


def construir_roster(filas_roster, respaldo):
    """Que entidades estan REALMENTE corriendo hoy.

    Se arma en cadena, no por el estado propio de cada una: una entidad cuenta
    como viva solo si su campana esta viva. Sin eso, `ads_get_errors` entierra
    lo de hoy abajo de la historia de la cuenta (ver el comentario de
    ESTADOS_VIVOS).

    `filas_roster` son las tres respuestas del MCP (campana, conjunto, anuncio)
    guardadas en un mismo archivo. El nivel se deduce de que padres trae la fila,
    igual que en meta_desde_mcp.py.
    """
    campanas_vivas = {f["nombre"] for f in filas_roster
                      if not f["campana"] and not f["conjunto"]
                      and f["estado"] in ESTADOS_VIVOS}
    roster = {}
    for f in filas_roster:
        if not f["id"] or f["estado"] not in ESTADOS_VIVOS:
            continue
        if f["conjunto"]:
            nivel, campana = "anuncio", f["campana"]
        elif f["campana"]:
            nivel, campana = "conjunto", f["campana"]
        else:
            nivel, campana = "campana", f["nombre"]
        if campana not in campanas_vivas:
            continue                              # cuelga de una campana apagada
        roster[f["id"]] = {"nombre": f["nombre"], "estado": f["estado"],
                           "nivel": nivel, "campana": campana}

    # Sin roster propio (el agente no lo guardo), se cae a lo que gasto en la
    # ventana: peor filtro, pero filtro. Se avisa, porque cambia que se ve.
    if not roster:
        print("[aviso] no hay roster.json: se filtra por lo que tuvo gasto en la "
              "ventana. Un conjunto activo que no entrega NO va a aparecer.",
              file=sys.stderr)
        for f in respaldo:
            if f["id"]:
                roster[f["id"]] = {"nombre": f["nombre"], "estado": f["estado"] or "ACTIVE",
                                   "nivel": "anuncio" if f["conjunto"] else "campana",
                                   "campana": f["campana"] or f["nombre"]}
    return roster


# ---------------------------------------------------------------- reglas

def g0_controles(anuncio_dia, anuncio_total, campana_dia, campana_total, u, ayer):
    """Antes de opinar, chequear que los datos sirvan.

    Dos cosas distintas y las dos son alerta:
      - la cuenta no registra gasto -> la pauta esta frenada
      - el detalle diario no trae todas las entidades que trae el total de la
        misma ventana -> trampa 6 de referencias/meta-mcp.md: la llamada diaria
        puede perder entidades enteras SIN avisar con un cursor.

    **Historia de esta segunda, porque explica como esta escrita.** Joana la
    saco el 2026-09-25: el aviso decia "los datos del MCP no cierran a nivel
    anuncio" con un porcentaje, y desde afuera de la corrida eso no significa
    nada. La primera simulacion despues de sacarla mostro el problema en vivo:
    faltaban 16.594 ARS en 4 de 18 anuncios y los cuatro eran los creativos
    nuevos, asi que G2 y G3 corrieron sobre 14 de 18 sin que nada lo dijera.
    Joana la repuso el mismo dia.

    Vuelve **nombrando los anuncios que faltan**, no con un porcentaje. El
    problema nunca fue la regla: era que el aviso no decia que buscar.
    """
    alertas, controles = [], {}
    tol = float(u["control_totales_tolerancia_pct"])

    for nivel, dia, total in (("anuncio", anuncio_dia, anuncio_total),
                              ("campana", campana_dia, campana_total)):
        s_dia = round(sum(f["gasto"] for f in dia), 2)
        s_tot = round(sum(f["gasto"] for f in total), 2)
        dif = abs(s_dia - s_tot)
        pct = (dif / s_tot * 100) if s_tot else (100.0 if dif else 0.0)
        controles[nivel] = {"gasto_diario_sumado": s_dia, "gasto_total": s_tot,
                            "diferencia_pct": round(pct, 3)}
        controles[nivel]["cuadra"] = pct <= tol
        if pct > tol:
            # Nombrar QUE falta, no cuanto. Un porcentaje no le dice a nadie
            # que hacer; "faltan estos cuatro anuncios" si.
            por_id = {}
            for f in dia:
                por_id[f["id"]] = por_id.get(f["id"], 0.0) + f["gasto"]
            faltan = sorted((f for f in total
                             if f["gasto"] - por_id.get(f["id"], 0.0) > 1),
                            key=lambda f: -(f["gasto"] - por_id.get(f["id"], 0.0)))
            lista = " · ".join(
                f"{f['nombre']} ({ars(f['gasto'] - por_id.get(f['id'], 0.0))} ARS)"
                for f in faltan[:6])
            if len(faltan) > 6:
                lista += f" y {len(faltan) - 6} mas"
            cuantos = f"{len(faltan)} de {len(total)}"
            alertas.append({
                "clave": f"G0:totales:{nivel}",
                "tipo": "datos_incompletos", "nivel": nivel, "entidad": nivel,
                "titulo": (f"El conector no trajo el desglose diario de {cuantos} "
                           f"{nivel}s ({ars(dif)} ARS)"),
                "detalle": (f"No es que estos {nivel}s esten rotos, pausados o hayan "
                            f"dejado de gastar: Meta les asigno gasto igual (aparecen "
                            f"bien en el total de la ventana), pero la llamada que "
                            f"pide el detalle dia por dia no devolvio su fila. Ya paso "
                            f"antes y fue con {nivel}s recien creados. Afectados: "
                            f"{lista}. **Consecuencia:** el chequeo de hoy de \"gasta y "
                            f"no trae nada\" y \"el costo esta empeorando\" no pudo "
                            f"mirar a estos {nivel}s puntuales — el resto de la cuenta "
                            f"si se reviso entera. Se arregla pidiendo de nuevo el "
                            f"nivel {nivel} con las mismas llamadas."),
                "valor": len(faltan),
            })

    gasto_ayer = sum(f["gasto"] for f in anuncio_dia if f["dia"] == ayer.isoformat())
    controles["gasto_de_ayer"] = round(gasto_ayer, 2)
    if not anuncio_dia:
        alertas.append({
            "clave": "G0:sin_datos", "tipo": "sin_datos", "nivel": "cuenta",
            "entidad": "cuenta",
            "titulo": "El MCP no devolvio ni una fila con gasto",
            "detalle": ("O la cuenta esta completamente frenada, o la llamada "
                        "salio mal. Revisar en el Administrador antes de "
                        "suponer cualquiera de las dos."),
            "valor": 0,
        })
    elif gasto_ayer <= 0:
        alertas.append({
            "clave": "G0:sin_gasto_ayer", "tipo": "sin_gasto", "nivel": "cuenta",
            "entidad": "cuenta",
            "titulo": f"La cuenta no registro gasto el {ayer.strftime('%d/%m')}",
            "detalle": ("Ningun anuncio gasto ayer. Puede ser una pausa "
                        "deliberada, un problema de cobro o entrega frenada."),
            "valor": 0,
        })
    return alertas, controles


def g1_errores(errores_json, roster, u):
    """Errores de entrega, quedandose SOLO con las entidades vivas.

    ads_get_errors sobre la cuenta devuelve el arbol entero, historia incluida:
    medido el 2026-09-15 dio decenas de errores sobre anuncios de campanas
    apagadas hace meses. Mandar eso a Slack es garantizar que nadie lo lea.
    """
    vivos = {i: d for i, d in roster.items() if d["estado"] in ESTADOS_VIVOS}
    encontrados, alertas = [], []

    def recorrer(nodo):
        if isinstance(nodo, list):
            for n in nodo:
                recorrer(n)
            return
        if not isinstance(nodo, dict):
            return
        eid = str(nodo.get("id") or "")
        for e in (nodo.get("errors") or []):
            msg = (e.get("error_message") or "").strip()
            if msg:
                encontrados.append((eid, nodo.get("level") or "", msg))
        recorrer(nodo.get("children") or [])

    crudo = (errores_json or {}).get("errors", errores_json)
    recorrer(json.loads(crudo) if isinstance(crudo, str) else crudo)

    for eid, nivel, msg in encontrados:
        if eid not in vivos:
            continue                              # historia: no es de hoy
        d = vivos[eid]
        alertas.append({
            "clave": f"G1:{eid}:{msg[:60]}",
            "tipo": "entrega_rota", "nivel": nivel or d["nivel"], "entidad_id": eid,
            "entidad": d["nombre"],
            "titulo": f"Entrega rota en {d['nombre']}",
            "detalle": f"{msg} (estado en Meta: {d['estado']})",
            "valor": 1,
        })
    return alertas, {"errores_leidos": len(encontrados),
                     "sobre_entidades_vivas": len(alertas)}


def g2_sin_resultados(anuncio_dia, u, ayer):
    """Anuncio que gasta y no trae nada. Avisa desde el PRIMER dia.

    Cambio pedido por Joana el 2026-09-25: antes esperaba 4 dias seguidos.
    El problema de avisar el dia 1 a secas es que con ~7 leads por dia
    repartidos en ~10 anuncios, la mayoria de los anuncios tiene cero
    resultados casi cualquier dia: eso no es una falla, es aritmetica.
    Medido sobre 14 dias, avisar el dia 1 sin filtro daba **1,21 mensajes
    por dia**, todos los dias.

    Lo que separa la senal del ruido no son los dias, es LA PLATA:

    - **Dia 1** avisa solo si el anuncio quemo `gasto_dia_1_ars` (6.000 ARS,
      dos veces el CPL objetivo) sin traer nada. Si gastaste lo que deberian
      haber costado dos leads y no vino ninguno, eso si es noticia el mismo dia.
    - **Dia 2 en adelante** avisa con el piso normal, porque ya no es un dia
      flojo: es una racha.

    Con ese corte, los mismos 14 dias dan **0,07 mensajes por dia**. Y `valor`
    es la racha, asi que cada dia que sigue sin traer nada la alerta escala y
    vuelve a sonar mas fuerte, que es lo que Joana pidio.
    """
    piso = float(u["gasto_minimo_diario_ars"])
    piso_dia_1 = float(u["sin_resultados"]["gasto_dia_1_ars"])
    min_racha = int(u["sin_resultados"]["dias_seguidos"])
    ventana = int(u["ventana_dias"])
    por_id = {}
    for f in anuncio_dia:
        por_id.setdefault(f["id"], {})[f["dia"]] = f

    alertas = []
    for eid, dias in por_id.items():
        racha, gastado = 0, 0.0
        for d in reversed(dias_de(ayer, ventana)):        # de ayer hacia atras
            f = dias.get(d)
            if not f or f["gasto"] < piso:
                break
            if f["resultados"] not in ("", None) and f["resultados"] > 0:
                break
            racha += 1
            gastado += f["gasto"]
        if not racha:
            continue
        if racha < min_racha and gastado < piso_dia_1:
            continue                                      # un dia flojo y barato
        ref = next(iter(dias.values()))
        cuantos = f"{racha} dia{'s' if racha != 1 else ''}"
        urgencia = "" if racha < min_racha else f" ({cuantos} seguidos)"
        alertas.append({
            "clave": f"G2:{eid}",
            "tipo": "sin_resultados", "nivel": "anuncio", "entidad_id": eid,
            "entidad": ref["nombre"],
            "titulo": (f"{ref['nombre']}: {ars(gastado)} ARS en {cuantos} "
                       f"sin un solo resultado{urgencia}"),
            "detalle": (f"Campana {ref['campana']} · conjunto {ref['conjunto']}. "
                        f"Ojo: puede ser que el lead haya entrado al CRM y Meta "
                        f"no lo atribuya — el cruce real es el del lunes."),
            "valor": racha,
        })
    return alertas


def _agregado(filas_dia, dias):
    dias = set(dias)
    g = i = c = r = 0.0
    for f in filas_dia:
        if f["dia"] in dias:
            g += f["gasto"]
            i += f["impresiones"]
            c += f["clics"]
            r += f["resultados"] or 0
    return {"gasto": g, "impresiones": i, "clics": c, "resultados": r}


def _racha_deterioro(fs, ayer, ventana, peor_que, valor_de, valido):
    """Cuantos dias seguidos, terminando ayer, empeoro contra el dia anterior.

    Devuelve (racha, valor_al_inicio, valor_ayer). La racha se corta en cuanto
    un dia no empeora o no cumple el filtro de volumen.
    """
    dias = dias_de(ayer, ventana)
    racha, v_ini, v_fin = 0, None, None
    for i in range(len(dias) - 1, 0, -1):
        hoy_d, prev_d = dias[i], dias[i - 1]
        a, b = _agregado(fs, [hoy_d]), _agregado(fs, [prev_d])
        if not (valido(a) and valido(b)):
            break
        va, vb = valor_de(a), valor_de(b)
        if va is None or vb is None or not peor_que(va, vb):
            break
        racha += 1
        if v_fin is None:
            v_fin = va
        v_ini = vb
    return racha, v_ini, v_fin


def _sostenido_bajo_base(fs, ayer, n, base_dias, valor_de, valido_base,
                         valido_dia, peor_que):
    """Cuantos de los ultimos N dias estuvieron peor que la base de 7 dias.

    Es la regla vieja y sigue haciendo falta: una metrica que se cae y **se
    queda abajo** no empeora de un dia para el otro, asi que el disparo rapido
    no la ve. El caso tipico es la fatiga de creativo, que es justo lo que mas
    interesa agarrar. Devuelve (dias_mal, valor_base, serie).
    """
    b = _agregado(fs, base_dias)
    if not valido_base(b):
        return 0, None, []
    vb = valor_de(b)
    if vb is None:
        return 0, None, []
    dias_mal, serie = 0, []
    for d in dias_de(ayer, n):
        dia = _agregado(fs, [d])
        if not valido_dia(dia):
            return 0, vb, []
        vd = valor_de(dia)
        serie.append(vd)
        if vd is None or peor_que(vd, vb):
            dias_mal += 1
        else:
            return 0, vb, serie
    return dias_mal, vb, serie


def g3_deterioro(anuncio_dia, campana_dia, u, ayer):
    """CTR cayendo o costo por resultado subiendo, DE UN DIA PARA EL OTRO.

    Cambio pedido por Joana el 2026-09-25: antes pedia 3 dias seguidos contra
    una base de 7. Ahora avisa apenas el salto ocurre, y si se sostiene dice
    cuanto se movio en total desde que empezo.

    El costo de mirar dia contra dia es el ruido, y aca es grande: esta cuenta
    hace entre 3 y 10 leads por dia EN TOTAL. Una campana que pasa de 3 leads
    a 2 muestra el costo por resultado "subiendo" 50% sin que haya pasado
    nada — es aritmetica de enteros, no deterioro. Medido sobre 14 dias, dia
    contra dia sin filtro daba 0,57 mensajes/dia de CPL y 1,00 de CTR.

    Por eso cada regla pide volumen en el dia con el que se compara:

    - **Costo por resultado**, por campana: el dia base tiene que tener al
      menos `resultados_minimos_dia_base` (3) resultados. Baja a 0,36/dia.
    - **CTR**, por anuncio: los dos dias con `impresiones_minimas_por_dia`
      (1.500) impresiones. Baja a 0,21/dia.

    El nivel de cada una no cambio y no es cosmetico: el CTR se mide por
    anuncio porque junta miles de impresiones por dia, y el costo por
    resultado por campana porque un anuncio junta 0, 1 o 2 leads.

    Vale entera la trampa 6 (efecto de descomposicion): esto abre una
    hipotesis, nunca una pausa.
    """
    ventana = int(u["ventana_dias"])
    sube = float(u["cpl"]["suba_pct"]) / 100
    cae = float(u["ctr"]["caida_pct"]) / 100
    min_imp = float(u["ctr"]["impresiones_minimas_por_dia"])
    min_res = float(u["cpl"]["resultados_minimos_dia_base"])
    alertas = []

    # ---- CTR por anuncio
    por_id = {}
    for f in anuncio_dia:
        por_id.setdefault(f["id"], []).append(f)
    for eid, fs in por_id.items():
        ctr_de = lambda x: (x["clics"] / x["impresiones"] * 100) if x["impresiones"] else None
        racha, v_ini, v_fin = _racha_deterioro(
            fs, ayer, ventana,
            peor_que=lambda a, b: a < b * (1 - cae),
            valor_de=ctr_de,
            valido=lambda x: x["impresiones"] >= min_imp)
        # Segundo disparo: cayo y SE QUEDO abajo de la base. No empeora de un
        # dia para el otro, asi que el rapido no lo ve, y es el caso tipico de
        # fatiga de creativo.
        n_sost = int(u["ctr"]["dias_seguidos"])
        sost, ctr_base, serie = _sostenido_bajo_base(
            fs, ayer, n_sost, dias_de(ayer - datetime.timedelta(days=n_sost), 7),
            valor_de=ctr_de,
            valido_base=lambda x: x["impresiones"] >= float(u["ctr"]["impresiones_minimas_base"]),
            valido_dia=lambda x: x["impresiones"] >= min_imp,
            peor_que=lambda vd, vb: vd <= vb * (1 - cae))
        if not racha and sost < n_sost:
            continue
        ref = fs[0]
        if racha:
            total = 100 * (1 - v_fin / v_ini) if v_ini else 0
            cuantos = f"{racha} dia{'s' if racha != 1 else ''}"
            cuanto = (f"Cayo {total:.0f}% en {cuantos}, de {v_ini:.2f}% a {v_fin:.2f}%."
                      if racha > 1 else
                      f"De {v_ini:.2f}% a {v_fin:.2f}% de un dia para el otro.")
        else:
            racha = sost
            cuantos = f"{sost} dias"
            fechas = dias_de(ayer, n_sost)
            detalle_dias = " · ".join(
                f"{f}: {x:.2f}%" for f, x in zip(fechas, serie) if x is not None)
            cuanto = (f"{detalle_dias} — contra {ctr_base:.2f}% de base "
                      f"(7 dias previos). Cayo y no volvio a subir.")
        alertas.append({
            "clave": f"G3:ctr:{eid}",
            "tipo": "ctr_cayendo", "nivel": "anuncio", "entidad_id": eid,
            "entidad": ref["nombre"],
            "titulo": f"{ref['nombre']}: el CTR cae hace {cuantos}",
            "detalle": (f"{cuanto} Campana {ref['campana']}. Suele ser fatiga de "
                        f"creativo: se confirma mirando la frecuencia del periodo, "
                        f"no subiendo el presupuesto."),
            "valor": racha,
        })

    # ---- Costo por resultado por campana
    por_camp = {}
    for f in campana_dia:
        if any(f["indicador"].startswith(x) for x in INDICADORES_LEAD):
            por_camp.setdefault(f["id"], []).append(f)
    for eid, fs in por_camp.items():
        racha, v_ini, v_fin = _racha_deterioro(
            fs, ayer, ventana,
            peor_que=lambda a, b: a > b * (1 + sube),
            valor_de=lambda x: (x["gasto"] / x["resultados"]) if x["resultados"] else None,
            valido=lambda x: x["gasto"] >= float(u["gasto_minimo_diario_ars"]),
            )
        # El dia con el que se compara tiene que tener volumen: si no, el salto
        # es aritmetica de enteros y no deterioro.
        if racha:
            base = _agregado(fs, [dias_de(ayer, racha + 1)[0]])
            if base["resultados"] < min_res:
                racha = 0
        n_sost = int(u["cpl"]["dias_seguidos"])
        sost, cpl_base, serie = _sostenido_bajo_base(
            fs, ayer, n_sost, dias_de(ayer - datetime.timedelta(days=n_sost), 7),
            valor_de=lambda x: (x["gasto"] / x["resultados"]) if x["resultados"] else None,
            valido_base=lambda x: (x["resultados"] >= float(u["cpl"]["resultados_minimos_base"])
                                   and x["gasto"] > 0),
            valido_dia=lambda x: x["gasto"] >= float(u["gasto_minimo_diario_ars"]),
            peor_que=lambda vd, vb: vd is None or vd >= vb * (1 + sube))
        if not racha and sost < n_sost:
            continue
        ref = fs[0]
        if racha:
            total = 100 * (v_fin / v_ini - 1) if v_ini else 0
            cuantos = f"{racha} dia{'s' if racha != 1 else ''}"
            cuanto = (f"Subio {total:.0f}% en {cuantos}, de {ars(v_ini)} a {ars(v_fin)} ARS."
                      if racha > 1 else
                      f"De {ars(v_ini)} a {ars(v_fin)} ARS de un dia para el otro.")
        else:
            racha = sost
            cuantos = f"{sost} dias"
            fechas = dias_de(ayer, n_sost)
            detalle_dias = " · ".join(
                f"{f}: sin leads ese dia" if x is None else f"{f}: {ars(x)} ARS/lead"
                for f, x in zip(fechas, serie))
            cuanto = (f"{detalle_dias} — contra un promedio de {ars(cpl_base)} "
                      f"ARS/lead en los 7 dias previos. Subio y no volvio a bajar.")
        alertas.append({
            "clave": f"G3:cpl:{eid}",
            "tipo": "cpl_subiendo", "nivel": "campana", "entidad_id": eid,
            "entidad": ref["nombre"],
            "titulo": f"{ref['nombre']}: el costo por resultado sube hace {cuantos}",
            "detalle": (f"{cuanto} Este es el costo que reporta Meta, no el CPL "
                        f"real sobre leads que llegaron al CRM: el que gobierna "
                        f"se calcula el lunes."),
            "valor": racha,
        })
    return alertas


def g4_gasto_innecesario(anuncio_dia, anuncio_tot, campana_dia, eventos, u, ayer):
    """Plata que se esta yendo sin volver.

    Tres cosas distintas, y ninguna es "esta caro": la cuenta puede estar cara y
    no tener nada de esto, o estar barata y tener las tres. Lo que busca es
    gasto que **no puede** producir nada.

    - **G4a, el evento que ya paso.** Una campana de webinar que sigue gastando
      despues del webinar es plata tirada sin matices: nadie se puede anotar a
      algo que ya ocurrio. Es la unica de las tres que no admite interpretacion.
    - **G4b, el anuncio que quema al mismo publico.** Frecuencia de la ventana
      por encima del techo: se le esta pagando a Meta por mostrarle el mismo
      anuncio a la misma gente. **La frecuencia se lee del total de la ventana,
      NUNCA sumando filas diarias**, que cuentan dos veces a quien vio el
      anuncio dos dias.
    - **G4c, cuanto de la ventana se fue sin un solo resultado.** Suma lo que
      gastaron los anuncios que no trajeron nada. Es el numero que contesta
      "cuanta plata estamos tirando", que G2 no contesta: G2 mira un anuncio y
      su racha, esto mira la cuenta y su total.

    Ninguna de las tres pausa nada. Se avisan como plata identificada, y la
    decision es de Joana.
    """
    g = u["gasto_innecesario"]
    alertas = []

    # --- G4a: evento vencido que sigue gastando
    gracia = int(g["evento_vencido_dias_gracia"])
    por_camp = {}
    for f in campana_dia:
        por_camp.setdefault(f["nombre"], []).append(f)
    for nombre, fs in por_camp.items():
        fecha = eventos.get(nombre)
        if not fecha:
            continue
        try:
            corte = datetime.date.fromisoformat(str(fecha)) + datetime.timedelta(days=gracia)
        except ValueError:
            print(f"[aviso] fecha_evento invalida en '{nombre}': {fecha}", file=sys.stderr)
            continue
        tarde = [f for f in fs if f["dia"] and datetime.date.fromisoformat(f["dia"]) > corte
                 and f["gasto"] > 0]
        if not tarde:
            continue
        gastado = sum(f["gasto"] for f in tarde)
        alertas.append({
            "clave": f"G4a:{fs[0]['id']}",
            "tipo": "evento_vencido", "nivel": "campana", "entidad_id": fs[0]["id"],
            "entidad": nombre,
            "titulo": f"{nombre} sigue gastando y el evento ya paso",
            "detalle": (f"El evento fue el {fecha}. Desde entonces la campana "
                        f"gasto {ars(gastado)} ARS en {len(tarde)} dias. Nadie se "
                        f"puede anotar a algo que ya ocurrio: es plata tirada."),
            "valor": round(gastado),
        })

    # --- G4b: frecuencia por las nubes en la ventana
    techo = float(g["frecuencia_maxima_ventana"])
    piso_gasto = float(u["gasto_minimo_diario_ars"])
    for f in anuncio_tot:
        frec = f.get("frecuencia")
        if not isinstance(frec, (int, float)) or frec < techo:
            continue
        if f["gasto"] < piso_gasto:
            continue                              # gasto marginal: no vale el aviso
        alertas.append({
            "clave": f"G4b:{f['id']}",
            "tipo": "publico_quemado", "nivel": "anuncio", "entidad_id": f["id"],
            "entidad": f["nombre"],
            "titulo": f"{f['nombre']}: frecuencia {frec:.1f} — le pega a la misma gente",
            "detalle": (f"Campana {f['campana']}. {ars(f['gasto'])} ARS en la "
                        f"ventana para mostrarle el mismo anuncio {frec:.1f} veces "
                        f"a cada persona (techo {techo:g}). Se arregla rotando "
                        f"creativo o ampliando publico, NO subiendo presupuesto."),
            "valor": round(frec, 1),
        })

    # G4c (cuanta plata de la ventana no trajo nada) se saco el 2026-09-25
    # por pedido de Joana: no se entendia que estaba midiendo. Lo que
    # contestaba ("cuanta plata estamos tirando") sigue saliendo del cruce
    # del lunes, que ademas lo puede decir contra leads reales del CRM y no
    # contra atribucion de Meta.

    return alertas


# ---------------------------------------------------------------- estado

ORIGENES_NUCLEO = ("Meta Ads Formulario", "Meta Ads")


def resultados_que_van_al_crm(campana_dia, anuncio_dia, ventana):
    """{dia: n} — los resultados de Meta que DEBERIAN aparecer en el CRM.

    No son todos los resultados de la cuenta, y la diferencia importa:

    - Una visita al perfil de una campana de awareness no genera prospecto.
      Solo cuentan las familias `lead` y `mensaje`.
    - Las campanas eventuales (webinar, curso, presencial) guardan sus leads en
      SU PROPIO origen del CRM, no en "Meta Ads Formulario"/"Meta Ads". Contarlas
      de un lado y no del otro daria un hueco permanente que no existe.
    - Lo mismo con los conjuntos de evento que cuelgan de una campana nucleo:
      son parte de la campana en Meta pero van a otro origen en el CRM. Se
      restan, y SOLO esos.

    Es la misma definicion de "cruzable" que usan analizar_meta y el panel. Por
    eso `bloque_de` y `CONJUNTOS_DE_EVENTO` se importan y no se reescriben aca.
    """
    def es_generadora(fila):
        if bloque_de(fila["campana"] or fila["nombre"]) not in ("conversion", "remarketing"):
            return False
        fam = FAMILIA.get(fila["indicador"] or "", ("desconocido",))[0]
        return fam in ("lead", "mensaje")

    por_dia = {d: 0 for d in ventana}
    for f in campana_dia:
        if f["dia"] in por_dia and es_generadora(f):
            por_dia[f["dia"]] += f["resultados"] or 0

    # Los conjuntos de evento viven adentro de campanas nucleo: se descuentan
    # desde el nivel anuncio, que es donde la guardia tiene el nombre del conjunto.
    for f in anuncio_dia:
        if (f["dia"] in por_dia and f["conjunto"] in CONJUNTOS_DE_EVENTO
                and es_generadora(f)):
            por_dia[f["dia"]] -= f["resultados"] or 0

    return {d: max(0, n) for d, n in por_dia.items()}


def gasto_que_va_al_crm(campana_dia, ventana):
    """{dia: ARS} gastado en campanas de conversion/remarketing que buscan leads o mensajes."""
    por_dia = {d: 0.0 for d in ventana}
    for f in campana_dia:
        if f["dia"] not in por_dia:
            continue
        if bloque_de(f["campana"] or f["nombre"]) not in ("conversion", "remarketing"):
            continue
        if FAMILIA.get(f["indicador"] or "", ("desconocido",))[0] in ("lead", "mensaje"):
            por_dia[f["dia"]] += f["gasto"] or 0.0
    return por_dia


def leads_del_crm(desde, hasta):
    """{dia ART: n} de prospectos creados con origen Meta pago.

    Levanta el modulo que ya sabe hablar con Bitrix en vez de armar otra
    llamada: `traer_prospectos` resuelve los IDs de origen contra el portal y
    —lo que mas importa aca— convierte `DATE_CREATE` a hora argentina. La API
    del portal devuelve en +03:00, seis horas adelante de ART: un lead de las
    21:00 del lunes vuelve como martes. Con una regla que mira "ayer", leer la
    fecha cruda seria inventar un hueco cada noche.

    Devuelve tambien las filas crudas, para dejarlas versionadas como evidencia.
    """
    import traer_prospectos as tp
    filas = tp.prospectos(desde.isoformat(), hasta.isoformat())
    fuentes = tp.catalogo("SOURCE")
    por_dia = {d.isoformat(): 0 for d in _rango(desde, hasta)}
    crudas = []
    for f in filas:
        art = f.get("_art") or tp.a_hora_argentina(f.get("DATE_CREATE"))
        if not art:
            continue
        dia = art.date().isoformat()
        origen = fuentes.get(str(f.get("SOURCE_ID")), str(f.get("SOURCE_ID") or ""))
        if dia in por_dia and origen in ORIGENES_NUCLEO:
            por_dia[dia] += 1
            crudas.append({"id": f.get("ID"), "dia_art": dia, "origen": origen})
    return por_dia, crudas


def _rango(desde, hasta):
    d, out = desde, []
    while d <= hasta:
        out.append(d)
        d += datetime.timedelta(days=1)
    return out


def leer_avisos_slack(carpeta, ventana):
    """{dia: n} de re-ingresos y recontactos avisados en #adqui-automatizaciones.

    Es la tercera pata de la cuenta que pidio Joana el 2026-09-25: Meta cobro
    N, el CRM creo M, y Slack aviso R. Lo que falta de verdad es N - M - R.

    **Por que importa tanto.** Cuando alguien que YA existe en Bitrix vuelve a
    completar el formulario, el workflow no crea un prospecto: le avisa a la
    SDR por Slack y termina ahi (decision de Joana, 2026-09-09, EXP-002). Meta
    igual lo cobra. Sin contar esos avisos, esos leads se ven como perdidos y
    no lo estan: llegaron a quien tenian que llegar.

    Lo trae el AGENTE, no el script: las herramientas de Slack son MCP y un
    script de Python no las puede llamar. Si el archivo no esta, G5 igual corre
    pero sin la tercera pata, y lo dice.

    **Limite conocido, y hay que nombrarlo al reportar:** el aviso NO dice de
    que formulario vino, y ese mismo workflow recibe tambien los formularios
    web. Entonces R es un TECHO de lo que explica: restarlo entero puede
    perdonar de mas, nunca de menos.
    """
    crudo = leer(carpeta, "avisos-slack.json", obligatorio=False, sub="slack")
    if not crudo:
        return None
    por_dia = (crudo or {}).get("por_dia") or {}
    return {d: int(por_dia.get(d) or 0) for d in ventana}


def g5_conciliacion_crm(meta_por_dia, crm_por_dia, u, ayer, avisos=None):
    """Meta dice que hubo leads y en el CRM no estan.

    Pedido de Joana el 2026-09-25. Es la primera regla de la guardia que mira
    fuera de la plataforma, y la que mas facil se rompe si se la calibra mal,
    porque **el hueco es cronico**: medido sobre 82 dias (jul-sep 2026) la
    conciliacion diaria es del 69%, no del 100%. Hay re-ingresos que no generan
    prospecto (y esta bien, EXP-002), y leads que Meta cobra y el CRM nunca ve.

    Una regla "Meta > CRM" habria disparado 39 de 51 dias. Seria ruido puro.
    Lo que se busca no es el hueco: es **la tuberia cortada**.

    G5a — el CRM en CERO habiendo leads en Meta. Sobre los mismos 82 dias
    habria disparado 1 vez con el umbral de 4. Es el sintoma de n8n caido, del
    webhook desconectado o del formulario despegado del CRM, y no se parece al
    hueco cronico: el hueco deja pasar la mayoria, una tuberia cortada no deja
    pasar ninguno. `valor` es la racha, asi que si sigue cortada al dia
    siguiente la alerta ESCALA sola y vuelve a sonar.

    G5b — la conciliacion de la ventana se derrumba. Agarra la rotura parcial,
    que G5a no ve: la mitad de los leads dejan de entrar. Piso en 25% contra un
    normal de 69%; sobre los 82 dias, 0 disparos (el minimo historico fue 30%).

    Las dos hablan de resultados que META ATRIBUYE, no de leads reales. Con 0%
    de UTM hasta el 08/09 el sentido de la comparacion es "faltan prospectos
    donde deberia haberlos", nunca "este anuncio no funciona".
    """
    c = u["conciliacion_crm"]
    minimo = int(c["minimo_leads_meta"])
    av = avisos or {}

    def sin_explicar(d):
        """Meta cobro N, el CRM creo M, Slack aviso R. Faltan N - M - R."""
        return max(0, meta_por_dia.get(d, 0) - crm_por_dia.get(d, 0) - av.get(d, 0))
    n_vent = int(c["ventana_conciliacion_dias"])   # cuanto mira G5a hacia atras
    alertas = []

    # --- G5a: racha de dias con el CRM en cero
    racha, meta_racha = 0, 0
    for d in reversed(dias_de(ayer, n_vent)):          # de ayer hacia atras
        m, k = meta_por_dia.get(d), crm_por_dia.get(d)
        if m is None or k is None or k > 0 or m <= 0:
            break
        racha += 1
        meta_racha += m
    dias_racha = dias_de(ayer, racha) if racha else []
    faltan = sum(sin_explicar(d) for d in dias_racha)
    avisados = sum(av.get(d, 0) for d in dias_racha)
    if racha and faltan >= minimo:
        desde = (ayer - datetime.timedelta(days=racha - 1)).strftime("%d/%m")
        cuando = f"el {ayer.strftime('%d/%m')}" if racha == 1 else f"del {desde} al {ayer.strftime('%d/%m')}"
        # La cuenta completa, que es lo que pidio Joana el 2026-09-25: no
        # alcanza con decir que el CRM esta en cero, hay que mostrar cuantos
        # de esos leads SI llegaron a la SDR por el aviso de re-ingreso.
        if avisos is None:
            cuenta = (f"Meta atribuyo {meta_racha} · el CRM creo 0. "
                      f"No se pudieron leer los avisos de re-ingreso de "
                      f"#adqui-automatizaciones, asi que no se puede descontar "
                      f"cuantos de esos ya le llegaron a la SDR por ahi.")
        else:
            cuenta = (f"Meta atribuyo {meta_racha} · el CRM creo 0 · Slack aviso "
                      f"{avisados} re-ingreso{'s' if avisados != 1 else ''} → "
                      f"**quedan {faltan} sin explicar**.")
        alertas.append({
            "clave": "G5:tuberia",
            "tipo": "tuberia_cortada", "nivel": "cuenta", "entidad": "Meta -> Bitrix24",
            "titulo": (f"{faltan} lead{'s' if faltan != 1 else ''} que cobro Meta "
                       f"{cuando} no llegaron ni al CRM ni a la SDR"),
            "detalle": (f"{cuenta} Origenes {' y '.join(ORIGENES_NUCLEO)}, "
                        f"{racha} dia{'s' if racha != 1 else ''} con el CRM en cero. "
                        f"Un cero se parece a la tuberia cortada (n8n, el webhook de "
                        f"leadgen o el formulario despegado del CRM), no al hueco de "
                        f"siempre. Revisar el workflow de n8n antes que la pauta. "
                        f"Ojo: el aviso de re-ingreso no dice de que formulario vino "
                        f"y ese workflow tambien recibe los formularios web, asi que "
                        f"lo descontado es un techo."),
            "valor": racha,
        })

    # G5b (la conciliacion de la ventana abajo de un piso) se saco el
    # 2026-09-25 por pedido de Joana: no se entendia que estaba midiendo.
    # G5a sigue agarrando el corte total, que es el caso que importa.
    # Lo que se pierde es la rotura PARCIAL (entra la mitad de lo que
    # deberia): eso vuelve a quedar para el cruce del lunes, que ya lo
    # mide como conciliacion Meta-CRM contra el piso de 85%.

    return alertas


def g6_dia_sin_leads(crm_por_dia, gasto_generador_por_dia, u, ayer, g5_disparo=False):
    """Ayer no entro NINGUN lead de Meta al CRM, habiendo gastado en captacion.

    Pedido de Joana el 2026-09-30 ("tomemos como alarma los dias que no generen
    nada a nivel leads en el CRM"). No es lo mismo que G5a: G5a mira la tuberia
    (Meta atribuyo >= 4 y el CRM creo 0); G6 mira el RESULTADO, aunque Meta
    tampoco haya atribuido nada. Si G5a ya disparo, G6 se calla: ese cero ya
    tiene una explicacion mejor.

    El piso de 5 leads/dia que puso Joana es un OBJETIVO, no una alarma: sobre
    el Q3 (91 dias) solo 27 dias llegaron a 5, asi que como alerta sonaria casi
    todos los dias. Ese se mide en el panel y el lunes. El cero si es raro:
    5 dias de 91 (y 2 fueron la falla de n8n del 23-24/09).

    `valor` es la racha de dias en cero, asi que si sigue al dia siguiente la
    alerta escala y vuelve a sonar.
    """
    if g5_disparo:
        return []
    piso = float(u["dia_sin_leads"]["gasto_minimo_ars"])
    racha = 0
    for d in reversed(dias_de(ayer, 7)):
        k = crm_por_dia.get(d)
        if k is None or k > 0 or gasto_generador_por_dia.get(d, 0) < piso:
            break
        racha += 1
    if not racha:
        return []
    gasto = sum(gasto_generador_por_dia.get(d, 0) for d in dias_de(ayer, racha))
    cuando = (f"el {ayer.strftime('%d/%m')}" if racha == 1 else
              f"del {(ayer - datetime.timedelta(days=racha - 1)).strftime('%d/%m')} "
              f"al {ayer.strftime('%d/%m')}")
    return [{
        "clave": "G6:dia-sin-leads",
        "tipo": "dia_sin_leads", "nivel": "cuenta", "entidad": "Meta -> Bitrix24",
        "titulo": f"No entro ningun lead de Meta al CRM {cuando}",
        "detalle": (f"Se gastaron {gasto:,.0f} ARS en campanas de captacion y el CRM "
                    f"no creo ningun prospecto con origen {' ni '.join(ORIGENES_NUCLEO)}. "
                    f"Meta tampoco atribuyo leads suficientes como para pensar en la "
                    f"tuberia, asi que lo primero a mirar es la entrega de los "
                    f"conjuntos de conversion. El objetivo del canal es 5 leads/dia "
                    f"(Joana, 2026-09-30).").replace(",", "."),
        "valor": racha,
    }]


def cargar_estado(ruta):
    if not os.path.isfile(ruta):
        return {}
    estado = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            estado[d["clave"]] = d               # la ultima gana
    return estado


def decidir(alertas, estado, u, hoy):
    """Que se manda hoy y que se calla.

    Una alerta ya avisada vuelve solo si escala o si vencio el recordatorio.
    Lo demas sigue abierto en el estado, en silencio.
    """
    recordar = int(u["repeticion"]["recordar_cada_dias"])
    escalada = int(u["repeticion"]["escalada_dias"])
    hoy_s = hoy.isoformat()
    vistas, mandar, silenciadas = set(), [], []

    for a in alertas:
        vistas.add(a["clave"])
        previo = estado.get(a["clave"])
        if not previo or previo.get("estado") == "resuelta":
            a["motivo_aviso"] = "nueva"
            a["primer_aviso"] = hoy_s
            mandar.append(a)
            continue
        dias = (hoy - datetime.date.fromisoformat(previo["ultimo_aviso"])).days
        crecio = (a.get("valor") or 0) - (previo.get("valor") or 0)
        a["primer_aviso"] = previo.get("primer_aviso", hoy_s)
        if crecio >= escalada:
            a["motivo_aviso"] = f"escalo (de {previo.get('valor')} a {a.get('valor')})"
            mandar.append(a)
        elif dias >= recordar:
            a["motivo_aviso"] = f"sigue abierta hace {(hoy - datetime.date.fromisoformat(a['primer_aviso'])).days} dias"
            mandar.append(a)
        else:
            a["motivo_aviso"] = "ya avisada"
            silenciadas.append(a)

    resueltas = [dict(v, estado="resuelta", resuelta_el=hoy_s)
                 for k, v in estado.items()
                 if k not in vistas and v.get("estado") == "abierta"]
    return mandar, silenciadas, resueltas


def guardar_estado(ruta, mandar, silenciadas, resueltas, estado, hoy):
    hoy_s = hoy.isoformat()
    for a in mandar:
        estado[a["clave"]] = {
            "clave": a["clave"], "tipo": a["tipo"], "nivel": a["nivel"],
            "entidad": a.get("entidad", ""), "entidad_id": a.get("entidad_id", ""),
            "titulo": a["titulo"], "valor": a.get("valor"),
            "primer_aviso": a["primer_aviso"], "ultimo_aviso": hoy_s,
            "estado": "abierta",
        }
    for a in silenciadas:
        d = dict(estado.get(a["clave"], {}))
        d.update({"clave": a["clave"], "valor": a.get("valor"), "estado": "abierta",
                  "visto_el": hoy_s})
        estado[a["clave"]] = d
    for r in resueltas:
        estado[r["clave"]] = r
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("# Estado de la guardia diaria. Una linea por alerta, la ultima manda.\n"
                "# La escribe scripts/guardia_diaria.py: no editar a mano salvo para\n"
                "# cerrar algo que ya se resolvio en la plataforma.\n")
        for clave in sorted(estado):
            f.write(json.dumps(estado[clave], ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- salida

ORDEN = {"crm_sin_mirar": 0, "datos_incompletos": 0, "sin_datos": 0,
         "tuberia_cortada": 1, "dia_sin_leads": 1,
         "sin_gasto": 1, "entrega_rota": 2, "evento_vencido": 3,
         "sin_resultados": 5, "publico_quemado": 6,
         "cpl_subiendo": 7, "ctr_cayendo": 8}

# Pedido de Joana el 2026-09-27: separar lo que es un problema DE LA CUENTA
# (delivery roto, gasto sin resultado, CPL/CTR empeorando, plata quemada,
# leads que no llegan al CRM) de lo que es un problema DE LA GUARDIA MISMA
# (el conector no trajo el desglose diario, no se pudo leer Bitrix). Lo
# primero es algo para mirar en la pauta; lo segundo es "reintentar la
# llamada", no un hallazgo sobre los anuncios.
TIPOS_CONECTOR = {"datos_incompletos", "sin_datos", "crm_sin_mirar"}


def mensaje_slack(mandar, resueltas, ayer):
    """5-8 lineas. Si no entra en una notificacion del celular, no se lee."""
    fecha = ayer.strftime("%d/%m")
    out = [f"*Guardia de Meta Ads · datos al {fecha}*", ""]

    de_cuenta = [a for a in mandar if a["tipo"] not in TIPOS_CONECTOR]
    de_conector = [a for a in mandar if a["tipo"] in TIPOS_CONECTOR]

    def bloque(titulo, alertas):
        if not alertas:
            return
        if de_cuenta and de_conector:
            out.append(f"*{titulo}*")
        for a in sorted(alertas, key=lambda x: ORDEN.get(x["tipo"], 9)):
            marca = "" if a["motivo_aviso"] == "nueva" else f" _({a['motivo_aviso']})_"
            out.append(f"• *{a['titulo']}*{marca}")
            out.append(f"   {a['detalle']}")
        out.append("")

    # La cuenta primero: es lo que hay que leer si solo se lee una linea.
    bloque("La cuenta y los anuncios", de_cuenta)
    bloque("El conector (no es un problema de la pauta)", de_conector)
    if out[-1] == "":
        out.pop()

    if resueltas:
        out.append("")
        out.append("Se resolvio: " + " · ".join(r["titulo"] for r in resueltas))
    out.append("")
    out.append("_La guardia mira la plataforma y chequea que los leads lleguen al "
               "CRM. El cruce completo (CPL real, calidad, derivacion) y las "
               "decisiones van el lunes._")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Guardia diaria del canal de Meta Ads.")
    ap.add_argument("carpeta", nargs="?", help="datos/meta-ads/guardia/<AAAA-MM-DD>/")
    ap.add_argument("--hoy", help="AAAA-MM-DD. Por defecto, hoy.")
    ap.add_argument("--estado", default=ESTADO_POR_DEFECTO)
    ap.add_argument("--json", dest="salida_json", help="Donde dejar el detalle completo.")
    ap.add_argument("--umbrales", default=UMBRALES_YAML)
    ap.add_argument("--dry-run", action="store_true",
                    help="No escribe el estado ni la evidencia del CRM. "
                         "Para probar sin gastar el silencio.")
    ap.add_argument("--sin-crm", action="store_true",
                    help="No consulta Bitrix. G5 no corre y se dice en la salida.")
    ap.add_argument("--autotest", action="store_true")
    a = ap.parse_args()

    if a.autotest:
        return autotest()
    if not a.carpeta:
        ap.error("falta la carpeta de la corrida (o --autotest)")

    # Freno: las respuestas guardadas tienen que abrir y cuadrar (scripts/validar_mcp.py).
    # Una respuesta cortada o mal copiada daria alertas falsas o un silencio falso.
    from validar_mcp import validar
    malos, _ = validar(a.carpeta)
    if malos:
        print("NO CUADRA — la guardia no corre con estas respuestas:")
        for m in malos:
            print(f"  - {m}")
        return 1

    u = cargar_umbrales(a.umbrales)
    hoy = datetime.date.fromisoformat(a.hoy) if a.hoy else datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)

    try:
        anuncio_dia = filas(leer(a.carpeta, "anuncio-diario.json"))
        anuncio_tot = filas(leer(a.carpeta, "anuncio-total.json"))
        campana_dia = filas(leer(a.carpeta, "campana-diario.json"))
        campana_tot = filas(leer(a.carpeta, "campana-total.json"))
        errores = leer(a.carpeta, "errores.json")
        roster_crudo = filas(leer(a.carpeta, "roster.json", obligatorio=False) or [])
    except FileNotFoundError as e:
        print(f"""[error] falta {os.path.basename(str(e))} en {a.carpeta}mcp/

NO HAY CON QUE OPINAR. La guardia no puede decir "esta todo bien" sin haber
mirado: un silencio por falta de datos es peor que una alerta de mas.

Volver a llamar al MCP con las llamadas de referencias/guardia-diaria.md. Si el
MCP no contesta dos veces seguidas, avisar eso por Slack — que la guardia esta
ciega ES la noticia del dia.""", file=sys.stderr)
        return 1

    roster = construir_roster(roster_crudo, anuncio_tot + campana_tot)

    alertas, controles = g0_controles(anuncio_dia, anuncio_tot,
                                      campana_dia, campana_tot, u, ayer)
    alertas_g1, control_errores = g1_errores(errores, roster, u)
    controles["errores"] = control_errores
    alertas += alertas_g1
    alertas += g2_sin_resultados(anuncio_dia, u, ayer)
    alertas += g3_deterioro(anuncio_dia, campana_dia, u, ayer)
    alertas += g4_gasto_innecesario(anuncio_dia, anuncio_tot, campana_dia,
                                    fechas_de_evento(), u, ayer)

    # G5 es la unica regla que mira fuera de la plataforma. Si Bitrix no
    # contesta NO se sigue en silencio: un "no encontre nada" que en realidad
    # es "no pude mirar" se lee como que esta todo bien, y es lo contrario.
    n_vent = int(u["conciliacion_crm"]["ventana_conciliacion_dias"])
    ventana_crm = dias_de(ayer, n_vent)
    meta_crm = resultados_que_van_al_crm(campana_dia, anuncio_dia, ventana_crm)
    controles["resultados_que_van_al_crm"] = meta_crm
    if a.sin_crm:
        controles["crm"] = "no se consulto (--sin-crm)"
    else:
        try:
            desde = ayer - datetime.timedelta(days=n_vent - 1)
            crm_por_dia, crudas = leads_del_crm(desde, ayer)
            controles["crm"] = {"leads_por_dia": crm_por_dia,
                                "origenes": list(ORIGENES_NUCLEO)}
            # Con --dry-run no se deja rastro: la evidencia del CRM va en la
            # carpeta de una corrida REAL, y una prueba que escribe ahi mete
            # datos de hoy adentro de la corrida de otro dia.
            if not a.dry_run:
                ruta_crm = os.path.join(a.carpeta, "crm",
                                        f"prospectos-{ayer.isoformat()}.json")
                os.makedirs(os.path.dirname(ruta_crm), exist_ok=True)
                with open(ruta_crm, "w", encoding="utf-8") as fh:
                    json.dump({"desde": desde.isoformat(), "hasta": ayer.isoformat(),
                               "origenes": list(ORIGENES_NUCLEO),
                               "por_dia": crm_por_dia, "prospectos": crudas},
                              fh, ensure_ascii=False, indent=2)
            avisos = leer_avisos_slack(a.carpeta, ventana_crm)
            controles["avisos_slack"] = (avisos if avisos is not None
                                         else "no se trajeron (falta slack/avisos-slack.json)")
            a_g5 = g5_conciliacion_crm(meta_crm, crm_por_dia, u, ayer, avisos)
            alertas += a_g5
            alertas += g6_dia_sin_leads(crm_por_dia, gasto_que_va_al_crm(campana_dia, ventana_crm),
                                        u, ayer, g5_disparo=bool(a_g5))
        except Exception as e:                    # noqa: BLE001
            controles["crm"] = f"ERROR: {e}"
            alertas.append({
                "clave": "G5:sin-crm",
                "tipo": "crm_sin_mirar", "nivel": "cuenta", "entidad": "Bitrix24",
                "titulo": "La guardia no pudo leer el CRM",
                "detalle": (f"Bitrix no contesto ({e}). No se pudo chequear si los leads "
                            f"que Meta atribuyo ayer estan creados como prospectos. "
                            f"Esto se avisa en vez de callarse: un silencio por falta de "
                            f"datos se lee como que esta todo bien. Revisar "
                            f"BITRIX_WEBHOOK_URL en el environment."),
                "valor": 1,
            })

    estado = cargar_estado(a.estado)
    mandar, silenciadas, resueltas = decidir(alertas, estado, u, hoy)

    detalle = {
        "corrida": hoy.isoformat(), "datos_hasta": ayer.isoformat(),
        "ventana_dias": u["ventana_dias"], "controles": controles,
        "alertas_que_disparan": alertas,
        "se_mandan": [x["clave"] for x in mandar],
        "silenciadas": [{"clave": x["clave"], "motivo": x["motivo_aviso"]}
                        for x in silenciadas],
        "resueltas": [x["clave"] for x in resueltas],
    }
    if a.salida_json:
        os.makedirs(os.path.dirname(a.salida_json), exist_ok=True)
        with open(a.salida_json, "w", encoding="utf-8") as f:
            json.dump(detalle, f, ensure_ascii=False, indent=2)

    print(f"Guardia del {hoy.strftime('%d/%m/%Y')} · datos hasta {ayer.strftime('%d/%m')}")
    print(f"  gasto de ayer      : {ars(controles['gasto_de_ayer'])} ARS")
    print(f"  errores del MCP    : {control_errores['errores_leidos']} "
          f"({control_errores['sobre_entidades_vivas']} sobre entidades vivas)")
    ctrl_crm = controles.get("crm")
    if isinstance(ctrl_crm, dict):
        d = ayer.isoformat()
        k = ctrl_crm["leads_por_dia"].get(d, 0)
        m = meta_crm.get(d, 0)
        avs = controles.get("avisos_slack")
        r = avs.get(d, 0) if isinstance(avs, dict) else None
        cola = (f", {r} avisados por Slack -> faltan {max(0, m - k - r)}"
                if r is not None else " (sin los avisos de Slack)")
        print(f"  leads de ayer      : Meta {m}, CRM {k}{cola}")
    else:
        print(f"  CRM                : {ctrl_crm}")
    print(f"  alertas que aplican: {len(alertas)} "
          f"({len(mandar)} se mandan, {len(silenciadas)} ya avisadas)")

    if not a.dry_run:
        guardar_estado(a.estado, mandar, silenciadas, resueltas, estado, hoy)

    if not mandar:
        print("\nSIN NOVEDADES. No se manda nada a Slack y no se commitea nada.")
        if resueltas:
            print("Se cerraron en el estado: " + ", ".join(r["clave"] for r in resueltas))
        return 0

    print("\n------------------------------ MENSAJE DE SLACK ------------------------------")
    print(mensaje_slack(mandar, resueltas, ayer))
    print("------------------------------------------------------------------------------")
    return 0


# ---------------------------------------------------------------- autotest

def autotest():
    """Prueba las reglas con datos armados. No toca disco."""
    hoy = datetime.date(2026, 9, 15)
    ayer = hoy - datetime.timedelta(days=1)
    u = json.loads(json.dumps(DEFAULTS))
    fallas = []

    def chequear(nombre, ok):
        print(("  ok   " if ok else "  FALLA") + f" {nombre}")
        if not ok:
            fallas.append(nombre)

    # G2: ahora avisa desde el dia 1, pero solo si la plata lo justifica.
    dias = dias_de(ayer, 14)
    ad = [{"id": "A1", "nombre": "Anuncio mudo", "campana": "C", "conjunto": "CJ",
           "dia": d, "gasto": 5000.0, "impresiones": 1000, "clics": 10, "ctr": 1.0,
           "resultados": "", "indicador": "actions:lead", "estado": "ACTIVE"}
          for d in dias]
    chequear("G2 dispara con 14 dias sin resultado", len(g2_sin_resultados(ad, u, ayer)) == 1)
    ad[-1]["resultados"] = 2
    chequear("G2 se calla si ayer trajo un resultado", not g2_sin_resultados(ad, u, ayer))
    ad[-1]["resultados"] = ""
    ad[-2]["gasto"] = 0.0
    chequear("G2 no cuenta un dia sin gasto (pausado no es fallando)",
             not g2_sin_resultados(ad, u, ayer))

    # Un solo dia: depende de cuanta plata quemo, no de la racha.
    uno = [dict(ad[0], dia=ayer.isoformat(), gasto=7000.0, resultados="")]
    a2 = g2_sin_resultados(uno, u, ayer)
    chequear("G2 avisa el DIA 1 si quemo mas de 6.000 ARS sin traer nada",
             len(a2) == 1 and a2[0]["valor"] == 1)
    barato = [dict(ad[0], dia=ayer.isoformat(), gasto=2500.0, resultados="")]
    chequear("G2 se calla el dia 1 si gasto poco (un dia flojo no es una falla)",
             not g2_sin_resultados(barato, u, ayer))
    dos = [dict(ad[0], dia=d, gasto=2500.0, resultados="") for d in dias_de(ayer, 2)]
    a2 = g2_sin_resultados(dos, u, ayer)
    chequear("G2 avisa al segundo dia aunque sea barato: ya es una racha",
             len(a2) == 1 and a2[0]["valor"] == 2)

    # G3 CTR: base sana, tres dias al piso.
    base = [{"id": "A2", "nombre": "Anuncio cansado", "campana": "C", "conjunto": "CJ",
             "dia": d, "gasto": 5000.0, "impresiones": 2000, "clics": 40, "ctr": 2.0,
             "resultados": 1, "indicador": "actions:lead", "estado": "ACTIVE"}
            for d in dias_de(ayer - datetime.timedelta(days=3), 7)]
    recientes = [{"id": "A2", "nombre": "Anuncio cansado", "campana": "C", "conjunto": "CJ",
                  "dia": d, "gasto": 5000.0, "impresiones": 2000, "clics": 10, "ctr": 0.5,
                  "resultados": 1, "indicador": "actions:lead", "estado": "ACTIVE"}
                 for d in dias_de(ayer, 3)]
    ctr_alertas = [x for x in g3_deterioro(base + recientes, [], u, ayer)
                   if x["tipo"] == "ctr_cayendo"]
    chequear("G3 CTR dispara con 3 dias 75% abajo de la base", len(ctr_alertas) == 1)
    sanos = [dict(x, clics=40) for x in recientes]
    chequear("G3 CTR se calla si el CTR se sostiene",
             not [x for x in g3_deterioro(base + sanos, [], u, ayer)
                  if x["tipo"] == "ctr_cayendo"])
    flacos = [dict(x, impresiones=100) for x in recientes]
    chequear("G3 CTR se calla con impresiones por debajo del piso diario",
             not [x for x in g3_deterioro(base + flacos, [], u, ayer)
                  if x["tipo"] == "ctr_cayendo"])

    # G3 CPL: base de 10 leads a 5.000, tres dias a 15.000.
    cbase = [{"id": "C1", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
              "dia": d, "gasto": 10000.0, "impresiones": 5000, "clics": 50, "ctr": 1.0,
              "resultados": 2, "indicador": "actions:lead", "estado": "ACTIVE"}
             for d in dias_de(ayer - datetime.timedelta(days=3), 7)]
    cmal = [{"id": "C1", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
             "dia": d, "gasto": 15000.0, "impresiones": 5000, "clics": 50, "ctr": 1.0,
             "resultados": 1, "indicador": "actions:lead", "estado": "ACTIVE"}
            for d in dias_de(ayer, 3)]
    chequear("G3 CPL dispara con 3 dias 3x la base",
             len([x for x in g3_deterioro([], cbase + cmal, u, ayer)
                  if x["tipo"] == "cpl_subiendo"]) == 1)
    awareness = [dict(x, indicador="profile_visit_view") for x in cbase + cmal]
    chequear("G3 CPL ignora campanas que no optimizan por lead",
             not [x for x in g3_deterioro([], awareness, u, ayer)
                  if x["tipo"] == "cpl_subiendo"])

    # G1: solo entidades vivas.
    errores = {"errors": json.dumps([
        {"id": "VIVO", "level": "ad", "errors": [{"error_message": "Ad rechazado"}],
         "children": []},
        {"id": "MUERTO", "level": "ad", "errors": [{"error_message": "Historia vieja"}],
         "children": []}])}
    roster = {"VIVO": {"nombre": "Anuncio vivo", "estado": "ACTIVE", "nivel": "anuncio"},
              "MUERTO": {"nombre": "Anuncio viejo", "estado": "PAUSED", "nivel": "anuncio"}}
    g1, _ = g1_errores(errores, roster, u)
    chequear("G1 deja pasar el error del anuncio activo y descarta el pausado",
             len(g1) == 1 and g1[0]["entidad"] == "Anuncio vivo")

    # G4a: el evento que ya paso y sigue gastando.
    camp = [{"id": "W1", "nombre": "JY | Webinar Mostrador", "campana": "", "conjunto": "",
             "dia": d, "gasto": 8000.0, "impresiones": 2000, "clics": 20, "ctr": 1.0,
             "frecuencia": 1.2, "resultados": 1, "indicador": "actions:lead",
             "estado": "ACTIVE"} for d in dias_de(ayer, 6)]
    eventos = {"JY | Webinar Mostrador": "2026-09-11"}
    g4 = g4_gasto_innecesario([], [], camp, eventos, u, ayer)
    chequear("G4a avisa del evento vencido que sigue gastando",
             len([x for x in g4 if x["tipo"] == "evento_vencido"]) == 1)
    chequear("G4a no se calla por tener resultados: el evento ya paso igual",
             any("plata tirada" in x["detalle"] for x in g4))
    chequear("G4a no opina de una campana sin fecha_evento cargada",
             not g4_gasto_innecesario([], [], camp, {}, u, ayer))
    futuro = {"JY | Webinar Mostrador": "2026-10-30"}
    chequear("G4a se calla si el evento todavia no paso",
             not g4_gasto_innecesario([], [], camp, futuro, u, ayer))

    # G4b: frecuencia de la VENTANA, no sumando dias.
    tot = [{"id": "Q1", "nombre": "Anuncio quemado", "campana": "JY | Conversiones",
            "conjunto": "", "dia": "", "gasto": 90000.0, "impresiones": 50000,
            "clics": 500, "ctr": 1.0, "frecuencia": 7.95, "resultados": 3,
            "indicador": "actions:lead", "estado": "ACTIVE"}]
    chequear("G4b avisa cuando la frecuencia de la ventana pasa el techo",
             len([x for x in g4_gasto_innecesario([], tot, [], {}, u, ayer)
                  if x["tipo"] == "publico_quemado"]) == 1)
    chequear("G4b se calla con frecuencia normal",
             not [x for x in g4_gasto_innecesario([], [dict(tot[0], frecuencia=1.4)],
                                                  [], {}, u, ayer)
                  if x["tipo"] == "publico_quemado"])
    chequear("G4b ignora un anuncio con gasto marginal",
             not [x for x in g4_gasto_innecesario([], [dict(tot[0], gasto=300.0)],
                                                  [], {}, u, ayer)
                  if x["tipo"] == "publico_quemado"])

    # G4c se saco: el test verifica que efectivamente ya no dispara.
    mudos = [{"id": "M1", "nombre": "Mudo", "campana": "C", "conjunto": "CJ", "dia": d,
              "gasto": 5000.0, "impresiones": 1000, "clics": 10, "ctr": 1.0,
              "frecuencia": 1.1, "resultados": "", "indicador": "actions:lead",
              "estado": "ACTIVE"} for d in dias_de(ayer, 6)]
    chequear("G4c ya no existe: se saco el 2026-09-25",
             not [x for x in g4_gasto_innecesario(mudos, [], [], {}, u, ayer)
                  if x["tipo"] == "gasto_sin_resultado"])

    # Roster: el caso real medido en esta cuenta el 2026-09-15.
    crudo = [
        {"id": "CAMP_VIVA", "nombre": "JY | Awareness Boxer Taller", "campana": "",
         "conjunto": "", "estado": "ACTIVE"},
        {"id": "CAMP_MUERTA", "nombre": "Hot Sale Mayo 2025", "campana": "",
         "conjunto": "", "estado": "PAUSED"},
        {"id": "AD_VIVO", "nombre": "Meme IA - Reel feed",
         "campana": "JY | Awareness Boxer Taller", "conjunto": "Conjunto 1",
         "estado": "WITH_ISSUES"},
        {"id": "AD_ZOMBI", "nombre": "Nuevo anuncio de Trafico",
         "campana": "Hot Sale Mayo 2025", "conjunto": "Re direccion al Feed",
         "estado": "WITH_ISSUES"},
    ]
    r = construir_roster([dict(x, dia="", gasto=0.0, impresiones=0, clics=0, ctr="",
                               resultados="", indicador="") for x in crudo], [])
    chequear("roster: un anuncio WITH_ISSUES de campana apagada NO cuenta como vivo",
             "AD_VIVO" in r and "AD_ZOMBI" not in r and "CAMP_MUERTA" not in r)

    # G0: el control de la trampa 6.
    dia = [{"id": "X", "nombre": "x", "campana": "", "conjunto": "", "dia": ayer.isoformat(),
            "gasto": 900.0, "impresiones": 0, "clics": 0, "ctr": "", "resultados": "",
            "indicador": "", "estado": "ACTIVE"}]
    dia = [dict(dia[0], id="X", nombre="Anuncio viejo")]
    total = [dict(dia[0], gasto=900.0),
             {"id": "NUEVO", "nombre": "DemoIA | Video35", "campana": "C", "conjunto": "CJ",
              "dia": "", "gasto": 1090.0, "impresiones": 0, "clics": 0, "ctr": "",
              "resultados": "", "indicador": "", "estado": "ACTIVE"}]
    g0, ctrl = g0_controles(dia, total, [], [], u, ayer)
    falta = [x for x in g0 if x["tipo"] == "datos_incompletos"]
    chequear("G0 avisa si el detalle diario se comio un anuncio", len(falta) == 1)
    chequear("y lo NOMBRA en vez de dar un porcentaje (por eso volvio el 25/09)",
             "DemoIA | Video35" in falta[0]["detalle"] and falta[0]["valor"] == 1)
    chequear("el numero tambien queda en los controles, para el lunes",
             ctrl["anuncio"]["diferencia_pct"] > 1 and ctrl["anuncio"]["cuadra"] is False)
    igual = [dict(x) for x in total]
    chequear("G0 se calla cuando el detalle trae todo",
             not [x for x in g0_controles(igual, total, [], [], u, ayer)[0]
                  if x["tipo"] == "datos_incompletos"])

    # Dedup.
    alerta = {"clave": "G2:A1", "tipo": "sin_resultados", "nivel": "anuncio",
              "entidad": "x", "titulo": "t", "detalle": "d", "valor": 4}
    estado = {"G2:A1": {"clave": "G2:A1", "valor": 4, "estado": "abierta",
                        "primer_aviso": "2026-09-14", "ultimo_aviso": "2026-09-14"}}
    mandar, silenciadas, _ = decidir([dict(alerta)], estado, u, hoy)
    chequear("dedup: una alerta ya avisada no se repite al dia siguiente",
             not mandar and len(silenciadas) == 1)
    mandar, _, _ = decidir([dict(alerta, valor=8)], estado, u, hoy)
    chequear("dedup: si escala, vuelve a avisar", len(mandar) == 1)
    viejo = {"G2:A1": dict(estado["G2:A1"], ultimo_aviso="2026-09-01")}
    mandar, _, _ = decidir([dict(alerta)], viejo, u, hoy)
    chequear("dedup: recordatorio a los 7 dias", len(mandar) == 1)
    _, _, resueltas = decidir([], estado, u, hoy)
    chequear("dedup: lo que deja de disparar queda resuelto", len(resueltas) == 1)

    # G3 rapido: el salto de un dia para el otro, que es lo que pidio Joana.
    salto = ([{"id": "C9", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
               "dia": d, "gasto": 10000.0, "impresiones": 0, "clics": 0, "ctr": None,
               "resultados": 5, "indicador": "actions:lead", "estado": "ACTIVE"}
              for d in dias_de(ayer - datetime.timedelta(days=1), 13)]
             + [{"id": "C9", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
                 "dia": ayer.isoformat(), "gasto": 10000.0, "impresiones": 0, "clics": 0,
                 "ctr": None, "resultados": 2, "indicador": "actions:lead", "estado": "ACTIVE"}])
    a3 = [x for x in g3_deterioro([], salto, u, ayer) if x["tipo"] == "cpl_subiendo"]
    chequear("G3 CPL avisa el mismo dia si salta +30% contra ayer", len(a3) == 1)
    chequear("y el aviso dice cuanto se movio, no solo que se movio",
             "De 2.000 a 5.000 ARS" in a3[0]["detalle"])

    chico = [dict(x, resultados=(2 if x["dia"] != ayer.isoformat() else 1)) for x in salto]
    chequear("G3 CPL NO dispara si el dia base tenia 2 leads (aritmetica de enteros)",
             not [x for x in g3_deterioro([], chico, u, ayer) if x["tipo"] == "cpl_subiendo"])

    ctr_salto = ([{"id": "A7", "nombre": "Pieza", "campana": "C", "conjunto": "CJ",
                   "dia": d, "gasto": 5000.0, "impresiones": 4000, "clics": 80, "ctr": 2.0,
                   "resultados": 1, "indicador": "actions:lead", "estado": "ACTIVE"}
                  for d in dias_de(ayer - datetime.timedelta(days=1), 13)]
                 + [{"id": "A7", "nombre": "Pieza", "campana": "C", "conjunto": "CJ",
                     "dia": ayer.isoformat(), "gasto": 5000.0, "impresiones": 4000,
                     "clics": 20, "ctr": 0.5, "resultados": 1,
                     "indicador": "actions:lead", "estado": "ACTIVE"}])
    chequear("G3 CTR avisa el mismo dia si cae 25% contra ayer",
             len([x for x in g3_deterioro(ctr_salto, [], u, ayer) if x["tipo"] == "ctr_cayendo"]) == 1)
    flaco = [dict(x, impresiones=800, clics=int(x["clics"] / 5)) for x in ctr_salto]
    chequear("G3 CTR NO dispara con pocas impresiones, aunque el % se desplome",
             not [x for x in g3_deterioro(flaco, [], u, ayer) if x["tipo"] == "ctr_cayendo"])

    # G5: la conciliacion con el CRM. Lo que se prueba sobre todo es el
    # SILENCIO, porque el hueco Meta-CRM es cronico (69%) y una regla mal
    # calibrada convierte la guardia en ruido diario.
    vent = dias_de(ayer, 7)
    meta_ok = {d: 5 for d in vent}
    crm_ok = {d: 4 for d in vent}                       # 80%: mejor que el normal
    chequear("G5 se calla con el hueco normal de la cuenta",
             not g5_conciliacion_crm(meta_ok, crm_ok, u, ayer))
    crm_hueco = {d: 3 for d in vent}                    # 60%: peor, pero es lo de siempre
    chequear("G5 NO dispara por el hueco cronico (60%, y lo normal es 69%)",
             not g5_conciliacion_crm(meta_ok, crm_hueco, u, ayer))

    crm_cero = dict(crm_ok, **{ayer.isoformat(): 0})
    a5 = g5_conciliacion_crm(meta_ok, crm_cero, u, ayer)
    # La cuenta de tres patas que pidio Joana: Meta - CRM - avisados = faltan.
    avisados = {d: 0 for d in vent}
    avisados[ayer.isoformat()] = 5                      # los 5 eran re-ingresos
    chequear("G5a NO dispara si Slack aviso a la SDR de todos esos leads",
             not [x for x in g5_conciliacion_crm(meta_ok, crm_cero, u, ayer, avisados)
                  if x["tipo"] == "tuberia_cortada"])
    avisados[ayer.isoformat()] = 1                      # 5 - 0 - 1 = 4 sin explicar
    a5r = [x for x in g5_conciliacion_crm(meta_ok, crm_cero, u, ayer, avisados)
           if x["tipo"] == "tuberia_cortada"]
    chequear("G5a dispara por los que NO se explican, y los cuenta bien",
             len(a5r) == 1 and "quedan 4 sin explicar" in a5r[0]["detalle"])
    chequear("y el titulo habla de los que no llegaron a ningun lado",
             a5r and a5r[0]["titulo"].startswith("4 leads"))
    chequear("G5a dispara si ayer Meta atribuyo leads y el CRM creo cero",
             [x["tipo"] for x in a5] == ["tuberia_cortada"] and a5[0]["valor"] == 1)

    flojo = dict(meta_ok, **{ayer.isoformat(): 2})
    chequear("G5a se calla si el dia en cero tuvo pocos leads en Meta (2 < 4)",
             not [x for x in g5_conciliacion_crm(flojo, crm_cero, u, ayer)
                  if x["tipo"] == "tuberia_cortada"])

    anteayer = (ayer - datetime.timedelta(days=1)).isoformat()
    crm_dos = dict(crm_cero, **{anteayer: 0})
    a5b = [x for x in g5_conciliacion_crm(meta_ok, crm_dos, u, ayer)
           if x["tipo"] == "tuberia_cortada"]
    chequear("G5a escala: dos dias cortada valen 2, y por eso vuelve a sonar",
             a5b and a5b[0]["valor"] == 2)

    crm_derrumbe = {d: 1 for d in vent}                 # 20%: antes disparaba G5b
    chequear("G5b ya no existe: se saco el 2026-09-25",
             not [x for x in g5_conciliacion_crm(meta_ok, crm_derrumbe, u, ayer)
                  if x["tipo"] == "conciliacion_derrumbada"])

    camp_g6 = [{"id": "C1", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
                "dia": ayer.isoformat(), "gasto": 9000.0, "impresiones": 0, "clics": 0,
                "ctr": None, "resultados": 6, "indicador": "actions:lead", "estado": "ACTIVE"},
               {"id": "C2", "nombre": "JY | Awareness", "campana": "", "conjunto": "",
                "dia": ayer.isoformat(), "gasto": 2000.0, "impresiones": 0, "clics": 0,
                "ctr": None, "resultados": 300, "indicador": "profile_visit_view",
                "estado": "ACTIVE"}]
    # G6: dia sin ningun lead en el CRM (Joana, 2026-09-30).
    gasto_ok = {d: 15000.0 for d in vent}
    chequear("G6 se calla si ayer entro al menos un lead",
             not g6_dia_sin_leads(crm_ok, gasto_ok, u, ayer))
    a6 = g6_dia_sin_leads(crm_cero, gasto_ok, u, ayer)
    chequear("G6 dispara si ayer el CRM quedo en cero con gasto de captacion",
             [x["clave"] for x in a6] == ["G6:dia-sin-leads"] and a6[0]["valor"] == 1)
    chequear("G6 se calla si G5a ya explico el cero (tuberia cortada)",
             not g6_dia_sin_leads(crm_cero, gasto_ok, u, ayer, g5_disparo=True))
    chequear("G6 se calla si ayer casi no se gasto en captacion",
             not g6_dia_sin_leads(crm_cero, dict(gasto_ok, **{ayer.isoformat(): 1000.0}), u, ayer))
    chequear("G6 escala: dos dias en cero valen 2",
             g6_dia_sin_leads(crm_dos, gasto_ok, u, ayer)[0]["valor"] == 2)
    chequear("G6 NO dispara por un dia flojo (1 lead, abajo del objetivo de 5)",
             not g6_dia_sin_leads(dict(crm_ok, **{ayer.isoformat(): 1}), gasto_ok, u, ayer))
    chequear("gasto de captacion: el awareness no cuenta",
             gasto_que_va_al_crm(camp_g6, [ayer.isoformat()])[ayer.isoformat()] == 9000.0)

    # Que resultados de Meta cuentan como "deberian estar en el CRM".
    camp = [{"id": "C1", "nombre": "JY | Conversiones", "campana": "", "conjunto": "",
             "dia": ayer.isoformat(), "gasto": 9000.0, "impresiones": 0, "clics": 0,
             "ctr": None, "resultados": 6, "indicador": "actions:lead", "estado": "ACTIVE"},
            {"id": "C2", "nombre": "JY | Awareness", "campana": "", "conjunto": "",
             "dia": ayer.isoformat(), "gasto": 2000.0, "impresiones": 0, "clics": 0,
             "ctr": None, "resultados": 300, "indicador": "profile_visit_view",
             "estado": "ACTIVE"}]
    m = resultados_que_van_al_crm(camp, [], [ayer.isoformat()])
    chequear("las visitas al perfil no cuentan como leads del CRM",
             m[ayer.isoformat()] == 6)
    conj_ev = sorted(CONJUNTOS_DE_EVENTO)[0]
    ads_ev = [{"id": "A9", "nombre": "x", "campana": "JY | Conversiones",
               "conjunto": conj_ev, "dia": ayer.isoformat(), "gasto": 1000.0,
               "impresiones": 0, "clics": 0, "ctr": None, "resultados": 2,
               "indicador": "actions:lead", "estado": "ACTIVE"}]
    m2 = resultados_que_van_al_crm(camp, ads_ev, [ayer.isoformat()])
    chequear("los conjuntos de evento se descuentan: van a otro origen del CRM",
             m2[ayer.isoformat()] == 4)

    # Parseo de plata, que es la trampa que mas caro sale.
    chequear("la plata en es-AR se lee bien", moneda("$20.498,46 ARS") == 20498.46)
    chequear("y se escribe bien", ars(37709.4) == "37.709")

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
