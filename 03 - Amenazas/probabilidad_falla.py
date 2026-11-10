"""Probabilidad de falla del dron por amenaza, para cada zona, enlace y nodo (punto 5).

Cada amenaza se convierte en un conjunto de *zonas* (polígonos) con una probabilidad de falla
p ∈ [0, 1]: la probabilidad de que el dron no complete la misión si cruza esa zona.

  lluvia   celdas Open-Meteo      i = min(1, precip_max / umbral_mm_h)
                                  q = prob_lluvia_max / 100
                                  p = 1 - (1 - i)(1 - peso_probabilidad · q)
           Lluvia sobre el umbral => falla segura (p = 1). La sola probabilidad de lluvia aporta
           a lo más `peso_probabilidad` (pronóstico incierto).

  viento   celdas Open-Meteo      r = max(viento_max / umbral_kmh, rafaga_max / umbral_rafaga_kmh)
                                  p = clamp((r - inicio_riesgo) / (1 - inicio_riesgo), 0, 1)
           Rampa lineal: p = 0 bajo `inicio_riesgo` del umbral, p = 1 desde el umbral.

  robo_7d  hexágonos STOP 7 días  p = p_max · nivel / niveles_total
           Riesgo de ataque o de inhibidores de señal (usados en encerronas) sobre focos
           recientes de robo con violencia.

Lluvia y viento: los hexágonos que caen en la misma celda del modelo meteorológico reciben el
mismo pronóstico; se agrupan en una sola zona porque son un único evento (no independientes).

Enlaces y nodos heredan la probabilidad de las zonas que tocan, suponiendo zonas independientes:

    p_k(elemento) = 1 - Π_{zonas z de la amenaza k que toca} (1 - p_z)
    p(elemento)   = 1 - Π_k (1 - p_k(elemento))

La API de ruteo (05 - API) importa este módulo para recalcular las probabilidades con los
parámetros que el usuario elige en la web. Ejecutado como script, calcula todo con los
parámetros por defecto y lo guarda en las tablas probabilidad_falla_* y en
OUT_DIR/probabilidad_falla_zonas.geojson y OUT_DIR/probabilidad_falla_grafo.geojson.
"""
import copy
import json
import math

AMENAZAS = ("lluvia", "viento", "robo_7d")

PARAMS_DEFECTO = {
    "lluvia": {"umbral_mm_h": 0.5, "peso_probabilidad": 0.25},
    "viento": {"umbral_kmh": 36.0, "umbral_rafaga_kmh": 43.0, "inicio_riesgo": 0.7},
    "robo_7d": {"p_max": 0.3},
}

P_MAX = 0.999  # tope para no tener log(0) en los modelos que usan -ln(1 - p)


def mezclar_parametros(params=None):
    """PARAMS_DEFECTO actualizados con los valores que vengan en `params` (por amenaza)."""
    salida = copy.deepcopy(PARAMS_DEFECTO)
    for amenaza, valores in (params or {}).items():
        if amenaza in salida and isinstance(valores, dict):
            salida[amenaza].update({k: float(v) for k, v in valores.items() if v is not None})
    return salida


def _clamp(x):
    return max(0.0, min(1.0, x))


def p_lluvia(precip_max_mm_h, prob_max_pct, prm):
    i = _clamp((precip_max_mm_h or 0.0) / prm["umbral_mm_h"]) if prm["umbral_mm_h"] > 0 else 0.0
    q = _clamp((prob_max_pct or 0.0) / 100.0)
    return 1.0 - (1.0 - i) * (1.0 - prm["peso_probabilidad"] * q)


def p_viento(viento_max_kmh, rafaga_max_kmh, prm):
    r = max((viento_max_kmh or 0.0) / prm["umbral_kmh"], (rafaga_max_kmh or 0.0) / prm["umbral_rafaga_kmh"])
    inicio = prm["inicio_riesgo"]
    return _clamp((r - inicio) / (1.0 - inicio)) if inicio < 1 else float(r >= 1)


def p_robo(nivel, niveles_total, prm):
    return _clamp(prm["p_max"] * (nivel or 0) / (niveles_total or 1))


def combinar(probabilidades):
    """1 - Π(1 - p): probabilidad de que falle al menos una de las zonas independientes."""
    sobrevive = 1.0
    for p in probabilidades:
        sobrevive *= 1.0 - p
    return 1.0 - sobrevive


def riesgo_aditivo(p):
    """-ln(1 - p): con esto, la supervivencia de una ruta es exp(-Σ riesgo) y se puede sumar."""
    return -math.log(1.0 - min(p, P_MAX))


