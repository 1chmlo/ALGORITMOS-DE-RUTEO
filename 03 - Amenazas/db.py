"""Conexión y carga genérica de un GeoJSON de amenazas a una tabla PostGIS."""
import json
import os
from pathlib import Path

import psycopg

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salidas"))


def conectar():
    return psycopg.connect(
        host=os.environ.get("PGHOST", "db"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "ruteo"),
        user=os.environ.get("PGUSER", "ruteo"),
        password=os.environ.get("PGPASSWORD", "ruteo"),
    )


def cargar_puntos(archivo, tabla, columnas, clave, reemplazar=False):
    """Upsert de los features de `archivo` en `tabla`.

    `columnas` son las propiedades del GeoJSON que se guardan con el mismo nombre;
    `clave` es la columna única usada para ON CONFLICT. Con `reemplazar` se vacía antes la
    tabla (en la misma transacción), para datos de amenazas activas en tiempo real.
    """
    features = json.loads((OUT_DIR / archivo).read_text(encoding="utf-8"))["features"]
    cols = ", ".join(columnas)
    marcas = ", ".join(f"%({c})s" for c in columnas)
    actualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in columnas if c != clave)
    sql = (
        f"INSERT INTO {tabla} ({cols}, geom) "
        f"VALUES ({marcas}, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) "
        f"ON CONFLICT ({clave}) DO UPDATE SET {actualiza}, geom = EXCLUDED.geom"
    )
    filas = [
        {**{c: f["properties"].get(c) for c in columnas}, "geom": json.dumps(f["geometry"])}
        for f in features
    ]
    with conectar() as con:
        if reemplazar:
            con.execute(f"DELETE FROM {tabla}")
        con.cursor().executemany(sql, filas)
    print(f"{len(filas)} filas -> {tabla}")
