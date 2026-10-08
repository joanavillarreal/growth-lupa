#!/usr/bin/env python3
"""
Trae los PROSPECTOS del canal de Meta Ads directo del CRM Bitrix24 y escribe el
CSV reducido que consume `analizar_crm.py`. Reemplaza el export manual.

Uso:
    python3 scripts/traer_prospectos.py datos/crm/2026-W37/prospectos.csv
    python3 scripts/traer_prospectos.py <salida> --desde 2026-03-01 --hasta 2026-09-06

Requiere la variable de entorno BITRIX_WEBHOOK_URL (ver referencias/bitrix.md).
Nunca imprime la URL del webhook ni pide datos personales.

Solo trae PROSPECTOS, nunca NEGOCIACIONES.
Los IDs de opcion de los campos de lista se resuelven en cada corrida contra
`crm.lead.fields`: si alguien agrega una razon de descarte nueva en Bitrix,
aparece sola sin tocar el script.
"""
import argparse, csv, datetime, json, os, sys, time, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(RAIZ, "config", "campanas.json")

# Origenes que SIEMPRE se traen: los tres del canal.
#   3          Meta Ads Formulario  -> formulario nativo de Meta (lead ad)
#   UC_HDLOFX  Meta Ads             -> clic al boton de WhatsApp desde un anuncio
#   UC_GJPS17  Redes                -> organico de IG/FB. NO es pauta: entra como
#                                      contraste, nunca se mezcla en los KPI del canal.
ORIGENES_BASE = {
    "3": "Meta Ads Formulario",
    "UC_HDLOFX": "Meta Ads",
    "UC_GJPS17": "Redes",
}


def origenes():
    """Los tres del canal + todos los que aparezcan en config/campanas.json.

    Las campanas eventuales (webinars, cursos, presenciales) guardan sus leads
    en su propio origen del CRM. Para poder cruzarlas hay que traerlos tambien.
    Si el archivo no esta, se trabaja solo con los tres del canal.
    """
    out = dict(ORIGENES_BASE)
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"[aviso] no se pudo leer {CONFIG} ({e}); se traen solo los tres "
              f"origenes del canal.", file=sys.stderr)
        return out
    for nombre, sid in (cfg.get("origenes") or {}).items():
        out.setdefault(str(sid), nombre)
    return out


ORIGENES = origenes()

# Campos personalizados. Los codigos son estables; las opciones se resuelven
# en runtime. crm.lead.fields NO devuelve el titulo en espanol: los nombres de
# esta tabla los pusimos nosotros identificando el campo por sus opciones.
CAMPOS = {
    "UF_CRM_1772648753515": "Tipo de negocio",
    "UF_CRM_1772731499441": "Razon de no derivacion",
    "UF_CRM_1773070614344": "Interes en producto",
    "UF_CRM_1772649355387": "Prioridad",
    "UF_CRM_1782833237269": "Contacto efectivo",
}

COLUMNAS = [
    "ID", "Etapa", "Origen", "Creado",
    "Razon de no derivacion", "Tipo de negocio", "Interes en producto",
    "Prioridad", "Contacto efectivo",
    "UTM Source", "UTM Medium", "UTM Campaign", "UTM Content", "UTM Term",
]
PAUSA = 0.4   # Bitrix tolera ~2 req/s; no apurarlo

# El portal de Bitrix devuelve DATE_CREATE en su propia zona (+03:00), no en la
# de Argentina. Son 6 horas: un prospecto de las 20:00 del domingo ART sale como
# lunes en la API y caeria en la semana ISO equivocada.
ART = ZoneInfo("America/Argentina/Buenos_Aires")


def a_hora_argentina(iso):
    """'2026-09-06T00:26:56+03:00' -> datetime en ART. None si no parsea."""
    if not iso:
        return None
    try:
        return datetime.datetime.fromisoformat(iso).astimezone(ART)
    except ValueError:
        return None


