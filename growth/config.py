"""Carga de config/definitions.yaml y helpers de mapeo origen -> canal."""
from __future__ import annotations
from pathlib import Path
import yaml

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "config" / "definitions.yaml"
DIR_SNAPSHOTS = RAIZ / "data" / "snapshots"
DIR_HISTORIA = RAIZ / "data" / "history"


class Config:
    def __init__(self, ruta: Path = RUTA_CONFIG):
        self.d = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        # índice inverso: SOURCE_ID -> clave de canal
        self._por_origen: dict[str, str] = {}
        for clave, canal in self.d["canales"].items():
            for origen in canal["origenes"]:
                self._por_origen[str(origen)] = clave
        # índice inverso: tipo de gasto -> clave de canal
        self._por_tipo_gasto: dict[int, str] = {}
        for clave, canal in self.d["canales"].items():
            for tipo in canal.get("tipos_gasto", []):
                self._por_tipo_gasto[int(tipo)] = clave

    def __getitem__(self, k):
        return self.d[k]

    def canal_de_origen(self, source_id) -> str:
        """Devuelve la clave del canal para un SOURCE_ID, o 'sin_atribuir'."""
        return self._por_origen.get(str(source_id or ""), "sin_atribuir")

    def canal_de_tipo_gasto(self, tipo) -> str | None:
        try:
            return self._por_tipo_gasto.get(int(tipo))
        except (TypeError, ValueError):
            return None

    def es_overhead(self, tipo) -> bool:
        try:
            return int(tipo) in self.d["gasto"]["tipos_overhead"]
        except (TypeError, ValueError):
            return False

    @property
    def canales(self) -> dict:
        return self.d["canales"]

    @property
    def canales_activos(self) -> list[str]:
        return [k for k, v in self.d["canales"].items() if v.get("activo")]

    def nombre_canal(self, clave: str) -> str:
        if clave == "sin_atribuir":
            return "Sin atribuir"
        return self.d["canales"].get(clave, {}).get("nombre", clave)
