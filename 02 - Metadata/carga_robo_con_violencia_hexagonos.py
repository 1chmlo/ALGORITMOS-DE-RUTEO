"""Carga salida/robo_con_violencia_hexagonos.geojson en la tabla robo_con_violencia_hexagonos.

La tabla se reemplaza completa: STOP entrega una ventana móvil de 90 días, no un histórico.
Al vaciarla se borran también los centroides (ON DELETE CASCADE), que se cargan después.
"""
from db import cargar_puntos

COLUMNAS = [
    "hex_id", "stop_id", "codigo_delito", "tipo_delito", "cantidad", "nivel", "niveles_total",
    "rango", "color", "color_border", "fecha_min", "fecha_max", "periodo_desde", "periodo_hasta",
    "tamanio_hexagono_m", "fuente",
]

if __name__ == "__main__":
    cargar_puntos(
        "robo_con_violencia_hexagonos.geojson", "robo_con_violencia_hexagonos", COLUMNAS, "hex_id",
        reemplazar=True,
    )
