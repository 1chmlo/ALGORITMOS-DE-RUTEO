-- Esquema inicial. Por ahora solo infraestructura puntual; metadata, amenazas y
-- la red vial (nodos/aristas para pgRouting) se agregan en entregas posteriores.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

-- Unidades de Carabineros de la Región Metropolitana (ArcGIS MDSF).
CREATE TABLE IF NOT EXISTS comisarias (
    id            SERIAL PRIMARY KEY,
    objectid      INTEGER NOT NULL UNIQUE,
    codigo_unidad TEXT,
    nombre        TEXT NOT NULL,
    tipo_unidad   TEXT,
    direccion     TEXT,
    cod_region    SMALLINT,
    region        TEXT,
    cod_provincia SMALLINT,
    provincia     TEXT,
    cod_comuna    INTEGER,
    comuna        TEXT,
    prefectura    TEXT,
    zona          TEXT,
    anio_creacion SMALLINT,
    vigente       BOOLEAN,
    geom          geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS comisarias_geom_idx ON comisarias USING GIST (geom);

-- Puntos críticos de encerronas citados por la Fiscalía / Emol.
CREATE TABLE IF NOT EXISTS puntos_criticos_fiscalia (
    id                SERIAL PRIMARY KEY,
    nombre            TEXT NOT NULL UNIQUE,
    tipo_delito       TEXT NOT NULL,
    severidad         TEXT CHECK (severidad IN ('alta', 'media', 'baja')),
    fuente            TEXT NOT NULL,
    fuente_url        TEXT,
    pagina_informe    SMALLINT,
    cita              TEXT,
    cita_verificada   BOOLEAN,
    periodo           TEXT,
    separacion_vias_m INTEGER,
    geom              geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS puntos_criticos_fiscalia_geom_idx ON puntos_criticos_fiscalia USING GIST (geom);

-- Robos con violencia de la plataforma STOP (Carabineros): grilla de hexágonos de la RM,
-- ventana móvil de 90 días. Se reemplaza completa en cada carga.
CREATE TABLE IF NOT EXISTS robo_con_violencia_hexagonos (
    id                 SERIAL PRIMARY KEY,
    hex_id             TEXT NOT NULL UNIQUE,
    stop_id            TEXT,
    codigo_delito      TEXT NOT NULL,
    tipo_delito        TEXT NOT NULL,
    cantidad           INTEGER NOT NULL,
    nivel              SMALLINT NOT NULL,
    niveles_total      SMALLINT NOT NULL,
    rango              TEXT,
    color              TEXT,
    color_border       TEXT,
    fecha_min          DATE,
    fecha_max          DATE,
    periodo_desde      DATE,
    periodo_hasta      DATE,
    tamanio_hexagono_m INTEGER,
    fuente             TEXT,
    geom               geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS robo_con_violencia_hexagonos_geom_idx ON robo_con_violencia_hexagonos USING GIST (geom);

-- Centroide de cada hexágono (un punto por hexágono, para cruzar con la red vial).
CREATE TABLE IF NOT EXISTS robo_con_violencia_centroides (
    id            SERIAL PRIMARY KEY,
    hex_id        TEXT NOT NULL UNIQUE REFERENCES robo_con_violencia_hexagonos (hex_id) ON DELETE CASCADE,
    cantidad      INTEGER NOT NULL,
    nivel         SMALLINT NOT NULL,
    niveles_total SMALLINT NOT NULL,
    color         TEXT,
    geom          geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS robo_con_violencia_centroides_geom_idx ON robo_con_violencia_centroides USING GIST (geom);

-- Luminarias públicas detectadas en Maipú (Mapillary Graph API v4).
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
