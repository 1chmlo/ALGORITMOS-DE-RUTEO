#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETL de Metadata (TomTom Traffic Flow API v4): Velocidad actual vs. velocidad de flujo libre.

Extrae los segmentos de flujo vehicular en tiempo real para las autopistas, enlaces y arterias
principales de Maipú y alrededores desde la API Traffic Flow de TomTom
(flowSegmentData/absolute/10/json).

Propósito en el modelo de ruteo:
  - Menor velocidad actual respecto a la velocidad de flujo libre (mayor congestión o detención)
    incrementa la vulnerabilidad ante encerronas y robos con violencia de vehículos
    ("MENOR VELOCIDAD, + DELITOS").
  - Guarda el resultado en OUT_DIR/tomtom_trafico.geojson.
"""

import hashlib
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_TOMTOM_API_KEY = os.getenv(
    "TOMTOM_API_KEY",
    "GQVqBFj3IpVrvCUR4lYP8nCy9VQl4IhL",
)

TOMTOM_FLOW_ENDPOINT = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/14/json"
)

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))

# Puntos estratégicos de muestreo sobre la red de autopistas, enlaces y arterias de Maipú (lat, lon, nombre)
PUNTOS_MUESTREO_MAIPU: List[Tuple[float, float, str]] = [
    # Autopista del Sol (Ruta 78) y enlaces en Maipú
    (-33.5112, -70.7415, "Autopista del Sol (Ruta 78) - Enlace Vespucio Sur"),
    (-33.5175, -70.7520, "Autopista del Sol (Ruta 78) - Sector Pajaritos / Segunda Transversal"),
    (-33.5248, -70.7650, "Autopista del Sol (Ruta 78) - Sector Américo Vespucio Poniente"),
    (-33.5340, -70.7805, "Autopista del Sol (Ruta 78) - Sector Rinconada / El Rosal"),
    (-33.5435, -70.7960, "Autopista del Sol (Ruta 78) - Sector El Abrazo / Padre Hurtado"),
    (-33.5045, -70.7285, "Autopista del Sol (Ruta 78) - Enlace Cerrillos / General Velásquez"),
    # Autopista Vespucio Sur / Américo Vespucio en Maipú
    (-33.4755, -70.7390, "Américo Vespucio - Sector Pudahuel Sur / Enlace Ruta 68"),
    (-33.4850, -70.7420, "Américo Vespucio - Sector Las Parcelas / El Rosal"),
    (-33.4955, -70.7418, "Américo Vespucio - Sector Av. Pajaritos / Monte Tabor"),
    (-33.5045, -70.7412, "Américo Vespucio - Sector Segunda Transversal / Mall Arauco Maipú"),
    (-33.5125, -70.7405, "Américo Vespucio Sur - Cruce Ruta 78 (Autopista del Sol)"),
    (-33.5210, -70.7350, "Américo Vespucio Sur - Sector Camino a Melipilla / Cerrillos"),
    (-33.5285, -70.7180, "Américo Vespucio Sur - Sector Lo Espejo / General Velásquez"),
    # Eje Av. Los Pajaritos (Norte a Sur)
    (-33.4795, -70.7455, "Av. Los Pajaritos - Sector Teniente Cruz / Las Torres"),
    (-33.4900, -70.7510, "Av. Los Pajaritos - Sector Las Parcelas / Santiago Bueras"),
    (-33.5015, -70.7555, "Av. Los Pajaritos - Sector Plaza de Maipú / 5 de Abril"),
    (-33.5105, -70.7575, "Av. Los Pajaritos - Sector Esquina Blanca / Chacabuco"),
    (-33.5215, -70.7585, "Av. Los Pajaritos - Enlace Camino a Melipilla"),
    # Eje Camino a Melipilla (Ruta 76)
    (-33.5135, -70.7380, "Camino a Melipilla - Sector Esquina Blanca / Cerrillos"),
    (-33.5240, -70.7570, "Camino a Melipilla - Sector Pajaritos / Santa Marta"),
    (-33.5320, -70.7695, "Camino a Melipilla - Sector Tres Poniente / Industrial"),
    (-33.5415, -70.7830, "Camino a Melipilla - Sector El Abrazo de Maipú"),
    (-33.5515, -70.7975, "Camino a Melipilla - Sector Ciudad Satélite"),
    # Eje Av. 5 de Abril y Camino a Rinconada
    (-33.5008, -70.7425, "Av. 5 de Abril - Sector Esquina Blanca / Vespucio"),
    (-33.5012, -70.7650, "Av. 5 de Abril - Sector Primera Transversal / Templo Votivo"),
    (-33.5025, -70.7785, "Camino a Rinconada - Sector Carmen / Tres Poniente"),
    (-33.5040, -70.7935, "Camino a Rinconada - Sector Cuatro Poniente / Hospital El Carmen"),
    (-33.5085, -70.8120, "Camino a Rinconada - Sector Rinconada Rural / Autopista del Sol"),
    # Arterias transversales y colectoras de Maipú
    (-33.4885, -70.7610, "Av. El Rosal - Sector Ingeniero Domínguez"),
    (-33.4820, -70.7550, "Av. Las Parcelas - Sector Av. Sur / Pajaritos"),
    (-33.5140, -70.7755, "Av. Portales - Sector Tres Poniente / Nueva San Martín"),
    (-33.5180, -70.7900, "Av. Portales - Sector Cuatro Poniente / El Conquistador"),
    (-33.4950, -70.7740, "Av. Nueva San Martín - Sector Tres Poniente"),
    (-33.5090, -70.7460, "Av. Segunda Transversal - Sector Central / Vespucio"),
    (-33.5150, -70.7280, "Av. Lo Errázuriz - Límite Maipú / Cerrillos"),
    (-33.5300, -70.7810, "Av. Tres Poniente - Sector Sur / Camino a Melipilla"),
]


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def consultar_segmento_tomtom(
    lat: float,
    lon: float,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    """Consulta el endpoint flowSegmentData de TomTom para un punto (lat, lon)."""
    params = urllib.parse.urlencode(
        {
            "point": f"{lat},{lon}",
            "unit": "KMPH",
            "openLr": "false",
            "key": api_key,
        }
    )
    url = f"{TOMTOM_FLOW_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25, context=_ssl_ctx()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("flowSegmentData")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        print(f"  [WARN] TomTom HTTP {e.code} en ({lat}, {lon}): {body[:160]}", file=sys.stderr)
    except Exception as e:
        print(f"  [WARN] Error consultando TomTom en ({lat}, {lon}): {e}", file=sys.stderr)
    return None


def transformar_segmento(
    fsd: Dict[str, Any],
    lat_consulta: float,
    lon_consulta: float,
    corredor: str,
) -> Optional[Dict[str, Any]]:
    """Transforma la respuesta flowSegmentData de TomTom en un GeoJSON Feature LineString."""
    raw_coords = fsd.get("coordinates", {}).get("coordinate", [])
    coords = [
        [round(float(pt["longitude"]), 6), round(float(pt["latitude"]), 6)]
        for pt in raw_coords
        if "longitude" in pt and "latitude" in pt
    ]
    if len(coords) < 2:
        return None

    # Identificador único determinístico basado en la geometría del tramo entregado por TomTom
    firma_geom = f"{coords[0][0]:.5f},{coords[0][1]:.5f}_{coords[-1][0]:.5f},{coords[-1][1]:.5f}_{len(coords)}"
    segment_id = "tomtom_" + hashlib.md5(firma_geom.encode("utf-8")).hexdigest()[:12]

    vel_actual = float(fsd.get("currentSpeed") or 0.0)
    vel_libre = max(1.0, float(fsd.get("freeFlowSpeed") or vel_actual or 1.0))
    tiempo_actual = int(fsd.get("currentTravelTime") or 0)
    tiempo_libre = int(fsd.get("freeFlowTravelTime") or 0)
    confianza = float(fsd.get("confidence") or 0.0)
    cierre_vial = bool(fsd.get("roadClosure", False))
    frc = str(fsd.get("frc") or "FRC3")

    diferencia_vel = round(max(0.0, vel_libre - vel_actual), 2)
    razon_velocidad = round(min(1.5, vel_actual / vel_libre), 4)
    indice_congestion = round(max(0.0, 1.0 - (vel_actual / vel_libre)), 4)
    demora_seg = max(0, tiempo_actual - tiempo_libre)

    # Riesgo delictual asociado al flujo vehicular: menor velocidad o congestión -> mayor exposición
    riesgo_por_congestion = indice_congestion * 0.65
    riesgo_por_baja_vel = max(0.0, min(1.0, (60.0 - vel_actual) / 60.0)) * 0.35
    factor_riesgo_trafico = round(
        1.0 if cierre_vial else min(1.0, riesgo_por_congestion + riesgo_por_baja_vel),
        4,
    )

    if cierre_vial or razon_velocidad < 0.65 or vel_actual <= 25.0:
        nivel_riesgo_trafico = "alto"
    elif razon_velocidad < 0.85 or vel_actual <= 45.0:
        nivel_riesgo_trafico = "medio"
    else:
        nivel_riesgo_trafico = "bajo"

    return {
        "type": "Feature",
        "id": segment_id,
        "geometry": {
            "type": "LineString",
            "coordinates": coords,
        },
        "properties": {
            "segment_id": segment_id,
            "corredor_vial": corredor,
            "comuna": "Maipú",
            "frc": frc,
            "velocidad_actual_kmh": vel_actual,
            "velocidad_flujo_libre_kmh": vel_libre,
            "diferencia_velocidad_kmh": diferencia_vel,
            "razon_velocidad": razon_velocidad,
            "indice_congestion": indice_congestion,
            "tiempo_actual_seg": tiempo_actual,
            "tiempo_flujo_libre_seg": tiempo_libre,
            "demora_seg": demora_seg,
            "confianza": confianza,
            "cierre_vial": cierre_vial,
            "nivel_riesgo_trafico": nivel_riesgo_trafico,
            "factor_riesgo_trafico": factor_riesgo_trafico,
            "punto_consulta_lat": lat_consulta,
            "punto_consulta_lon": lon_consulta,
            "vertices_count": len(coords),
        },
    }


def extraer_y_transformar(api_key: str = DEFAULT_TOMTOM_API_KEY) -> Dict[str, Any]:
    """Recorre los puntos estratégicos de Maipú, consulta TomTom API y consolida los tramos únicos."""
    segmentos_unicos: Dict[str, Dict[str, Any]] = {}

    for lat, lon, corredor in PUNTOS_MUESTREO_MAIPU:
        fsd = consultar_segmento_tomtom(lat, lon, api_key=api_key)
        if not fsd:
            continue
        feat = transformar_segmento(fsd, lat, lon, corredor)
        if feat and feat["id"] not in segmentos_unicos:
            segmentos_unicos[feat["id"]] = feat

    features = list(segmentos_unicos.values())
    features.sort(
        key=lambda f: (
            -f["properties"]["factor_riesgo_trafico"],
            f["properties"]["velocidad_actual_kmh"],
        )
    )

    vel_actual_prom = (
        round(sum(f["properties"]["velocidad_actual_kmh"] for f in features) / len(features), 2)
        if features
        else 0.0
    )
    vel_libre_prom = (
        round(sum(f["properties"]["velocidad_flujo_libre_kmh"] for f in features) / len(features), 2)
        if features
        else 0.0
    )

    return {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "TomTom Traffic Flow API v4 (flowSegmentData)",
            "endpoint": TOMTOM_FLOW_ENDPOINT,
            "descripcion": (
                "Comparación entre velocidad actual y velocidad de flujo libre en autopistas "
                "y arterias de Maipú (menor velocidad implica mayor exposición a encerronas)."
            ),
            "comuna": "Maipú",
            "region": "Región Metropolitana de Santiago",
            "crs": "EPSG:4326 (WGS84)",
            "puntos_muestreados": len(PUNTOS_MUESTREO_MAIPU),
            "total_segmentos_unicos": len(features),
            "velocidad_actual_promedio_kmh": vel_actual_prom,
            "velocidad_flujo_libre_promedio_kmh": vel_libre_prom,
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(),
        },
        "features": features,
    }


def main() -> int:
    geojson = extraer_y_transformar()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "tomtom_trafico.geojson"
    destino.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    meta = geojson["metadata"]
    print(
        f"{meta['total_segmentos_unicos']} segmentos TomTom "
        f"(vel. prom: {meta['velocidad_actual_promedio_kmh']} vs "
        f"{meta['velocidad_flujo_libre_promedio_kmh']} km/h flujo libre) -> {destino}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
