"""Utilidades comunes de los ETL de clima para drones (lluvia y viento) con Open-Meteo.

Ambos procesos usan la misma grilla de hexágonos, así que sus `hex_id` coinciden y las capas
se pueden cruzar por `hex_id`.
"""
import math

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Mismo rectángulo de referencia de Maipú que usa etl_cortes_ruta_tomtom.py
# (min_lon, min_lat, max_lon, max_lat). Contiene todos los nodos del grafo aéreo.
BBOX_MAIPU = (-70.93, -33.57, -70.71, -33.46)
RADIO_HEX_M = 1000  # distancia del centro a cada vértice
LOTE = 50  # coordenadas por solicitud a Open-Meteo (cada una cuenta como una llamada)
M_POR_GRADO_LAT = 111_320.0


def grilla_hexagonos(bbox=BBOX_MAIPU, radio_m=RADIO_HEX_M):
    """Hexágonos de vértice superior (pointy-top) que cubren el bbox.

    Proyección equirectangular local: a esta escala (~20 km) el error es despreciable.
    El `hex_id` depende solo de fila/columna, así que es estable mientras no cambien el bbox
    ni el radio.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    lat0 = (min_lat + max_lat) / 2
    m_por_grado_lon = M_POR_GRADO_LAT * math.cos(math.radians(lat0))
    dx = math.sqrt(3) * radio_m  # separación entre centros de una fila
    dy = 1.5 * radio_m  # separación entre filas
    ancho = (max_lon - min_lon) * m_por_grado_lon
    alto = (max_lat - min_lat) * M_POR_GRADO_LAT

    hexagonos = []
    for fila in range(int(alto / dy) + 2):
        y = fila * dy
        desfase = dx / 2 if fila % 2 else 0.0
        for col in range(int(ancho / dx) + 2):
            x = col * dx + desfase
            clon = min_lon + x / m_por_grado_lon
            clat = min_lat + y / M_POR_GRADO_LAT
            anillo = []
            for k in range(6):
                ang = math.radians(60 * k + 30)
                anillo.append(
                    [
                        round(clon + radio_m * math.cos(ang) / m_por_grado_lon, 6),
                        round(clat + radio_m * math.sin(ang) / M_POR_GRADO_LAT, 6),
                    ]
                )
            anillo.append(anillo[0])
            hexagonos.append(
                {
                    "hex_id": f"hex_clima_{fila:02d}_{col:02d}",
                    "centro": (round(clon, 6), round(clat, 6)),
                    "anillo": anillo,
                }
            )
    return hexagonos


def consultar_horario(centros, variables, horas):
    """Pronóstico horario de `variables` para cada centro, desde la hora actual.

    Devuelve una respuesta de Open-Meteo por centro, en el mismo orden.
    """
    respuestas = []
    for i in range(0, len(centros), LOTE):
        lote = centros[i : i + LOTE]
        r = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": ",".join(str(lat) for _, lat in lote),
                "longitude": ",".join(str(lon) for lon, _ in lote),
                "hourly": ",".join(variables),
                "forecast_hours": horas,  # parte en la hora actual
                "timezone": "America/Santiago",
            },
            timeout=60,
        )
        r.raise_for_status()
        datos = r.json()
        datos = datos if isinstance(datos, list) else [datos]  # 1 coordenada => objeto
        if len(datos) != len(lote):
            raise RuntimeError(f"Open-Meteo devolvió {len(datos)} resultados para {len(lote)} puntos")
        respuestas.extend(datos)
    return respuestas


def serie(respuesta, variable):
    """Valores no nulos de una variable horaria."""
    return [v for v in (respuesta.get("hourly") or {}).get(variable, []) if v is not None]


def parsear_simulacion(texto, nombre_variable):
    """Lee "lon,lat,radio_m" desde una variable de entorno; None si está vacía."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        lon, lat, radio = (float(v) for v in texto.split(","))
    except ValueError:
        raise SystemExit(f'{nombre_variable} debe ser "lon,lat,radio_m", no {texto!r}')
    return {"lon": lon, "lat": lat, "radio_m": radio}


def dentro_de_simulacion(centro, simulacion):
    if not simulacion:
        return False
    lon1, lat1 = centro
    dlat = (simulacion["lat"] - lat1) * M_POR_GRADO_LAT
    dlon = (simulacion["lon"] - lon1) * M_POR_GRADO_LAT * math.cos(math.radians((lat1 + simulacion["lat"]) / 2))
    return math.hypot(dlat, dlon) <= simulacion["radio_m"]


def celdas_distintas(features):
    return len(
        {(f["properties"]["celda_modelo_lon"], f["properties"]["celda_modelo_lat"]) for f in features}
    )
