"""Acceso a PostGIS: nodos, obstáculos estáticos, metadatos y capas para la web."""
import json
import os
import threading
import time

import numpy as np
import psycopg
import shapely
from shapely.geometry import box, shape

import probabilidad_falla as pf
from grafo import a_metros, geom_a_metros

METADATOS = ("stop_90d", "oscuridad", "trafico", "formas")
MARGEN_AREA_M = 3500.0  # el área de ruteo es el rectángulo de los nodos más este margen


def conectar():
    return psycopg.connect(
        host=os.environ.get("PGHOST", "db"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "ruteo"),
        user=os.environ.get("PGUSER", "ruteo"),
        password=os.environ.get("PGPASSWORD", "ruteo"),
        autocommit=True,
    )


class _Cache:
    def __init__(self):
        self._datos, self._lock = {}, threading.Lock()

    def obtener(self, clave, ttl, fabrica):
        with self._lock:
            hit = self._datos.get(clave)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        valor = fabrica()
        with self._lock:
            self._datos[clave] = (time.time(), valor)
        return valor

    def limpiar(self):
        with self._lock:
            self._datos.clear()


cache = _Cache()


# ------------------------------------------------------------------ nodos y área de ruteo

def nodos():
    def cargar():
        with conectar() as con:
            filas = con.execute("""
                SELECT n.id, n.tipo, n.nombre, n.descripcion, ST_X(n.geom), ST_Y(n.geom)
                FROM nodos_aereos n ORDER BY n.id""").fetchall()
        return [
            {"id": i, "tipo": t, "nombre": nom, "descripcion": d, "lon": lon, "lat": lat,
             "xy": a_metros(lon, lat)}
            for i, t, nom, d, lon, lat in filas
        ]
    return cache.obtener("nodos", 600, cargar)


def area_ruteo():
    """Rectángulo (en metros y en WKT lon/lat) que contiene todos los nodos más un margen."""
    xs = [n["xy"][0] for n in nodos()]
    ys = [n["xy"][1] for n in nodos()]
    area = box(min(xs) - MARGEN_AREA_M, min(ys) - MARGEN_AREA_M, max(xs) + MARGEN_AREA_M, max(ys) + MARGEN_AREA_M)
    from grafo import geom_a_grados
    return area, geom_a_grados(area).wkt


# ------------------------------------------------------------------ grilla de metadatos

def grilla_metadatos():
    """Valor de vigilancia de cada hexágono de 500 m, por metadato.

    stop_90d   nivel/niveles_total del hexágono STOP de 90 días
    oscuridad  1 - min(1, luminarias / P75): menos luminarias => más oscuro => más delito.
               Solo dentro de la zona relevada por Mapillary (fuera de ella vale 0: sin dato)
    trafico    factor_riesgo_trafico máximo de los tramos TomTom que lo cruzan (velocidad baja)
    formas     factor_riesgo_geom máximo de las vías Overpass (curvas, enlaces), normalizado
    """
    def cargar():
        _, wkt = area_ruteo()
        with conectar() as con:
            filas = con.execute("""
                WITH t AS (SELECT hex_id, nivel, niveles_total, geom FROM robo_con_violencia_hexagonos
                           WHERE ST_Intersects(geom, ST_GeomFromText(%s, 4326))),
                cobertura AS (SELECT ST_ConvexHull(ST_Collect(geom)) AS g FROM luminarias_mapillary)
                SELECT t.hex_id, ST_AsGeoJSON(t.geom, 6),
                  coalesce(t.nivel::float / nullif(t.niveles_total, 0), 0),
                  (SELECT count(*) FROM luminarias_mapillary l WHERE ST_Intersects(l.geom, t.geom)),
                  ST_Within(ST_Centroid(t.geom), (SELECT g FROM cobertura)),
                  coalesce((SELECT max(r.factor_riesgo_trafico) FROM tomtom_trafico r
                            WHERE ST_Intersects(r.geom, t.geom)), 0),
                  coalesce((SELECT max(o.factor_riesgo_geom) FROM overpass_formas_viales o
                            WHERE ST_Intersects(o.geom, t.geom)), 0)
                FROM t""", (wkt,)).fetchall()
        conteos = [f[3] for f in filas if f[4] and f[3] > 0]
        ref = float(np.percentile(conteos, 75)) if conteos else 1.0
        max_formas = max((f[6] for f in filas), default=1.0) or 1.0
        hexes = []
        for hex_id, g, stop, lum, cubierto, traf, formas in filas:
            gj = json.loads(g)
            hexes.append({
                "hex_id": hex_id, "geojson": gj, "geom": geom_a_metros(shape(gj)),
                "valores": {
                    "stop_90d": round(float(stop), 3),
                    "oscuridad": round(1 - min(1.0, lum / ref), 3) if cubierto else 0.0,
                    "trafico": round(float(traf), 3),
                    "formas": round(float(formas) / max_formas, 3),
                },
                "luminarias": lum,
            })
        return hexes
    return cache.obtener("grilla_metadatos", 900, cargar)


