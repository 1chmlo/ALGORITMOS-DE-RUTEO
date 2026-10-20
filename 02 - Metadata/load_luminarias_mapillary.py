#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Carga de Metadata a Base de Datos PostgreSQL / PostGIS
Archivo origen: luminarias_mapillary.json
Tabla destino: luminarias_mapillary (definida en 00 - DB/init.sql)
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
    from psycopg2.extras import execute_values
except ImportError:
    psycopg2 = None
    execute_values = None

# Parámetros de conexión alineados con docker-compose.yml y 01 - Infraestructura/db.py
PGHOST = os.environ.get("PGHOST", os.environ.get("DB_HOST", "localhost"))
PGPORT = os.environ.get("PGPORT", os.environ.get("DB_PORT", "5432"))
PGDATABASE = os.environ.get("PGDATABASE", os.environ.get("DB_NAME", "ruteo"))
PGUSER = os.environ.get("PGUSER", os.environ.get("DB_USER", "ruteo"))
PGPASSWORD = os.environ.get("PGPASSWORD", os.environ.get("DB_PASSWORD", "ruteo"))

INPUT_JSON_PATH = Path(os.environ.get("OUT_DIR", Path(__file__).parent)) / "luminarias_mapillary.json"

COLUMNAS = [
    "mapillary_id",
    "object_value",
    "object_type",
    "comuna",
    "region",
    "latitud",
    "longitud",
    "aligned_direction",
    "first_seen_at",
    "last_seen_at",
    "detections_count",
    "confianza_deteccion",
    "factor_iluminacion",
    "radio_cobertura_m",
]

DDL_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS luminarias_mapillary (
    id                  SERIAL PRIMARY KEY,
    mapillary_id        TEXT NOT NULL UNIQUE,
    object_value        TEXT NOT NULL,
    object_type         TEXT,
    comuna              TEXT,
    region              TEXT,
    latitud             DOUBLE PRECISION NOT NULL,
    longitud            DOUBLE PRECISION NOT NULL,
    aligned_direction   DOUBLE PRECISION,
    first_seen_at       TIMESTAMPTZ,
    last_seen_at        TIMESTAMPTZ,
    detections_count    INTEGER,
    confianza_deteccion TEXT,
    factor_iluminacion  DOUBLE PRECISION,
    radio_cobertura_m   DOUBLE PRECISION,
    geom                geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS luminarias_mapillary_geom_idx ON luminarias_mapillary USING GIST (geom);
"""


def cargar_luminarias(json_path: Path = INPUT_JSON_PATH) -> None:
    """Reemplaza el contenido de la tabla luminarias_mapillary por los puntos de luminarias_mapillary.json."""
    if not json_path.exists():
        raise FileNotFoundError(
            f"No se encontró '{json_path}'. Ejecute primero 'extract_luminarias_mapillary.py'."
        )

    features = json.loads(json_path.read_text(encoding="utf-8"))["features"]
    cols = ", ".join(COLUMNAS)
    marcas = ", ".join(f"%({c})s" for c in COLUMNAS)
    actualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNAS if c != "mapillary_id")

    sql = (
        f"INSERT INTO luminarias_mapillary ({cols}, geom) "
        f"VALUES ({marcas}, ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) "
        f"ON CONFLICT (mapillary_id) DO UPDATE SET {actualiza}, geom = EXCLUDED.geom"
    )

    filas = [
        {
            **{c: f["properties"].get(c) for c in COLUMNAS},
            "geom": json.dumps(f["geometry"]),
        }
        for f in features
        if f.get("geometry") and f.get("properties", {}).get("mapillary_id")
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
                cur.execute("DELETE FROM luminarias_mapillary")  # la tabla refleja la última extracción
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
                    cur.execute("DELETE FROM luminarias_mapillary")  # la tabla refleja la última extracción
                    cur.executemany(sql, filas)
        finally:
            con.close()
    else:
        print(
            "[ERROR] Instale 'psycopg[binary]' o 'psycopg2-binary' (pip install -r requirements.txt).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"{len(filas)} filas -> luminarias_mapillary")


if __name__ == "__main__":
    cargar_luminarias()
