# robo_con_violencia_hexagonos.geojson

Grilla de hexágonos de **robos con violencia** (código STOP `EVE_ROB_VI`, capa "4.1 Robos con violencia") de toda la Región Metropolitana, de la plataforma **STOP** de Carabineros de Chile (https://stop.carabineros.cl). Cada hexágono trae la cantidad de casos de los últimos 90 días y el color con que el visor lo pinta.

- **Generado por:** `etl_robo_con_violencia.py` (genera también `robo_con_violencia_centroides.geojson`)
- **Cargado a la BD por:** `carga_robo_con_violencia_hexagonos.py` → tabla `robo_con_violencia_hexagonos`. La tabla se **reemplaza completa** en cada carga, porque STOP entrega una ventana móvil y no un histórico.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Polygon` (hexágono) por cada hexágono con al menos un caso.

## Cómo se obtiene

1. Un `POST /serviceCall4/{bbox}/EVE_ROB_VI/12/{desde}/{hasta}` sobre el bbox de la RM, con las cookies de sesión y el `XSRF-TOKEN` de la portada. El resultado depende de la fecha de ejecución: la ventana son los 91 días anteriores.
2. Se descartan los hexágonos fuera de la RM (el bbox incluye esquinas de las regiones vecinas) usando el polígono regional de OpenStreetMap/Nominatim. Se conserva el hexágono si su centroide o alguno de sus vértices está dentro.
3. El ETL falla si STOP devuelve un tamaño de hexágono distinto de 1200 m.

**Tamaño de la grilla:** STOP solo ofrece tamaños de 150 m × 2ⁿ (150, 300, 600, 1200, 2400 m…), según el zoom del mapa. No existe 1000 m. Se usa el zoom 12: 1200 m de punta a punta (lado de 600 m, ~1039 m de alto, ~0,94 km²), la grilla más cercana a 1 km.

**Rangos de la leyenda:** STOP calcula los rangos de color (quiebres naturales de Jenks) a partir de los datos de cada consulta, así que cambian con el bbox, el zoom y la fecha (p. ej. `1 - 4` en una consulta de solo Maipú y `1 - 12` en la RM). Por eso se guarda `nivel` (1 = menor concentración, N = mayor) junto al rango: los niveles solo son comparables dentro de un mismo archivo.

## Bloque `metadata`

| Campo | Tipo | Descripción |
|---|---|---|
| `fuente` | texto | Plataforma y endpoint consultado |
| `codigo_delito` | texto | `EVE_ROB_VI` |
| `zoom` | entero | Zoom enviado a STOP (`12`); determina el tamaño del hexágono |
| `tamanio_hexagono_m` | entero | Tamaño del hexágono en metros, de vértice a vértice (`1200`) |
| `bbox_consulta` | 4 flotantes | `[min_lon, min_lat, max_lon, max_lat]` consultado |
| `periodo_desde`, `periodo_hasta` | texto `YYYY-MM-DD` | Ventana consultada |
| `eventos_en_periodo` | entero | Casos que STOP cuenta en todo el bbox, incluidos los de fuera de la RM |
| `total_hexagonos` | entero | Hexágonos que quedan dentro de la RM |
| `total_eventos_rm` | entero | Suma de `cantidad` de los hexágonos de la RM |
| `leyenda` | arreglo | Rangos de la leyenda de STOP: `label`, `min`, `max`, `color`, `color_border`. El rango i incluye `min < cantidad <= max`, salvo el primero, que parte en 1 |

## Propiedades de cada `Feature`

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador estable del hexágono: `hex_rm_` + hash del centroide (clave única en la BD; une este archivo con el de centroides). La grilla de STOP es global, así que es estable entre ejecuciones y entre consultas con distinto bbox, mientras no cambie el zoom |
| `stop_id` | texto | Índice correlativo que entrega STOP en esa respuesta; **no es estable** entre ejecuciones |
| `codigo_delito` | texto | `EVE_ROB_VI` |
| `tipo_delito` | texto | `Robo con violencia` |
| `cantidad` | entero | Casos de robo con violencia dentro del hexágono en el período |
| `nivel` | entero | Posición del rango de la leyenda al que pertenece `cantidad`: 1 es el más bajo y `niveles_total` el más alto |
| `niveles_total` | entero | Cantidad de rangos de la leyenda (hoy 5) |
| `rango` | texto | Etiqueta del rango, p. ej. `"13 - 39"` |
| `color` | texto | Color de relleno `rgba(...)` que usa STOP para ese rango |
| `color_border` | texto | Color `rgba(...)` del borde |
| `fecha_min`, `fecha_max` | texto `YYYY-MM-DD` | Primer y último caso registrado en el hexágono |
| `periodo_desde`, `periodo_hasta` | texto `YYYY-MM-DD` | Ventana consultada (se repite en cada hexágono) |
| `tamanio_hexagono_m` | entero | `1200` |
| `fuente` | texto | `STOP Carabineros de Chile` |
