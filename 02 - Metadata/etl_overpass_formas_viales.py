#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL de Metadata (Overpass API): Forma de carreteras, curvas y salidas en Maipú y alrededores.

Un estudio en EE.UU. y el análisis espacial de encerronas muestran que los robos con violencia
de vehículos se concentran en puntos con geometrías viales específicas: enlaces de autopistas
(*_link), salidas/entradas, rotondas y curvas pronunciadas que obligan a reducir la velocidad
y limitan la capacidad de escape.

Extrae las vías principales y enlaces desde OpenStreetMap (Overpass API), calcula métricas
geométricas (longitud, sinuosidad, ángulo máximo de giro, ángulo acumulado, tipo de forma vial
y factor de riesgo geométrico) y guarda el resultado en OUT_DIR/overpass_formas_viales.geojson.
"""

import json
import math
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Ventana de Maipú y sus corredores de autopistas (sur, oeste, norte, este)
BBOX_MAIPU_SUR_OESTE_NORTE_ESTE: Tuple[float, float, float, float] = (
    -33.560,  # Sur (Ciudad Satélite / Camino a Melipilla / Autopista del Sol)
    -70.825,  # Oeste (El Abrazo / Rinconada / Ruta 78)
    -33.465,  # Norte (Enlace Ruta 68 / Vespucio / Pajaritos Norte)
    -70.705,  # Este (Eje Vespucio Sur / Cerrillos / Estación Central)
)

HIGHWAY_REGEX = "^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link)$"

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def distancia_haversine_m(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Distancia Haversine en metros entre dos coordenadas (lon, lat)."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a)))


def acimut_grados(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Rumbo (bearing) en grados [0, 360) desde p1(lon, lat) hacia p2(lon, lat)."""
    lon1, lat1 = math.radians(p1[0]), math.radians(p1[1])
    lon2, lat2 = math.radians(p2[0]), math.radians(p2[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def diferencia_angular(a1: float, a2: float) -> float:
    """Diferencia angular mínima en grados [0, 180] entre dos rumbos."""
    diff = abs(a2 - a1) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def calcular_metricas_geometria(coords: List[List[float]]) -> Dict[str, float]:
    """Calcula longitud, distancia recta, sinuosidad y ángulos de curvatura de una polilínea."""
    if len(coords) < 2:
        return {
            "longitud_m": 0.0,
            "distancia_recta_m": 0.0,
            "indice_sinuosidad": 1.0,
            "angulo_giro_max_grados": 0.0,
            "angulo_giro_total_grados": 0.0,
        }

    longitud_m = 0.0
    rumbos: List[float] = []

    for i in range(len(coords) - 1):
        p1 = (coords[i][0], coords[i][1])
        p2 = (coords[i + 1][0], coords[i + 1][1])
        seg_m = distancia_haversine_m(p1, p2)
        longitud_m += seg_m
        if seg_m > 0.5:
            rumbos.append(acimut_grados(p1, p2))

    distancia_recta_m = distancia_haversine_m(
        (coords[0][0], coords[0][1]),
        (coords[-1][0], coords[-1][1]),
    )

    if distancia_recta_m < 1.0:
        # Anillo cerrado o retorno en U
        indice_sinuosidad = round(max(longitud_m / 5.0, 2.5), 4)
    else:
        indice_sinuosidad = round(max(1.0, longitud_m / distancia_recta_m), 4)

    giros = [
        diferencia_angular(rumbos[i], rumbos[i + 1])
        for i in range(len(rumbos) - 1)
    ]
    angulo_max = round(max(giros), 2) if giros else 0.0
    angulo_total = round(sum(giros), 2) if giros else 0.0

    return {
        "longitud_m": round(longitud_m, 2),
        "distancia_recta_m": round(distancia_recta_m, 2),
        "indice_sinuosidad": indice_sinuosidad,
        "angulo_giro_max_grados": angulo_max,
        "angulo_giro_total_grados": angulo_total,
    }


def extraer_overpass() -> List[Dict[str, Any]]:
    """Consulta las vías principales y enlaces en Maipú desde Overpass API."""
    s, w, n, e = BBOX_MAIPU_SUR_OESTE_NORTE_ESTE
    query = (
        f"[out:json][timeout:90];"
        f'way["highway"~"{HIGHWAY_REGEX}"]({s},{w},{n},{e});'
        f"out body geom;"
    )
    data_bytes = urllib.parse.urlencode({"data": query}).encode("utf-8")

    for intento in range(1, 4):
        for url in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=90, context=_ssl_ctx()) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    return payload.get("elements", [])
            except Exception as err:
                print(f"  [WARN] Overpass {url} intento {intento}: {err}", file=sys.stderr)
        time.sleep(3 * intento)

    raise RuntimeError("No fue posible obtener respuesta desde Overpass API.")


def transformar(elementos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transforma los ways de OSM en un GeoJSON FeatureCollection con clasificación de forma vial."""
    features: List[Dict[str, Any]] = []
    conteo_formas = {
        "salida_curva": 0,
        "salida_recta": 0,
        "rotonda": 0,
        "curva_pronunciada": 0,
        "recta": 0,
    }

    for el in elementos:
        if el.get("type") != "way" or not el.get("geometry"):
            continue

        coords = [
            [round(float(pt["lon"]), 6), round(float(pt["lat"]), 6)]
            for pt in el["geometry"]
        ]
        if len(coords) < 2:
            continue

        tags = el.get("tags", {})
        highway = str(tags.get("highway", ""))
        junction = str(tags.get("junction", ""))
        nombre = (tags.get("name") or tags.get("ref") or "Vía sin nombre").strip()
        ref_via = (tags.get("ref") or "").strip() or None
        oneway = str(tags.get("oneway", "")).lower() in ("yes", "1", "true")

        es_carril = tags.get("lanes")
        lanes = int(es_carril) if (es_carril and str(es_carril).isdigit()) else None

        partes_vel = str(tags.get("maxspeed") or "").split()
        maxspeed_kmh = int(partes_vel[0]) if partes_vel and partes_vel[0].isdigit() else None

        metricas = calcular_metricas_geometria(coords)
        es_enlace_salida = highway.endswith("_link")
        es_rotonda = junction in ("roundabout", "circular")
        es_curva = (
            metricas["angulo_giro_max_grados"] >= 25.0
            or metricas["indice_sinuosidad"] >= 1.12
            or metricas["angulo_giro_total_grados"] >= 45.0
        )

        if es_rotonda:
            forma_vial = "rotonda"
        elif es_enlace_salida and es_curva:
            forma_vial = "salida_curva"
        elif es_enlace_salida:
            forma_vial = "salida_recta"
        elif es_curva:
            forma_vial = "curva_pronunciada"
        else:
            forma_vial = "recta"

        conteo_formas[forma_vial] += 1

        # Cálculo de factor de riesgo geométrico [0.0, 1.0] basado en forma vial y curvatura
        base_riesgo = {
            "salida_curva": 0.75,
            "rotonda": 0.65,
            "salida_recta": 0.55,
            "curva_pronunciada": 0.45,
            "recta": 0.10,
        }[forma_vial]
        aporte_angulo = min(0.20, (metricas["angulo_giro_max_grados"] / 180.0) * 0.20)
        aporte_sinuosidad = min(0.05, max(0.0, metricas["indice_sinuosidad"] - 1.0) * 0.10)
        factor_riesgo_geom = round(min(1.0, base_riesgo + aporte_angulo + aporte_sinuosidad), 4)

        mid_idx = len(coords) // 2
        centroide_lon, centroide_lat = coords[mid_idx][0], coords[mid_idx][1]

        osm_id = int(el["id"])
        features.append(
            {
                "type": "Feature",
                "id": str(osm_id),
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "osm_id": osm_id,
                    "nombre": nombre,
                    "ref_via": ref_via,
                    "highway": highway,
                    "junction": junction or None,
                    "comuna": "Maipú",
                    "oneway": oneway,
                    "lanes": lanes,
                    "maxspeed_kmh": maxspeed_kmh,
                    "es_enlace_salida": es_enlace_salida,
                    "es_curva_pronunciada": es_curva,
                    "forma_vial": forma_vial,
                    "longitud_m": metricas["longitud_m"],
                    "distancia_recta_m": metricas["distancia_recta_m"],
                    "indice_sinuosidad": metricas["indice_sinuosidad"],
                    "angulo_giro_max_grados": metricas["angulo_giro_max_grados"],
                    "angulo_giro_total_grados": metricas["angulo_giro_total_grados"],
                    "factor_riesgo_geom": factor_riesgo_geom,
                    "centroide_lon": centroide_lon,
                    "centroide_lat": centroide_lat,
                },
            }
        )

    features.sort(key=lambda f: (-f["properties"]["factor_riesgo_geom"], f["properties"]["osm_id"]))

    return {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "OpenStreetMap via Overpass API",
            "descripcion": (
                "Morfología de carreteras, enlaces/salidas y curvas en Maipú y autopistas "
                "aledañas para modelar propensión geométrica a encerronas."
            ),
            "bbox_sur_oeste_norte_este": list(BBOX_MAIPU_SUR_OESTE_NORTE_ESTE),
            "crs": "EPSG:4326 (WGS84)",
            "total_tramos": len(features),
            "resumen_formas_viales": conteo_formas,
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(),
        },
        "features": features,
    }


def main() -> int:
    elementos = extraer_overpass()
    geojson = transformar(elementos)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "overpass_formas_viales.geojson"
    destino.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    meta = geojson["metadata"]
    print(
        f"{meta['total_tramos']} tramos viales (resumen: {meta['resumen_formas_viales']}) -> {destino}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
