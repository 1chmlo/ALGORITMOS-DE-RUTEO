"""ETL de puntos críticos de encerronas en la Región Metropolitana.

Fuentes:
  - Fiscalía Nacional, Reporte de Fenómenos Criminales N°5 (robo violento de
    vehículos), sección 5.4 "Análisis espacial".
  - Emol (26-06-2026), que cita el mismo informe y agrega el caso de San Bernardo.

El informe describe los puntos en texto (intersecciones de vías), sin
coordenadas. Este script:
  1. descarga el PDF y comprueba que cada punto del catálogo siga citado en la
     página indicada;
  2. obtiene la geometría de las dos vías de cada intersección desde OpenStreetMap
     (Overpass) y toma el punto medio del par de nodos más cercanos entre ambas
     (en enlaces de autopista las vías no comparten nodo por estar a distinto nivel);
  3. guarda OUT_DIR/puntos_criticos_fiscalia.geojson.
"""
import io
import json
import math
import os
import sys
import time
from pathlib import Path

import requests
from pypdf import PdfReader

PDF_URL = (
    "https://www.fiscaliadechile.cl/sites/default/files/documentos/"
    "INFORME_ROBO_VIOLENTO_DE_VEHICULOS.pdf"
)
EMOL_URL = (
    "https://www.emol.com/noticias/Nacional/2026/06/26/1203878/"
    "mapa-encerronas-portonazos-rm.html"
)
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "etl-ruteo-udp/1.0 (trabajo academico)"}
OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))
DISTANCIA_MAX_M = 400  # si las dos vías no se acercan a menos de esto, el punto se descarta

MOTORWAY = '["highway"~"^(motorway|motorway_link|trunk|trunk_link)$"]'

# Catálogo de puntos descritos en el informe. `ventana` (sur, oeste, norte, este)
# acota dónde buscar el cruce cuando las dos vías se encuentran más de una vez en la RM;
# es una decisión nuestra, no del informe. `pagina`/`claves` permiten verificar la cita.
PUNTOS = [
    {
        "nombre": "Vespucio Sur con Ruta 78 (Autopista del Sol)",
        "via_a": f'way{MOTORWAY}["name"~"Vespucio Sur"]',
        "via_b": f'way{MOTORWAY}["ref"="78"]',
        "ventana": (-33.56, -70.82, -33.46, -70.70),
        "severidad": "alta",
        "fuente": "fiscalia",
        "pagina": 24,
        "claves": ["Vespucio Sur", "Ruta 78", "Autopista del Sol"],
        "cita": "hay una concentración importante de casos en la intersección de Vespucio Sur con la Ruta 78 (Autopista del Sol) y en los alrededores de esta",
    },
    {
        "nombre": "Vespucio Sur con Ruta 5",
        "via_a": f'way{MOTORWAY}["name"~"Vespucio Sur"]',
        "via_b": f'way{MOTORWAY}["ref"="5"]',
        "ventana": (-33.58, -70.72, -33.49, -70.62),
        "severidad": "alta",
        "fuente": "fiscalia",
        "pagina": 24,
        "claves": ["Vespucio Sur", "Ruta 5", "alta densidad"],
        "cita": "se observa una alta densidad en la intersección de Vespucio Sur con la Ruta 5",
    },
    {
        "nombre": "Vespucio Sur con General Velásquez",
        "via_a": f'way{MOTORWAY}["name"~"Vespucio Sur"]',
        "via_b": 'way["highway"~"^(motorway|motorway_link|trunk|primary)$"]["name"~"General Velásquez"]',
        "ventana": (-33.58, -70.72, -33.49, -70.62),
        "severidad": "alta",
        "fuente": "fiscalia",
        "pagina": 24,
        "claves": ["Vespucio Sur", "General Velásquez", "alta densidad"],
        "cita": "se observa una alta densidad en la intersección de Vespucio Sur [...] con General Velásquez",
    },
    {
        "nombre": "Costanera Norte con General Velásquez",
        "via_a": f'way{MOTORWAY}["name"~"Costanera Norte"]',
        "via_b": 'way["highway"~"^(motorway|motorway_link|trunk|primary)$"]["name"~"General Velásquez"]',
        "ventana": (-33.50, -70.74, -33.40, -70.64),
        "severidad": "media",
        "fuente": "fiscalia",
        "pagina": 24,
        "claves": ["Costanera Norte", "General Velásquez", "menor"],
        "cita": "Esta densidad es menor en la intersección de la Costanera Norte con General Velásquez",
    },
    {
        "nombre": "Vespucio Norte con Ruta 5",
        "via_a": f'way{MOTORWAY}["name"~"Vespucio Norte"]',
        "via_b": f'way{MOTORWAY}["ref"="5"]',
        "ventana": (-33.44, -70.72, -33.32, -70.62),
        "severidad": "baja",
        "fuente": "fiscalia",
        "pagina": 24,
        "claves": ["Vespucio Norte", "Ruta 5", "menor aún"],
        "cita": "es menor aún en la intersección de Vespucio Norte con la Ruta 5",
    },
    {
        "nombre": "Barrancón con Avenida Jorge Alessandri (San Bernardo)",
        "via_a": 'way["highway"]["name"~"Barrancón"]',
        "via_b": 'way["highway"]["name"~"Jorge Alessandri"]',
        "ventana": (-33.66, -70.76, -33.56, -70.66),
        "severidad": None,
        "fuente": "emol",
        "pagina": None,
        "claves": [],
        "cita": "encerrona del 23-06-2026 que causó la muerte de un menor, en la intersección de la calle Barrancón con Avenida Jorge Alessandri (poca iluminación y cercanía a autopistas)",
    },
]


