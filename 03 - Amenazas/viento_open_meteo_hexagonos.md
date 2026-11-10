# viento_open_meteo_hexagonos.geojson

Zonas de **Maipú** donde el dron **no debe volar por viento** durante la ventana de vuelo. Se calculan con el pronóstico horario de **Open-Meteo**, que es gratis y no pide API key.

- **Generado por:** `etl_viento_open_meteo.py`. Es un proceso aparte de la lluvia (`etl_lluvia_open_meteo.py`), pero usa la misma grilla (`open_meteo.py`).
- **Cargado a la BD por:** `carga_viento_open_meteo_hexagonos.py` → tabla `viento_open_meteo_hexagonos` (se reemplaza completa en cada carga)
- **Fuente:** Open-Meteo Forecast API (`https://api.open-meteo.com/v1/forecast`), variables horarias `wind_speed_80m`, `wind_speed_120m`, `wind_direction_120m` y `wind_gusts_10m`, modelo `best_match`.
- **Rol como amenaza en el modelo de ruteo:** igual que la lluvia. La vista `aristas_aereas_volables` (`00 - DB/dijkstra.sql`) descarta toda arista aérea que cruce un hexágono con `no_volable = true` en la tabla de viento **o** en la de lluvia. El circuito de cada dron informa por separado `aristas_bloqueadas_viento` y `aristas_bloqueadas_lluvia`.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`). Un `Feature` `Polygon` por hexágono.

## Grilla y resolución

Es la misma grilla de la lluvia: 130 hexágonos de 1000 m de radio, con `hex_id` `hex_clima_<fila>_<col>`. Las dos tablas se cruzan por `hex_id`. Open-Meteo usa celdas de unos 9 a 13 km en Chile, así que varios hexágonos reciben el mismo valor (`celdas_modelo_distintas` en la metadata).

## Criterio de bloqueo

Un hexágono queda `no_volable` si, en las `ventana_horas` que empiezan en la hora actual, se cumple alguna de estas condiciones:

- **viento sostenido a la altura de vuelo** ≥ `VIENTO_UMBRAL_KMH` (por defecto **36 km/h**, unos 10 m/s). Para cada hora se toma el mayor valor entre 80 m y 120 m sobre el suelo, que es la franja donde vuela un dron (el techo en Chile está cerca de 120 m).
- **ráfagas** ≥ `VIENTO_UMBRAL_RAFAGA_KMH` (por defecto **43 km/h**, unos 12 m/s). Open-Meteo solo entrega ráfagas a 10 m. A la altura de vuelo suelen ser más fuertes, así que este dato subestima el riesgo.

Los valores por defecto corresponden a la tolerancia típica de un dron comercial mediano. Conviene reemplazarlos por la que indique el fabricante del dron que se use.

| Variable de entorno | Por defecto | Uso |
|---|---|---|
| `VIENTO_UMBRAL_KMH` | `36` | Umbral de viento sostenido (km/h) |
| `VIENTO_UMBRAL_RAFAGA_KMH` | `43` | Umbral de ráfagas (km/h) |
| `VIENTO_VENTANA_HORAS` | `2` | Horas evaluadas desde la hora actual |
| `VIENTO_SIMULADO` | vacío | `"lon,lat,radio_m"`: fuerza viento fuerte en un círculo para probar el ruteo. Ejemplo: `VIENTO_SIMULADO="-70.7992,-33.5076,1500" ./main.sh` aísla el nodo 7 y también la base 2 (52A Rinconada, a 860 m), así que el dron 2 no puede despegar |

Los datos son una foto del momento de la extracción. Para usarlos en operación hay que volver a correr el ETL y la carga antes de cada vuelo.

## Bloque `metadata`

| Campo | Descripción |
|---|---|
| `fuente`, `endpoint`, `descripcion`, `crs` | Origen y propósito del dataset |
| `bbox_consulta` | `[min_lon, min_lat, max_lon, max_lat]` cubierto por la grilla |
| `tamanio_hexagono_m` | Radio del hexágono (centro a vértice) |
| `ventana_horas`, `umbral_kmh`, `umbral_rafaga_kmh` | Parámetros usados |
| `altura_viento_m`, `altura_rafaga_m` | Alturas sobre el suelo de las variables consultadas (`[80, 120]` y `10`) |
| `simulacion` | `null` o `{lon, lat, radio_m}` si se usó `VIENTO_SIMULADO` |
| `celdas_modelo_distintas` | Cuántas celdas distintas del modelo cubren la grilla |
| `total_hexagonos`, `total_no_volables` | Conteos |
| `fecha_extraccion_utc` | Cuándo se ejecutó el ETL |

## Propiedades (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador del hexágono (clave única; el mismo de la lluvia) |
| `centro_lon`, `centro_lat` | flotante | Centro del hexágono (punto consultado) |
| `celda_modelo_lon`, `celda_modelo_lat` | flotante | Centro de la celda del modelo que respondió Open-Meteo |
| `viento_actual_kmh` | flotante o `null` | Viento a la altura de vuelo en la hora actual |
| `viento_max_kmh` | flotante o `null` | Máximo de la ventana a la altura de vuelo |
| `rafaga_max_kmh` | flotante o `null` | Ráfaga máxima de la ventana (10 m) |
| `direccion_grados` | flotante o `null` | Desde dónde sopla el viento (grados desde el norte, a 120 m), en la hora de mayor viento |
| `hora_desde`, `hora_hasta` | texto ISO (hora local de Santiago) | Primera y última hora evaluadas |
| `ventana_horas`, `umbral_kmh`, `umbral_rafaga_kmh` | | Parámetros con que se evaluó |
| `simulado` | booleano | `true` si el bloqueo viene de `VIENTO_SIMULADO` |
| `no_volable` | booleano | `true` = el dron no puede cruzar esta zona |
| `motivo` | texto o `null` | Qué umbral se superó |
| `tamanio_hexagono_m` | entero | Radio del hexágono |
| `fecha_extraccion_utc` | texto ISO 8601 | Momento de la extracción |
| `fuente` | texto | `Open-Meteo Forecast API` |