def base():
    url = os.environ.get("BITRIX_WEBHOOK_URL", "").strip()
    if not url:
        raise SystemExit(
            "Falta BITRIX_WEBHOOK_URL. Cargarla como variable de entorno del\n"
            "environment de Claude Code (ver referencias/bitrix.md)."
        )
    return url if url.endswith("/") else url + "/"


def llamar(metodo, params=None):
    """POST al webhook. Devuelve el bloque `result`."""
    datos = urllib.parse.urlencode(params or {}, doseq=True).encode()
    req = urllib.request.Request(base() + metodo, data=datos)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            cuerpo = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo}: HTTP {e.code}. {e.read()[:300].decode(errors='replace')}")
    except OSError as e:
        raise SystemExit(
            f"{metodo}: no se pudo conectar ({e}).\n"
            "Si es un 403 en el CONNECT, el dominio de Bitrix no esta permitido en\n"
            "la politica de red del environment. No es la credencial."
        )
    if "error" in cuerpo:
        raise SystemExit(f"{metodo}: {cuerpo.get('error')} - {cuerpo.get('error_description')}")
    return cuerpo.get("result")


def catalogo(entity_id):
    """STATUS_ID -> nombre visible, para etapas (STATUS) u origenes (SOURCE)."""
    return {r["STATUS_ID"]: r["NAME"]
            for r in llamar("crm.status.list", {"filter[ENTITY_ID]": entity_id})}


def opciones():
    """{campo: {id_opcion: texto}} para los campos de lista que nos importan."""
    fields = llamar("crm.lead.fields")
    out = {}
    for code in CAMPOS:
        v = fields.get(code) or {}
        out[code] = {str(i["ID"]): i["VALUE"] for i in (v.get("items") or [])}
        if not out[code]:
            print(f"[aviso] {code} ({CAMPOS[code]}) no devolvio opciones; "
                  f"los valores van a salir como ID crudo.", file=sys.stderr)
    return out


def prospectos(desde=None, hasta=None):
    """Pagina crm.lead.list filtrando por los origenes del canal."""
    seleccion = ["ID", "STATUS_ID", "SOURCE_ID", "DATE_CREATE",
                 "UTM_SOURCE", "UTM_MEDIUM", "UTM_CAMPAIGN", "UTM_CONTENT", "UTM_TERM"]
    seleccion += list(CAMPOS)
    filtro = {f"filter[SOURCE_ID][{i}]": s for i, s in enumerate(ORIGENES)}
    # El filtro de la API corre en la zona del portal: se pide un dia de mas a
    # cada lado y se recorta con precision despues, ya en ART.
    dia = datetime.timedelta(days=1)
    if desde:
        d = datetime.date.fromisoformat(desde) - dia
        filtro["filter[>=DATE_CREATE]"] = f"{d}T00:00:00"
    if hasta:
        h = datetime.date.fromisoformat(hasta) + dia
        filtro["filter[<=DATE_CREATE]"] = f"{h}T23:59:59"

    filas, start, pagina = [], 0, 0
    while True:
        params = dict(filtro)
        params["select[]"] = seleccion
        params["start"] = start
        params["order[DATE_CREATE]"] = "ASC"
        lote = llamar("crm.lead.list", params) or []
        filas.extend(lote)
        pagina += 1
        print(f"  pagina {pagina}: {len(lote)} prospectos (acumulado {len(filas)})",
              file=sys.stderr)
        if len(lote) < 50:
            break
        start += 50
        time.sleep(PAUSA)

    d0 = datetime.date.fromisoformat(desde) if desde else None
    d1 = datetime.date.fromisoformat(hasta) if hasta else None
    dentro, fuera = [], 0
    for f in filas:
        art = a_hora_argentina(f.get("DATE_CREATE"))
        f["_art"] = art
        if art and ((d0 and art.date() < d0) or (d1 and art.date() > d1)):
            fuera += 1
            continue
        dentro.append(f)
    if fuera:
        print(f"  descartados {fuera} fuera de rango en hora argentina", file=sys.stderr)
    return dentro


