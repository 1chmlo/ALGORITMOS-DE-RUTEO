"""Carga salidas/cortes_ruta_tomtom.geojson en la tabla cortes_ruta_tomtom.

Se reemplaza en cada ejecución porque los cortes de ruta corresponden a incidentes activos.
"""
from db import cargar_puntos

COLUMNAS = [
    "incident_id",
    "icon_category",
    "tipo_amenaza",
    "descripcion_evento",
    "codigo_evento",
    "magnitud_retraso",
    "desde_via",
    "hasta_via",
    "numeros_ruta",
    "longitud_m",
    "retraso_seg",
    "probabilidad",
    "validez_temporal",
    "fecha_inicio",
    "fecha_fin",
    "en_maipu",
    "bloqueo_total",
    "centroide_lon",
    "centroide_lat",
    "fuente",
]

if __name__ == "__main__":
    cargar_puntos(
        "cortes_ruta_tomtom.geojson",
        "cortes_ruta_tomtom",
        COLUMNAS,
        "incident_id",
        reemplazar=True,
    )
