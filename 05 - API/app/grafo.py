"""Grafo de visibilidad para el vuelo del dron.

Idea: el dron vuela en línea recta salvo que algo se lo impida. Los obstáculos (zonas de
amenaza con p >= umbral) se unen en polígonos; sus vértices convexos, desplazados unos metros
hacia afuera, son los únicos puntos donde una ruta más corta puede doblar.
El grafo tiene como nodos los puntos de misión más esos vértices, y una arista entre cada par de
nodos que se "ven" (el segmento no cruza obstáculos). Dijkstra sobre este grafo da la ruta más
corta que rodea los obstáculos.

Además se agregan los vértices de las zonas *blandas* (amenaza con p >= umbral_blando pero bajo
el umbral duro): se pueden cruzar pagando su riesgo, pero así el optimizador también tiene la
opción de rodearlas.

Todo se calcula en una proyección local en metros (equirectangular centrada en Maipú; a ~20 km
el error es < 0.1 %).
"""
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

LAT0, LON0 = -33.51, -70.77
_phi = math.radians(LAT0)
M_LAT = 111_132.92 - 559.82 * math.cos(2 * _phi) + 1.175 * math.cos(4 * _phi)
M_LON = 111_412.84 * math.cos(_phi) - 93.5 * math.cos(3 * _phi)

HOLGURA_M = 40.0          # distancia mínima del dron a un obstáculo duro
DESPLAZAMIENTO_WP_M = 15.0  # los waypoints quedan fuera del obstáculo ampliado
CIERRE_M = 100.0          # cierre morfológico: rellena muescas entre hexágonos
MAX_WAYPOINTS = 70
MAX_VARIABLES = 1990      # aristas + nodos + zonas del MILP: licencia libre de Gurobi (2000)


def a_metros(lon, lat):
    return (lon - LON0) * M_LON, (lat - LAT0) * M_LAT


def a_grados(x, y):
    return LON0 + x / M_LON, LAT0 + y / M_LAT


def geom_a_metros(geom):
    return shapely.transform(geom, lambda c: np.column_stack(((c[:, 0] - LON0) * M_LON, (c[:, 1] - LAT0) * M_LAT)))


def geom_a_grados(geom):
    return shapely.transform(geom, lambda c: np.column_stack((LON0 + c[:, 0] / M_LON, LAT0 + c[:, 1] / M_LAT)))


def geojson_a_metros(gj):
    return geom_a_metros(shape(gj))


def feature(geom_m, **props):
    return {"type": "Feature", "geometry": mapping(geom_a_grados(geom_m)), "properties": props}


@dataclass
class Zona:
    zona_id: str
    amenaza: str
    p: float
    detalle: str
    geom: object  # polígono en metros
    simulada: bool = False


@dataclass
class Grafo:
    nodos: dict                     # id -> (x, y)
    tipo_nodo: dict                 # id -> 'mision' | 'waypoint_duro' | 'waypoint_blando'
    aristas: list                   # dicts: id, u, v, largo, zonas (idx), riesgo, metadato
    obstaculo: object               # MultiPolygon/Polygon en metros (puede ser vacío)
    zonas: list = field(default_factory=list)  # Zona activas (índices usados en aristas["zonas"])
    inalcanzables: list = field(default_factory=list)
    podado: bool = False


def _cierre(geom, d=CIERRE_M):
    return geom.buffer(d, join_style="mitre", mitre_limit=2.0).buffer(-d, join_style="mitre", mitre_limit=2.0)


def _poligonos(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def _vertices_convexos(geom, desplazamiento):
    """Vértices de `geom` ampliado en `desplazamiento` (unión mitre: conserva las esquinas)
    que son convexos para el obstáculo, es decir, por donde una ruta puede doblar."""
    salida = []
    ampliado = geom.buffer(desplazamiento, join_style="mitre", mitre_limit=2.0)
    for poli in _poligonos(ampliado):
        poli = orient(poli, sign=1.0)  # exterior antihorario, agujeros horarios
        for anillo in [poli.exterior, *poli.interiors]:
            c = list(anillo.coords)[:-1]
            n = len(c)
            for i in range(n):
                (x0, y0), (x1, y1), (x2, y2) = c[i - 1], c[i], c[(i + 1) % n]
                cruz = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)
                if cruz > 1e-6:
                    salida.append((x1, y1))
    return salida


def preparar_obstaculo(poligonos, holgura=HOLGURA_M, tolerancia=20.0):
    """Une, cierra y simplifica los obstáculos duros, y les agrega la holgura de seguridad."""
    if not poligonos:
        return shapely.Polygon()
    union = unary_union([p.buffer(0) for p in poligonos])
    return _cierre(union).simplify(tolerancia).buffer(holgura, join_style="mitre", mitre_limit=2.0)


