#!/usr/bin/env bash
# Automatizar la ejecucion de los etl y levantamiento de la web
set -euo pipefail
cd "$(dirname "$0")"

INFRA="docker compose run --rm infraestructura"
META="docker compose run --rm metadata"
AMENAZAS="docker compose run --rm amenazas"

echo "==> Levantando base de datos (PostGIS + pgRouting)"
docker compose up -d --wait db
docker compose build infraestructura metadata amenazas

echo "==> 00 - DB: aplicando esquema (idempotente, agrega tablas nuevas a una BD existente)"
docker compose exec -T db psql -U ruteo -d ruteo -c "SET client_min_messages = warning" -f - < "00 - DB/init.sql"

echo "==> 01 - Infraestructura: extraccion y transformacion"
$INFRA python etl_comisarias.py
$INFRA python etl_puntos_criticos_fiscalia.py
# Restricciones físicas del vuelo (si la API externa falla se conserva el GeoJSON versionado)
$INFRA python etl_elevacion_terreno.py

echo "==> 01 - Infraestructura: carga a la base de datos"
$INFRA python carga_comisarias.py
$INFRA python carga_puntos_criticos_fiscalia.py
$INFRA python carga_elevacion_terreno.py

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
$AMENAZAS python etl_robo_con_violencia_semanal.py
$AMENAZAS python etl_lluvia_open_meteo.py
$AMENAZAS python etl_viento_open_meteo.py

echo "==> 03 - Amenazas: carga a la base de datos"
$AMENAZAS python carga_robo_con_violencia_semanal_hexagonos.py
$AMENAZAS python carga_robo_con_violencia_semanal_centroides.py
$AMENAZAS python carga_lluvia_open_meteo_hexagonos.py
$AMENAZAS python carga_viento_open_meteo_hexagonos.py
# Capas de clima para el visualizador estático de la Fase 2 (visualizador_dijkstra.html)
cp "03 - Amenazas/salidas/lluvia_open_meteo_hexagonos.geojson" "04 - Web/"
cp "03 - Amenazas/salidas/viento_open_meteo_hexagonos.geojson" "04 - Web/"

echo "==> 03 - Amenazas: probabilidad de falla de cada zona, enlace y nodo"
$AMENAZAS python probabilidad_falla.py

echo "==> 05 - API: levantando API de ruteo (grafo de visibilidad, Dijkstra, Gurobi, genético)"
docker compose build api web
docker compose up -d --force-recreate api
# Espera a la API, vacía su caché (datos recién cargados) y calcula las 4 rutas de prueba.
# Se ejecuta dentro del contenedor para no depender de Python/curl en el equipo anfitrión.
docker compose exec -T api python - <<'PY' || echo "   [WARN] la API no respondió; revise: docker compose logs api"
import json, time, urllib.request
base = "http://localhost:8000/api"
for _ in range(30):
    try:
        urllib.request.urlopen(base + "/salud", timeout=5)
        break
    except Exception:
        time.sleep(2)
urllib.request.urlopen(urllib.request.Request(base + "/recargar", method="POST"), timeout=10)
req = urllib.request.Request(base + "/rutas", data=b'{"incluir_grafo": false}', headers={"Content-Type": "application/json"})
d = json.load(urllib.request.urlopen(req, timeout=180))
for r in d["rutas"]:
    print(f"   {r['nombre']:32} ok={r['ok']} factible={r['factible']} R={r['resiliencia']} ({r['tiempo_computo_ms']} ms)")
print("   mejor:", d["mejor"], "| mas resiliente:", d["mas_resiliente"])
PY

echo "==> 04 - Web: levantando visualizador"
docker compose up -d --force-recreate web
echo "==> Visualizador web disponible en: http://localhost:8080 (escenario de ejemplo: http://localhost:8080/#demo)"
echo "==> Documentación de la API: http://localhost:8080/api/docs"

echo "==> Levantando explorador de la base de datos (pgAdmin)"
docker compose up -d pgadmin
echo "==> pgAdmin disponible en: http://localhost:5050"
