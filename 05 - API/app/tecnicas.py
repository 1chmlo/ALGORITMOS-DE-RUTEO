"""Las 4 técnicas de ruteo (punto 6) sobre el grafo de visibilidad.

Problema: el dron sale de `origen`, visita todos los `destinos` alcanzables y (modo circuito)
vuelve al origen. En modo punto va de origen a un único destino.

Función objetivo (la misma para comparar las 4 rutas):
    J(ruta) = Σ_{e∈ruta} L_e  +  β · K · Σ_{z∈Z(ruta)} w_k(z) · (-ln(1 - p_z))
    L_e = largo_e · (1 + γ · (1 - m_e))
  m_e   valor de vigilancia de los metadatos activos en [0, 1] (volar sobre focos de delito,
        zonas oscuras, tráfico lento y enlaces/curvas "rinde" más, así que cuesta menos)
  Z     zonas de amenaza que toca la ruta (cada zona se paga UNA vez aunque la crucen varios
        tramos: es un único evento de falla)
  p_z   probabilidad de falla de la zona; Σ -ln(1 - p_z) = -ln R, con R la resiliencia
  K     1000 m: equivalencia entre riesgo y distancia
Gurobi y el genético optimizan J exactamente. Dijkstra solo admite costos por arista, así que
usa la aproximación c_e = L_e + β·K·Σ_{z∋e} w·(-ln(1 - p_z)), que cobra una zona cada vez que
un tramo la cruza (sobrestima el riesgo de las zonas grandes).

1. dijkstra_distancia    pgr_dijkstra con costo = largo (ignora amenazas y metadatos). Solo
                         respeta los obstáculos estáticos (zonas restringidas, terreno).
2. gurobi                MILP: restricciones duras de batería y riesgo (ver modelo en gurobi()).
3. dijkstra_parametros   pgr_dijkstra con costo = c_e sobre el mismo grafo que Gurobi; las
                         restricciones de batería y riesgo solo se verifican después.
4. genetico              Algoritmo genético: orden de visita + elección entre k rutas
                         alternativas por tramo; batería y riesgo como penalización.
"""
import itertools
import math
import random
import time

import networkx as nx

K_RIESGO_M = 1000.0

TECNICAS = {
    "dijkstra_distancia": {"nombre": "pgr_dijkstra (solo distancia)", "color": "#64748b"},
    "gurobi": {"nombre": "Gurobi (MILP)", "color": "#22c55e"},
    "dijkstra_parametros": {"nombre": "pgr_dijkstra (con parámetros)", "color": "#38bdf8"},
    "genetico": {"nombre": "Algoritmo genético", "color": "#f59e0b"},
}


class SinRuta(Exception):
    pass


# ----------------------------------------------------------------------------- utilidades

def costo_largo(a, cfg):
    """L_e: largo con recargo por volar sobre zonas de poco valor de vigilancia."""
    return a["largo"] * (1 + cfg["peso_metadatos"] * (1 - a["metadato"]))


def riesgo_zona(z, cfg, ponderado=True):
    """-ln(1 - p_z), multiplicado por el peso de su amenaza si `ponderado`."""
    r = -math.log(1 - min(z.p, 0.999))
    return r * float((cfg.get("pesos_amenazas") or {}).get(z.amenaza, 1.0)) if ponderado else r


def costo_arista(a, cfg):
    """c_e aproximado para Dijkstra (cobra cada zona en cada tramo que la cruza)."""
    return costo_largo(a, cfg) + cfg["peso_riesgo"] * K_RIESGO_M * a["riesgo_ponderado"]


def objetivo(tramos, idx_zonas, zonas, cfg):
    """J(ruta) exacto: largo ponderado + riesgo de cada zona tocada una sola vez."""
    return (sum(costo_largo(a, cfg) for a in tramos)
            + cfg["peso_riesgo"] * K_RIESGO_M * sum(riesgo_zona(zonas[i], cfg) for i in idx_zonas))


def a_networkx(grafo, peso):
    g = nx.Graph()
    g.add_nodes_from(grafo.nodos)
    for a in grafo.aristas:
        g.add_edge(a["u"], a["v"], id=a["id"], peso=peso(a), datos=a)
    return g


