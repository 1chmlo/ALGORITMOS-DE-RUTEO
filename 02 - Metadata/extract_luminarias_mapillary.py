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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

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

# La API v4 de Mapillary (/map_features) restringe el área máxima por consulta (< 0.01 grados^2).
# Subdividimos el BBOX en celdas de 0.03 x 0.025 grados (= 0.00075 grados^2 por celda).
TILE_STEP_LON = 0.030
TILE_STEP_LAT = 0.025

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


def fetch_tile_features(
    tile: Tuple[float, float, float, float],
    token: str,
    limit: int = 1000,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """Consulta las luminarias (object--street-light) dentro de una cuadrícula específica."""
    bbox_str = f"{tile[0]},{tile[1]},{tile[2]},{tile[3]}"
    params = urllib.parse.urlencode(
        {
            "access_token": token,
            "fields": FIELDS,
            "bbox": bbox_str,
            "object_values": OBJECT_VALUE,
            "limit": limit,
        }
    )
    url = f"{MAPILLARY_ENDPOINT}?{params}"

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AlgoritmosDeRuteo-ETL/1.0"},
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("data", [])
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
            print(
                f"  [WARN] HTTPError {e.code} en celda {bbox_str} (intento {attempt}/{max_retries}): {body}",
                file=sys.stderr,
            )
            if e.code in (400, 401, 403):
                break
            time.sleep(1.5 * attempt)
        except Exception as e:
            print(
                f"  [WARN] Error de red en celda {bbox_str} (intento {attempt}/{max_retries}): {e}",
                file=sys.stderr,
            )
            time.sleep(1.5 * attempt)

    return []


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
) -> Dict[str, Any]:
    """Ejecuta el flujo ETL completo de extracción y transformación a GeoJSON/JSON."""
    print("=" * 70)
    print("ETL METADATA: Extracción de Luminarias desde Mapillary API v4")
    print(f"Zona: Comuna de Maipú, RM | BBOX: {bbox}")
    print("=" * 70)

    tiles = generate_bbox_tiles(bbox)
    print(f"[INFO] Bounding box subdividido en {len(tiles)} cuadrículas de consulta.")

    unique_features: Dict[str, Dict[str, Any]] = {}

    for idx, tile in enumerate(tiles, start=1):
        raw_items = fetch_tile_features(tile, token=token)
        new_count = 0
        for item in raw_items:
            fid = str(item.get("id", ""))
            if fid and fid not in unique_features:
                unique_features[fid] = transform_feature(item)
                new_count += 1
        print(
            f"  [{idx:02d}/{len(tiles):02d}] Celda {tile} -> "
            f"{len(raw_items)} recibidas ({new_count} nuevas, total acumulado: {len(unique_features)})"
        )

    features_list = list(unique_features.values())

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


if __name__ == "__main__":
    extract_and_transform()