def evaluador_metadatos(activos, pesos=None):
    """Función (array de LineString en m) -> array con el valor de vigilancia en [0, 1].

    Valor de un hexágono = promedio ponderado de sus metadatos activos; el de una arista es el
    promedio de los hexágonos que cruza, ponderado por el largo dentro de cada uno.
    """
    activos = [m for m in activos if m in METADATOS]
    if not activos:
        return lambda lineas: np.zeros(len(lineas))
    pesos = {m: float((pesos or {}).get(m, 1.0)) for m in activos}
    total = sum(pesos.values()) or 1.0
    hexes = grilla_metadatos()
    geoms = np.array([h["geom"] for h in hexes], dtype=object)
    valor = np.array([sum(pesos[m] * h["valores"][m] for m in activos) / total for h in hexes])
    arbol = shapely.STRtree(geoms)

    def evaluar(lineas):
        lineas = np.asarray(lineas, dtype=object)
        li, hi = arbol.query(lineas, predicate="intersects")
        largos = shapely.length(shapely.intersection(lineas[li], geoms[hi]))
        suma = np.bincount(li, weights=largos * valor[hi], minlength=len(lineas))
        total_l = shapely.length(lineas)
        return np.divide(suma, total_l, out=np.zeros(len(lineas)), where=total_l > 0)
    return evaluar


# ------------------------------------------------------------------ zonas de amenaza

def zonas_amenaza(amenazas, params):
    """Zonas de amenaza activas con su p de falla (03 - Amenazas/probabilidad_falla.py)."""
    clave = ("zonas", tuple(sorted(amenazas)), json.dumps(params or {}, sort_keys=True))

    def cargar():
        _, wkt = area_ruteo()
        with conectar() as con:
            return pf.zonas(con, amenazas, params, wkt)
    return cache.obtener(clave, 60, cargar)


# ------------------------------------------------------------------ capas para la web

def _fc(sql, args=()):
    with conectar() as con:
        fila = con.execute(f"""
            SELECT json_build_object('type', 'FeatureCollection',
                   'features', coalesce(json_agg(ST_AsGeoJSON(t.*, 'geom', 6)::json), '[]'::json))
            FROM ({sql}) t""", args).fetchone()
    return fila[0]


def capa(nombre):
    _, wkt = area_ruteo()
    f = "ST_Intersects(geom, ST_GeomFromText(%s, 4326))"
    consultas = {
        "nodos": ("SELECT id, tipo, nombre, descripcion, geom FROM nodos_aereos", ()),
        "lluvia": (f"""SELECT hex_id, precipitacion_actual_mm_h, precipitacion_max_mm_h, probabilidad_max_pct,
                          hora_desde, hora_hasta, no_volable, motivo, simulado, geom
                      FROM lluvia_open_meteo_hexagonos WHERE {f}""", (wkt,)),
        "viento": (f"""SELECT hex_id, viento_actual_kmh, viento_max_kmh, rafaga_max_kmh, direccion_grados,
                          hora_desde, hora_hasta, no_volable, motivo, simulado, geom
                      FROM viento_open_meteo_hexagonos WHERE {f}""", (wkt,)),
        "stop_90d": (f"""SELECT hex_id, cantidad, nivel, niveles_total, rango, color, periodo_desde, periodo_hasta, geom
                        FROM robo_con_violencia_hexagonos WHERE {f}""", (wkt,)),
        "luminarias": (f"""SELECT mapillary_id, object_value, detections_count, factor_iluminacion, geom
                          FROM luminarias_mapillary WHERE {f}""", (wkt,)),
        "trafico": (f"""SELECT corredor_vial, velocidad_actual_kmh, velocidad_flujo_libre_kmh, indice_congestion,
                           nivel_riesgo_trafico, factor_riesgo_trafico, cierre_vial, geom
                       FROM tomtom_trafico WHERE {f}""", (wkt,)),
        "formas": (f"""SELECT nombre, ref_via, highway, forma_vial, es_enlace_salida, es_curva_pronunciada,
                          indice_sinuosidad, factor_riesgo_geom, geom
                      FROM overpass_formas_viales WHERE {f}""", (wkt,)),
    }
    if nombre == "metadatos_grilla":
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": h["geojson"],
             "properties": {"hex_id": h["hex_id"], "luminarias": h["luminarias"], **h["valores"]}}
            for h in grilla_metadatos()]}
    if nombre not in consultas:
        return None
    sql, args = consultas[nombre]
    return cache.obtener(("capa", nombre), 120, lambda: _fc(sql, args))
