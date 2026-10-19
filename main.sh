#!/usr/bin/env bash
# Automatizar la ejecucion de los etl y levantamiento de la web
set -euo pipefail
cd "$(dirname "$0")"

INFRA="docker compose run --rm infraestructura"
META="docker compose run --rm metadata"
AMEN="docker compose run --rm amenazas"

echo "==> Levantando base de datos (PostGIS + pgRouting)"
docker compose up -d --wait db
docker compose build infraestructura metadata amenazas

echo "==> 01 - Infraestructura: extraccion y transformacion"
$INFRA python etl_comisarias.py
$INFRA python etl_puntos_criticos_fiscalia.py

echo "==> 01 - Infraestructura: carga a la base de datos"
$INFRA python carga_comisarias.py
$INFRA python carga_puntos_criticos_fiscalia.py

echo "==> 02 - Metadata: extraccion y transformacion"
$META python etl_robo_con_violencia.py
$META python extract_luminarias_mapillary.py

echo "==> 02 - Metadata: carga a la base de datos"
$META python carga_robo_con_violencia_hexagonos.py
$META python carga_robo_con_violencia_centroides.py
$META python load_luminarias_mapillary.py

echo "==> 03 - Amenazas: extraccion y transformacion"
$AMEN python etl_robo_con_violencia_semanal.py

echo "==> 03 - Amenazas: carga a la base de datos"
$AMEN python carga_robo_con_violencia_semanal_hexagonos.py
$AMEN python carga_robo_con_violencia_semanal_centroides.py

# TODO: 04 - Web
