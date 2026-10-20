#!/usr/bin/env bash
# Automatizar la ejecucion de los etl y levantamiento de la web
set -euo pipefail
cd "$(dirname "$0")"

INFRA="docker compose run --rm infraestructura"
META="docker compose run --rm metadata"
AMENAZAS="docker compose run --rm amenazas"

echo "==> Levantando base de datos (PostGIS + pgRouting)"
docker compose up -d --wait db
docker compose build infraestructura metadata amenazas web

echo "==> 01 - Infraestructura: extraccion y transformacion"
$INFRA python etl_comisarias.py
$INFRA python etl_puntos_criticos_fiscalia.py

echo "==> 01 - Infraestructura: carga a la base de datos"
$INFRA python carga_comisarias.py
$INFRA python carga_puntos_criticos_fiscalia.py

echo "==> 01 - Infraestructura: generando grafo aéreo y aristas para Dijkstra"
docker compose exec -T db psql -U ruteo -d ruteo < "00 - DB/dijkstra.sql"

echo "==> 02 - Metadata: extraccion y transformacion"
$META python etl_robo_con_violencia.py
$META python extract_luminarias_mapillary.py
$META python etl_overpass_formas_viales.py
$META python etl_tomtom_trafico.py

echo "==> 02 - Metadata: carga a la base de datos"
$META python carga_robo_con_violencia_hexagonos.py
$META python carga_robo_con_violencia_centroides.py
$META python load_luminarias_mapillary.py
$META python carga_overpass_formas_viales.py
$META python carga_tomtom_trafico.py

echo "==> 03 - Amenazas: extraccion y transformacion"
$AMENAZAS python etl_cortes_ruta_tomtom.py
$AMENAZAS python etl_robo_con_violencia_semanal.py

echo "==> 03 - Amenazas: carga a la base de datos"
$AMENAZAS python carga_cortes_ruta_tomtom.py
$AMENAZAS python carga_robo_con_violencia_semanal_hexagonos.py
$AMENAZAS python carga_robo_con_violencia_semanal_centroides.py

echo "==> 04 - Web: levantando visualizador"
docker compose up -d web
echo "==> Visualizador web disponible en: http://localhost:8080"
