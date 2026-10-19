-- Esquema inicial: infraestructura puntual y metadata. Las amenazas y la red vial
-- (nodos/aristas para pgRouting) se agregan en entregas posteriores.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

-- ===== 01 - INFRAESTRUCTURA =====

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

-- ===== 02 - METADATA =====

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

-- Morfología de carreteras, enlaces/salidas y curvas en Maipú (Overpass API / OSM).
CREATE TABLE IF NOT EXISTS overpass_formas_viales (
    id                       SERIAL PRIMARY KEY,
    osm_id                   BIGINT NOT NULL UNIQUE,
    nombre                   TEXT,
    ref_via                  TEXT,
    highway                  TEXT NOT NULL,
    junction                 TEXT,
    comuna                   TEXT,
    oneway                   BOOLEAN,
    lanes                    SMALLINT,
    maxspeed_kmh             SMALLINT,
    es_enlace_salida         BOOLEAN,
    es_curva_pronunciada     BOOLEAN,
    forma_vial               TEXT,
    longitud_m               DOUBLE PRECISION,
    distancia_recta_m        DOUBLE PRECISION,
    indice_sinuosidad        DOUBLE PRECISION,
    angulo_giro_max_grados   DOUBLE PRECISION,
    angulo_giro_total_grados DOUBLE PRECISION,
    factor_riesgo_geom       DOUBLE PRECISION,
    centroide_lon            DOUBLE PRECISION,
    centroide_lat            DOUBLE PRECISION,
    geom                     geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS overpass_formas_viales_geom_idx ON overpass_formas_viales USING GIST (geom);

-- Velocidad actual vs. velocidad de flujo libre en autopistas y arterias de Maipú (TomTom API v4).
CREATE TABLE IF NOT EXISTS tomtom_trafico (
    id                        SERIAL PRIMARY KEY,
    segment_id                TEXT NOT NULL UNIQUE,
    corredor_vial             TEXT,
    comuna                    TEXT,
    frc                       TEXT,
    velocidad_actual_kmh      DOUBLE PRECISION NOT NULL,
    velocidad_flujo_libre_kmh DOUBLE PRECISION NOT NULL,
    diferencia_velocidad_kmh  DOUBLE PRECISION,
    razon_velocidad           DOUBLE PRECISION,
    indice_congestion         DOUBLE PRECISION,
    tiempo_actual_seg         INTEGER,
    tiempo_flujo_libre_seg    INTEGER,
    demora_seg                INTEGER,
    confianza                 DOUBLE PRECISION,
    cierre_vial               BOOLEAN,
    nivel_riesgo_trafico      TEXT,
    factor_riesgo_trafico     DOUBLE PRECISION,
    punto_consulta_lat        DOUBLE PRECISION,
    punto_consulta_lon        DOUBLE PRECISION,
    vertices_count            INTEGER,
    geom                      geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS tomtom_trafico_geom_idx ON tomtom_trafico USING GIST (geom);

-- ===== 03 - AMENAZAS =====

-- Cortes de ruta totales activos (TomTom Traffic Incidents API v5, iconCategory = 8).
CREATE TABLE IF NOT EXISTS cortes_ruta_tomtom (
    id                 SERIAL PRIMARY KEY,
    incident_id        TEXT NOT NULL UNIQUE,
    icon_category      SMALLINT NOT NULL,
    tipo_amenaza       TEXT NOT NULL,
    descripcion_evento TEXT,
    codigo_evento      INTEGER,
    magnitud_retraso   SMALLINT,
    desde_via          TEXT,
    hasta_via          TEXT,
    numeros_ruta       TEXT,
    longitud_m         DOUBLE PRECISION,
    retraso_seg        INTEGER,
    probabilidad       TEXT,
    validez_temporal   TEXT,
    fecha_inicio       TIMESTAMPTZ,
    fecha_fin          TIMESTAMPTZ,
    en_maipu           BOOLEAN,
    bloqueo_total      BOOLEAN,
    centroide_lon      DOUBLE PRECISION,
    centroide_lat      DOUBLE PRECISION,
    fuente             TEXT,
    geom               geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS cortes_ruta_tomtom_geom_idx ON cortes_ruta_tomtom USING GIST (geom);
