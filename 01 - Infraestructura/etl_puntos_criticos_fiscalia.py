"""ETL de puntos críticos de encerronas en la Región Metropolitana.

Fuentes:
  - Fiscalía Nacional, Reporte de Fenómenos Criminales N°5 (robo violento de
    vehículos), sección 5.4 "Análisis espacial", página 24.
  - Emol (26-06-2026), que cita el mismo informe y agrega el caso de San Bernardo.

El informe describe los puntos en texto (intersecciones de vías), sin coordenadas,
y su contenido no cambia. Por eso el catálogo es fijo: las citas fueron verificadas
contra el PDF y las coordenadas se obtuvieron una vez desde OpenStreetMap (punto medio
del par de nodos más cercanos entre ambas vías; en enlaces de autopista las vías están
a distinto nivel y no comparten nodo, `separacion_vias_m` indica esa distancia).

Genera OUT_DIR/puntos_criticos_fiscalia.geojson sin acceso a red.
"""
import json
import os
import sys
from pathlib import Path

PDF_URL = (
    "https://www.fiscaliadechile.cl/sites/default/files/documentos/"
    "INFORME_ROBO_VIOLENTO_DE_VEHICULOS.pdf"
)
EMOL_URL = (
    "https://www.emol.com/noticias/Nacional/2026/06/26/1203878/"
    "mapa-encerronas-portonazos-rm.html"
)
OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salida"))

# (nombre, lat, lon, severidad, fuente, página, separación entre vías en m, cita)
PUNTOS = [
    ("Vespucio Sur con Ruta 78 (Autopista del Sol)", -33.490288, -70.749023, "alta", "fiscalia", 24, 37,
     "hay una concentración importante de casos en la intersección de Vespucio Sur con la Ruta 78 (Autopista del Sol) y en los alrededores de esta"),
    ("Vespucio Sur con Ruta 5", -33.532130, -70.681616, "alta", "fiscalia", 24, 18,
     "se observa una alta densidad en la intersección de Vespucio Sur con la Ruta 5"),
    ("Vespucio Sur con General Velásquez", -33.520343, -70.703375, "alta", "fiscalia", 24, 89,
     "se observa una alta densidad en la intersección de Vespucio Sur [...] con General Velásquez"),
    ("Costanera Norte con General Velásquez", -33.415863, -70.691935, "media", "fiscalia", 24, 4,
     "Esta densidad es menor en la intersección de la Costanera Norte con General Velásquez"),
    ("Vespucio Norte con Ruta 5", -33.366142, -70.700180, "baja", "fiscalia", 24, 6,
     "es menor aún en la intersección de Vespucio Norte con la Ruta 5"),
    ("Barrancón con Avenida Jorge Alessandri (San Bernardo)", -33.609854, -70.716989, None, "emol", None, 0,
     "encerrona del 23-06-2026 que causó la muerte de un menor, en la intersección de la calle Barrancón con Avenida Jorge Alessandri (poca iluminación y cercanía a autopistas)"),
]


def feature(nombre, lat, lon, severidad, fuente, pagina, separacion, cita):
    fiscalia = fuente == "fiscalia"
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "nombre": nombre,
            "tipo_delito": "encerrona",
            "severidad": severidad,
            "fuente": fuente,
            "fuente_url": PDF_URL if fiscalia else EMOL_URL,
            "pagina_informe": pagina,
            "cita": cita,
            "cita_verificada": True,
            "periodo": "2020-2025" if fiscalia else "2026-06-23",
            "separacion_vias_m": separacion,
        },
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "puntos_criticos_fiscalia.geojson"
    coleccion = {"type": "FeatureCollection", "features": [feature(*p) for p in PUNTOS]}
    destino.write_text(json.dumps(coleccion, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(PUNTOS)} puntos -> {destino}")


if __name__ == "__main__":
    sys.exit(main())
