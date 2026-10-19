-- =====================================================================
-- 00 - DB/dijkstra.sql
-- Construcción del Grafo Aéreo y Soporte para Algoritmo Dijkstra
-- EXCLUSIVO: COMUNA DE MAIPÚ (100% dentro del territorio comunal)
-- =====================================================================
-- Topología:
-- 1. Nodos: 3 Comisarías de Maipú + 6 Puntos Críticos de Maipú (Autopistas y STOP).
-- 2. Aristas: Vuelos directos con distancia euclidiana en metros (ST_Distance).
--    - Interés <-> Interés: SÍ
--    - Comisaría <-> Interés: SÍ
--    - Comisaría <-> Comisaría: NO (no hay aristas directas entre bases)
-- =====================================================================

DROP TABLE IF EXISTS aristas_aereas CASCADE;
DROP TABLE IF EXISTS nodos_aereos CASCADE;

-- 1. Tabla de Nodos Aéreos Unificada
CREATE TABLE nodos_aereos (
    id SERIAL PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN ('comisaria', 'interes')),
    nombre TEXT NOT NULL,
    descripcion TEXT,
    geom geometry(Point, 4326) NOT NULL
);

-- Insertar las 3 Comisarías de Maipú (Bases de operación aérea)
INSERT INTO nodos_aereos (tipo, nombre, descripcion, geom)
SELECT 
    'comisaria', 
    nombre, 
    'Base policial de despegue y aterrizaje',
    geom
FROM comisarias
WHERE comuna ILIKE 'MAIP%'
ORDER BY id;

-- Insertar los 6 Puntos Críticos 100% dentro de Maipú (Autopistas y accesos críticos)
INSERT INTO nodos_aereos (tipo, nombre, descripcion, geom) VALUES
('interes', 'Vespucio Sur con Ruta 78 (Autopista del Sol)', 'Enlace autopistas - Punto crítico Fiscalía', ST_SetSRID(ST_MakePoint(-70.749023, -33.490288), 4326)),
('interes', 'Autopista del Sol con Av. Pajaritos (Mall Arauco)', 'Salida de autopista - Foco STOP 36 delitos', ST_SetSRID(ST_MakePoint(-70.746100, -33.481600), 4326)),
('interes', 'Plaza de Maipú / Pajaritos con 5 de Abril', 'Centro neurálgico - Foco STOP 49 delitos', ST_SetSRID(ST_MakePoint(-70.755300, -33.514500), 4326)),
('interes', 'Autopista del Sol con Camino a Rinconada', 'Enlace autopista poniente - Foco STOP 42 delitos', ST_SetSRID(ST_MakePoint(-70.794000, -33.514900), 4326)),
('interes', 'Camino a Melipilla con 3 Poniente', 'Acceso sur a Ruta 78 y corredor industrial', ST_SetSRID(ST_MakePoint(-70.778000, -33.535000), 4326)),
('interes', 'Vespucio Sur con Av. Lumen / Segunda Transversal', 'Enlace autopista oriente - Foco STOP 21 delitos', ST_SetSRID(ST_MakePoint(-70.726300, -33.509500), 4326));

CREATE INDEX IF NOT EXISTS nodos_aereos_geom_idx ON nodos_aereos USING GIST (geom);

-- 2. Tabla de Aristas Aéreas (Distancia euclidiana en metros)
CREATE TABLE aristas_aereas (
    id SERIAL PRIMARY KEY,
    source INTEGER NOT NULL REFERENCES nodos_aereos(id) ON DELETE CASCADE,
    target INTEGER NOT NULL REFERENCES nodos_aereos(id) ON DELETE CASCADE,
    cost DOUBLE PRECISION NOT NULL,         -- Distancia euclidiana en metros
    reverse_cost DOUBLE PRECISION NOT NULL, -- Vuelo bidireccional
    geom geometry(LineString, 4326) NOT NULL
);

-- Generar conexiones cumpliendo la regla: NO comisaría con comisaría
INSERT INTO aristas_aereas (source, target, cost, reverse_cost, geom)
SELECT 
    a.id AS source,
    b.id AS target,
    ST_Distance(a.geom::geography, b.geom::geography) AS cost,
    ST_Distance(a.geom::geography, b.geom::geography) AS reverse_cost,
    ST_MakeLine(a.geom, b.geom) AS geom
