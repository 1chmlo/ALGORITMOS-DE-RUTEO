"""ETL de la amenaza "lluvia" para el vuelo de drones (Open-Meteo, Maipú).

El dron vuela libre (en línea recta entre nodos del grafo aéreo), así que la lluvia no se
asocia a calles sino a zonas: se cubre Maipú con la grilla de hexágonos de open_meteo.py y se
consulta el pronóstico horario de Open-Meteo en el centro de cada hexágono. Un hexágono queda
`no_volable` si, dentro de la ventana de vuelo (hora actual + siguientes), la precipitación
supera UMBRAL_MM_H o la probabilidad de lluvia supera UMBRAL_PROB. En el ruteo
(00 - DB/dijkstra.sql) se descartan las aristas aéreas que cruzan un hexágono no volable.
El viento es un proceso aparte (etl_viento_open_meteo.py) con la misma grilla.

Resolución: Open-Meteo usa modelos globales (~9-13 km de celda en Chile). Varios hexágonos
caen en la misma celda del modelo y reciben el mismo valor; las propiedades
`celda_modelo_lat/lon` indican qué celda se usó. La grilla fina sirve para recortar las
aristas con precisión, no agrega detalle meteorológico.

Variables de entorno (opcionales):
  LLUVIA_UMBRAL_MM_H     mm/h desde los que no se vuela (por defecto 0.5)
  LLUVIA_UMBRAL_PROB     % de probabilidad desde el que no se vuela (por defecto 70)
  LLUVIA_VENTANA_HORAS   horas evaluadas desde la hora actual (por defecto 2)
  LLUVIA_SIMULADA        "lon,lat,radio_m": fuerza lluvia en un círculo, para probar el
                         ruteo en días secos. Queda registrado en la metadata (`simulacion`).

Genera OUT_DIR/lluvia_open_meteo_hexagonos.geojson.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from open_meteo import (
    BBOX_MAIPU, OPEN_METEO_URL, RADIO_HEX_M, celdas_distintas, consultar_horario,
    dentro_de_simulacion, grilla_hexagonos, parsear_simulacion, serie,
)

UMBRAL_MM_H = float(os.environ.get("LLUVIA_UMBRAL_MM_H", "0.5"))
UMBRAL_PROB = float(os.environ.get("LLUVIA_UMBRAL_PROB", "70"))
VENTANA_HORAS = int(os.environ.get("LLUVIA_VENTANA_HORAS", "2"))
VARIABLES = ["precipitation", "precipitation_probability"]

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salidas"))


def transformar(hexagonos, respuestas, simulacion, ahora):
    features = []
    for h, resp in zip(hexagonos, respuestas):
        precip = serie(resp, "precipitation")
        precip_max = max(precip, default=0.0)
        prob_max = max(serie(resp, "precipitation_probability"), default=None)
        horas = (resp.get("hourly") or {}).get("time") or [None]

        simulado = dentro_de_simulacion(h["centro"], simulacion)
        motivos = []
        if precip_max >= UMBRAL_MM_H:
            motivos.append(f"precipitación {precip_max} mm/h >= {UMBRAL_MM_H}")
        if prob_max is not None and prob_max >= UMBRAL_PROB:
            motivos.append(f"probabilidad {prob_max}% >= {UMBRAL_PROB}%")
        if simulado:
            motivos.append("lluvia simulada (LLUVIA_SIMULADA)")

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [h["anillo"]]},
                "properties": {
                    "hex_id": h["hex_id"],
                    "centro_lon": h["centro"][0],
                    "centro_lat": h["centro"][1],
                    "celda_modelo_lon": resp.get("longitude"),
                    "celda_modelo_lat": resp.get("latitude"),
                    "precipitacion_actual_mm_h": precip[0] if precip else None,
                    "precipitacion_max_mm_h": precip_max,
                    "probabilidad_max_pct": prob_max,
                    "hora_desde": horas[0],
                    "hora_hasta": horas[-1],
                    "ventana_horas": VENTANA_HORAS,
                    "umbral_mm_h": UMBRAL_MM_H,
                    "umbral_prob_pct": UMBRAL_PROB,
                    "simulado": simulado,
                    "no_volable": bool(motivos),
                    "motivo": "; ".join(motivos) or None,
                    "tamanio_hexagono_m": RADIO_HEX_M,
                    "fecha_extraccion_utc": ahora,
                    "fuente": "Open-Meteo Forecast API",
                },
            }
        )

    metadata = {
        "fuente": "Open-Meteo Forecast API (modelo best_match)",
        "endpoint": OPEN_METEO_URL,
        "descripcion": "Zonas donde el dron no debe volar por lluvia en la ventana de vuelo",
        "crs": "EPSG:4326 (WGS84)",
        "bbox_consulta": list(BBOX_MAIPU),
        "tamanio_hexagono_m": RADIO_HEX_M,
        "ventana_horas": VENTANA_HORAS,
        "umbral_mm_h": UMBRAL_MM_H,
        "umbral_prob_pct": UMBRAL_PROB,
        "simulacion": simulacion,
        "celdas_modelo_distintas": celdas_distintas(features),
        "total_hexagonos": len(features),
        "total_no_volables": sum(f["properties"]["no_volable"] for f in features),
        "fecha_extraccion_utc": ahora,
    }
    return {"type": "FeatureCollection", "metadata": metadata, "features": features}


def main():
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    simulacion = parsear_simulacion(os.environ.get("LLUVIA_SIMULADA"), "LLUVIA_SIMULADA")
    hexagonos = grilla_hexagonos()
    respuestas = consultar_horario([h["centro"] for h in hexagonos], VARIABLES, VENTANA_HORAS)
    coleccion = transformar(hexagonos, respuestas, simulacion, ahora)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "lluvia_open_meteo_hexagonos.geojson"
    destino.write_text(json.dumps(coleccion, ensure_ascii=False, indent=1), encoding="utf-8")
    m = coleccion["metadata"]
    print(f"{m['total_hexagonos']} hexágonos -> {destino}")
    print(
        f"{m['total_no_volables']} no volables (umbral {UMBRAL_MM_H} mm/h o {UMBRAL_PROB}%, "
        f"ventana {VENTANA_HORAS} h, {m['celdas_modelo_distintas']} celdas del modelo)"
        + (" [con lluvia simulada]" if simulacion else "")
    )


if __name__ == "__main__":
    sys.exit(main())
