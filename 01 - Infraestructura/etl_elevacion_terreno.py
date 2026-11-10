"""ETL de infraestructura: elevación del terreno para el techo de vuelo del dron (Open-Meteo).

El dron vuela a altitud constante: despega de su comisaría y sube a `altura_vuelo_m` sobre ella
(máximo 120 m sobre el suelo según la DAN 151). Los cerros del poniente de Maipú superan los
750 m s.n.m., mientras la llanura está en ~450-500 m, así que una línea recta hacia el poniente
puede chocar con el terreno. Este ETL mide la elevación en una grilla de hexágonos de 500 m; la
API de ruteo convierte en obstáculo todo hexágono cuya elevación supera el techo de vuelo.

Fuente: Open-Meteo Elevation API (DEM Copernicus GLO-90), gratis y sin API key.
Si la API no responde se conserva el GeoJSON anterior.

Genera OUT_DIR/elevacion_terreno_hexagonos.geojson.
"""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))
ARCHIVO = "elevacion_terreno_hexagonos.geojson"
URL = "https://api.open-meteo.com/v1/elevation"
BBOX = (-70.93, -33.60, -70.68, -33.44)  # min_lon, min_lat, max_lon, max_lat
RADIO_HEX_M = int(os.environ.get("ELEVACION_RADIO_HEX_M", "500"))
LOTE = 100  # máximo de coordenadas por solicitud de la Elevation API
M_POR_GRADO_LAT = 111_320.0


def grilla_hexagonos(bbox=BBOX, radio_m=RADIO_HEX_M):
    """Hexágonos pointy-top que cubren el bbox (mismo método que 03 - Amenazas/open_meteo.py)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat0 = (min_lat + max_lat) / 2
    m_lon = M_POR_GRADO_LAT * math.cos(math.radians(lat0))
    dx, dy = math.sqrt(3) * radio_m, 1.5 * radio_m
    ancho, alto = (max_lon - min_lon) * m_lon, (max_lat - min_lat) * M_POR_GRADO_LAT
    hexagonos = []
    for fila in range(int(alto / dy) + 2):
        for col in range(int(ancho / dx) + 2):
            x = col * dx + (dx / 2 if fila % 2 else 0.0)
            clon, clat = min_lon + x / m_lon, min_lat + fila * dy / M_POR_GRADO_LAT
            anillo = [
                [round(clon + radio_m * math.cos(math.radians(60 * k + 30)) / m_lon, 6),
                 round(clat + radio_m * math.sin(math.radians(60 * k + 30)) / M_POR_GRADO_LAT, 6)]
                for k in range(6)
            ]
            anillo.append(anillo[0])
            hexagonos.append({"hex_id": f"hex_elev_{fila:02d}_{col:02d}",
                              "centro": (round(clon, 6), round(clat, 6)), "anillo": anillo})
    return hexagonos


def consultar(centros):
    elevaciones = []
    for i in range(0, len(centros), LOTE):
        if i:
            time.sleep(11)  # Open-Meteo cuenta cada coordenada como una llamada (límite 600/min)
        lote = centros[i:i + LOTE]
        for intento in range(1, 4):
            try:
                r = requests.get(URL, params={
                    "latitude": ",".join(str(lat) for _, lat in lote),
                    "longitude": ",".join(str(lon) for lon, _ in lote),
                }, timeout=60)
                r.raise_for_status()
                elevaciones.extend(r.json()["elevation"])
                break
            except Exception as err:  # noqa: BLE001
                print(f"  [WARN] Elevation API intento {intento}: {err}", file=sys.stderr)
                time.sleep(5 * intento)
        else:
            return None
    return elevaciones


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / ARCHIVO
    hexagonos = grilla_hexagonos()
    elevaciones = consultar([h["centro"] for h in hexagonos])
    if elevaciones is None:
        if destino.exists():
            print(f"[WARN] Elevation API no respondió: se conserva {destino}")
            return
        raise SystemExit("Elevation API no respondió y no hay archivo previo")
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [h["anillo"]]},
            "properties": {
                "hex_id": h["hex_id"],
                "centro_lon": h["centro"][0],
                "centro_lat": h["centro"][1],
                "elevacion_m": elev,
                "tamanio_hexagono_m": RADIO_HEX_M,
                "fuente": "Open-Meteo Elevation API (Copernicus GLO-90)",
            },
        }
        for h, elev in zip(hexagonos, elevaciones)
        if elev is not None
    ]
    valores = [f["properties"]["elevacion_m"] for f in features]
    coleccion = {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "Open-Meteo Elevation API",
            "endpoint": URL,
            "descripcion": "Elevación del terreno (m s.n.m.) en el centro de cada hexágono, para el techo de vuelo del dron",
            "crs": "EPSG:4326",
            "bbox_consulta": list(BBOX),
            "tamanio_hexagono_m": RADIO_HEX_M,
            "elevacion_min_m": min(valores),
            "elevacion_max_m": max(valores),
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_hexagonos": len(features),
        },
        "features": features,
    }
    destino.write_text(json.dumps(coleccion, ensure_ascii=False), encoding="utf-8")
    print(f"{len(features)} hexágonos ({min(valores):.0f}-{max(valores):.0f} m) -> {destino}")


if __name__ == "__main__":
    main()
