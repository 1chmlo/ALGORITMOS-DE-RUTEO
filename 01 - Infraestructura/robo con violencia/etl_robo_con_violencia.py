#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETL de Infraestructura: Hexágonos de Robo con Violencia (STOP Carabineros)
Zona de estudio: Comuna de Maipú, Región Metropolitana, Chile.
Fuente: Plataforma STOP de Carabineros de Chile (https://stop.carabineros.cl)
Endpoint: POST /serviceCall4/{bbox}/EVE_ROB_VI/{zoom}/{date_desde}/{date_hasta}
"""

import hashlib
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

STOP_BASE_URL = "https://stop.carabineros.cl"
FILTRO_DELITO = "EVE_ROB_VI"  # 4.1 - Robos con violencia en STOP Carabineros
ZOOM_HEXAGONOS = 15  # Nivel de zoom 15 entrega la grilla más fina (hexágonos de 150m)
VENTANA_DIAS = 91  # Ventana móvil oficial de 90 días que utiliza el visor STOP

NOMINATIM_MAIPU_URL = (
    "https://nominatim.openstreetmap.org/search"
    "?q=Maip%C3%BA,+Santiago,+Chile&format=geojson&polygon_geojson=1&limit=1"
)

# Bounding Box de respaldo para la comuna de Maipú en caso de que Nominatim no responda
FALLBACK_MAIPU_BBOX: Tuple[float, float, float, float] = (
    -70.9299813,
    -33.5718464,
    -70.7183638,
    -33.4582090,
)

OUT_FILE = Path(
    os.environ.get(
        "OUT_FILE",
        Path(__file__).parent / "robo_con_violencia_maipu.geojson",
    )
)


def _crear_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def obtener_poligono_maipu() -> Tuple[Tuple[float, float, float, float], List[List[Tuple[float, float]]]]:
    """
    Obtiene el polígono administrativo oficial de la comuna de Maipú desde OpenStreetMap
    para recortar espacialmente los hexágonos exclusivamente dentro de la comuna.
    """
    try:
        req = urllib.request.Request(
            NOMINATIM_MAIPU_URL,
            headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"},
        )
        with urllib.request.urlopen(req, timeout=25, context=_crear_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        feat = data["features"][0]
        bbox = tuple(float(x) for x in feat["bbox"])  # (min_lon, min_lat, max_lon, max_lat)
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            rings = [[(float(pt[0]), float(pt[1])) for pt in geom["coordinates"][0]]]
        elif geom["type"] == "MultiPolygon":
            rings = [
                [(float(pt[0]), float(pt[1])) for pt in poly[0]]
                for poly in geom["coordinates"]
            ]
        else:
            rings = []
        return bbox, rings
    except Exception as e:
        print(f"  [WARN] No se pudo descargar polígono comunal desde Nominatim ({e}); usando BBOX de Maipú.")
        return FALLBACK_MAIPU_BBOX, []


def punto_en_anillo(lon: float, lat: float, ring: List[Tuple[float, float]]) -> bool:
    """Algoritmo Ray-Casting para verificar si un punto (lon, lat) cae dentro de un polígono."""
    dentro = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        ):
            dentro = not dentro
        j = i
    return dentro


def hexagono_en_maipu(
    coords_anillo: List[List[float]],
    rings_maipu: List[List[Tuple[float, float]]],
) -> Tuple[bool, float, float]:
    """
    Calcula el centroide del hexágono y verifica si su centroide o alguno de sus vértices
    se encuentra dentro de los límites comunales de Maipú.
    """
    vertices = coords_anillo[:-1] if len(coords_anillo) > 1 else coords_anillo
    clon = sum(p[0] for p in vertices) / len(vertices)
    clat = sum(p[1] for p in vertices) / len(vertices)

    if not rings_maipu:
        return True, round(clon, 6), round(clat, 6)

    for ring in rings_maipu:
        if punto_en_anillo(clon, clat, ring):
            return True, round(clon, 6), round(clat, 6)
        if any(punto_en_anillo(p[0], p[1], ring) for p in vertices):
            return True, round(clon, 6), round(clat, 6)

    return False, round(clon, 6), round(clat, 6)


def clasificar_severidad(cantidad: int, legend_items: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Clasifica la severidad del hexágono según los rangos de quiebres naturales (Jenks)
    entregados por la leyenda de STOP Carabineros.
    """
    etiquetas_severidad = ["baja", "media", "alta", "muy_alta"]
    for idx, item in enumerate(legend_items):
        min_v = item.get("min", 0)
        max_v = item.get("max", 999999)
        if idx == 0 and cantidad <= max_v:
            return etiquetas_severidad[min(idx, 3)], item.get("label", f"1 - {max_v}")
        if min_v < cantidad <= max_v:
            return etiquetas_severidad[min(idx, 3)], item.get("label", f"{min_v + 1} - {max_v}")

    if cantidad >= 13:
        return "muy_alta", "13+"
    if cantidad >= 8:
        return "alta", "8 - 12"
    if cantidad >= 4:
        return "media", "4 - 7"
    return "baja", "1 - 3"


def extraer_stop_carabineros(
    bbox: Tuple[float, float, float, float],
    zoom: int = ZOOM_HEXAGONOS,
) -> Dict[str, Any]:
    """
    Inicia sesión en https://stop.carabineros.cl para obtener las cookies y token XSRF,
    y consulta el endpoint oficial `serviceCall4` para EVE_ROB_VI (Robos con violencia).
    """
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_crear_ssl_context()),
        urllib.request.HTTPCookieProcessor(cj),
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{STOP_BASE_URL}/",
        "Origin": STOP_BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }

    # 1. Obtener cookies de sesión y XSRF-TOKEN desde la portada de STOP
    req_home = urllib.request.Request(f"{STOP_BASE_URL}/", headers=headers)
    opener.open(req_home, timeout=30).read()

    for cookie in cj:
        if cookie.name == "XSRF-TOKEN":
            headers["X-XSRF-TOKEN"] = urllib.parse.unquote(cookie.value)

    # 2. Construir ventana de tiempo de 90 días (misma lógica del frontend de STOP)
    hoy = datetime.now()
    desde = hoy - timedelta(days=VENTANA_DIAS)
    date_hasta = urllib.parse.quote(hoy.strftime("%Y-%m-%d") + " 00:00")
    date_desde = urllib.parse.quote(desde.strftime("%Y-%m-%d") + " 23:59")

    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    url = (
        f"{STOP_BASE_URL}/serviceCall4/"
        f"{bbox_str}/{FILTRO_DELITO}/{zoom}/{date_desde}/{date_hasta}"
    )

    print(f"[INFO] Consultando STOP Carabineros: POST {url}")
    req_post = urllib.request.Request(url, data=b"", headers=headers, method="POST")
    with opener.open(req_post, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def transformar(
    raw_geojson: Dict[str, Any],
    rings_maipu: List[List[Tuple[float, float]]],
    bbox_consulta: Tuple[float, float, float, float],
) -> Dict[str, Any]:
    """
    Filtra los hexágonos pertenecientes a la comuna de Maipú y normaliza sus propiedades
    en un GeoJSON FeatureCollection limpio.
    """
    raw_features = raw_geojson.get("features", [])
    bbox_meta_feat = next((f for f in raw_features if f.get("id") == "bbox"), {})
    meta_props = bbox_meta_feat.get("properties", {})

    hexagon_size_m = int(meta_props.get("hexagon_size") or 150)
    legend_items = meta_props.get("legend", {}).get("items", [])
    periodo_min = meta_props.get("event_fecha_min")
    periodo_max = meta_props.get("event_fecha_max")

    features_maipu: List[Dict[str, Any]] = []
    vistos = set()

    for f in raw_features:
        if f.get("id") == "bbox":
            continue
        geom = f.get("geometry") or {}
        if geom.get("type") != "Polygon" or not geom.get("coordinates"):
            continue

        anillo = geom["coordinates"][0]
        pertenece, clon, clat = hexagono_en_maipu(anillo, rings_maipu)
        if not pertenece:
            continue

        # Identificador determinístico único para cada hexágono basado en su centroide
        hex_id = "hex_maipu_" + hashlib.md5(f"{clon:.5f},{clat:.5f}".encode("utf-8")).hexdigest()[:12]
        if hex_id in vistos:
            continue
        vistos.add(hex_id)

        p = f.get("properties") or {}
        cantidad = int(p.get("cantidad") or 0)
        severidad, rango_jenks = clasificar_severidad(cantidad, legend_items)

        features_maipu.append(
            {
                "type": "Feature",
                "id": hex_id,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": geom["coordinates"],
                },
                "properties": {
                    "hex_id": hex_id,
                    "stop_id": str(f.get("id", "")),
                    "comuna": "Maipú",
                    "region": "Región Metropolitana de Santiago",
                    "codigo_delito": FILTRO_DELITO,
                    "tipo_delito": "Robo con violencia",
                    "cantidad": cantidad,
                    "severidad": severidad,
                    "rango_jenks": rango_jenks,
                    "color": p.get("color"),
                    "color_border": p.get("color_border"),
                    "fecha_min": p.get("fecha_min"),
                    "fecha_max": p.get("fecha_max"),
                    "tamanio_hexagono_m": hexagon_size_m,
                    "centroide_lon": clon,
                    "centroide_lat": clat,
                    "fuente": "STOP Carabineros de Chile",
                },
            }
        )

    # Ordenar de mayor a menor cantidad de robos con violencia
    features_maipu.sort(key=lambda item: (-item["properties"]["cantidad"], item["properties"]["hex_id"]))

    total_eventos_maipu = sum(item["properties"]["cantidad"] for item in features_maipu)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "Plataforma STOP - Carabineros de Chile (https://stop.carabineros.cl)",
            "endpoint": "serviceCall4",
            "codigo_delito": FILTRO_DELITO,
            "delito": "Robos con violencia",
            "comuna": "Maipú",
            "region": "Región Metropolitana de Santiago",
            "crs": "EPSG:4326 (WGS84)",
            "tamanio_hexagono_m": hexagon_size_m,
            "periodo_fecha_min": periodo_min,
            "periodo_fecha_max": periodo_max,
            "bbox_consulta": list(bbox_consulta),
            "total_hexagonos_maipu": len(features_maipu),
            "total_robos_con_violencia_maipu": total_eventos_maipu,
            "leyenda_jenks": legend_items,
            "fecha_extraccion": datetime.now().isoformat(timespec="seconds"),
        },
        "features": features_maipu,
    }


def main() -> int:
    print("=" * 70)
    print("ETL INFRAESTRUCTURA: Hexágonos de Robo con Violencia (STOP Carabineros)")
    print("Comuna: Maipú, Región Metropolitana")
    print("=" * 70)

    bbox_maipu, rings_maipu = obtener_poligono_maipu()
    raw_geojson = extraer_stop_carabineros(bbox_maipu, zoom=ZOOM_HEXAGONOS)
    geojson_maipu = transformar(raw_geojson, rings_maipu, bbox_maipu)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(geojson_maipu, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    meta = geojson_maipu["metadata"]
    print("-" * 70)
    print(f"[OK] Hexágonos en Maipú extraídos : {meta['total_hexagonos_maipu']}")
    print(f"[OK] Total robos con violencia    : {meta['total_robos_con_violencia_maipu']}")
    print(f"[OK] Tamaño de hexágono           : {meta['tamanio_hexagono_m']} m")
    print(f"[OK] Período registrado           : {meta['periodo_fecha_min']} a {meta['periodo_fecha_max']}")
    print(f"[OK] GeoJSON guardado en          : {OUT_FILE}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
