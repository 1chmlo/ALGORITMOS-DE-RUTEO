"""Carga salida/tomtom_trafico.geojson en la tabla tomtom_trafico.

Se reemplaza en cada ejecución porque el flujo de tráfico corresponde al estado actual.
"""
from db import cargar_puntos

COLUMNAS = [
    "segment_id",
    "corredor_vial",
    "comuna",
    "frc",
    "velocidad_actual_kmh",
    "velocidad_flujo_libre_kmh",
    "diferencia_velocidad_kmh",
    "razon_velocidad",
    "indice_congestion",
    "tiempo_actual_seg",
    "tiempo_flujo_libre_seg",
    "demora_seg",
    "confianza",
    "cierre_vial",
    "nivel_riesgo_trafico",
    "factor_riesgo_trafico",
    "punto_consulta_lat",
    "punto_consulta_lon",
    "vertices_count",
]

if __name__ == "__main__":
    cargar_puntos(
        "tomtom_trafico.geojson",
        "tomtom_trafico",
        COLUMNAS,
        "segment_id",
        reemplazar=True,
    )
