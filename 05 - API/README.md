# 05 - API de ruteo de drones

API en FastAPI que recibe la consulta de la web (misión, restricciones, capas activas), arma el grafo de visibilidad, calcula la probabilidad de falla, corre las 4 técnicas de ruteo y devuelve las rutas con su resiliencia.

- **Servicio:** `api` en `docker-compose.yml`, puerto 8000. La web la usa vía nginx en `http://localhost:8080/api/...`, el mismo origen, así que no hay CORS.
- **Documentación interactiva:** `http://localhost:8080/api/docs`
- **Código:** `app/` (`main.py`, `servicio.py`, `grafo.py`, `tecnicas.py`, `datos.py`) más `03 - Amenazas/probabilidad_falla.py`, que se copia en la imagen.

## Por qué una API

El front de la Fase 2 tenía las rutas escritas a mano. La Fase 3 exige recalcular cada vez que el usuario cambia restricciones o activa amenazas, y dos de las técnicas (Gurobi y el genético) corren en Python, no en PostgreSQL. La API hace de puente: valida los parámetros, usa PostGIS y pgRouting para los datos y `pgr_dijkstra`, y Python para Gurobi y el genético.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/salud` | Verifica conexión a la BD |
| GET | `/api/config` | Amenazas, metadatos, parámetros y consulta por defecto |
| GET | `/api/capas/{nombre}` | GeoJSON desde PostGIS: `nodos`, `lluvia`, `viento`, `stop_90d`, `luminarias`, `trafico`, `formas`, `metadatos_grilla` |
| POST | `/api/rutas` | Calcula las 4 rutas (cuerpo: ver abajo) |
| POST | `/api/simular-fallas` | Sorteo 0–100 por zona y rutas recalculadas (punto 7) |
| POST | `/api/recargar` | Vacía la caché después de volver a correr los ETL |

Cuerpo de `/api/rutas` y `/api/simular-fallas`. Todos los campos son opcionales:

```json
{
  "modo": "circuito",                 // "circuito" (vuelve a la base) o "punto" (origen → destino)
  "origen": 1, "destinos": [4,5,6,7,8,9],
  "bateria_km": 25, "velocidad_kmh": 54, "altura_vuelo_m": 120,
  "riesgo_max": 0.6,                  // P(falla de la misión) máxima aceptada
  "umbral_falla": 0.7,                // zona caída si p >= umbral (modelo probabilístico)
  "umbral_blando": 0.15,              // desde esta p se agregan waypoints para rodear la zona
  "modelo": "probabilistico",         // o "ponderado"
  "amenazas": ["lluvia","viento"],
  "metadatos": ["stop_90d","oscuridad","trafico","formas"],
  "restricciones_estaticas": true,
  "peso_riesgo": 2.0, "peso_metadatos": 0.3,
  "pesos_amenazas": {"lluvia": 1}, "params_amenazas": {"viento": {"umbral_kmh": 30}},
  "amenazas_simuladas": [{"tipo":"lluvia","lon":-70.763,"lat":-33.523,"radio_m":1300,"p":0.95}],
  "semilla": 42, "simulaciones_mc": 2000
}
```

## 1. Infraestructura: grafo de visibilidad (punto 2)

El dron vuela en línea recta salvo que algo se lo impida. Los obstáculos corresponden a **zonas de amenaza caídas**: en el modelo probabilístico, las zonas con p ≥ `umbral_falla`, y en la simulación, las zonas cuya falla ocurrió.

Los obstáculos se unen, se cierran (morfología de 100 m), se simplifican y se amplían 40 m de holgura. Los **vértices convexos** de esos polígonos, desplazados 15 m hacia afuera, son los únicos puntos donde la ruta más corta puede doblar. Esos son los waypoints.

El grafo queda así:
- **Nodos:** los 9 nodos de misión más los waypoints.
- **Aristas:** un segmento entre cada par de nodos que se "ven", es decir, cuyo segmento no toca un obstáculo.

Así ninguna arista atraviesa un obstáculo y las rutas los rodean pegadas a su borde, en vez de trazar líneas rectas imposibles.

También se agregan los vértices de las **zonas blandas** (`umbral_blando ≤ p < umbral_falla`). Esas zonas sí se pueden cruzar, pero con sus vértices en el grafo el optimizador también puede elegir rodearlas.

Se construyen dos grafos por consulta:
- **Grafo A**, para Dijkstra solo distancia: solo obstáculos por fallas ya ocurridas.
- **Grafo B**, para las otras tres técnicas: además, las zonas de amenaza caídas y los waypoints blandos.

Si el grafo B supera las 1.990 variables del MILP, se deja a cada nodo con sus k vecinos más cercanos. El límite viene de la licencia libre de Gurobi.

## 2. Probabilidad de falla (punto 5)

Las fórmulas están en `03 - Amenazas/probabilidad_falla.py` (ver `probabilidad_falla.md`). Cada amenaza se convierte en zonas con una probabilidad p. Una arista o un nodo hereda `1 − Π(1 − p_z)` de las zonas que toca. Los parámetros de cada fórmula se pueden cambiar desde la web.

## 3. Las 4 técnicas (punto 6)

Las cuatro resuelven el mismo problema: salir de la base, visitar los destinos alcanzables y, en modo circuito, volver.

**Función objetivo común**, con la que se comparan las cuatro rutas:

```
J(ruta) = Σ_{e∈ruta} L_e  +  β · 1000 · Σ_{z ∈ Z(ruta)} w_k(z) · (−ln(1 − p_z))
L_e     = largo_e · (1 + γ · (1 − m_e))
```

- `m_e ∈ [0,1]` es el **valor de vigilancia** de los metadatos activos a lo largo de la arista. Se calcula promediando la grilla de 500 m ponderada por el largo de la arista dentro de cada hexágono:
  - `stop_90d`: nivel STOP de 90 días.
  - `oscuridad`: 1 − luminarias/P75.
  - `trafico`: factor de velocidad baja.
  - `formas`: factor de curvas y enlaces.

  Para un dron de patrullaje, volar sobre focos de delito **suma** vigilancia, por eso abarata la arista.
- `Z(ruta)` son las zonas de amenaza que toca la ruta. Cada zona se cobra **una sola vez**, porque es un único evento de falla.
- `−ln(1 − p)` es aditivo: `Σ_z −ln(1 − p_z) = −ln R`.

| # | Técnica | Grafo | Costo | Restricciones |
|---|---|---|---|---|
| 1 | `pgr_dijkstra` solo distancia | A | `largo_e` en metros | Ninguna (es el peor caso); se verifican después |
| 2 | Gurobi (MILP) | B | J exacto | Duras: autonomía, riesgo máximo, zonas caídas |
| 3 | `pgr_dijkstra` con parámetros | B | `c_e = L_e + β·1000·Σ_{z∋e} w·(−ln(1 − p_z))` | Zonas caídas fuera del grafo; autonomía y riesgo se verifican después |
| 4 | Algoritmo genético | B | J exacto + penalización | Autonomía y riesgo como penalización |

**Dijkstra (1 y 3).** El grafo de la consulta se copia a una tabla temporal y se ejecuta `pgr_dijkstra` *many-to-many* entre todos los nodos de misión dentro de PostgreSQL. El orden de visita se obtiene probando todas las permutaciones sobre esa matriz de costos (6 destinos son 720 órdenes). Dijkstra solo admite costos por arista, así que la técnica 3 cobra una zona cada vez que un tramo la cruza. Por eso sobrestima el riesgo de las zonas grandes, y no puede imponer a la vez autonomía y riesgo.

**Gurobi (2): modelo formal.**

- Conjuntos: aristas `E`, nodos `V`, zonas `Zn`, aristas que tocan la zona k `E_k ⊆ E`, nodos requeridos `Req`.
- Variables:
  - `y_e ∈ {0,1,2}`: veces que se usa la arista. El valor 2 permite ir y volver por el mismo tramo.
  - `t_v ∈ ℤ≥0`: pasadas por el nodo v.
  - `z_k ∈ {0,1}`: la ruta toca la zona k.

```
min   Σ_e L_e·y_e  +  β·1000·Σ_k w_k·ρ_k·z_k                    (ρ_k = −ln(1 − p_k))
s.a.  Σ_{e∈δ(v)} y_e = 2·t_v + b_v               ∀v∈V   (b_v = 1 en origen/destino del modo punto)
      t_v ≥ 1                                     ∀v∈Req (modo circuito)
      Σ_{e∈E_k} y_e ≤ M_k·z_k                     ∀k∈Zn
      Σ_e largo_e·y_e ≤ autonomía
      Σ_k ρ_k·z_k ≤ −ln(1 − riesgo_max)           (⇔ P(falla) ≤ riesgo_max, exacto)
      Σ_{e∈δ(S)} y_e ≥ 2  (≥ 1 en modo punto)     ∀S con un requerido y sin el origen  [lazy]
