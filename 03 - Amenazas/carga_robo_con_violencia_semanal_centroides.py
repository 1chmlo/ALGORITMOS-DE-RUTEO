"""Carga salida/robo_con_violencia_semanal_centroides.geojson en la tabla robo_con_violencia_semanal_centroides.

Debe ejecutarse después de carga_robo_con_violencia_semanal_hexagonos.py (hex_id es clave foránea).
"""
from db import cargar_puntos

COLUMNAS = ["hex_id", "cantidad", "nivel", "niveles_total", "color"]

if __name__ == "__main__":
    cargar_puntos(
        "robo_con_violencia_semanal_centroides.geojson", "robo_con_violencia_semanal_centroides",
        COLUMNAS, "hex_id", reemplazar=True,
    )
