"""ETL de robos con violencia de la plataforma STOP de Carabineros (toda la RM).

Consulta el endpoint que usa el visor, POST /serviceCall4/{bbox}/EVE_ROB_VI/{zoom}/{desde}/{hasta},
que devuelve la grilla de hexágonos con la cantidad de casos de los últimos 90 días y el color
que el visor les asigna. Se recortan los hexágonos a la Región Metropolitana y se generan dos
GeoJSON con el mismo `hex_id`:

  - OUT_DIR/robo_con_violencia_hexagonos.geojson: polígono del hexágono con su color y cantidad.
  - OUT_DIR/robo_con_violencia_centroides.geojson: punto central de cada hexágono.

STOP solo ofrece tamaños de 150 m * 2^n. El zoom 12 entrega hexágonos de 1200 m de punta a
punta (~0,94 km²), la grilla más cercana a 1 km.
"""
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests

STOP_URL = "https://stop.carabineros.cl"
FILTRO_DELITO = "EVE_ROB_VI"  # 4.1 Robos con violencia
ZOOM = 12
TAMANIO_ESPERADO_M = 1200
VENTANA_DIAS = 91  # misma ventana móvil que el visor (~90 días)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# bbox fijo de la RM (min_lon, min_lat, max_lon, max_lat), con margen sobre el polígono regional.
# La grilla de STOP es global (no depende del bbox), así que los hex_id son estables; sí dependen
# del bbox los rangos de la leyenda, por eso se fija en vez de tomarlo de Nominatim.
BBOX_RM = (-71.72, -34.30, -69.76, -32.92)

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))


def poligono_rm():
    """Anillos exteriores de la RM desde OSM. Sin polígono no se recorta (lista vacía)."""
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={
                "q": "Región Metropolitana de Santiago, Chile",
                "featuretype": "state",
                "format": "geojson",
                "polygon_geojson": 1,
                "polygon_threshold": 0.005,
                "limit": 1,
            },
            headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"},
            timeout=40,
        )
        r.raise_for_status()
        geom = r.json()["features"][0]["geometry"]
        if geom.get("type") == "Polygon":
            poligonos = [geom["coordinates"]]
        elif geom.get("type") == "MultiPolygon":
            poligonos = geom["coordinates"]
        else:
            print(f"AVISO: geometría no soportada ({geom.get('type')}); no se recorta por región")
            return []
        return [[tuple(p) for p in poligono[0]] for poligono in poligonos]
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
        print(f"AVISO: sin polígono de la RM ({e}); no se recorta por región")
        return []


