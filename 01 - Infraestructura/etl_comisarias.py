"""ETL de comisarías (unidades de Carabineros) de la Región Metropolitana.

Extrae la capa "Carabineros" del servidor ArcGIS del Ministerio de Desarrollo
Social, la transforma a un GeoJSON con nombres de campo normalizados y la
guarda en OUT_DIR/comisarias.geojson.
"""
import json
import os
import sys
from pathlib import Path

import requests

URL = (
    "https://mdsfterritorial.ministeriodesarrollosocial.gob.cl/server/rest/services/"
    "RED_PROTECCION_SOCIAL/SSEGURIDAD/MapServer/3/query"
)
COD_REGION_RM = 13
PAGINA = 1000
OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))


def extraer():
    """Descarga todas las unidades de la RM paginando sobre el servicio ArcGIS."""
    features, offset = [], 0
    while True:
        r = requests.get(
            URL,
            params={
                "where": f"cod_reg={COD_REGION_RM}",
                "outFields": "*",
                "outSR": 4326,
                "orderByFields": "objectid",
                "resultOffset": offset,
                "resultRecordCount": PAGINA,
                "f": "geojson",
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        lote = data["features"]
        features += lote
        if len(lote) < PAGINA:
            return features
        offset += PAGINA


def _texto(valor):
    valor = (valor or "").strip()
    return valor or None


def transformar(features):
    salida = []
    for f in features:
        p = f["properties"]
        if not f.get("geometry"):
            continue
        salida.append(
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    "objectid": p["objectid"],
                    "codigo_unidad": _texto(p["uni_cod"]),
                    "nombre": _texto(p["nombre_uni"]),
                    "tipo_unidad": _texto(p["tipo_de_un"]),
                    "direccion": _texto(p["direccion_1"]),
                    "cod_region": p["cod_reg"],
                    "region": _texto(p["nom_reg"]),
                    "cod_provincia": p["cod_prov"],
                    "provincia": _texto(p["nom_prov"]),
                    "cod_comuna": p["cod_com"],
                    "comuna": _texto(p["nom_com"]),
                    "prefectura": _texto(p["prefectura"]),
                    "zona": _texto(p["zona"]),
                    "anio_creacion": int(p["hecho"]) if (p["hecho"] or "").isdigit() else None,
                    "vigente": p["vigencia"] == 1,
                },
            }
        )
    return {"type": "FeatureCollection", "features": salida}


def main():
    geojson = transformar(extraer())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "comisarias.geojson"
    destino.write_text(json.dumps(geojson, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(geojson['features'])} unidades -> {destino}")


if __name__ == "__main__":
    sys.exit(main())