def waypoints(obstaculo, blandas, area):
    """Waypoints duros (alrededor del obstáculo) y blandos (alrededor de zonas cruzables).

    Si son demasiados, se simplifican más los contornos hasta que quepan en MAX_WAYPOINTS.
    """
    for tolerancia in (30.0, 80.0, 150.0, 300.0, 600.0):
        duros = [p for p in _vertices_convexos(obstaculo.simplify(tolerancia), DESPLAZAMIENTO_WP_M + tolerancia)
                 ] if not obstaculo.is_empty else []
        blandos = []
        if blandas:
            zb = _cierre(unary_union([z.buffer(0) for z in blandas])).simplify(tolerancia)
            blandos = _vertices_convexos(zb, 25.0 + tolerancia)
        duros = [p for p in duros if area.contains(Point(p)) and not obstaculo.contains(Point(p))]
        blandos = [p for p in blandos if area.contains(Point(p)) and not obstaculo.contains(Point(p))]
        if len(duros) + len(blandos) <= MAX_WAYPOINTS:
            return duros, blandos
    return duros[:MAX_WAYPOINTS], blandos[: max(0, MAX_WAYPOINTS - len(duros))]


def construir(nodos_mision, obstaculos_duros, zonas_activas, zonas_blandas, area,
              valor_metadato, peso_amenaza):
    """Arma el grafo de visibilidad.

    nodos_mision:   {id: (x, y)} en metros
    obstaculos_duros: polígonos (m) que ninguna arista puede cruzar
    zonas_activas:  lista de Zona: se registran las que cruza cada arista (riesgo y resiliencia)
    zonas_blandas:  polígonos (m) cuyos vértices se agregan como waypoints
    valor_metadato: función(array de LineString) -> array de valor de vigilancia en [0, 1]
    peso_amenaza:   {amenaza: w} que multiplica el riesgo de esa amenaza en el costo
    """
    obstaculo = preparar_obstaculo(obstaculos_duros)
    shapely.prepare(obstaculo)
    wp_duros, wp_blandos = waypoints(obstaculo, zonas_blandas, area)

    nodos, tipo = {}, {}
    inalcanzables = []
    for i, xy in nodos_mision.items():
        if not obstaculo.is_empty and obstaculo.contains(Point(xy)):
            inalcanzables.append(i)
            continue
        nodos[i], tipo[i] = xy, "mision"
    sig = 1000
    vistos = set()
    for lista, t in ((wp_duros, "waypoint_duro"), (wp_blandos, "waypoint_blando")):
        for x, y in lista:
            clave = (round(x), round(y))
            if clave in vistos:
                continue
            vistos.add(clave)
            nodos[sig], tipo[sig] = (x, y), t
            sig += 1

    ids = list(nodos)
    pares = [(ids[a], ids[b]) for a in range(len(ids)) for b in range(a + 1, len(ids))]
    if not pares:
        return Grafo(nodos, tipo, [], obstaculo, zonas_activas, inalcanzables)
    lineas = np.array([LineString([nodos[u], nodos[v]]) for u, v in pares], dtype=object)
    if obstaculo.is_empty:
        visibles = np.ones(len(pares), dtype=bool)
    else:
        visibles = ~shapely.intersects(lineas, obstaculo)
    pares = [par for par, ok in zip(pares, visibles) if ok]
    lineas = lineas[visibles]

    podado = False
    max_aristas = MAX_VARIABLES - len(nodos) - len(zonas_activas)
    if len(pares) > max_aristas:
        for k in (60, 45, 35, 28, 22, 18, 14, 10, 8, 6, 4):
            p2, l2 = _podar(pares, lineas, nodos, tipo, k)
            if len(p2) <= max_aristas:
                break
        pares, lineas, podado = p2, l2, True

    # Zonas que cruza cada arista (consulta masiva con un índice espacial)
    zonas_por_arista = [[] for _ in pares]
    if zonas_activas and len(lineas):
        arbol = shapely.STRtree([z.geom for z in zonas_activas])
        idx_linea, idx_zona = arbol.query(lineas, predicate="intersects")
        for li, zi in zip(idx_linea, idx_zona):
            zonas_por_arista[li].append(int(zi))

    vigilancia = valor_metadato(lineas) if len(lineas) else []
    aristas = []
    for k, ((u, v), linea, zs, vig) in enumerate(zip(pares, lineas, zonas_por_arista, vigilancia)):
        riesgo = sum(-math.log(1 - min(zonas_activas[z].p, 0.999)) for z in zs)
        riesgo_pond = sum(peso_amenaza.get(zonas_activas[z].amenaza, 1.0) * -math.log(1 - min(zonas_activas[z].p, 0.999))
                          for z in zs)
        aristas.append({
            "id": k + 1, "u": u, "v": v, "largo": linea.length, "zonas": zs,
            "riesgo": riesgo, "riesgo_ponderado": riesgo_pond, "metadato": float(vig),
        })
    return Grafo(nodos, tipo, aristas, obstaculo, zonas_activas, inalcanzables, podado)


def _podar(pares, lineas, nodos, tipo, k=14):
    """Deja, para cada nodo, sus k vecinos visibles más cercanos (más todas las aristas entre
    puntos de misión). Solo se usa si el grafo excede MAX_ARISTAS."""
    vecinos = {}
    for idx, (u, v) in enumerate(pares):
        d = lineas[idx].length
        vecinos.setdefault(u, []).append((d, idx))
        vecinos.setdefault(v, []).append((d, idx))
    mantener = {i for i, (u, v) in enumerate(pares) if tipo[u] == "mision" and tipo[v] == "mision"}
    for lista in vecinos.values():
        mantener.update(i for _, i in sorted(lista)[:k])
    orden = sorted(mantener)
    return [pares[i] for i in orden], lineas[orden]
