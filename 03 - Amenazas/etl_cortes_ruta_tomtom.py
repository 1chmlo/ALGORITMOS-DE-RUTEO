#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL de Amenazas (TomTom Traffic Incidents API v5): Cortes de ruta totales.

Consulta el servicio de incidentes de tráfico de TomTom (incidentDetails v5) filtrando
exclusivamente por `categoryFilter=8` (Road Closed / Corte de ruta total) en el Gran
Santiago / Región Metropolitana (con énfasis e identificación de la comuna de Maipú).

En el modelo de ruteo, un corte de ruta total representa una amenaza activa que inhabilita
el paso vehicular sobre las aristas afectadas (bloqueo total / penalización máxima).
Guarda el resultado en OUT_DIR/cortes_ruta_tomtom.geojson.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_TOMTOM_API_KEY = os.getenv(
    "TOMTOM_API_KEY",
    "GQVqBFj3IpVrvCUR4lYP8nCy9VQl4IhL",
)

TOMTOM_INCIDENTS_ENDPOINT = "https://api.tomtom.com/traffic/services/5/incidentDetails"

# Categoría 8 en TomTom Traffic Incidents v5 corresponde a "Road Closed" (Corte de ruta total)
CATEGORY_ROAD_CLOSED = "8"

# Bounding Box del Gran Santiago / Región Metropolitana (min_lon, min_lat, max_lon, max_lat)
BBOX_RM_URBANA: Tuple[float, float, float, float] = (
    -71.15,
    -33.85,
    -70.45,
    -33.15,
)

# Bounding Box referencial de Maipú y sus accesos viales para marcar cortes locales
BBOX_MAIPU: Tuple[float, float, float, float] = (
    -70.93,
    -33.57,
    -70.71,
    -33.46,
)

FIELDS_SPEC = (
    "{incidents{type,geometry{type,coordinates},"
    "properties{id,iconCategory,magnitudeOfDelay,"
    "events{description,code,iconCategory},"
    "startTime,endTime,from,to,length,delay,"
    "roadNumbers,timeValidity,probabilityOfOccurrence}}}"
)

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salidas"))


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _en_bbox(lon: float, lat: float, bbox: Tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def extraer_cortes_tomtom(
    bbox: Tuple[float, float, float, float] = BBOX_RM_URBANA,
    api_key: str = DEFAULT_TOMTOM_API_KEY,
) -> List[Dict[str, Any]]:
    """Descarga los incidentes activos de categoría 8 (Road Closed) desde TomTom API v5."""
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    params = urllib.parse.urlencode(
        {
            "key": api_key,
            "bbox": bbox_str,
            "fields": FIELDS_SPEC,
            "language": "es-ES",
            "categoryFilter": CATEGORY_ROAD_CLOSED,
            "timeValidityFilter": "present",
        }
    )
    url = f"{TOMTOM_INCIDENTS_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("incidents", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        raise RuntimeError(f"Error HTTP {e.code} en TomTom Incident Details: {body[:300]}") from e


def _normalizar_linestring(geom: Dict[str, Any]) -> List[List[float]]:
    """Asegura que la geometría sea una lista de coordenadas LineString [[lon, lat], ...]."""
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "LineString" and len(coords) >= 2:
        return [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in coords]
    if gtype == "Point" and len(coords) >= 2:
        lon, lat = round(float(coords[0]), 6), round(float(coords[1]), 6)
        return [[lon, lat], [lon, lat]]
    if gtype == "MultiLineString" and coords and len(coords[0]) >= 2:
        flat = [pt for line in coords for pt in line]
        return [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in flat]
    return []


def transformar(incidentes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transforma los incidentes de corte de ruta de TomTom en un GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    vistos = set()
    total_maipu = 0

    for inc in incidentes:
        props = inc.get("properties") or {}
        incident_id = str(props.get("id") or "").strip()
        if not incident_id or incident_id in vistos:
            continue

        coords = _normalizar_linestring(inc.get("geometry") or {})
        if len(coords) < 2:
            continue
        vistos.add(incident_id)

        mid_idx = len(coords) // 2
        clon, clat = coords[mid_idx][0], coords[mid_idx][1]
        en_maipu = any(_en_bbox(p[0], p[1], BBOX_MAIPU) for p in coords)
        if en_maipu:
            total_maipu += 1

        eventos = props.get("events") or []
        descripciones = [str(ev.get("description", "")).strip() for ev in eventos if ev.get("description")]
        descripcion_evento = "; ".join(dict.fromkeys(descripciones)) if descripciones else "Cerrado"
        codigo_evento = int(eventos[0]["code"]) if eventos and eventos[0].get("code") is not None else 401

        road_numbers = [str(r).strip() for r in (props.get("roadNumbers") or []) if str(r).strip()]
        numeros_ruta = ", ".join(road_numbers) if road_numbers else None

        longitud_m = round(float(props.get("length") or 0.0), 2)
        retraso_raw = props.get("delay")
        retraso_seg = int(retraso_raw) if retraso_raw is not None else None

        features.append(
            {
                "type": "Feature",
                "id": incident_id,
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "incident_id": incident_id,
                    "icon_category": int(props.get("iconCategory") or 8),
                    "tipo_amenaza": "Corte de ruta total",
                    "descripcion_evento": descripcion_evento,
                    "codigo_evento": codigo_evento,
                    "magnitud_retraso": int(props.get("magnitudeOfDelay") or 4),
                    "desde_via": (props.get("from") or "").strip() or None,
                    "hasta_via": (props.get("to") or "").strip() or None,
                    "numeros_ruta": numeros_ruta,
                    "longitud_m": longitud_m,
                    "retraso_seg": retraso_seg,
                    "probabilidad": props.get("probabilityOfOccurrence"),
                    "validez_temporal": props.get("timeValidity"),
                    "fecha_inicio": props.get("startTime"),
                    "fecha_fin": props.get("endTime"),
                    "en_maipu": en_maipu,
                    "bloqueo_total": True,
                    "centroide_lon": clon,
                    "centroide_lat": clat,
                    "fuente": "TomTom Traffic Incidents API v5",
                },
            }
        )

    # Priorizar cortes dentro de Maipú y luego por longitud de tramo afectado
    features.sort(
        key=lambda f: (
            not f["properties"]["en_maipu"],
            -f["properties"]["longitud_m"],
            f["properties"]["incident_id"],
        )
    )

    return {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "TomTom Traffic Incidents API v5 (incidentDetails)",
            "endpoint": TOMTOM_INCIDENTS_ENDPOINT,
            "categoria_filtro": "8 (Road Closed / Corte de ruta total)",
            "descripcion": (
                "Cortes de ruta totales activos en la Región Metropolitana y Maipú. "
                "Representan amenazas de bloqueo vial en tiempo real para el algoritmo de ruteo."
            ),
            "crs": "EPSG:4326 (WGS84)",
            "bbox_consulta": list(BBOX_RM_URBANA),
            "bbox_maipu_referencia": list(BBOX_MAIPU),
            "total_cortes_rm": len(features),
            "total_cortes_maipu": total_maipu,
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(),
        },
        "features": features,
    }


def main() -> int:
    incidentes = extraer_cortes_tomtom()
    geojson = transformar(incidentes)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "cortes_ruta_tomtom.geojson"
    destino.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    meta = geojson["metadata"]
    print(
        f"{meta['total_cortes_rm']} cortes de ruta totales en RM "
        f"({meta['total_cortes_maipu']} en Maipú y accesos) -> {destino}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
