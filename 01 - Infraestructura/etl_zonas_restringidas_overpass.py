"""ETL de infraestructura: zonas de exclusión aérea permanentes para el dron (Overpass / OSM).

El dron no puede volar en línea recta sobre cualquier punto: la norma DAN 151 de la DGAC
prohíbe operar cerca de aeródromos y helipuertos, y sobre recintos militares o penitenciarios.
Este ETL descarga esos lugares desde OpenStreetMap y les asigna un radio de exclusión. La API
de ruteo (05 - API) los trata como obstáculos duros del grafo de visibilidad: ninguna arista
puede cruzarlos, para ninguna de las 4 técnicas.

Si Overpass no responde se conserva el GeoJSON anterior (versionado en el repositorio), para
que el proyecto se pueda replicar sin depender del servicio.

Variables de entorno (opcionales):
  RADIO_AERODROMO_M   (por defecto 1000)
  RADIO_HELIPUERTO_M  (por defecto 150)
  RADIO_MILITAR_M     (por defecto 50)
  RADIO_CARCEL_M      (por defecto 50)

Genera OUT_DIR/zonas_restringidas_overpass.geojson.
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))
ARCHIVO = "zonas_restringidas_overpass.geojson"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# (sur, oeste, norte, este): Maipú y alrededores, algo más grande que el área de ruteo
BBOX = (-33.62, -70.95, -33.42, -70.68)

RADIOS = {
    "aerodromo": float(os.environ.get("RADIO_AERODROMO_M", "1000")),
    "helipuerto": float(os.environ.get("RADIO_HELIPUERTO_M", "150")),
    "militar": float(os.environ.get("RADIO_MILITAR_M", "50")),
    "carcel": float(os.environ.get("RADIO_CARCEL_M", "50")),
}
MOTIVOS = {
    "aerodromo": "DAN 151: prohibido operar RPA en las cercanías de un aeródromo",
    "helipuerto": "DAN 151: prohibido operar RPA en las cercanías de un helipuerto (p. ej. hospitales)",
    "militar": "Recinto militar: espacio aéreo restringido",
    "carcel": "Recinto penitenciario: sobrevuelo prohibido",
}


def consulta():
    s, w, n, e = BBOX
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:90];
(
  nwr["aeroway"~"^(aerodrome|heliport|helipad)$"]{b};
  nwr["landuse"="military"]{b};
  nwr["military"~"^(base|barracks|airfield|range|training_area)$"]{b};
  nwr["amenity"="prison"]{b};
);
out geom;"""


def extraer():
    datos = urllib.parse.urlencode({"data": consulta()}).encode("utf-8")
    ctx = ssl.create_default_context()
    for intento in range(1, 3):
        for url in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    url, data=datos, headers={"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"}
                )
                with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                    return json.loads(r.read().decode("utf-8"))["elements"]
            except Exception as err:  # noqa: BLE001 - se reintenta con otro servidor
                print(f"  [WARN] Overpass {url} intento {intento}: {err}", file=sys.stderr)
        time.sleep(5 * intento)
    return None


def tipo_de(tags):
    aeroway = tags.get("aeroway")
    if aeroway == "aerodrome":
        return "aerodromo"
    if aeroway in ("heliport", "helipad"):
        return "helipuerto"
    if tags.get("amenity") == "prison":
        return "carcel"
    return "militar"


def geometria(el):
    """Geometría GeoJSON del elemento: punto, polígono (vía cerrada) o línea/multipolígono."""
    if el["type"] == "node":
        return {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    if el["type"] == "way":
        coords = [[p["lon"], p["lat"]] for p in el.get("geometry", [])]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return {"type": "Polygon", "coordinates": [coords]}
        if len(coords) >= 2:
            return {"type": "LineString", "coordinates": coords}
        return None
    # relation: anillos "outer" que ya vienen cerrados; si no, el rectángulo de la relación
    anillos = []
    for m in el.get("members", []):
        coords = [[p["lon"], p["lat"]] for p in m.get("geometry", []) or []]
        if m.get("role") == "outer" and len(coords) >= 4 and coords[0] == coords[-1]:
            anillos.append([coords])
    if anillos:
        return {"type": "MultiPolygon", "coordinates": anillos}
    b = el.get("bounds")
    if b:
        ring = [
            [b["minlon"], b["minlat"]], [b["maxlon"], b["minlat"]], [b["maxlon"], b["maxlat"]],
            [b["minlon"], b["maxlat"]], [b["minlon"], b["minlat"]],
        ]
        return {"type": "Polygon", "coordinates": [ring]}
    return None


def transformar(elementos):
    features = []
    for el in elementos:
        tags = el.get("tags", {})
        geom = geometria(el)
        if geom is None:
            continue
        tipo = tipo_de(tags)
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "osm_ref": f"{el['type']}/{el['id']}",
                "tipo": tipo,
                "nombre": tags.get("name"),
                "motivo": MOTIVOS[tipo],
                "radio_exclusion_m": RADIOS[tipo],
                "fuente": "OpenStreetMap via Overpass API",
            },
        })
    return features


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / ARCHIVO
    elementos = extraer()
    if elementos is None:
        if destino.exists():
            print(f"[WARN] Overpass no respondió: se conserva {destino}")
            return
        print("[WARN] Overpass no respondió y no hay archivo previo: se genera una capa vacía")
        elementos = []
    features = transformar(elementos)
    coleccion = {
        "type": "FeatureCollection",
        "metadata": {
            "fuente": "OpenStreetMap via Overpass API",
            "descripcion": "Zonas de exclusión aérea permanentes para el dron (aeródromos, helipuertos, recintos militares y cárceles)",
            "crs": "EPSG:4326",
            "bbox_consulta": [BBOX[1], BBOX[0], BBOX[3], BBOX[2]],
            "radios_exclusion_m": RADIOS,
            "fecha_extraccion_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_zonas": len(features),
        },
        "features": features,
    }
    destino.write_text(json.dumps(coleccion, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(features)} zonas restringidas -> {destino}")


if __name__ == "__main__":
    main()
