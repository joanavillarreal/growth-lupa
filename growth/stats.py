"""Herramientas para no confundir una tasa alta con un canal bueno.

Con ~230 prospectos y ~12 cierres por mes repartidos entre canales, las tasas
de conversión se calculan sobre puñados de eventos. Un canal con 17 prospectos
y 1 cierre muestra 5,9%, pero con un cierre más mostraría 11,8% y con uno menos
0%. Comparar ese número contra el 4,4% de un canal con 45 prospectos, como si
fueran equivalentes, lleva a mover presupuesto por ruido.

Todo lo de acá existe para responder una sola pregunta: ¿la diferencia que veo
es real, o entra dentro de lo que el azar explica?
"""
from __future__ import annotations
import math

Z95 = 1.96          # confianza del 95%
Z_POTENCIA80 = 0.8416


def wilson(exitos: int, n: int, z: float = Z95) -> tuple[float, float] | tuple[None, None]:
    """Intervalo de confianza de Wilson para una proporción.

    Se usa Wilson y no el intervalo normal clásico porque con pocos eventos
    el clásico devuelve cosas absurdas, como límites negativos.

    Devuelve (límite_inferior, límite_superior) en tanto por uno.
    """
    # Si hay más cierres que prospectos no estamos ante una proporción sino
    # ante el cruce de períodos (cerraron negociaciones que entraron antes).
    # Eso no tiene intervalo de confianza posible y no debe competir.
    if n <= 0 or exitos < 0 or exitos > n:
        return (None, None)
    p = exitos / n
    denom = 1 + z * z / n
    centro = p + z * z / (2 * n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centro - margen) / denom), min(1.0, (centro + margen) / denom))


def piso_confiable(exitos: int, n: int) -> float | None:
    """El límite inferior: la tasa que el canal sostiene aun siendo pesimista.

    Ordenar por este valor en lugar de por la tasa observada es lo que evita
    que un canal con tres datos le gane a uno con trescientos.
    """
    lb, _ = wilson(exitos, n)
    return lb


def distinguibles(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """¿Se puede afirmar que `a` convierte mejor que `b`?

    Sí solo si el piso de `a` queda por encima del techo de `b`: ahí los
    rangos no se superponen y la diferencia no se explica por azar.
    """
    a_lb, _ = wilson(*a)
    _, b_ub = wilson(*b)
    if a_lb is None or b_ub is None:
        return False
    return a_lb > b_ub


def n_necesario(p1: float, p2: float, z: float = Z95, zb: float = Z_POTENCIA80) -> int | None:
    """Prospectos por canal que harían falta para distinguir dos tasas.

    Sirve para contestar "¿cuánto más tengo que esperar?" con un número en
    vez de una intuición. Si la respuesta es mayor a lo que el negocio genera
    en un año, la comparación no se va a poder hacer nunca a ese nivel del
    funnel y hay que decidir mirando una etapa más temprana, donde hay más
    eventos.
    """
    if p1 == p2:
        return None
    media = (p1 + p2) / 2
    termino = (z * math.sqrt(2 * media * (1 - media))
               + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)))
    return math.ceil(termino ** 2 / (p1 - p2) ** 2)