FROM nodos_aereos a
JOIN nodos_aereos b ON a.id < b.id
WHERE NOT (a.tipo = 'comisaria' AND b.tipo = 'comisaria')
ORDER BY a.id, b.id;

CREATE INDEX IF NOT EXISTS aristas_aereas_geom_idx ON aristas_aereas USING GIST (geom);
CREATE INDEX IF NOT EXISTS aristas_aereas_source_idx ON aristas_aereas (source);
CREATE INDEX IF NOT EXISTS aristas_aereas_target_idx ON aristas_aereas (target);

-- 3. Funciones de Dijkstra

-- A) Ruta directa entre dos nodos cualesquiera:
CREATE OR REPLACE FUNCTION calcular_ruta_aerea_geojson(p_origen INTEGER, p_destino INTEGER)
RETURNS JSON AS $$
DECLARE
    v_result JSON;
BEGIN
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'properties', json_build_object(
            'origen_id', p_origen,
            'destino_id', p_destino,
            'distancia_total_m', coalesce(sum(d.cost), 0)
        ),
        'features', json_agg(
            json_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(a.geom)::json,
                'properties', json_build_object(
                    'seq', d.seq,
                    'node', d.node,
                    'edge', d.edge,
                    'cost_m', round(d.cost::numeric, 1),
                    'agg_cost_m', round(d.agg_cost::numeric, 1)
                )
            ) ORDER BY d.seq
        )
    ) INTO v_result
    FROM pgr_dijkstra(
        'SELECT id, source, target, cost, reverse_cost FROM aristas_aereas',
        p_origen,
        p_destino,
        directed := false
    ) d
    JOIN aristas_aereas a ON d.edge = a.id;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- B) Circuito completo de patrullaje para el dron de cada comisaría de Maipú:
-- Cada dron visita TODOS los 6 puntos críticos de Maipú y vuelve a su comisaría original.
CREATE OR REPLACE FUNCTION calcular_circuito_dron_geojson(p_comisaria_id INTEGER)
RETURNS JSON AS $$
DECLARE
    v_secuencia INTEGER[];
    v_result JSON;
BEGIN
    -- Secuencia óptima calculada para cada base que visita TODOS los puntos (4, 5, 6, 7, 8, 9) y retorna:
    IF p_comisaria_id = 1 THEN
        v_secuencia := ARRAY[1, 6, 8, 7, 4, 5, 9, 1];
    ELSIF p_comisaria_id = 2 THEN
        v_secuencia := ARRAY[2, 4, 5, 9, 6, 8, 7, 2];
    ELSIF p_comisaria_id = 3 THEN
        v_secuencia := ARRAY[3, 7, 4, 5, 9, 6, 8, 3];
    ELSE
        RAISE EXCEPTION 'ID de comisaría inválido (debe ser 1, 2 o 3)';
    END IF;

    WITH pares AS (
        SELECT 
            i AS orden_tramo,
            v_secuencia[i] AS origen,
            v_secuencia[i+1] AS destino
        FROM generate_series(1, array_length(v_secuencia, 1) - 1) AS i
    ),
    rutas AS (
        SELECT 
            p.orden_tramo,
            d.seq,
            d.node,
            d.edge,
            d.cost AS cost_m,
            a.geom
        FROM pares p
        CROSS JOIN LATERAL pgr_dijkstra(
            'SELECT id, source, target, cost, reverse_cost FROM aristas_aereas',
            p.origen,
            p.destino,
            directed := false
        ) d
        JOIN aristas_aereas a ON d.edge = a.id
    )
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'properties', json_build_object(
            'comisaria_id', p_comisaria_id,
            'nombre_base', (SELECT nombre FROM nodos_aereos WHERE id = p_comisaria_id),
            'distancia_total_m', (SELECT sum(cost_m) FROM rutas),
            'distancia_total_km', round(((SELECT sum(cost_m) FROM rutas) / 1000.0)::numeric, 2),
            'tiempo_estimado_min', round((((SELECT sum(cost_m) FROM rutas) / 1000.0) / (60.0 / 60.0))::numeric, 0)
        ),
        'features', json_agg(
            json_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(r.geom)::json,
                'properties', json_build_object(
                    'orden_tramo', r.orden_tramo,
                    'edge', r.edge,
                    'cost_m', round(r.cost_m::numeric, 1)
                )
            ) ORDER BY r.orden_tramo, r.seq
        )
    ) INTO v_result
    FROM rutas r;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;
