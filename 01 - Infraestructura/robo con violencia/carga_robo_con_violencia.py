#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga robo_con_violencia_maipu.geojson en la tabla PostGIS robo_con_violencia_stop.
"""

import json
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:
    psycopg = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

PGHOST = os.environ.get("PGHOST", os.environ.get("DB_HOST", "localhost"))
PGPORT = os.environ.get("PGPORT", os.environ.get("DB_PORT", "5432"))
PGDATABASE = os.environ.get("PGDATABASE", os.environ.get("DB_NAME", "ruteo"))
PGUSER = os.environ.get("PGUSER", os.environ.get("DB_USER", "ruteo"))
PGPASSWORD = os.environ.get("PGPASSWORD", os.environ.get("DB_PASSWORD", "ruteo"))

INPUT_GEOJSON = Path(
    os.environ.get(
        "OUT_FILE",
        Path(__file__).parent / "robo_con_violencia_maipu.geojson",
    )
)

COLUMNAS = [
    "hex_id",
    "stop_id",
    "comuna",
    "region",
    "codigo_delito",
    "tipo_delito",
    "cantidad",
    "severidad",
    "rango_jenks",
    "color",
    "color_border",
    "fecha_min",
    "fecha_max",
    "tamanio_hexagono_m",
    "centroide_lon",
    "centroide_lat",
    "fuente",
]

DDL_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS robo_con_violencia_stop (
    id                 SERIAL PRIMARY KEY,
    hex_id             TEXT NOT NULL UNIQUE,
    stop_id            TEXT,
    comuna             TEXT,
    region             TEXT,
    codigo_delito      TEXT NOT NULL,
    tipo_delito        TEXT NOT NULL,
    cantidad           INTEGER NOT NULL,
    severidad          TEXT,
    rango_jenks        TEXT,
    color              TEXT,
    color_border       TEXT,
    fecha_min          DATE,
    fecha_max          DATE,
    tamanio_hexagono_m INTEGER,
    centroide_lon      DOUBLE PRECISION,
    centroide_lat      DOUBLE PRECISION,
    fuente             TEXT,
    geom               geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS robo_con_violencia_stop_geom_idx
    ON robo_con_violencia_stop USING GIST (geom);
"""


def cargar_hexagonos(geojson_path: Path = INPUT_GEOJSON) -> None:
    if not geojson_path.exists():
        raise FileNotFoundError(
            f"No se encontró '{geojson_path}'. Ejecute primero 'etl_robo_con_violencia.py'."
        )

    features = json.loads(geojson_path.read_text(encoding="utf-8"))["features"]
    cols = ", ".join(COLUMNAS)
    marcas = ", ".join(f"%({c})s" for c in COLUMNAS)
    actualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNAS if c != "hex_id")

    sql = (
        f"INSERT INTO robo_con_violencia_stop ({cols}, geom) "
        f"VALUES ({marcas}, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) "
        f"ON CONFLICT (hex_id) DO UPDATE SET {actualiza}, geom = EXCLUDED.geom"
    )

    filas = [
        {
            **{c: f["properties"].get(c) for c in COLUMNAS},
            "geom": json.dumps(f["geometry"]),
        }
        for f in features
        if f.get("geometry") and f.get("properties", {}).get("hex_id")
    ]

    if psycopg is not None:
        with psycopg.connect(
            host=PGHOST,
            port=PGPORT,
            dbname=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
        ) as con:
            with con.cursor() as cur:
                cur.execute(DDL_ENSURE_TABLE)
                cur.executemany(sql, filas)
    elif psycopg2 is not None:
        con = psycopg2.connect(
            host=PGHOST,
            port=PGPORT,
            dbname=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
        )
        try:
            with con:
                with con.cursor() as cur:
                    cur.execute(DDL_ENSURE_TABLE)
                    cur.executemany(sql, filas)
        finally:
            con.close()
    else:
        print(
            "[ERROR] Instale 'psycopg[binary]' o 'psycopg2-binary' (pip install -r requirements.txt).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"{len(filas)} filas -> robo_con_violencia_stop")


if __name__ == "__main__":
    cargar_hexagonos()
