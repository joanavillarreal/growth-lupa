"""
Utilidades comunes del team creativo: rutas, semanas, conteo de palabras y el plan de la semana.

Lo importan revisar_plan.py, semana.py, rendimiento_agentes.py y tablero_redes.py.
No se corre solo.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_MARCAS = json.loads((RAIZ / "config" / "marcas.json").read_text(encoding="utf-8"))
CONFIG_EQUIPO = json.loads((RAIZ / "config" / "equipo.json").read_text(encoding="utf-8"))

# Estados de la semana, en orden. El plan pasa por todos; ninguno se saltea salvo
# DISENO_EN_APROBACION, que se omite cuando config/equipo.json dice joana_aprueba_diseno: false.
ESTADOS = [
    "BORRADOR",                 # Chispa está escribiendo
    "EN_REVISION",              # Batuta revisa el plan (revisión 1)
    "PLAN_EN_APROBACION",       # Joana tiene el artefacto de la semana
    "PLAN_APROBADO",            # todas las piezas aceptadas
    "EN_DISENO",                # Pixel diseña
    "DISENO_EN_REVISION",       # Batuta revisa el diseño (revisión 2)
    "DISENO_EN_APROBACION",     # Joana aprueba los diseños
    "DISENO_APROBADO",
    "EN_PUBLICACION",           # Turbo carga en Metricool
    "PUBLICACION_EN_APROBACION",  # Joana aprueba en Metricool
    "CERRADA",
]

FORMATOS_DISENADOS = ("carrusel", "placa", "historia")
FORMATOS = FORMATOS_DISENADOS + ("reel", "linkedin")


def semana_iso(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def rango_semana(semana: str):
    """'2026-W40' -> (lunes, domingo) como date."""
    y, w = semana.split("-W")
    lunes = date.fromisocalendar(int(y), int(w), 1)
    return lunes, lunes + timedelta(days=6)


def carpeta_semana(semana: str) -> Path:
    return RAIZ / "contenido" / semana


def ruta_plan(semana: str) -> Path:
    return carpeta_semana(semana) / "plan.json"


def cargar_plan(semana: str) -> dict:
    return json.loads(ruta_plan(semana).read_text(encoding="utf-8"))


def guardar_plan(semana: str, plan: dict) -> Path:
    ruta = ruta_plan(semana)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ruta


HASHTAG = re.compile(r"#[\wÁÉÍÓÚáéíóúÑñÜü]+")
PALABRA = re.compile(r"[\wÁÉÍÓÚáéíóúÑñÜü]+(?:['’.-][\wÁÉÍÓÚáéíóúÑñÜü]+)*")


def palabras(texto) -> int:
    """Palabras de un texto, sin contar hashtags ni emojis."""
    if not texto:
        return 0
    return len(PALABRA.findall(HASHTAG.sub(" ", str(texto))))


def hashtags(texto) -> list:
    return HASHTAG.findall(texto or "")


CTA = re.compile(r"[Cc]oment[aá]\s+[\"“«]?([A-ZÁÉÍÓÚÑ]{3,})")


def palabras_clave(texto) -> list:
    """Palabras clave de CTA de comentario ("Comentá LUNES") que aparecen en un texto."""
    return [m.upper() for m in CTA.findall(texto or "")]
