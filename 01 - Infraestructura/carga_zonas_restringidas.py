"""Carga salida/zonas_restringidas_overpass.geojson en la tabla zonas_restringidas.

La zona de exclusión (geom) se calcula en PostGIS ampliando la geometría original de OSM con
su radio_exclusion_m (buffer geográfico en metros). La tabla se reemplaza completa.
"""
import json

from db import OUT_DIR, conectar

SQL = """
INSERT INTO zonas_restringidas
    (osm_ref, tipo, nombre, motivo, radio_exclusion_m, fuente, geom_original, geom)
SELECT %(osm_ref)s, %(tipo)s, %(nombre)s, %(motivo)s, %(radio_exclusion_m)s, %(fuente)s, g,
       ST_Multi(ST_Buffer(g::geography, %(radio_exclusion_m)s)::geometry)
FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326) AS g) s
"""

if __name__ == "__main__":
    features = json.loads(
        (OUT_DIR / "zonas_restringidas_overpass.geojson").read_text(encoding="utf-8")
    )["features"]
    filas = [{**f["properties"], "geom": json.dumps(f["geometry"])} for f in features]
    with conectar() as con:
        con.execute("DELETE FROM zonas_restringidas")
        con.cursor().executemany(SQL, filas)
    print(f"{len(filas)} filas -> zonas_restringidas")
