"""Gasto diario de Google Ads leído de la API (Google Ads API, REST).

Las credenciales llegan por variables de entorno del entorno de la rutina y
nunca se escriben en disco ni se loguean:

  GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN
  GOOGLE_ADS_CUSTOMER_ID          la cuenta que gasta (AIT Solutions)
  GOOGLE_ADS_LOGIN_CUSTOMER_ID    la MCC por la que se entra
  GOOGLE_ADS_DEVELOPER_TOKEN      opcional acá: el proxy del entorno ya lo pone

Los montos vienen en micros de la moneda de la cuenta (ARS). Contra el export
CSV que se cargaba a mano coincide al centavo (verificado 08/09 a 14/09/2026).
"""
from __future__ import annotations
import os
import requests

# Google da de baja cada versión al año más o menos. Si todas dan 404, sumá
# la vigente adelante: https://developers.google.com/google-ads/api/docs/sunset-dates
VERSIONES = ("v23", "v24", "v25", "v22")
TIMEOUT = 60


class GoogleAdsError(RuntimeError):
    pass


def _env(nombre: str) -> str:
    v = os.environ.get(nombre, "").strip()
    if not v:
        raise GoogleAdsError(f"Falta la variable de entorno {nombre}.")
    return v


def _token() -> str:
    r = requests.post("https://oauth2.googleapis.com/token", timeout=TIMEOUT, data={
        "client_id": _env("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    })
    datos = r.json()
    if "access_token" not in datos:
        raise GoogleAdsError(f"OAuth rechazado: {datos.get('error')} {datos.get('error_description', '')}")
    return datos["access_token"]


def _buscar(query: str) -> list[dict]:
    cid = _env("GOOGLE_ADS_CUSTOMER_ID").replace("-", "")
    headers = {"Authorization": f"Bearer {_token()}",
               "login-customer-id": _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID").replace("-", "")}
    if os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
        headers["developer-token"] = os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]
    for v in VERSIONES:
        url = f"https://googleads.googleapis.com/{v}/customers/{cid}/googleAds:search"
        filas, token_pagina = [], None
        while True:
            cuerpo = {"query": query}
            if token_pagina:
                cuerpo["pageToken"] = token_pagina
            r = requests.post(url, headers=headers, json=cuerpo, timeout=TIMEOUT)
            if r.status_code == 404:
                break  # versión dada de baja, probamos la siguiente
            if r.status_code != 200:
                raise GoogleAdsError(f"HTTP {r.status_code}: {r.text[:400]}")
            datos = r.json()
            filas.extend(datos.get("results", []))
            token_pagina = datos.get("nextPageToken")
            if not token_pagina:
                return filas
    raise GoogleAdsError(f"Ninguna versión de la API respondió ({', '.join(VERSIONES)}).")


def moneda() -> str:
    return _buscar("SELECT customer.currency_code FROM customer")[0]["customer"]["currencyCode"]


def gasto_diario(desde: str, hasta: str) -> dict[str, float]:
    """{'YYYY-MM-DD': monto en la moneda de la cuenta}. Un día sin fila es un día sin gasto."""
    filas = _buscar(
        "SELECT segments.date, metrics.cost_micros FROM customer "
        f"WHERE segments.date BETWEEN '{desde}' AND '{hasta}'")
    out: dict[str, float] = {}
    for f in filas:
        d = f["segments"]["date"]
        out[d] = out.get(d, 0.0) + int(f["metrics"].get("costMicros", 0)) / 1e6
    return out