def punto_en_anillo(lon, lat, anillo):
    """Ray casting: True si (lon, lat) cae dentro del anillo."""
    dentro, j = False, len(anillo) - 1
    for i, (xi, yi) in enumerate(anillo):
        xj, yj = anillo[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def en_rm(vertices, centroide, anillos):
    """El hexágono se conserva si su centroide o algún vértice está dentro de la RM."""
    if not anillos:
        return True
    puntos = [centroide, *vertices]
    return any(punto_en_anillo(lon, lat, a) for a in anillos for lon, lat in puntos)


def extraer(hoy):
    """Descarga los hexágonos de toda la RM desde STOP (una sola consulta)."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{STOP_URL}/",
            "Origin": STOP_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    s.get(f"{STOP_URL}/", timeout=30).raise_for_status()  # cookies de sesión y XSRF-TOKEN
    xsrf = s.cookies.get("XSRF-TOKEN")
    if xsrf:
        s.headers["X-XSRF-TOKEN"] = urllib.parse.unquote(xsrf)

    desde = urllib.parse.quote(f"{hoy - timedelta(days=VENTANA_DIAS)} 23:59")
    hasta = urllib.parse.quote(f"{hoy} 00:00")
    bbox = ",".join(str(c) for c in BBOX_RM)
    url = f"{STOP_URL}/serviceCall4/{bbox}/{FILTRO_DELITO}/{ZOOM}/{desde}/{hasta}"
    r = s.post(url, timeout=180)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f"STOP no devolvió JSON (¿bloqueo del WAF?): {r.text[:200]!r}")


def nivel_de(cantidad, items):
    """Posición (1..N) del rango de la leyenda de STOP que contiene `cantidad`."""
    for i, it in enumerate(items, start=1):
        if cantidad <= it["max"] and (i == 1 or cantidad > it["min"]):
            return i
    return len(items)


def transformar(crudo, anillos_rm, hoy):
    """Devuelve (hexagonos, centroides) como FeatureCollections con el mismo `hex_id`."""
    features = crudo["features"]
    meta = next((f["properties"] for f in features if f.get("id") == "bbox"), {})
    tamanio = int(meta.get("hexagon_size") or 0)
    if tamanio != TAMANIO_ESPERADO_M:
        raise RuntimeError(f"STOP devolvió hexágonos de {tamanio} m; se esperaban {TAMANIO_ESPERADO_M} m")
    items = meta["legend"]["items"]
    desde = hoy - timedelta(days=VENTANA_DIAS)

    hexagonos, centroides, vistos = [], [], set()
    for f in features:
        geom = f.get("geometry") or {}
        if f.get("id") == "bbox" or geom.get("type") != "Polygon":
            continue
        vertices = geom["coordinates"][0][:-1]  # el último punto repite el primero
        clon = round(sum(v[0] for v in vertices) / len(vertices), 6)
        clat = round(sum(v[1] for v in vertices) / len(vertices), 6)
        if not en_rm(vertices, (clon, clat), anillos_rm):
            continue
        hex_id = "hex_rm_" + hashlib.md5(f"{clon:.5f},{clat:.5f}".encode()).hexdigest()[:12]
        if hex_id in vistos:
            continue
        vistos.add(hex_id)

        p = f["properties"]
        cantidad = int(p["cantidad"])
        nivel = nivel_de(cantidad, items)
        comunes = {
            "hex_id": hex_id,
            "cantidad": cantidad,
            "nivel": nivel,
            "niveles_total": len(items),
            "color": p["color"],
        }
        hexagonos.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    **comunes,
                    "stop_id": str(f["id"]),
                    "codigo_delito": FILTRO_DELITO,
                    "tipo_delito": "Robo con violencia",
                    "rango": items[nivel - 1]["label"],
                    "color_border": p["color_border"],
                    "fecha_min": p["fecha_min"],
                    "fecha_max": p["fecha_max"],
                    "periodo_desde": str(desde),
                    "periodo_hasta": str(hoy),
                    "tamanio_hexagono_m": tamanio,
                    "fuente": "STOP Carabineros de Chile",
                },
            }
        )
        centroides.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [clon, clat]},
                "properties": comunes,
            }
        )

    hexagonos.sort(key=lambda h: (-h["properties"]["cantidad"], h["properties"]["hex_id"]))
    centroides.sort(key=lambda c: (-c["properties"]["cantidad"], c["properties"]["hex_id"]))
    metadata = {
        "fuente": f"{STOP_URL} (serviceCall4)",
        "codigo_delito": FILTRO_DELITO,
        "zoom": ZOOM,
        "tamanio_hexagono_m": tamanio,
        "bbox_consulta": list(BBOX_RM),
        "periodo_desde": str(desde),
        "periodo_hasta": str(hoy),
        "eventos_en_periodo": meta.get("event_count"),
        "total_hexagonos": len(hexagonos),
        "total_eventos_rm": sum(h["properties"]["cantidad"] for h in hexagonos),
        "leyenda": items,
    }
    return (
        {"type": "FeatureCollection", "metadata": metadata, "features": hexagonos},
        {"type": "FeatureCollection", "metadata": metadata, "features": centroides},
    )


def main():
    hoy = date.today()
    hexagonos, centroides = transformar(extraer(hoy), poligono_rm(), hoy)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, coleccion in (
        ("robo_con_violencia_hexagonos.geojson", hexagonos),
        ("robo_con_violencia_centroides.geojson", centroides),
    ):
        destino = OUT_DIR / nombre
        destino.write_text(json.dumps(coleccion, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(coleccion['features'])} features -> {destino}")
    m = hexagonos["metadata"]
    print(f"{m['total_eventos_rm']} robos con violencia entre {m['periodo_desde']} y {m['periodo_hasta']}")


if __name__ == "__main__":
    sys.exit(main())
