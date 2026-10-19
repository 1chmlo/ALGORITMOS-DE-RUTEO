# robo_con_violencia_semanal_hexagonos.geojson

Grilla de hexágonos de **robos con violencia** (código STOP `EVE_ROB_VI`) de toda la Región Metropolitana en una **ventana corta de 7 días**, de la plataforma **STOP** de Carabineros de Chile (https://stop.carabineros.cl).

Es la amenaza dinámica del problema: el delito se desplaza, y la infraestructura (comisarías, puntos críticos conocidos) puede quedar desactualizada y dejar sin supervisión zonas nuevas. La capa de **metadata** (`02 - Metadata`, 90 días) muestra dónde se concentra el delito; esta capa muestra dónde ocurre **ahora**.

- **Generado por:** `etl_robo_con_violencia_semanal.py` (genera también `robo_con_violencia_semanal_centroides.geojson`). Es la misma lógica de `02 - Metadata/etl_robo_con_violencia.py`, con otra ventana y otros nombres de salida.
- **Cargado a la BD por:** `carga_robo_con_violencia_semanal_hexagonos.py` → tabla `robo_con_violencia_semanal_hexagonos`. La tabla se **reemplaza completa** en cada carga.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Polygon` por cada hexágono con al menos un caso en la ventana.

## Relación con la capa de metadata

La grilla es la misma (zoom 12, hexágonos de 1200 m de punta a punta, ~0,94 km²) y el `hex_id` se calcula igual, así que **los hexágonos de ambas capas coinciden y se cruzan por `hex_id`**. Como los 7 días están contenidos en los 90, todo hexágono de esta capa existe también en la de metadata: lo que cambia es *cuántos* casos tiene, no si existe. Para detectar zonas que se calientan hay que comparar `cantidad` de esta capa con el ritmo de la de 90 días (por ejemplo, `cantidad_90d / 90` casos por día contra `cantidad_semana / 6`), no buscar hexágonos "nuevos".

## Cómo se obtiene

1. `POST /serviceCall4/{bbox}/EVE_ROB_VI/12/{desde}/{hasta}` sobre el bbox de la RM, con `desde = hoy - 7 días` y `hasta = hoy`.
2. **Rezago de STOP:** los datos llegan con ~2 días de retraso, por lo que en la práctica la ventana contiene ~6 días de casos. `metadata.fecha_max_con_datos` indica el último día con casos.
3. Se descartan los hexágonos fuera de la RM con el polígono regional de OpenStreetMap/Nominatim, y el ETL falla si STOP devuelve un tamaño de hexágono distinto de 1200 m.

**Cuidado con `nivel` y `rango`:** STOP calcula los rangos de la leyenda con los datos de cada consulta (aquí `1 - 3`, `4 - 6`, `7 - 12`, `13 - 23`; en la de 90 días van hasta 386). Por eso `nivel`, `rango` y `color` **no son comparables entre esta capa y la de metadata**; para comparar usa `cantidad`. Con 7 días los conteos son bajos: más de la mitad de los hexágonos tiene un solo caso, así que un hexágono aislado con 1 o 2 casos es ruido.

## Bloque `metadata`

| Campo | Tipo | Descripción |
|---|---|---|
| `fuente` | texto | Plataforma y endpoint consultado |
| `codigo_delito` | texto | `EVE_ROB_VI` |
| `zoom` | entero | Zoom enviado a STOP (`12`); determina el tamaño del hexágono |
| `tamanio_hexagono_m` | entero | Tamaño del hexágono en metros, de vértice a vértice (`1200`) |
| `bbox_consulta` | 4 flotantes | `[min_lon, min_lat, max_lon, max_lat]` consultado |
| `ventana_dias` | entero | Largo de la ventana solicitada (`7`) |
| `periodo_desde`, `periodo_hasta` | texto `YYYY-MM-DD` | Ventana consultada |
| `fecha_max_con_datos` | texto `YYYY-MM-DD` | Último día con casos registrados (por el rezago de STOP) |
| `eventos_en_periodo` | entero | Casos que STOP cuenta en todo el bbox, incluidos los de fuera de la RM |
| `total_hexagonos` | entero | Hexágonos dentro de la RM |
| `total_eventos_rm` | entero | Suma de `cantidad` de los hexágonos de la RM |
| `leyenda` | arreglo | Rangos de la leyenda de STOP: `label`, `min`, `max`, `color`, `color_border`. El rango i incluye `min < cantidad <= max`, salvo el primero, que parte en 1 |

## Propiedades de cada `Feature`

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador estable del hexágono: `hex_rm_` + hash del centroide; es el mismo de `robo_con_violencia_hexagonos` (clave única en la BD y llave de cruce con la metadata) |
| `stop_id` | texto | Índice correlativo de STOP en esa respuesta; **no es estable** entre ejecuciones |
| `codigo_delito` | texto | `EVE_ROB_VI` |
| `tipo_delito` | texto | `Robo con violencia` |
| `cantidad` | entero | Casos de robo con violencia dentro del hexágono en la ventana |
| `nivel` | entero | Posición del rango de la leyenda de esta consulta: 1 es el más bajo y `niveles_total` el más alto |
| `niveles_total` | entero | Cantidad de rangos de la leyenda de esta consulta |
| `rango` | texto | Etiqueta del rango, p. ej. `"4 - 6"` |
| `color` | texto | Color de relleno `rgba(...)` que usa STOP para ese rango |
| `color_border` | texto | Color `rgba(...)` del borde |
| `fecha_min`, `fecha_max` | texto `YYYY-MM-DD` | Primer y último caso registrado en el hexágono dentro de la ventana |
| `periodo_desde`, `periodo_hasta` | texto `YYYY-MM-DD` | Ventana consultada (se repite en cada hexágono) |
| `ventana_dias` | entero | `7` |
| `tamanio_hexagono_m` | entero | `1200` |
| `fuente` | texto | `STOP Carabineros de Chile` |
