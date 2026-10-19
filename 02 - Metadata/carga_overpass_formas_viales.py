"""Carga salida/overpass_formas_viales.geojson en la tabla overpass_formas_viales."""
from db import cargar_puntos

COLUMNAS = [
    "osm_id",
    "nombre",
    "ref_via",
    "highway",
    "junction",
    "comuna",
    "oneway",
    "lanes",
    "maxspeed_kmh",
    "es_enlace_salida",
    "es_curva_pronunciada",
    "forma_vial",
    "longitud_m",
    "distancia_recta_m",
    "indice_sinuosidad",
    "angulo_giro_max_grados",
    "angulo_giro_total_grados",
    "factor_riesgo_geom",
    "centroide_lon",
    "centroide_lat",
]

if __name__ == "__main__":
    cargar_puntos(
        "overpass_formas_viales.geojson",
        "overpass_formas_viales",
        COLUMNAS,
        "osm_id",
    )
