# Mapa conjunto -> campana de marzo a junio

Respuesta cruda de `ads_get_ad_entities`, nivel conjunto, 01/03 al 30/06, SIN
`time_increment` (un total por conjunto), traida el 2026-09-28.

Existe solo para el mapa: desde el 2026-09-27 el panel trae el Q anterior entero
para comparar, y los CSV del Administrador de marzo-junio no dicen de que
campana cuelga cada conjunto. Sin esto, 297.835 ARS de conjuntos de evento
(Lead Magnet, After Automechanika, Campana Webinar Marketing) no se descontaban
del gasto cruzable del Q2. Los cinco cuelgan de
`7. Clientes potenciales - formulario - Copia`.

No es una serie diaria y `panel_meta.py` no lo suma como gasto: solo lee de
aca el nombre del conjunto y su campana (`mapa_conjunto_campana`).
