"""Carga salida/comisarias.geojson en la tabla comisarias."""
from db import cargar_puntos

COLUMNAS = [
    "objectid", "codigo_unidad", "nombre", "tipo_unidad", "direccion", "cod_region",
    "region", "cod_provincia", "provincia", "cod_comuna", "comuna", "prefectura",
    "zona", "anio_creacion", "vigente",
]

if __name__ == "__main__":
    cargar_puntos("comisarias.geojson", "comisarias", COLUMNAS, "objectid")