def requeridos(cfg, grafo):
    """Destinos alcanzables (no dentro de un obstáculo) y destinos omitidos."""
    if cfg["origen"] not in grafo.nodos:
        raise SinRuta(f"La base de origen {cfg['origen']} queda dentro de un obstáculo")
    dest = [d for d in cfg["destinos"] if d != cfg["origen"]]
    return [d for d in dest if d in grafo.nodos], [d for d in dest if d not in grafo.nodos]


def mejor_orden(destinos, origen, costo, circuito):
    """Orden de visita óptimo por enumeración (≤ 8 destinos => ≤ 40.320 permutaciones)."""
    if not destinos:
        return []
    if len(destinos) > 8:  # no ocurre con 9 nodos, pero por si acaso: vecino más cercano
        orden, actual, resto = [], origen, set(destinos)
        while resto:
            actual = min(resto, key=lambda d: costo(actual, d))
            orden.append(actual)
            resto.remove(actual)
        return orden
    mejor, mejor_c = None, math.inf
    for perm in itertools.permutations(destinos):
        c = costo(origen, perm[0]) + sum(costo(perm[i], perm[i + 1]) for i in range(len(perm) - 1))
        if circuito:
            c += costo(perm[-1], origen)
        if c < mejor_c:
            mejor, mejor_c = list(perm), c
    if mejor is None or math.isinf(mejor_c):
        raise SinRuta("No existe una secuencia que conecte todos los destinos")
    return mejor


# ----------------------------------------------------------------------------- pgr_dijkstra

def _pgr_caminos(con, grafo, peso, nodos_mision):
    """Caminos más cortos entre todos los pares de nodos de misión con pgr_dijkstra.

    El grafo de visibilidad de esta consulta se copia a una tabla temporal y pgRouting lo
    resuelve en la base de datos (many-to-many, no dirigido).
    """
    with con.transaction():
        con.execute("""CREATE TEMP TABLE IF NOT EXISTS grafo_consulta
                       (id INTEGER, source BIGINT, target BIGINT, cost FLOAT8, reverse_cost FLOAT8)""")
        con.execute("TRUNCATE grafo_consulta")
        with con.cursor().copy("COPY grafo_consulta (id, source, target, cost, reverse_cost) FROM STDIN") as cp:
            for a in grafo.aristas:
                c = peso(a)
                cp.write_row((a["id"], a["u"], a["v"], c, c))
        filas = con.execute("""
            SELECT start_vid, end_vid, seq, node, edge, agg_cost
            FROM pgr_dijkstra('SELECT id, source, target, cost, reverse_cost FROM grafo_consulta',
                              %s::BIGINT[], %s::BIGINT[], directed := false)
            ORDER BY start_vid, end_vid, seq""", (nodos_mision, nodos_mision)).fetchall()
    caminos, costos = {}, {}
    for s, e, _seq, node, _edge, agg in filas:
        caminos.setdefault((s, e), []).append(node)
        costos[(s, e)] = agg
    return caminos, costos


def _dijkstra(con, grafo, cfg, peso):
    req, omitidos = requeridos(cfg, grafo)
    circuito = cfg["modo"] == "circuito"
    mision = [cfg["origen"], *req]
    caminos, costos = _pgr_caminos(con, grafo, peso, mision)

    def c(a, b):
        return costos.get((a, b), costos.get((b, a), math.inf))
    orden = mejor_orden(req, cfg["origen"], c, circuito)
    paradas = [cfg["origen"], *orden] + ([cfg["origen"]] if circuito else [])
    secuencia = [cfg["origen"]]
    for a, b in zip(paradas, paradas[1:]):
        tramo = caminos.get((a, b)) or list(reversed(caminos.get((b, a), [])))
        if not tramo:
            raise SinRuta(f"Sin camino entre {a} y {b}")
        secuencia.extend(tramo[1:])
    return {"secuencia": secuencia, "orden": orden, "omitidos": omitidos}


def dijkstra_distancia(con, grafo, cfg):
    return _dijkstra(con, grafo, cfg, lambda a: a["largo"])


def dijkstra_parametros(con, grafo, cfg):
    # Las aristas que cruzan zonas duras ya no existen en el grafo (son obstáculos)
    return _dijkstra(con, grafo, cfg, lambda a: costo_arista(a, cfg))


# ----------------------------------------------------------------------------- Gurobi

