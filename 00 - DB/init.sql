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

DROP TABLE IF EXISTS cortes_ruta_tomtom CASCADE;

-- Robos con violencia recientes de STOP (ventana de 7 días): hacia dónde se mueve el delito.
-- Misma grilla que robo_con_violencia_hexagonos (mismos hex_id), para poder cruzarlas.
-- Se reemplaza completa en cada carga.
CREATE TABLE IF NOT EXISTS robo_con_violencia_semanal_hexagonos (
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
    ventana_dias       SMALLINT,
    tamanio_hexagono_m INTEGER,
    fuente             TEXT,
    geom               geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS robo_con_violencia_semanal_hexagonos_geom_idx ON robo_con_violencia_semanal_hexagonos USING GIST (geom);

CREATE TABLE IF NOT EXISTS robo_con_violencia_semanal_centroides (
    id            SERIAL PRIMARY KEY,
    hex_id        TEXT NOT NULL UNIQUE REFERENCES robo_con_violencia_semanal_hexagonos (hex_id) ON DELETE CASCADE,
    cantidad      INTEGER NOT NULL,
    nivel         SMALLINT NOT NULL,
    niveles_total SMALLINT NOT NULL,
    color         TEXT,
    geom          geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS robo_con_violencia_semanal_centroides_geom_idx ON robo_con_violencia_semanal_centroides USING GIST (geom);

-- Lluvia por zonas para el vuelo de drones (Open-Meteo): grilla de hexágonos sobre Maipú.
-- no_volable = TRUE bloquea las aristas aéreas que la cruzan (vista aristas_aereas_volables).
-- Se reemplaza completa en cada carga. Horas en hora local de Santiago.
CREATE TABLE IF NOT EXISTS lluvia_open_meteo_hexagonos (
    id                        SERIAL PRIMARY KEY,
    hex_id                    TEXT NOT NULL UNIQUE,
    centro_lon                DOUBLE PRECISION,
    centro_lat                DOUBLE PRECISION,
    celda_modelo_lon          DOUBLE PRECISION,
    celda_modelo_lat          DOUBLE PRECISION,
    precipitacion_actual_mm_h DOUBLE PRECISION,
    precipitacion_max_mm_h    DOUBLE PRECISION,
    probabilidad_max_pct      DOUBLE PRECISION,
    hora_desde                TIMESTAMP,
    hora_hasta                TIMESTAMP,
    ventana_horas             SMALLINT,
    umbral_mm_h               DOUBLE PRECISION,
    umbral_prob_pct           DOUBLE PRECISION,
    simulado                  BOOLEAN NOT NULL DEFAULT FALSE,
    no_volable                BOOLEAN NOT NULL,
    motivo                    TEXT,
    tamanio_hexagono_m        INTEGER,
    fecha_extraccion_utc      TIMESTAMPTZ,
    fuente                    TEXT,
    geom                      geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS lluvia_open_meteo_hexagonos_geom_idx ON lluvia_open_meteo_hexagonos USING GIST (geom);

-- Viento por zonas para el vuelo de drones (Open-Meteo): misma grilla y hex_id que la lluvia.
-- Viento sostenido = máximo entre 80 m y 120 m; ráfagas a 10 m (única altura disponible).
-- no_volable = TRUE bloquea las aristas aéreas que la cruzan (vista aristas_aereas_volables).
CREATE TABLE IF NOT EXISTS viento_open_meteo_hexagonos (
    id                   SERIAL PRIMARY KEY,
    hex_id               TEXT NOT NULL UNIQUE,
    centro_lon           DOUBLE PRECISION,
    centro_lat           DOUBLE PRECISION,
    celda_modelo_lon     DOUBLE PRECISION,
    celda_modelo_lat     DOUBLE PRECISION,
    viento_actual_kmh    DOUBLE PRECISION,
    viento_max_kmh       DOUBLE PRECISION,
    rafaga_max_kmh       DOUBLE PRECISION,
    direccion_grados     DOUBLE PRECISION,
    hora_desde           TIMESTAMP,
    hora_hasta           TIMESTAMP,
    ventana_horas        SMALLINT,
    umbral_kmh           DOUBLE PRECISION,
    umbral_rafaga_kmh    DOUBLE PRECISION,
    simulado             BOOLEAN NOT NULL DEFAULT FALSE,
    no_volable           BOOLEAN NOT NULL,
    motivo               TEXT,
    tamanio_hexagono_m   INTEGER,
    fecha_extraccion_utc TIMESTAMPTZ,
    fuente               TEXT,
    geom                 geometry(Polygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS viento_open_meteo_hexagonos_geom_idx ON viento_open_meteo_hexagonos USING GIST (geom);

-- ===== 04 - RED VIAL Y GRAFO AÉREO (pgRouting) =====

CREATE TABLE IF NOT EXISTS nodos_aereos (
    id SERIAL PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN ('comisaria', 'interes')),
    nombre TEXT NOT NULL,
    descripcion TEXT,
    geom geometry(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS nodos_aereos_geom_idx ON nodos_aereos USING GIST (geom);

CREATE TABLE IF NOT EXISTS aristas_aereas (
    id SERIAL PRIMARY KEY,
    source INTEGER NOT NULL REFERENCES nodos_aereos(id) ON DELETE CASCADE,
    target INTEGER NOT NULL REFERENCES nodos_aereos(id) ON DELETE CASCADE,
    cost DOUBLE PRECISION NOT NULL,
    reverse_cost DOUBLE PRECISION NOT NULL,
    geom geometry(LineString, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS aristas_aereas_geom_idx ON aristas_aereas USING GIST (geom);
CREATE INDEX IF NOT EXISTS aristas_aereas_source_idx ON aristas_aereas (source);
CREATE INDEX IF NOT EXISTS aristas_aereas_target_idx ON aristas_aereas (target);

-- ===== 05 - FASE 3: RESTRICCIONES ESTÁTICAS Y PROBABILIDAD DE FALLA =====

DROP TABLE IF EXISTS zonas_restringidas CASCADE;
DROP TABLE IF EXISTS elevacion_terreno_hexagonos CASCADE;

-- Probabilidad de falla por amenaza (03 - Amenazas/probabilidad_falla.py, parámetros por defecto).
-- Cada zona de amenaza (hexágono de lluvia/viento/STOP 7d) tiene una p de falla
-- para el dron que la cruza. Las aristas y nodos del grafo aéreo heredan p de las zonas que tocan.
CREATE TABLE IF NOT EXISTS probabilidad_falla_zonas (
    id        SERIAL PRIMARY KEY,
    zona_id   TEXT NOT NULL UNIQUE,                  -- "<amenaza>:<id de origen>"
    amenaza   TEXT NOT NULL,                         -- lluvia | viento | robo_7d
    origen_id TEXT NOT NULL,
    p_falla   DOUBLE PRECISION NOT NULL CHECK (p_falla BETWEEN 0 AND 1),
    detalle   TEXT,
    geom      geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS probabilidad_falla_zonas_geom_idx ON probabilidad_falla_zonas USING GIST (geom);

CREATE TABLE IF NOT EXISTS probabilidad_falla_aristas (
    arista_id INTEGER NOT NULL,
    amenaza   TEXT NOT NULL,                         -- una fila por amenaza + 'total'
    p_falla   DOUBLE PRECISION NOT NULL,
    zonas     INTEGER NOT NULL,                      -- zonas de esa amenaza que cruza
    PRIMARY KEY (arista_id, amenaza)
);

CREATE TABLE IF NOT EXISTS probabilidad_falla_nodos (
    nodo_id INTEGER NOT NULL,
    amenaza TEXT NOT NULL,
    p_falla DOUBLE PRECISION NOT NULL,
    zonas   INTEGER NOT NULL,
    PRIMARY KEY (nodo_id, amenaza)
);
