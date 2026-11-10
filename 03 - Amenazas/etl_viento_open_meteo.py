"""ETL de la amenaza "viento" para el vuelo de drones (Open-Meteo, Maipú).

Proceso aparte del de lluvia (etl_lluvia_open_meteo.py), pero con la misma grilla de
hexágonos (open_meteo.py), así que los `hex_id` coinciden. Un hexágono queda `no_volable` si,
dentro de la ventana de vuelo (hora actual + siguientes), se cumple alguna de estas condiciones:

  - el viento sostenido a la altura de vuelo (máximo entre 80 m y 120 m sobre el suelo) llega
    a UMBRAL_KMH, o
  - las ráfagas llegan a UMBRAL_RAFAGA_KMH. Open-Meteo solo entrega ráfagas a 10 m; a la
    altura de vuelo suelen ser mayores, así que este umbral es conservador por el lado bajo.

Se usan 80/120 m porque el vuelo de drones en Chile tiene un techo cercano a 120 m sobre el
suelo. En el ruteo (00 - DB/dijkstra.sql) se descartan las aristas aéreas que cruzan un
hexágono no volable por viento, igual que con la lluvia.

Resolución: igual que la lluvia, Open-Meteo usa celdas de ~9-13 km en Chile.

Variables de entorno (opcionales):
  VIENTO_UMBRAL_KMH         viento sostenido máximo (por defecto 36 km/h = 10 m/s)
  VIENTO_UMBRAL_RAFAGA_KMH  ráfaga máxima (por defecto 43 km/h = 12 m/s)
  VIENTO_VENTANA_HORAS      horas evaluadas desde la hora actual (por defecto 2)
  VIENTO_SIMULADO           "lon,lat,radio_m": fuerza viento fuerte en un círculo, para
                            probar el ruteo. Queda registrado en la metadata (`simulacion`).

Genera OUT_DIR/viento_open_meteo_hexagonos.geojson.
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

UMBRAL_KMH = float(os.environ.get("VIENTO_UMBRAL_KMH", "36"))
UMBRAL_RAFAGA_KMH = float(os.environ.get("VIENTO_UMBRAL_RAFAGA_KMH", "43"))
VENTANA_HORAS = int(os.environ.get("VIENTO_VENTANA_HORAS", "2"))
VARIABLES = [
    "wind_speed_80m", "wind_speed_120m", "wind_direction_120m", "wind_gusts_10m",
]

OUT_DIR = Path(os.environ.get("OUT_DIR", Path(__file__).parent / "salidas"))


def transformar(hexagonos, respuestas, simulacion, ahora):
    features = []
    for h, resp in zip(hexagonos, respuestas):
        horario = resp.get("hourly") or {}
        v80 = horario.get("wind_speed_80m") or []
        v120 = horario.get("wind_speed_120m") or []
        # Viento a la altura de vuelo por hora: el mayor entre 80 m y 120 m
        por_hora = [max((x for x in par if x is not None), default=None) for par in zip(v80, v120)]
        validos = [v for v in por_hora if v is not None]
        viento_max = max(validos, default=None)
        rafaga_max = max(serie(resp, "wind_gusts_10m"), default=None)
        direcciones = horario.get("wind_direction_120m") or []
        # Dirección en la hora de mayor viento (de dónde sopla, grados desde el norte)
        direccion = (
            direcciones[por_hora.index(viento_max)]
            if viento_max is not None and por_hora.index(viento_max) < len(direcciones)
            else None
        )
        horas = horario.get("time") or [None]

        simulado = dentro_de_simulacion(h["centro"], simulacion)
        motivos = []
        if viento_max is not None and viento_max >= UMBRAL_KMH:
            motivos.append(f"viento {viento_max} km/h >= {UMBRAL_KMH}")
        if rafaga_max is not None and rafaga_max >= UMBRAL_RAFAGA_KMH:
            motivos.append(f"ráfagas {rafaga_max} km/h >= {UMBRAL_RAFAGA_KMH}")
        if simulado:
            motivos.append("viento simulado (VIENTO_SIMULADO)")

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
                    "viento_actual_kmh": validos[0] if validos else None,
                    "viento_max_kmh": viento_max,
                    "rafaga_max_kmh": rafaga_max,
                    "direccion_grados": direccion,
                    "hora_desde": horas[0],
                    "hora_hasta": horas[-1],
                    "ventana_horas": VENTANA_HORAS,
                    "umbral_kmh": UMBRAL_KMH,
                    "umbral_rafaga_kmh": UMBRAL_RAFAGA_KMH,
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
        "descripcion": "Zonas donde el dron no debe volar por viento en la ventana de vuelo",
        "crs": "EPSG:4326 (WGS84)",
        "bbox_consulta": list(BBOX_MAIPU),
        "tamanio_hexagono_m": RADIO_HEX_M,
        "ventana_horas": VENTANA_HORAS,
        "umbral_kmh": UMBRAL_KMH,
        "umbral_rafaga_kmh": UMBRAL_RAFAGA_KMH,
        "altura_viento_m": [80, 120],
        "altura_rafaga_m": 10,
        "simulacion": simulacion,
        "celdas_modelo_distintas": celdas_distintas(features),
        "total_hexagonos": len(features),
        "total_no_volables": sum(f["properties"]["no_volable"] for f in features),
        "fecha_extraccion_utc": ahora,
    }
    return {"type": "FeatureCollection", "metadata": metadata, "features": features}


def main():
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    simulacion = parsear_simulacion(os.environ.get("VIENTO_SIMULADO"), "VIENTO_SIMULADO")
    hexagonos = grilla_hexagonos()
    respuestas = consultar_horario([h["centro"] for h in hexagonos], VARIABLES, VENTANA_HORAS)
    coleccion = transformar(hexagonos, respuestas, simulacion, ahora)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    destino = OUT_DIR / "viento_open_meteo_hexagonos.geojson"
    destino.write_text(json.dumps(coleccion, ensure_ascii=False, indent=1), encoding="utf-8")
    m = coleccion["metadata"]
    print(f"{m['total_hexagonos']} hexágonos -> {destino}")
    print(
        f"{m['total_no_volables']} no volables (viento {UMBRAL_KMH} km/h o ráfagas "
        f"{UMBRAL_RAFAGA_KMH} km/h, ventana {VENTANA_HORAS} h, "
        f"{m['celdas_modelo_distintas']} celdas del modelo)"
        + (" [con viento simulado]" if simulacion else "")
    )


if __name__ == "__main__":
    sys.exit(main())
