#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Extracción y Transformación de Metadata: Luminarias (Mapillary API v4)
Zona de estudio: Comuna de Maipú, Región Metropolitana, Chile.
Propósito: Extraer luminarias públicas (object--street-light) desde Mapillary API v4
para identificar cobertura lumínica y zonas oscuras (asociadas a mayor riesgo de delitos)
en el grafo de ruteo.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Configuración por defecto
DEFAULT_MAPILLARY_TOKEN = os.getenv(
    "MAPILLARY_TOKEN",
    "MLY|40669536349311780|42770fcd33fd9847f27507d9a6694e6c",
)

# Bounding Box urbano de la comuna de Maipú, Región Metropolitana, Chile
# Formato: (min_lon / west, min_lat / south, max_lon / east, max_lat / north)
MAIPU_BBOX: Tuple[float, float, float, float] = (
    -70.810,  # Oeste (sector El Abrazo / Rinconada)
    -33.545,  # Sur (sector Ciudad Satélite / Camino a Melipilla)
    -70.720,  # Este (sector Pajaritos / límite con Estación Central y Cerrillos)
    -33.470,  # Norte (sector Pudahuel Sur / Av. Pajaritos Norte)
)

# La API v4 de Mapillary (/map_features) restringe el área máxima por consulta (< 0.01 grados^2)
# y responde HTTP 500 cuando una consulta tarda demasiado (el tiempo crece con la cantidad de
# luminarias y de imágenes de la celda). Se parte de celdas de 0.015 x 0.0125 grados (~3-4 s por
# consulta) y cualquier celda que falle o devuelva muchos resultados se divide en cuatro.
TILE_STEP_LON = 0.015
TILE_STEP_LAT = 0.0125
MIN_TILE_DEG = 0.004      # no se subdivide por debajo de ~400 m
PAGE_LIMIT = 500          # parámetro `limit` de la API
# La API recorta resultados EN SILENCIO en celdas densas, incluso muy por debajo de `limit`: una
# celda que devolvió 465 luminarias tenía 1126 al dividirla en cuatro. Por eso toda celda con
# SPLIT_AT resultados o más se subdivide; una de 357 sí resultó completa.
SPLIT_AT = 200
REQUEST_TIMEOUT_S = 30
MAX_ATTEMPTS = 2          # intentos por celda antes de subdividirla
WORKERS = 4               # consultas en paralelo
MAX_ERRORES_TOTALES = 40  # consultas fallidas (tras reintentos) que abortan la extracción
_errores_lock = threading.Lock()
_errores_acumulados = [0]

MAPILLARY_ENDPOINT = "https://graph.mapillary.com/map_features"
OBJECT_VALUE = "object--street-light"
FIELDS = "id,aligned_direction,first_seen_at,last_seen_at,object_value,object_type,geometry,images"

# OUT_DIR permite montar un volumen en Docker (ver docker-compose.yml); por defecto, junto al script.
OUTPUT_FILENAME = os.path.join(
    os.environ.get("OUT_DIR", os.path.dirname(os.path.abspath(__file__))),
    "luminarias_mapillary.json",
)


def generate_bbox_tiles(
    bbox: Tuple[float, float, float, float],
    step_lon: float = TILE_STEP_LON,
    step_lat: float = TILE_STEP_LAT,
) -> List[Tuple[float, float, float, float]]:
    """Subdivide un Bounding Box general en cuadrículas compatibles con Mapillary API v4."""
    min_lon, min_lat, max_lon, max_lat = bbox
    tiles: List[Tuple[float, float, float, float]] = []

    lon = min_lon
    while lon < max_lon - 1e-9:
        next_lon = min(round(lon + step_lon, 6), max_lon)
        lat = min_lat
        while lat < max_lat - 1e-9:
            next_lat = min(round(lat + step_lat, 6), max_lat)
            tiles.append((round(lon, 6), round(lat, 6), next_lon, next_lat))
            lat = next_lat
        lon = next_lon

    return tiles


class ErrorFatalAPI(Exception):
    """Error que no se arregla reintentando ni subdividiendo (token inválido, Mapillary caído)."""


