"""Cliente REST de Bitrix24 sobre el webhook entrante.

El webhook llega por la variable de entorno BITRIX_WEBHOOK_URL y nunca se
escribe en disco ni se loguea: contiene el token de acceso al CRM.
"""
from __future__ import annotations
import os
import time
import requests

TIMEOUT = 60
REINTENTOS = 4


class BitrixError(RuntimeError):
    pass


class Bitrix:
    def __init__(self, webhook: str | None = None):
        url = webhook or os.environ.get("BITRIX_WEBHOOK_URL", "")
        if not url:
            raise BitrixError(
                "Falta BITRIX_WEBHOOK_URL. Cargala como variable de entorno; "
                "no la pongas en un archivo del repo."
            )
        self.base = url.rstrip("/")
        self.sesion = requests.Session()

    def llamar(self, metodo: str, **params) -> dict:
        """Una llamada REST, con reintento exponencial ante error de red o rate limit."""
        espera = 2
        for intento in range(REINTENTOS):
            try:
                r = self.sesion.post(f"{self.base}/{metodo}.json", json=params, timeout=TIMEOUT)
                if r.status_code == 503 or r.status_code == 429:
                    raise requests.RequestException(f"HTTP {r.status_code}")
                datos = r.json()
            except (requests.RequestException, ValueError) as e:
                if intento == REINTENTOS - 1:
                    raise BitrixError(f"{metodo}: fallo de red tras {REINTENTOS} intentos ({e})")
                time.sleep(espera)
                espera *= 2
                continue
            if "error" in datos:
                raise BitrixError(f"{metodo}: {datos.get('error')} - {datos.get('error_description')}")
            return datos
        raise BitrixError(f"{metodo}: agotados los reintentos")

    def listar(self, metodo: str, **params) -> list[dict]:
        """Lista paginada completa (crm.lead.list, crm.deal.list, ...)."""
        salida, start = [], 0
        while True:
            datos = self.llamar(metodo, start=start, **params)
            salida.extend(datos.get("result") or [])
            if "next" not in datos:
                return salida
            start = datos["next"]

    def listar_items(self, entity_type_id: int, **params) -> list[dict]:
        """Lista paginada de un SPA (crm.item.list devuelve {'items': [...]})."""
        salida, start = [], 0
        while True:
            datos = self.llamar("crm.item.list", entityTypeId=entity_type_id, start=start, **params)
            salida.extend(datos["result"]["items"])
            if "next" not in datos:
                return salida
            start = datos["next"]

    def catalogo_origenes(self) -> dict[str, str]:
        """SOURCE_ID -> nombre legible."""
        filas = self.llamar("crm.status.list", filter={"ENTITY_ID": "SOURCE"})["result"]
        return {f["STATUS_ID"]: f["NAME"] for f in filas}