def main():
    ap = argparse.ArgumentParser(
        description="Trae los prospectos del canal de Meta Ads desde Bitrix24.")
    ap.add_argument("salida", help="Ruta del CSV a escribir")
    ap.add_argument("--desde", help="Fecha inicial YYYY-MM-DD")
    ap.add_argument("--hasta", help="Fecha final YYYY-MM-DD")
    a = ap.parse_args()

    print("Resolviendo catalogos...", file=sys.stderr)
    etapas = catalogo("STATUS")
    fuentes = catalogo("SOURCE")
    opts = opciones()

    print(f"Trayendo prospectos de {len(ORIGENES)} origenes...", file=sys.stderr)
    filas = prospectos(a.desde, a.hasta)
    if not filas:
        raise SystemExit("No vino ningun prospecto. Revisar el rango de fechas.")

    huerfanas = set()

    def enum(fila, code):
        """Resuelve un campo de lista a su texto.

        Si el ID guardado ya no existe en la definicion (alguien borro la opcion
        en Bitrix pero los leads viejos la siguen teniendo), se marca explicito:
        devolver el numero pelado inventaria una categoria falsa en los conteos.
        """
        val = fila.get(code)
        if val in (None, "", []):
            return ""
        if isinstance(val, list):
            val = val[0] if val else ""
        texto = opts.get(code, {}).get(str(val))
        if texto is None:
            huerfanas.add((CAMPOS[code], str(val)))
            return f"(opcion eliminada: {val})"
        return texto

    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    with open(a.salida, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writeheader()
        for f in filas:
            art = f.get("_art") or a_hora_argentina(f.get("DATE_CREATE"))
            w.writerow({
                "ID": f.get("ID", ""),
                "Etapa": etapas.get(f.get("STATUS_ID"), f.get("STATUS_ID") or ""),
                "Origen": fuentes.get(str(f.get("SOURCE_ID")), f.get("SOURCE_ID") or ""),
                "Creado": art.strftime("%d/%m/%Y %H:%M:%S") if art else "",
                "Razon de no derivacion": enum(f, "UF_CRM_1772731499441"),
                "Tipo de negocio": enum(f, "UF_CRM_1772648753515"),
                "Interes en producto": enum(f, "UF_CRM_1773070614344"),
                "Prioridad": enum(f, "UF_CRM_1772649355387"),
                "Contacto efectivo": enum(f, "UF_CRM_1782833237269"),
                "UTM Source": f.get("UTM_SOURCE") or "",
                "UTM Medium": f.get("UTM_MEDIUM") or "",
                "UTM Campaign": f.get("UTM_CAMPAIGN") or "",
                "UTM Content": f.get("UTM_CONTENT") or "",
                "UTM Term": f.get("UTM_TERM") or "",
            })

    print(f"\n{len(filas)} prospectos -> {a.salida}")
    print("Fechas convertidas a hora argentina (la API las devuelve en la zona del portal).")
    print("Sin datos personales: no se piden nombres, telefonos ni comentarios.")
    por_origen = {}
    for f in filas:
        n = fuentes.get(str(f.get("SOURCE_ID")), str(f.get("SOURCE_ID")))
        por_origen[n] = por_origen.get(n, 0) + 1
    print("\nPor origen:")
    for n, c in sorted(por_origen.items(), key=lambda kv: -kv[1]):
        print(f"  {c:>5}  {n}")
    con_utm = sum(1 for f in filas if f.get("UTM_SOURCE"))
    print(f"\nCon UTM: {con_utm} de {len(filas)}.")
    if con_utm == 0:
        print("  ^ Sigue en cero: el canal de Meta no tiene atribucion a campana/anuncio.")
        print("    Ver memoria/baseline.md (Hallazgo 1) y informes/setup-pendiente.md (B3).")
    if huerfanas:
        print("\n[!] Opciones borradas en Bitrix que siguen guardadas en prospectos:")
        for campo, oid in sorted(huerfanas):
            print(f"      {campo}: ID {oid} - la etiqueta ya no existe en el campo.")


if __name__ == "__main__":
    main()