def gurobi(con, grafo, cfg):
    """MILP sobre el grafo de visibilidad (no dirigido).

    Conjuntos
      E aristas, V nodos (misión + waypoints), Zn zonas de amenaza activas, E_k ⊆ E aristas que
      tocan la zona k, Req nodos que hay que visitar.
    Variables
      y_e ∈ {0, 1, 2}  veces que el dron usa la arista e (2 = ida y vuelta por el mismo tramo)
      t_v ∈ Z≥0        pasadas por el nodo v (grado(v) = 2·t_v)
      z_k ∈ {0, 1}     1 si la ruta toca la zona de amenaza k
    Objetivo
      min Σ_e L_e · y_e + β·K · Σ_k w_k · ρ_k · z_k            (ρ_k = -ln(1 - p_k))
    Restricciones
      grado:      Σ_{e∈δ(v)} y_e = 2·t_v + b_v                  ∀v ∈ V
                  (b_v = 1 en origen y destino del modo punto; 0 en el resto)
      visita:     t_v ≥ 1                                         ∀v ∈ Req (circuito)
      zona:       Σ_{e∈E_k} y_e ≤ M_k · z_k                        ∀k ∈ Zn
      batería:    Σ_e largo_e · y_e ≤ autonomía
      riesgo:     Σ_k ρ_k · z_k ≤ -ln(1 - riesgo_max)            (⇔ 1 - R ≤ riesgo_max, exacto)
      conexión:   Σ_{e∈δ(S)} y_e ≥ 2 (≥ 1 en modo punto)          ∀S con un requerido y sin origen
                  (cortes de subtour agregados como restricciones *lazy* cuando aparecen)
      zonas duras: las aristas que cruzarían una zona con p ≥ umbral no existen en el grafo.
    La ruta se reconstruye como circuito/camino euleriano sobre las aristas elegidas.
    """
    import gurobipy as gp
    from gurobipy import GRB

    req, omitidos = requeridos(cfg, grafo)
    o = cfg["origen"]
    circuito = cfg["modo"] == "circuito"
    if not req:
        return {"secuencia": [o], "orden": [], "omitidos": omitidos}
    destino_punto = None if circuito else req[0]

    env = _entorno_gurobi(gp)
    m = gp.Model("ruteo_dron", env=env)
    m.Params.TimeLimit = cfg.get("gurobi_tiempo_s", 20)
    m.Params.MIPGap = 1e-4
    m.Params.LazyConstraints = 1

    ar = grafo.aristas
    y = m.addVars(len(ar), vtype=GRB.INTEGER, lb=0, ub=2, name="y")
    t = m.addVars(list(grafo.nodos), vtype=GRB.INTEGER, lb=0, ub=4, name="t")
    incid = {v: [] for v in grafo.nodos}
    for i, a in enumerate(ar):
        incid[a["u"]].append(i)
        incid[a["v"]].append(i)
    zonas = grafo.zonas
    por_zona = {}
    for i, a in enumerate(ar):
        for k in a["zonas"]:
            por_zona.setdefault(k, []).append(i)
    z = m.addVars(list(por_zona), vtype=GRB.BINARY, name="z")
    for k, es in por_zona.items():
        m.addConstr(gp.quicksum(y[i] for i in es) <= min(2 * len(es), 30) * z[k])
    m.setObjective(gp.quicksum(costo_largo(a, cfg) * y[i] for i, a in enumerate(ar))
                   + cfg["peso_riesgo"] * K_RIESGO_M * gp.quicksum(riesgo_zona(zonas[k], cfg) * z[k] for k in por_zona),
                   GRB.MINIMIZE)
    for v in grafo.nodos:
        b = 1 if (not circuito and v in (o, destino_punto)) else 0
        m.addConstr(gp.quicksum(y[i] for i in incid[v]) == 2 * t[v] + b)
    if circuito:
        for v in [o, *req]:
            m.addConstr(t[v] >= 1)
    m.addConstr(gp.quicksum(a["largo"] * y[i] for i, a in enumerate(ar)) <= cfg["bateria_km"] * 1000)
    m.addConstr(gp.quicksum(riesgo_zona(zonas[k], cfg, ponderado=False) * z[k] for k in por_zona)
                <= -math.log(1 - min(cfg["riesgo_max"], 0.999)))

    requeridos_set = set(req)
    minimo_corte = 2 if circuito else 1

    def corte(modelo, donde):
        if donde != GRB.Callback.MIPSOL:
            return
        val = modelo.cbGetSolution(y)
        g = nx.Graph()
        g.add_nodes_from(grafo.nodos)
        g.add_edges_from((ar[i]["u"], ar[i]["v"]) for i in range(len(ar)) if val[i] > 0.5)
        for comp in nx.connected_components(g):
            if o in comp or not (comp & requeridos_set):
                continue
            frontera = [i for i, a in enumerate(ar) if (a["u"] in comp) != (a["v"] in comp)]
            modelo.cbLazy(gp.quicksum(y[i] for i in frontera) >= minimo_corte)

    m.optimize(corte)
    estado = {GRB.OPTIMAL: "óptimo", GRB.TIME_LIMIT: "límite de tiempo", GRB.INFEASIBLE: "infactible"}.get(m.Status, str(m.Status))
    if m.SolCount == 0:
        raise SinRuta(f"Gurobi: {estado} (no existe ruta que cumpla batería y riesgo con estas zonas)")
    multi = nx.MultiGraph()
    for i, a in enumerate(ar):
        for _ in range(int(round(y[i].X))):
            multi.add_edge(a["u"], a["v"])
    if circuito:
        pasos = list(nx.eulerian_circuit(multi, source=o))
    else:
        pasos = list(nx.eulerian_path(multi, source=o))
    secuencia = [o] + [b for _, b in pasos]
    detalle = {"estado": estado, "gap": round(m.MIPGap, 6) if m.IsMIP else None,
               "variables": m.NumVars, "restricciones": m.NumConstrs, "nodos_bb": int(m.NodeCount)}
    m.dispose()
    return {"secuencia": secuencia, "orden": _orden_visita(secuencia, req), "omitidos": omitidos, "detalle": detalle}


