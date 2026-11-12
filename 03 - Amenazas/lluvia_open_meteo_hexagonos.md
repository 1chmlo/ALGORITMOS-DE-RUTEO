# lluvia_open_meteo_hexagonos.geojson

Zonas de **Maipú** donde el dron **no debe volar por lluvia** durante la ventana de vuelo. Se calculan con el pronóstico horario de **Open-Meteo**, que es gratis y no pide API key.

- **Generado por:** `etl_lluvia_open_meteo.py`
- **Cargado a la BD por:** `carga_lluvia_open_meteo_hexagonos.py` → tabla `lluvia_open_meteo_hexagonos` (se reemplaza completa en cada carga)
- **Fuente:** Open-Meteo Forecast API (`https://api.open-meteo.com/v1/forecast`), variables horarias `precipitation` y `precipitation_probability`, modelo `best_match`.
- **Rol como amenaza en el modelo de ruteo:** el dron vuela libre, en línea recta entre los nodos del grafo aéreo. Por eso la lluvia se mide por zona y no por calle. La vista `aristas_aereas_volables` (`00 - DB/dijkstra.sql`) descarta toda arista aérea que cruce un hexágono con `no_volable = true`, y Dijkstra busca un desvío por otros nodos. El viento se procesa aparte (`etl_viento_open_meteo.py`) y bloquea aristas de la misma forma. Si un nodo queda dentro de la lluvia, sus tramos no tienen ruta y el circuito lo informa en `tramos_sin_ruta`.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`). Un `Feature` `Polygon` por hexágono.

## Grilla y resolución

La grilla de hexágonos es propia y está definida en `open_meteo.py`: 1000 m del centro a cada vértice sobre el rectángulo de referencia de Maipú, con 130 hexágonos. El `hex_id` (`hex_clima_<fila>_<col>`) es estable mientras no cambien el rectángulo ni el radio. Es la **misma** grilla del viento (`viento_open_meteo_hexagonos`), así que ambas capas se cruzan por `hex_id`. **No** coincide con la grilla de STOP.

Open-Meteo usa modelos globales con celdas de unos 9 a 13 km en Chile, así que varios hexágonos reciben el mismo valor (`celdas_modelo_distintas` en la metadata). La grilla fina sirve para recortar con precisión las aristas que se bloquean, pero **no** agrega detalle meteorológico. No va a detectar un chubasco de un solo barrio.

## Criterio de bloqueo

Un hexágono queda `no_volable` si, en las `ventana_horas` que empiezan en la hora actual, se cumple alguna de estas condiciones:

- precipitación ≥ `LLUVIA_UMBRAL_MM_H` (por defecto **2 mm/h**, la lluvia máxima con la que el DJI Dock 3 sigue operando con normalidad según la [FAQ oficial](https://enterprise.dji.com/dock-3/faq)), o
- probabilidad de lluvia ≥ `LLUVIA_UMBRAL_PROB` (por defecto **70 %**).

| Variable de entorno | Por defecto | Uso |
|---|---|---|
| `LLUVIA_UMBRAL_MM_H` | `2` | Umbral de precipitación |
| `LLUVIA_UMBRAL_PROB` | `70` | Umbral de probabilidad (%) |
| `LLUVIA_VENTANA_HORAS` | `2` | Horas evaluadas desde la hora actual |
| `LLUVIA_SIMULADA` | vacío | `"lon,lat,radio_m"`: fuerza lluvia en un círculo para probar el ruteo en días secos. Ejemplo: `LLUVIA_SIMULADA="-70.7695,-33.5361,1500" ./main.sh` deja aislado el nodo 8 |

Los datos son una foto del momento de la extracción. Para usarlos en operación hay que volver a correr el ETL y la carga antes de cada vuelo.

## Bloque `metadata`

| Campo | Descripción |
|---|---|
| `fuente`, `endpoint`, `descripcion`, `crs` | Origen y propósito del dataset |
| `bbox_consulta` | `[min_lon, min_lat, max_lon, max_lat]` cubierto por la grilla |
| `tamanio_hexagono_m` | Radio del hexágono (centro a vértice) |
| `ventana_horas`, `umbral_mm_h`, `umbral_prob_pct` | Parámetros usados |
| `simulacion` | `null` o `{lon, lat, radio_m}` si se usó `LLUVIA_SIMULADA` |
| `celdas_modelo_distintas` | Cuántas celdas distintas del modelo cubren la grilla (indica la resolución real) |
| `total_hexagonos`, `total_no_volables` | Conteos |
| `fecha_extraccion_utc` | Cuándo se ejecutó el ETL |

## Propiedades (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador del hexágono (clave única en la BD) |
| `centro_lon`, `centro_lat` | flotante | Centro del hexágono (punto consultado) |
| `celda_modelo_lon`, `celda_modelo_lat` | flotante | Centro de la celda del modelo que respondió Open-Meteo |
| `precipitacion_actual_mm_h` | flotante | Precipitación de la hora actual |
| `precipitacion_max_mm_h` | flotante | Máximo de la ventana |
| `probabilidad_max_pct` | flotante o `null` | Probabilidad máxima de la ventana |
| `hora_desde`, `hora_hasta` | texto ISO (hora local de Santiago) | Primera y última hora evaluadas |
| `ventana_horas`, `umbral_mm_h`, `umbral_prob_pct` | | Parámetros con que se evaluó |
| `simulado` | booleano | `true` si el bloqueo viene de `LLUVIA_SIMULADA` |
| `no_volable` | booleano | `true` = el dron no puede cruzar esta zona |
| `motivo` | texto o `null` | Qué umbral se superó |
| `tamanio_hexagono_m` | entero | Radio del hexágono |
| `fecha_extraccion_utc` | texto ISO 8601 | Momento de la extracción |
| `fuente` | texto | `Open-Meteo Forecast API` |