def request_tile(
    tile: Tuple[float, float, float, float], token: str
) -> Tuple[List[Dict[str, Any]], str]:
    """Una consulta a la API para la celda. Devuelve (datos, error); error vacío si salió bien."""
    bbox_str = f"{tile[0]},{tile[1]},{tile[2]},{tile[3]}"
    params = urllib.parse.urlencode(
        {
            "access_token": token,
            "fields": FIELDS,
            "bbox": bbox_str,
            "object_values": OBJECT_VALUE,
            "limit": PAGE_LIMIT,
        }
    )
    url = f"{MAPILLARY_ENDPOINT}?{params}"
    error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AlgoritmosDeRuteo-ETL/1.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8")).get("data", []), ""
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):  # el token o la consulta están mal: no tiene sentido seguir
                raise ErrorFatalAPI(f"HTTP {e.code} en celda {bbox_str} (revise MAPILLARY_TOKEN)")
            error = f"HTTP {e.code}"
        except Exception as e:  # timeout, red caída, JSON truncado
            error = type(e).__name__
        if attempt < MAX_ATTEMPTS:
            time.sleep(1.5 * attempt)
    with _errores_lock:  # corte: si Mapillary está caído, no seguir subdividiendo por minutos
        _errores_acumulados[0] += 1
        if _errores_acumulados[0] > MAX_ERRORES_TOTALES:
            raise ErrorFatalAPI(f"Mapillary no disponible: más de {MAX_ERRORES_TOTALES} consultas fallidas")
    return [], error


