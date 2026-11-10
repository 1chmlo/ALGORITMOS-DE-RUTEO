"""Carga salida/elevacion_terreno_hexagonos.geojson en la tabla elevacion_terreno_hexagonos."""
from db import cargar_puntos, conectar

COLUMNAS = ["hex_id", "centro_lon", "centro_lat", "elevacion_m", "tamanio_hexagono_m", "fuente"]

if __name__ == "__main__":
    with conectar() as con:
        con.execute("DELETE FROM elevacion_terreno_hexagonos")
    cargar_puntos("elevacion_terreno_hexagonos.geojson", "elevacion_terreno_hexagonos", COLUMNAS, "hex_id")
