"""Orquestación de una consulta: obstáculos, grafos, 4 técnicas, resiliencia y simulación de fallas.

Métrica de resiliencia (punto 8)
  R(ruta) = Π_{z ∈ Z(ruta)} (1 - p_z)
  donde Z(ruta) son las zonas de amenaza (independientes) que toca la ruta en cualquier tramo o
  nodo. Es la probabilidad de completar la misión sin que ocurra ninguna falla. Se valida con
  Monte Carlo: en cada simulación se sortea r_z ~ U[0, 100) por zona y la zona falla si
  r_z < 100·p_z (el mismo mecanismo del punto 7); R_mc es la fracción de simulaciones en que la
  ruta no toca ninguna zona fallada. Todas las rutas usan los mismos sorteos (comparación justa).
"""
import math
import random
import time

import numpy as np
from shapely.geometry import LineString, Point

import datos
import grafo as gr
import tecnicas as tc


def _zonas(cfg, fallas):
    """Zonas de amenaza activas (BD + simuladas) como objetos Zona en metros."""
    zonas = []
    for z in datos.zonas_amenaza(cfg["amenazas"], cfg.get("params_amenazas") or {}):
        zonas.append(gr.Zona(z["zona_id"], z["amenaza"], z["p"], z["detalle"], gr.geojson_a_metros(z["geometry"])))
    for i, s in enumerate(cfg.get("amenazas_simuladas") or [], start=1):
        x, y = gr.a_metros(s["lon"], s["lat"])
        zonas.append(gr.Zona(f"simulada:{i}", "simulada", float(s.get("p", 1.0)),
                             f"Amenaza simulada ({s.get('tipo', 'lluvia')}), radio {s.get('radio_m', 1000)} m",
                             Point(x, y).buffer(float(s.get("radio_m", 1000)), quad_segs=8), simulada=True))
    for z in zonas:
        if z.zona_id in fallas:
            z.p, z.detalle = 1.0, z.detalle + " — FALLA OCURRIDA (sorteo)"
    return zonas


def resolver(cfg, fallas=frozenset()):
    t0 = time.perf_counter()
    nodos = {n["id"]: n for n in datos.nodos()}
    if cfg["origen"] not in nodos:
        raise ValueError(f"Origen {cfg['origen']} no existe")
    cfg["destinos"] = [d for d in cfg["destinos"] if d in nodos and d != cfg["origen"]]
    if cfg["modo"] == "punto":
        cfg["destinos"] = cfg["destinos"][:1]
    if not cfg["destinos"]:
        raise ValueError("Debe elegir al menos un destino distinto del origen")

    area, _ = datos.area_ruteo()
    zonas = _zonas(cfg, fallas)
    probabilistico = cfg["modelo"] == "probabilistico"
    umbral = cfg["umbral_falla"]

    def es_dura(z):
        return z.zona_id in fallas or (probabilistico and z.p >= umbral)
    duras = [z for z in zonas if es_dura(z)]
    blandas = [z.geom for z in zonas if not es_dura(z) and z.p >= cfg["umbral_blando"]]
    falladas = [z.geom for z in zonas if z.zona_id in fallas]

    mision = {i: nodos[i]["xy"] for i in [cfg["origen"], *cfg["destinos"]]}
    evaluador = datos.evaluador_metadatos(cfg["metadatos"], cfg.get("pesos_metadatos"))
    pesos_amenaza = {k: float(v) for k, v in (cfg.get("pesos_amenazas") or {}).items()}

    # Grafo A (técnica 1): solo obstáculos por fallas ya ocurridas
    t1 = time.perf_counter()
    grafo_a = gr.construir(mision, falladas, zonas, [], area, evaluador, pesos_amenaza)
    # Grafo B (técnicas 2-4): además, zonas duras como obstáculo y waypoints de zonas blandas
    grafo_b = gr.construir(mision, [z.geom for z in duras], zonas, blandas, area, evaluador, pesos_amenaza)
    t_grafos = (time.perf_counter() - t1) * 1000

    resultados = []
    with datos.conectar() as con:
        for tec in cfg["tecnicas"]:
            g = grafo_a if tec == "dijkstra_distancia" else grafo_b
            res = tc.ejecutar(tec, con, g, cfg)
            resultados.append(_evaluar(tec, res, g, zonas, cfg, es_dura))

    _resiliencia_mc(resultados, zonas, cfg)
    factibles = [r for r in resultados if r["factible"]]
    mejor = min(factibles, key=lambda r: r["costo"])["tecnica"] if factibles else None
    con_ruta = [r for r in resultados if r["ok"]]
    mas_res = max(con_ruta, key=lambda r: (r["resiliencia"], -r["distancia_m"]))["tecnica"] if con_ruta else None
    for r in resultados:
        r["mejor"], r["mas_resiliente"] = r["tecnica"] == mejor, r["tecnica"] == mas_res

    return {
        "rutas": resultados,
        "mejor": mejor,
        "mas_resiliente": mas_res,
        "nodos": [{k: v for k, v in n.items() if k != "xy"} | {"alcanzable": n["id"] in grafo_b.nodos or n["id"] not in mision}
                  for n in nodos.values()],
        "inalcanzables": sorted(set(grafo_b.inalcanzables)),
        "zonas": {"type": "FeatureCollection", "features": [
            gr.feature(z.geom, zona_id=z.zona_id, amenaza=z.amenaza, p=round(z.p, 4), detalle=z.detalle,
                       dura=es_dura(z), fallada=z.zona_id in fallas) for z in zonas]},
        "obstaculos": {"type": "FeatureCollection", "features": [
            gr.feature(p, tipo="obstaculo_total") for p in gr._poligonos(grafo_b.obstaculo)]},
        "grafo": _grafo_geojson(grafo_b) if cfg.get("incluir_grafo", True) else None,
        "estadisticas": {
            "zonas_activas": len(zonas), "zonas_duras": len(duras), "zonas_blandas": len(blandas),
            "nodos_grafo_a": len(grafo_a.nodos), "aristas_grafo_a": len(grafo_a.aristas),
            "nodos_grafo_b": len(grafo_b.nodos), "aristas_grafo_b": len(grafo_b.aristas),
            "grafo_podado": grafo_b.podado, "tiempo_grafos_ms": round(t_grafos, 1),
            "tiempo_total_ms": round((time.perf_counter() - t0) * 1000, 1),
        },
        "_zonas": zonas,  # uso interno (simulación); se quita antes de responder
    }


