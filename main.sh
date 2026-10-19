#!/usr/bin/env bash
# Automatizar la ejecucion de los etl y levantamiento de la web
set -euo pipefail
cd "$(dirname "$0")"

INFRA="docker compose run --rm infraestructura"

echo "==> Levantando base de datos (PostGIS + pgRouting)"
docker compose up -d --wait db
docker compose build infraestructura

echo "==> 01 - Infraestructura: extraccion y transformacion"
$INFRA python etl_comisarias.py
$INFRA python etl_puntos_criticos_fiscalia.py
$INFRA python etl_robo_con_violencia.py

echo "==> 01 - Infraestructura: carga a la base de datos"
$INFRA python carga_comisarias.py
$INFRA python carga_puntos_criticos_fiscalia.py
$INFRA python carga_robo_con_violencia_hexagonos.py
$INFRA python carga_robo_con_violencia_centroides.py

META="docker compose run --rm metadata"
docker compose build metadata

echo "==> 02 - Metadata (luminarias): extraccion y transformacion"
$META python extract_luminarias_mapillary.py

echo "==> 02 - Metadata (luminarias): carga a la base de datos"
$META python load_luminarias_mapillary.py

# TODO: 03 - Amenazas, 04 - Web