def fetch_tile_features(
    tile: Tuple[float, float, float, float], token: str
) -> Tuple[List[Dict[str, Any]], List[Tuple[float, float, float, float]]]:
    """Luminarias de una celda. Si la consulta falla o devuelve muchos resultados (posible recorte
    silencioso de la API), divide la celda en cuatro y consulta cada parte.
    Devuelve (datos, celdas_fallidas)."""
    items, error = request_tile(tile, token)
    if not error and len(items) < SPLIT_AT:
        return items, []

    min_lon, min_lat, max_lon, max_lat = tile
    if max_lon - min_lon <= MIN_TILE_DEG or max_lat - min_lat <= MIN_TILE_DEG:
        if error:
            return [], [tile]
        print(f"  [WARN] celda mínima {tile} con {len(items)} resultados: no se puede subdividir más")
        return items, []

    motivo = error or f"{len(items)} resultados (posible recorte de la API)"
    print(f"  [INFO] subdividiendo celda {tile}: {motivo}")
    mid_lon, mid_lat = (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    partes = [
        (min_lon, min_lat, mid_lon, mid_lat),
        (mid_lon, min_lat, max_lon, mid_lat),
        (min_lon, mid_lat, mid_lon, max_lat),
        (mid_lon, mid_lat, max_lon, max_lat),
    ]
    datos: List[Dict[str, Any]] = []
    fallidas: List[Tuple[float, float, float, float]] = []
    for parte in partes:
        d, f = fetch_tile_features(parte, token)
        datos += d
        fallidas += f
    return datos, fallidas


def transform_feature(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforma un registro crudo de Mapillary API v4 a una estructura GeoJSON Feature
    estandarizada y enriquecida para el modelo de ruteo seguro.
    """
    feature_id = str(raw_item.get("id", ""))
    geometry = raw_item.get("geometry", {})
    coords = geometry.get("coordinates", [None, None])
    lon = float(coords[0]) if len(coords) >= 2 and coords[0] is not None else None
    lat = float(coords[1]) if len(coords) >= 2 and coords[1] is not None else None

    images_data = raw_item.get("images", {}).get("data", [])
    image_ids = [str(img.get("id")) for img in images_data if img.get("id")]
    num_detections = len(image_ids)

    # Nivel de confianza de la luminaria según cantidad de imágenes donde fue detectada
    if num_detections >= 5:
        confianza = "ALTA"
        factor_iluminacion = 1.0
    elif num_detections >= 2:
        confianza = "MEDIA"
        factor_iluminacion = 0.75
    else:
        confianza = "BAJA"
        factor_iluminacion = 0.5

    # Radio estimado de cobertura lumínica en metros de una luminaria vial estándar
    radio_iluminacion_m = 25.0

    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],
        },
        "properties": {
            "mapillary_id": feature_id,
            "object_value": raw_item.get("object_value", OBJECT_VALUE),
            "object_type": raw_item.get("object_type", "panoptic"),
            "comuna": "Maipú",
            "region": "Región Metropolitana de Santiago",
            "latitud": lat,
            "longitud": lon,
            "aligned_direction": raw_item.get("aligned_direction"),
            "first_seen_at": raw_item.get("first_seen_at"),
            "last_seen_at": raw_item.get("last_seen_at"),
            "detections_count": num_detections,
            "sample_image_ids": image_ids[:5],
            "confianza_deteccion": confianza,
            "factor_iluminacion": factor_iluminacion,
            "radio_cobertura_m": radio_iluminacion_m,
            "impacto_seguridad": (
                "Presencia de luminaria reduce riesgo nocturno de delito en un radio de "
                f"{int(radio_iluminacion_m)}m; aristas sin luminarias cercanas se clasifican como "
                "zonas oscuras (+riesgo delictual)."
            ),
        },
    }


def extract_and_transform(
    bbox: Tuple[float, float, float, float] = MAIPU_BBOX,
    token: str = DEFAULT_MAPILLARY_TOKEN,
    output_path: str = OUTPUT_FILENAME,
) -> Optional[Dict[str, Any]]:
    """Ejecuta el flujo ETL completo de extracción y transformación a GeoJSON/JSON.
    Devuelve None (sin escribir el archivo) si alguna celda no pudo obtenerse."""
    print("=" * 70)
    print("ETL METADATA: Extracción de Luminarias desde Mapillary API v4")
    print(f"Zona: Comuna de Maipú, RM | BBOX: {bbox}")
    print("=" * 70)

    tiles = generate_bbox_tiles(bbox)
    print(f"[INFO] Bounding box subdividido en {len(tiles)} cuadrículas de consulta.")

    unique_features: Dict[str, Dict[str, Any]] = {}
    celdas_fallidas: List[Tuple[float, float, float, float]] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futuros = {pool.submit(fetch_tile_features, tile, token): tile for tile in tiles}
        for hechos, futuro in enumerate(as_completed(futuros), start=1):
            tile = futuros[futuro]
            raw_items, fallidas = futuro.result()  # ErrorFatalAPI aborta toda la extracción
            celdas_fallidas += fallidas
            nuevas = 0
            for item in raw_items:
                fid = str(item.get("id", ""))
                if fid and fid not in unique_features:  # una luminaria puede caer en el borde de 2 celdas
                    unique_features[fid] = transform_feature(item)
                    nuevas += 1
            print(
                f"  [{hechos:02d}/{len(tiles):02d}] Celda {tile} -> {len(raw_items)} recibidas "
                f"({nuevas} nuevas, total acumulado: {len(unique_features)})"
            )

    if celdas_fallidas:
        # No se escribe nada: un archivo con huecos haría pasar zonas con luminarias por zonas oscuras.
        print(f"[ERROR] {len(celdas_fallidas)} celdas no pudieron obtenerse de Mapillary:", file=sys.stderr)
        for celda in celdas_fallidas:
            print(f"  - {celda}", file=sys.stderr)
        return None

    # Orden estable por id: la salida es reproducible y los diffs en git muestran solo cambios reales
    features_list = sorted(unique_features.values(), key=lambda f: f["properties"]["mapillary_id"])

    # Estadísticas resumen de la extracción
    total_luminarias = len(features_list)
    alta_confianza = sum(
        1 for f in features_list if f["properties"]["confianza_deteccion"] == "ALTA"
    )
    media_confianza = sum(
        1 for f in features_list if f["properties"]["confianza_deteccion"] == "MEDIA"
    )
    baja_confianza = sum(
        1 for f in features_list if f["properties"]["confianza_deteccion"] == "BAJA"
    )

    geojson_document: Dict[str, Any] = {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "Mapillary Graph API v4",
            "endpoint": MAPILLARY_ENDPOINT,
            "filtro_objeto": OBJECT_VALUE,
            "descripcion": (
                "Mapa de luminarias públicas detectadas mediante visión por computador en "
                "Mapillary para identificar zonas iluminadas vs. zonas sin luz (+ riesgo de delitos)."
            ),
            "comuna": "Maipú",
            "region": "Región Metropolitana de Santiago, Chile",
            "sistema_referencia": "EPSG:4326 (WGS 84)",
            "bbox": {
                "min_lon": bbox[0],
                "min_lat": bbox[1],
                "max_lon": bbox[2],
                "max_lat": bbox[3],
            },
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(),
            "total_luminarias": total_luminarias,
            "resumen_confianza": {
                "ALTA": alta_confianza,
                "MEDIA": media_confianza,
                "BAJA": baja_confianza,
            },
        },
        "features": features_list,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson_document, f, ensure_ascii=False, indent=2)

    print("-" * 70)
    print(f"[OK] Extracción completada exitosamente.")
    print(f"[OK] Total luminarias únicas extraídas: {total_luminarias}")
    print(
        f"[OK] Distribución por confianza -> ALTA: {alta_confianza}, "
        f"MEDIA: {media_confianza}, BAJA: {baja_confianza}"
    )
    print(f"[OK] Archivo generado en: {output_path}")
    print("=" * 70)

    return geojson_document


def main() -> int:
    try:
        resultado = extract_and_transform()
    except ErrorFatalAPI as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        if "no disponible" in str(e) and os.path.exists(OUTPUT_FILENAME):
            print(f"[WARN] Se conserva el archivo anterior ({OUTPUT_FILENAME}); sus datos pueden estar desactualizados.")
            return 0
        return 1
    if resultado is not None:
        return 0
    # Extracción incompleta: se conserva el archivo anterior para que el flujo pueda continuar
    if os.path.exists(OUTPUT_FILENAME):
        print(f"[WARN] Se conserva el archivo anterior ({OUTPUT_FILENAME}); sus datos pueden estar desactualizados.")
        return 0
    print("[ERROR] No hay datos previos que conservar.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