def _evaluar(tec, res, g, zonas, cfg, es_dura):
    base = {"tecnica": tec, **tc.TECNICAS[tec], "tiempo_computo_ms": res["tiempo_computo_ms"],
            "detalle": res.get("detalle"), "error": res.get("error"), "omitidos": res.get("omitidos", [])}
    sec = res.get("secuencia")
    if not sec:
        return {**base, "ok": False, "factible": False, "motivos": [res.get("error") or "sin ruta"],
                "resiliencia": 0.0, "distancia_m": math.inf, "costo": math.inf}
    arista = {}
    for a in g.aristas:
        arista[(a["u"], a["v"])] = arista[(a["v"], a["u"])] = a
    tramos = [arista[(u, v)] for u, v in zip(sec, sec[1:]) if u != v]
    dist = sum(a["largo"] for a in tramos)
    idx_zonas = sorted({z for a in tramos for z in a["zonas"]})
    if len(sec) == 1:  # sin tramos: solo el nodo de origen
        idx_zonas = [i for i, z in enumerate(zonas) if z.geom.contains(Point(g.nodos[sec[0]]))]
    R = math.prod(1 - zonas[i].p for i in idx_zonas)
    riesgo = -math.log(max(R, 1e-12))
    costo = tc.objetivo(tramos, idx_zonas, zonas, cfg)
    metadato = (sum(a["metadato"] * a["largo"] for a in tramos) / dist) if dist else 0.0
    motivos = []
    if dist > cfg["bateria_km"] * 1000 + 1e-6:
        motivos.append(f"Excede la autonomía: {dist / 1000:.2f} km > {cfg['bateria_km']} km")
    if 1 - R > cfg["riesgo_max"] + 1e-9:
        motivos.append(f"Riesgo de falla {100 * (1 - R):.1f}% > máximo {100 * cfg['riesgo_max']:.0f}%")
    duras = [zonas[i].zona_id for i in idx_zonas if es_dura(zonas[i])]
    if duras:
        motivos.append(f"Cruza {len(duras)} zona(s) bloqueada(s): {', '.join(duras[:4])}")
    if res.get("omitidos"):
        motivos.append(f"Destinos inalcanzables (dentro de un obstáculo): {res['omitidos']}")
    coords = [gr.a_grados(*g.nodos[v]) for v in sec]
    return {
        **base, "ok": True,
        "factible": not [m for m in motivos if not m.startswith("Destinos inalcanzables")],
        "motivos": motivos,
        "secuencia_nodos": [v if v < 1000 else None for v in sec],
        "orden_visita": res.get("orden", []),
        "geometria": {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]},
                      "properties": {"tecnica": tec}},
        "distancia_m": round(dist, 1),
        "tiempo_vuelo_min": round(dist / 1000 / cfg["velocidad_kmh"] * 60, 1),
        "costo": round(costo, 1),
        "riesgo_aditivo": round(riesgo, 4),
        "resiliencia": round(R, 4),
        "vigilancia_media": round(metadato, 3),
        "zonas_cruzadas": [{"zona_id": zonas[i].zona_id, "amenaza": zonas[i].amenaza, "p": zonas[i].p} for i in idx_zonas],
        "_idx_zonas": idx_zonas,
        "waypoints": sum(1 for v in sec if v >= 1000),
    }


