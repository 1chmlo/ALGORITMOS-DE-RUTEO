"""Carga salidas/viento_open_meteo_hexagonos.geojson en la tabla viento_open_meteo_hexagonos.

La tabla se reemplaza completa: es el pronóstico de la ventana de vuelo actual, no un histórico.
El ruteo aéreo (vista aristas_aereas_volables en 00 - DB/dijkstra.sql) la lee en cada consulta.
"""
from db import cargar_puntos

COLUMNAS = [
    "hex_id", "centro_lon", "centro_lat", "celda_modelo_lon", "celda_modelo_lat",
    "viento_actual_kmh", "viento_max_kmh", "rafaga_max_kmh", "direccion_grados",
    "hora_desde", "hora_hasta", "ventana_horas", "umbral_kmh", "umbral_rafaga_kmh",
    "simulado", "no_volable", "motivo", "tamanio_hexagono_m", "fecha_extraccion_utc", "fuente",
]

if __name__ == "__main__":
    cargar_puntos(
        "viento_open_meteo_hexagonos.geojson", "viento_open_meteo_hexagonos",
        COLUMNAS, "hex_id", reemplazar=True,
    )
