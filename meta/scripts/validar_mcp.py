#!/usr/bin/env python3
"""
Valida las respuestas de Meta guardadas en una carpeta del día ANTES de usarlas.

Uso:
    python3 scripts/validar_mcp.py datos/meta-ads/guardia/<hoy>/
    python3 scripts/validar_mcp.py --autotest

Las respuestas de los conectores se guardan tal cual vinieron (copiando el archivo de
resultado si es grande, o el texto exacto si es chico): nunca transcritas a mano ni
reformateadas. Este script es el freno que lo comprueba:

  1. Cada `mcp/*.json` abre como JSON, y su contenido interno (`ad_entities`, que Meta manda
     como texto JSON) también abre.
  2. Los totales cuadran: el gasto de cada campaña en `campana-total` es la suma de sus días en
     `campana-diario`, y lo mismo anuncio por anuncio entre `anuncio-total` y `anuncio-diario`
     (tolerancia de 1 ARS por redondeo). Una diferencia mayor es una respuesta cortada, mal
     copiada o de otra ventana.
  3. El roster trae las tres llamadas (campaign, adset, ad).

Código 0 = todo bien. Código 1 = algo no cuadra: el análisis NO sigue, se vuelve a pedir la
respuesta a Meta y, si sigue sin cuadrar, se marca fallido con este mensaje.
"""
import argparse, glob, json, os, sys
from collections import defaultdict

TOLERANCIA_ARS = 1.0


def interno(d):
    """Lo que trae una respuesta de ads_get_ad_entities: lista de filas."""
    r = d.get("ad_entities", d) if isinstance(d, dict) else d
    return json.loads(r) if isinstance(r, str) else r


def gasto(fila):
    v = (fila.get("amount_spent") or {})
    v = v.get("value") if isinstance(v, dict) else v
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def por_id(filas):
    out = defaultdict(float)
    for f in filas:
        out[f.get("id")] += gasto(f)
    return out


def cuadrar(total, diario, nivel):
    errores = []
    t, d = por_id(total), por_id(diario)
    for i, monto in t.items():
        if abs(monto - d.get(i, 0.0)) > TOLERANCIA_ARS:
            errores.append(f"{nivel} {i}: total {monto:,.2f} ARS, suma de los días {d.get(i, 0.0):,.2f} ARS")
    suma_t, suma_d = sum(t.values()), sum(d.values())
    if abs(suma_t - suma_d) > TOLERANCIA_ARS:
        errores.append(f"{nivel}: gasto total {suma_t:,.2f} ARS vs suma diaria {suma_d:,.2f} ARS")
    return errores


def validar(carpeta):
    errores, leidos = [], {}
    for ruta in sorted(glob.glob(os.path.join(carpeta, "mcp", "*.json"))):
        nombre = os.path.basename(ruta)
        try:
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
            if nombre == "roster.json":
                filas = [interno(x) for x in d]
                if len(filas) != 3:
                    errores.append(f"roster.json: trae {len(filas)} llamadas, se esperan 3 (campaign, adset, ad)")
            elif isinstance(d, dict) and "ad_entities" in d:
                filas = interno(d)
                if not isinstance(filas, list):
                    errores.append(f"{nombre}: ad_entities no es una lista")
            else:
                filas = d
            leidos[nombre] = filas
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            errores.append(f"{nombre}: no abre como JSON ({e})")
    if not leidos:
        errores.append(f"no hay respuestas en {os.path.join(carpeta, 'mcp')}")
    for total, diario, nivel in (("campana-total.json", "campana-diario.json", "campaña"),
                                 ("anuncio-total.json", "anuncio-diario.json", "anuncio")):
        if total in leidos and diario in leidos:
            errores += cuadrar(leidos[total], leidos[diario], nivel)
    return errores, sorted(leidos)


def autotest():
    t = [{"id": "1", "amount_spent": {"value": "100.5"}}, {"id": "2", "amount_spent": {"value": "50"}}]
    d = [{"id": "1", "amount_spent": {"value": "60"}}, {"id": "1", "amount_spent": {"value": "40.5"}},
         {"id": "2", "amount_spent": {"value": "50"}}]
    ok = cuadrar(t, d, "x") == []
    malo = cuadrar(t, d[:2], "x")
    ok &= len(malo) == 2 and "x 2" in malo[0]
    ok &= interno({"ad_entities": '[{"id": "1"}]'}) == [{"id": "1"}]
    print("TODO OK" if ok else "FALLA")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("carpeta", nargs="?")
    ap.add_argument("--autotest", action="store_true")
    a = ap.parse_args()
    if a.autotest:
        sys.exit(autotest())
    if not a.carpeta:
        ap.error("falta la carpeta")
    errores, leidos = validar(a.carpeta)
    if errores:
        print("NO CUADRA — no seguir con estas respuestas:")
        for e in errores:
            print(f"  - {e}")
        sys.exit(1)
    print(f"OK: {len(leidos)} respuestas abren y los totales cuadran ({', '.join(leidos)})")


if __name__ == "__main__":
    main()