def _resiliencia_mc(resultados, zonas, cfg):
    n = int(cfg.get("simulaciones_mc", 2000))
    if not zonas or n <= 0:
        for r in resultados:
            r["resiliencia_mc"] = r["resiliencia"] if r["ok"] else 0.0
        return
    rng = np.random.default_rng(cfg.get("semilla", 42))
    sorteos = rng.uniform(0, 100, size=(n, len(zonas)))
    umbral = np.array([100 * z.p for z in zonas])
    falla = sorteos < umbral
    for r in resultados:
        if not r["ok"]:
            r["resiliencia_mc"] = 0.0
            continue
        idx = r["_idx_zonas"]
        sobrevive = ~falla[:, idx].any(axis=1) if idx else np.ones(n, dtype=bool)
        r["resiliencia_mc"] = round(float(sobrevive.mean()), 4)
        r["simulaciones_mc"] = n


def _grafo_geojson(g):
    feats = [gr.feature(LineString([g.nodos[a["u"]], g.nodos[a["v"]]]), u=a["u"], v=a["v"],
                        largo_m=round(a["largo"], 1), p=round(1 - math.exp(-a["riesgo"]), 4),
                        vigilancia=round(a["metadato"], 3))
             for a in g.aristas]
    wps = [gr.feature(Point(xy), id=i, tipo=g.tipo_nodo[i]) for i, xy in g.nodos.items() if i >= 1000]
    return {"aristas": {"type": "FeatureCollection", "features": feats},
            "waypoints": {"type": "FeatureCollection", "features": wps}}


def limpiar(res):
    res.pop("_zonas", None)
    for r in res["rutas"]:
        r.pop("_idx_zonas", None)
        for k in ("distancia_m", "costo"):
            if isinstance(r.get(k), float) and math.isinf(r[k]):
                r[k] = None
    return res


def simular(cfg):
    """Punto 7: sorteo 0-100 por zona de amenaza; falla si el número es menor que 100·p.

    Devuelve las rutas antes del sorteo, qué zonas/nodos/tramos fallaron, si cada ruta
    sobrevivió, y las 4 rutas recalculadas tratando las zonas falladas como bloqueos.
    """
    antes = resolver(dict(cfg))
    zonas = antes["_zonas"]
    rng = random.Random(cfg.get("semilla", 42))
    sorteos = []
    for z in zonas:
        r = round(rng.uniform(0, 100), 2)
        sorteos.append({"zona_id": z.zona_id, "amenaza": z.amenaza, "p": z.p, "umbral": round(100 * z.p, 2),
                        "numero": r, "falla": r < 100 * z.p, "detalle": z.detalle})
    fallidas = {s["zona_id"] for s in sorteos if s["falla"]}
    nodos = {n["id"]: n for n in datos.nodos()}
    nodos_fallados = sorted(i for i, n in nodos.items()
                            if any(z.zona_id in fallidas and z.geom.contains(Point(n["xy"])) for z in zonas))
    impacto = []
    for r in antes["rutas"]:
        if not r["ok"]:
            impacto.append({"tecnica": r["tecnica"], "sobrevive": False, "motivo": "sin ruta"})
            continue
        tocadas = [zonas[i].zona_id for i in r["_idx_zonas"] if zonas[i].zona_id in fallidas]
        impacto.append({
            "tecnica": r["tecnica"], "sobrevive": not tocadas, "zonas_falladas": tocadas,
            "nodos_fallados": sorted({v for v in (r["secuencia_nodos"] or []) if v in nodos_fallados}),
        })
    despues = resolver(dict(cfg), fallas=frozenset(fallidas))
    return {
        "semilla": cfg.get("semilla", 42),
        "sorteos": sorted(sorteos, key=lambda s: (not s["falla"], -s["p"])),
        "zonas_falladas": sorted(fallidas),
        "nodos_fallados": nodos_fallados,
        "impacto": impacto,
        "antes": limpiar(antes),
        "despues": limpiar(despues),
    }