def _entorno_gurobi(gp):
    """Entorno con licencia académica WLS si las variables de entorno existen; si no, la
    licencia limitada que trae `pip install gurobipy` (2000 variables / restricciones)."""
    import os
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    for var, param, tipo in (("GRB_WLSACCESSID", "WLSACCESSID", str), ("GRB_WLSSECRET", "WLSSECRET", str),
                             ("GRB_LICENSEID", "LICENSEID", int)):
        if os.environ.get(var):
            env.setParam(param, tipo(os.environ[var]))
    env.start()
    return env


def _orden_visita(secuencia, req):
    vistos, orden = set(), []
    for v in secuencia:
        if v in req and v not in vistos:
            vistos.add(v)
            orden.append(v)
    return orden


# ----------------------------------------------------------------------------- Genético

def genetico(con, grafo, cfg):
    """Algoritmo genético.

    Cromosoma: (permutación de destinos, índice de ruta alternativa para cada tramo).
    Las rutas alternativas de cada par de nodos de misión son las k = 4 más baratas sin ciclos
    (algoritmo de Yen, networkx.shortest_simple_paths) según el costo c_e.
    Aptitud: J(ruta) exacto (cada zona tocada se cobra una vez) + penalización si excede la
    batería o el riesgo máximo.
    Operadores: torneo de 3, cruce OX (orden) + cruce uniforme (elecciones), mutación por
    intercambio y por cambio de alternativa, elitismo de 2. Semilla fija => reproducible.
    """
    req, omitidos = requeridos(cfg, grafo)
    o = cfg["origen"]
    circuito = cfg["modo"] == "circuito"
    if not req:
        return {"secuencia": [o], "orden": [], "omitidos": omitidos}
    g = a_networkx(grafo, lambda a: costo_arista(a, cfg))
    K = 4
    mision = [o, *req]
    alternativas = {}
    for a, b in itertools.combinations(mision, 2):
        try:
            rutas = list(itertools.islice(nx.shortest_simple_paths(g, a, b, weight="peso"), K))
        except nx.NetworkXNoPath:
            rutas = []
        info = []
        for r in rutas:
            datos = [g[u][v]["datos"] for u, v in zip(r, r[1:])]
            info.append({"nodos": r, "costo_largo": sum(costo_largo(d, cfg) for d in datos),
                         "largo": sum(d["largo"] for d in datos),
                         "zonas": frozenset(k for d in datos for k in d["zonas"])})
        alternativas[(a, b)] = info
        alternativas[(b, a)] = [{**x, "nodos": list(reversed(x["nodos"]))} for x in info]

    bateria = cfg["bateria_km"] * 1000
    riesgo_lim = -math.log(1 - min(cfg["riesgo_max"], 0.999))
    rng = random.Random(cfg.get("semilla", 42))
    n_tramos = len(req) + (1 if circuito else 0)

    def tramos(perm):
        paradas = [o, *perm] + ([o] if circuito else [])
        return list(zip(paradas, paradas[1:]))

    zonas = grafo.zonas
    rho = [riesgo_zona(z, cfg, ponderado=False) for z in zonas]
    rho_w = [riesgo_zona(z, cfg) for z in zonas]

    def evaluar(ind):
        perm, elec = ind
        costo = largo = 0.0
        tocadas = set()
        for (a, b), k in zip(tramos(perm), elec):
            alts = alternativas.get((a, b)) or []
            if not alts:
                return math.inf
            x = alts[k % len(alts)]
            costo, largo = costo + x["costo_largo"], largo + x["largo"]
            tocadas |= x["zonas"]
        riesgo = sum(rho[i] for i in tocadas)  # cada zona una sola vez (exacto)
        costo += cfg["peso_riesgo"] * K_RIESGO_M * sum(rho_w[i] for i in tocadas)
        pen = 0.0
        if largo > bateria:
            pen += 1e5 * (1 + (largo - bateria) / bateria)
        if riesgo > riesgo_lim:
            pen += 1e5 * (1 + (riesgo - riesgo_lim))
        return costo + pen

    def aleatorio():
        perm = req[:]
        rng.shuffle(perm)
        return (perm, [rng.randrange(K) for _ in range(n_tramos)])

    def ox(p1, p2):
        n = len(p1)
        if n < 2:
            return p1[:]
        i, j = sorted(rng.sample(range(n), 2))
        hijo = [None] * n
        hijo[i:j + 1] = p1[i:j + 1]
        resto = [x for x in p2 if x not in hijo]
        for k in range(n):
            if hijo[k] is None:
                hijo[k] = resto.pop(0)
        return hijo

    POB, GEN = 60, 120
    poblacion = [aleatorio() for _ in range(POB)]
    aptitud = [evaluar(i) for i in poblacion]
    for _ in range(GEN):
        orden_idx = sorted(range(POB), key=lambda i: aptitud[i])
        nueva = [poblacion[i] for i in orden_idx[:2]]
        while len(nueva) < POB:
            p1 = min(rng.sample(range(POB), 3), key=lambda i: aptitud[i])
            p2 = min(rng.sample(range(POB), 3), key=lambda i: aptitud[i])
            perm = ox(poblacion[p1][0], poblacion[p2][0])
            elec = [a if rng.random() < 0.5 else b for a, b in zip(poblacion[p1][1], poblacion[p2][1])]
            if rng.random() < 0.3 and len(perm) > 1:
                i, j = rng.sample(range(len(perm)), 2)
                perm[i], perm[j] = perm[j], perm[i]
            if rng.random() < 0.3:
                elec[rng.randrange(n_tramos)] = rng.randrange(K)
            nueva.append((perm, elec))
        poblacion = nueva
        aptitud = [evaluar(i) for i in poblacion]
    mejor = min(range(POB), key=lambda i: aptitud[i])
    if math.isinf(aptitud[mejor]):
        raise SinRuta("El genético no encontró una secuencia conectada")
    perm, elec = poblacion[mejor]
    secuencia = [o]
    for (a, b), k in zip(tramos(perm), elec):
        alts = alternativas[(a, b)]
        secuencia.extend(alts[k % len(alts)]["nodos"][1:])
    return {"secuencia": secuencia, "orden": perm, "omitidos": omitidos,
            "detalle": {"poblacion": POB, "generaciones": GEN, "alternativas_por_tramo": K,
                        "aptitud": round(aptitud[mejor], 1)}}


FUNCIONES = {
    "dijkstra_distancia": dijkstra_distancia,
    "gurobi": gurobi,
    "dijkstra_parametros": dijkstra_parametros,
    "genetico": genetico,
}


def ejecutar(tecnica, con, grafo, cfg):
    inicio = time.perf_counter()
    try:
        res = FUNCIONES[tecnica](con, grafo, cfg)
        res["error"] = None
    except SinRuta as e:
        res = {"secuencia": None, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - p. ej. licencia de Gurobi: se informa en la web
        res = {"secuencia": None, "error": f"{type(e).__name__}: {e}"}
    res["tiempo_computo_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
    return res