# Consultas por amenaza. %(bbox)s es un polígono WKT para filtrar el área de ruteo.
_FILTRO = "ST_Intersects(geom, ST_GeomFromText(%(bbox)s, 4326))"
SQL_ZONAS = {
    # Lluvia y viento: los hexágonos de una misma celda del modelo meteorológico (~9-13 km)
    # reciben exactamente el mismo pronóstico, así que no son eventos independientes: se agrupan
    # en una sola zona por celda (y por valores, para separar la lluvia/viento simulados).
    "lluvia": f"""
        SELECT 'celda_' || celda_modelo_lon || '_' || celda_modelo_lat
                   || CASE WHEN simulado THEN '_sim' ELSE '' END
                   || '_' || min(hex_id) AS origen_id,
               precipitacion_max_mm_h, probabilidad_max_pct, simulado, count(*) AS hexagonos,
               ST_AsGeoJSON(ST_Union(geom), 6) AS geojson
        FROM lluvia_open_meteo_hexagonos WHERE {_FILTRO}
        GROUP BY celda_modelo_lon, celda_modelo_lat, precipitacion_max_mm_h, probabilidad_max_pct, simulado""",
    "viento": f"""
        SELECT 'celda_' || celda_modelo_lon || '_' || celda_modelo_lat
                   || CASE WHEN simulado THEN '_sim' ELSE '' END
                   || '_' || min(hex_id) AS origen_id,
               viento_max_kmh, rafaga_max_kmh, simulado, count(*) AS hexagonos,
               ST_AsGeoJSON(ST_Union(geom), 6) AS geojson
        FROM viento_open_meteo_hexagonos WHERE {_FILTRO}
        GROUP BY celda_modelo_lon, celda_modelo_lat, viento_max_kmh, rafaga_max_kmh, simulado""",
    "robo_7d": f"""
        SELECT hex_id AS origen_id, cantidad, nivel, niveles_total, periodo_desde, periodo_hasta,
               ST_AsGeoJSON(geom, 6) AS geojson
        FROM robo_con_violencia_semanal_hexagonos WHERE {_FILTRO}""",
}


def _probabilidad_y_detalle(amenaza, f, prm):
    if amenaza == "lluvia":
        p = p_lluvia(f["precipitacion_max_mm_h"], f["probabilidad_max_pct"], prm)
        det = (f"Precipitación máx. {f['precipitacion_max_mm_h']} mm/h, "
               f"probabilidad máx. {f['probabilidad_max_pct']}% ({f['hexagonos']} hexágonos de la misma celda del modelo)"
               + (" (simulada)" if f["simulado"] else ""))
    elif amenaza == "viento":
        p = p_viento(f["viento_max_kmh"], f["rafaga_max_kmh"], prm)
        det = (f"Viento máx. {f['viento_max_kmh']} km/h (80-120 m), ráfaga máx. {f['rafaga_max_kmh']} km/h "
               f"({f['hexagonos']} hexágonos de la misma celda del modelo)" + (" (simulado)" if f["simulado"] else ""))
    else:
        p = p_robo(f["nivel"], f["niveles_total"], prm)
        det = (f"{f['cantidad']} robos con violencia en 7 días (nivel {f['nivel']}/{f['niveles_total']}, "
               f"{f['periodo_desde']} a {f['periodo_hasta']})")
    return p, det


def zonas(con, amenazas=AMENAZAS, params=None, bbox_wkt=None):
    """Zonas de amenaza con su p de falla, leídas desde la BD (con conexión psycopg `con`).

    Devuelve dicts {zona_id, amenaza, origen_id, p, detalle, geometry} (geometry en GeoJSON).
    Las zonas con p = 0 se omiten: no cambian ni el costo ni la resiliencia.
    """
    prm = mezclar_parametros(params)
    bbox_wkt = bbox_wkt or "POLYGON((-71.2 -33.9,-70.4 -33.9,-70.4 -33.2,-71.2 -33.2,-71.2 -33.9))"
    salida = []
    for amenaza in amenazas:
        if amenaza not in SQL_ZONAS:
            continue
        cur = con.execute(SQL_ZONAS[amenaza], {"bbox": bbox_wkt})
        nombres = [d.name for d in cur.description]
        for fila in cur.fetchall():
            f = dict(zip(nombres, fila))
            p, detalle = _probabilidad_y_detalle(amenaza, f, prm[amenaza])
            if p <= 0:
                continue
            salida.append({
                "zona_id": f"{amenaza}:{f['origen_id']}",
                "amenaza": amenaza,
                "origen_id": str(f["origen_id"]),
                "p": round(p, 4),
                "detalle": detalle,
                "geometry": json.loads(f["geojson"]),
            })
    return salida