def _post_overpass(consulta):
    for intento in range(4):
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": consulta}, headers=HEADERS, timeout=120)
                if r.status_code == 200:
                    return r.json()["elements"]
            except requests.RequestException:
                pass
        time.sleep(5 * (intento + 1))
    raise RuntimeError(f"Overpass no respondió para: {consulta}")


def descargar_vias():
    """Una consulta por filtro de vía, sobre la unión de las ventanas que lo usan.

    Devuelve {filtro: [(lat, lon), ...]} con los nodos de todas las vías descargadas.
    """
    ventanas = {}
    for p in PUNTOS:
        for filtro in (p["via_a"], p["via_b"]):
            ventanas.setdefault(filtro, []).append(p["ventana"])
    vias = {}
    for filtro, vs in ventanas.items():
        s, w = min(v[0] for v in vs), min(v[1] for v in vs)
        n, e = max(v[2] for v in vs), max(v[3] for v in vs)
        elementos = _post_overpass(f"[out:json][timeout:90];{filtro}({s},{w},{n},{e});out geom;")
        vias[filtro] = [(q["lat"], q["lon"]) for el in elementos for q in el.get("geometry", [])]
        print(f"  Overpass: {len(vias[filtro])} nodos para {filtro}")
    return vias


def en_ventana(nodos, ventana):
    s, w, n, e = ventana
    return [(la, lo) for la, lo in nodos if s <= la <= n and w <= lo <= e]


def distancia_m(a, b):
    """Distancia haversine en metros entre dos (lat, lon)."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def par_mas_cercano(nodos_a, nodos_b):
    """Par de nodos (uno de cada vía) con menor distancia; búsqueda en malla para evitar O(n*m)."""
    celda = 0.002  # ~200 m
    malla = {}
    for b in nodos_b:
        malla.setdefault((int(b[0] / celda), int(b[1] / celda)), []).append(b)
    mejor = (float("inf"), None, None)
    for a in nodos_a:
        ci, cj = int(a[0] / celda), int(a[1] / celda)
        for di in (-2, -1, 0, 1, 2):
            for dj in (-2, -1, 0, 1, 2):
                for b in malla.get((ci + di, cj + dj), ()):
                    d = distancia_m(a, b)
                    if d < mejor[0]:
                        mejor = (d, a, b)
    return mejor


def geocodificar(punto, vias):
    nodos_a = en_ventana(vias[punto["via_a"]], punto["ventana"])
    nodos_b = en_ventana(vias[punto["via_b"]], punto["ventana"])
    if not nodos_a or not nodos_b:
        return None
    d, a, b = par_mas_cercano(nodos_a, nodos_b)
    if a is None or d > DISTANCIA_MAX_M:
        return None
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, d


def verificar_pdf():
    """Descarga el informe y devuelve el texto por página (1-indexado)."""
    r = requests.get(PDF_URL, headers=HEADERS, timeout=120)
    r.raise_for_status()
    lector = PdfReader(io.BytesIO(r.content))
    return {i + 1: " ".join((p.extract_text() or "").split()) for i, p in enumerate(lector.pages)}


def main():
    paginas = verificar_pdf()
    vias = descargar_vias()
    features = []
    for p in PUNTOS:
        citado = True
        if p["pagina"]:
            texto = paginas.get(p["pagina"], "")
            citado = all(c in texto for c in p["claves"])
            if not citado:
                print(f"  AVISO: no se encontró la cita de '{p['nombre']}' en la página {p['pagina']} del PDF")
        resultado = geocodificar(p, vias)
        if resultado is None:
            print(f"  DESCARTADO: '{p['nombre']}' no se pudo ubicar (vías no se acercan a <{DISTANCIA_MAX_M} m)")
            continue
        lat, lon, d = resultado
        print(f"  {p['nombre']}: {lat:.5f}, {lon:.5f} (separación entre vías {d:.0f} m)")
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {
                    "nombre": p["nombre"],
                    "tipo_delito": "encerrona",
                    "severidad": p["severidad"],
                    "fuente": p["fuente"],
                    "fuente_url": PDF_URL if p["fuente"] == "fiscalia" else EMOL_URL,
                    "pagina_informe": p["pagina"],
                    "cita": p["cita"],
                    "cita_verificada": citado,
                    "periodo": "2020-2025" if p["fuente"] == "fiscalia" else "2026-06-23",
                    "separacion_vias_m": round(d),
                },
            }
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "puntos_criticos_fiscalia.geojson"
    destino.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"{len(features)}/{len(PUNTOS)} puntos -> {destino}")


if __name__ == "__main__":
    sys.exit(main())
