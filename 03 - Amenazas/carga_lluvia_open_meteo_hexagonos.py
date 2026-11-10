"""Carga salidas/lluvia_open_meteo_hexagonos.geojson en la tabla lluvia_open_meteo_hexagonos.

La tabla se reemplaza completa: es el pronóstico de la ventana de vuelo actual, no un histórico.
El ruteo aéreo (vista aristas_aereas_volables en 00 - DB/dijkstra.sql) la lee en cada consulta.
"""
from db import cargar_puntos

COLUMNAS = [
    "hex_id", "centro_lon", "centro_lat", "celda_modelo_lon", "celda_modelo_lat",
    "precipitacion_actual_mm_h", "precipitacion_max_mm_h", "probabilidad_max_pct",
    "hora_desde", "hora_hasta", "ventana_horas", "umbral_mm_h", "umbral_prob_pct",
    "simulado", "no_volable", "motivo", "tamanio_hexagono_m", "fecha_extraccion_utc", "fuente",
]

if __name__ == "__main__":
    cargar_puntos(
        "lluvia_open_meteo_hexagonos.geojson", "lluvia_open_meteo_hexagonos",
        COLUMNAS, "hex_id", reemplazar=True,
    )