```

- Las restricciones de conexión (eliminación de subtours) se agregan como *lazy constraints* en un callback, solo cuando aparecen.
- La ruta se reconstruye como un circuito (o camino) euleriano sobre las aristas elegidas.
- El tiempo límite es de 20 s y el gap de 0,01 %.
- Con los 9 nodos del proyecto el modelo tiene unas 1.000 a 1.990 variables y unas 130 restricciones, y se resuelve en menos de 1 s.

**Algoritmo genético (4).**
- Cromosoma: permutación de destinos más, para cada tramo, cuál de las k = 4 rutas alternativas usar. Las alternativas se obtienen con el algoritmo de Yen (`networkx.shortest_simple_paths`) según `c_e`.
- Aptitud: J exacto más una penalización de 10⁵ si se excede la autonomía o el riesgo.
- Parámetros: población 60, 120 generaciones, torneo de 3, cruce OX para la permutación y cruce uniforme para las elecciones, mutaciones de intercambio y de alternativa, elitismo 2.
- Usa semilla fija, así que el resultado es reproducible.

**Mejor ruta:** la factible de menor J. Una ruta es factible si cumple la autonomía, si 1 − R ≤ riesgo máximo y si no cruza zonas caídas.

## 4. Resiliencia (punto 8)

```
R(ruta) = Π_{z ∈ Z(ruta)} (1 − p_z)
```

R es la probabilidad de completar la misión sin que ocurra ninguna falla, suponiendo zonas independientes. Se valida con **Monte Carlo**: 2.000 sorteos 0–100 por zona, el mismo mecanismo del punto 7, y se cuenta en cuántos la ruta no toca ninguna zona fallada (`resiliencia_mc`). Todas las rutas usan los mismos sorteos, para que la comparación sea justa. La web muestra R y el tiempo de cómputo junto al nombre del algoritmo en la leyenda, y marca con 🛡 la ruta más resiliente.

## 5. Simulación de fallas (punto 7)

`/api/simular-fallas` hace lo siguiente:
1. Sortea `r_z ~ U[0,100)` por cada zona activa, con semilla para que sea reproducible. La falla **ocurre** si `r_z < 100·p_z`.
2. Informa qué zonas, nodos y rutas originales caen.
3. Recalcula las 4 rutas tratando las zonas falladas como bloqueos físicos para todas las técnicas.

## Licencia de Gurobi

`pip install gurobipy` trae una licencia limitada (2.000 variables y 2.000 restricciones). El grafo se poda para caber en ella, así que funciona sin configurar nada. Para quitar el límite se puede usar una licencia académica WLS, que es gratis con correo universitario. Basta con definir `GRB_WLSACCESSID`, `GRB_WLSSECRET` y `GRB_LICENSEID` en `.env` (ver `.env.example`). Si Gurobi falla por cualquier motivo, la web muestra el error en esa fila y las otras 3 técnicas siguen funcionando.