# --------------------------------------------------------------------------------------------
# Ejecución como script: tablas probabilidad_falla_* y GeoJSON con los parámetros por defecto
# --------------------------------------------------------------------------------------------

SQL_ELEMENTOS = """
WITH z AS (SELECT amenaza, p_falla, geom FROM probabilidad_falla_zonas),
por_amenaza AS (
    SELECT e.id, z.amenaza, 1 - exp(sum(ln(1 - least(z.p_falla, 0.999)))) AS p, count(*) AS n
    FROM {tabla} e JOIN z ON ST_Intersects(e.geom, z.geom)
    GROUP BY e.id, z.amenaza
)
SELECT id, amenaza, p, n FROM por_amenaza
UNION ALL
SELECT id, 'total', 1 - exp(sum(ln(1 - least(p, 0.999)))), sum(n) FROM por_amenaza GROUP BY id
"""


def main():
    from db import OUT_DIR, conectar  # solo al correr como script (contenedor amenazas)

    with conectar() as con:
        lista = zonas(con)
        con.execute("DELETE FROM probabilidad_falla_zonas")
        con.cursor().executemany(
            """INSERT INTO probabilidad_falla_zonas (zona_id, amenaza, origen_id, p_falla, detalle, geom)
               VALUES (%(zona_id)s, %(amenaza)s, %(origen_id)s, %(p)s, %(detalle)s,
                       ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)))""",
            [{**z, "geom": json.dumps(z["geometry"])} for z in lista],
        )
        for tabla, destino, col in (("aristas_aereas", "probabilidad_falla_aristas", "arista_id"),
                                    ("nodos_aereos", "probabilidad_falla_nodos", "nodo_id")):
            con.execute(f"DELETE FROM {destino}")
            filas = con.execute(SQL_ELEMENTOS.format(tabla=tabla)).fetchall()
            con.cursor().executemany(
                f"INSERT INTO {destino} ({col}, amenaza, p_falla, zonas) VALUES (%s, %s, %s, %s)", filas
            )
        grafo = con.execute("""
            SELECT 'arista' AS elemento, a.id, a.source, a.target, round(a.cost::numeric, 1) AS largo_m,
                   ST_AsGeoJSON(a.geom, 6),
                   coalesce((SELECT json_object_agg(amenaza, round(p_falla::numeric, 4))
                             FROM probabilidad_falla_aristas WHERE arista_id = a.id), '{}')
            FROM aristas_aereas a
            UNION ALL
            SELECT 'nodo', n.id, NULL, NULL, NULL, ST_AsGeoJSON(n.geom, 6),
                   coalesce((SELECT json_object_agg(amenaza, round(p_falla::numeric, 4))
                             FROM probabilidad_falla_nodos WHERE nodo_id = n.id), '{}')
            FROM nodos_aereos n ORDER BY 1, 2""").fetchall()

    def coleccion(features, descripcion):
        return {"type": "FeatureCollection",
                "metadata": {"descripcion": descripcion, "parametros": PARAMS_DEFECTO, "crs": "EPSG:4326"},
                "features": features}

    zonas_fc = coleccion([
        {"type": "Feature", "geometry": z["geometry"],
         "properties": {k: z[k] for k in ("zona_id", "amenaza", "origen_id", "p", "detalle")}}
        for z in lista
    ], "Zonas de amenaza con su probabilidad de falla para el dron")
    grafo_fc = coleccion([
        {"type": "Feature", "geometry": json.loads(geo),
         "properties": {"elemento": elem, "id": i, "source": s, "target": t,
                        "largo_m": float(l) if l is not None else None,
                        "p_falla": {k: float(v) for k, v in (ps or {}).items()}}}
        for elem, i, s, t, l, geo, ps in grafo
    ], "Probabilidad de falla por amenaza ('total' = combinada) de cada arista y nodo del grafo aéreo base")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "probabilidad_falla_zonas.geojson").write_text(json.dumps(zonas_fc, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "probabilidad_falla_grafo.geojson").write_text(json.dumps(grafo_fc, ensure_ascii=False, indent=1), encoding="utf-8")
    por_amenaza = {a: sum(1 for z in lista if z["amenaza"] == a) for a in AMENAZAS}
    print(f"{len(lista)} zonas con p > 0 {por_amenaza} -> probabilidad_falla_zonas")
    print(f"{sum(1 for g in grafo if g[0] == 'arista')} aristas y {sum(1 for g in grafo if g[0] == 'nodo')} nodos "
          "-> probabilidad_falla_aristas / probabilidad_falla_nodos")


if __name__ == "__main__":
    main()
