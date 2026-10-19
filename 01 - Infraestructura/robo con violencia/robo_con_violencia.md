# robo_con_violencia_maipu.geojson

Hexágonos de concentración de **Robos con violencia (`EVE_ROB_VI`)** en la **Comuna de Maipú** (Región Metropolitana), extraídos desde la plataforma oficial **STOP (Sistema Táctico de Operación Policial)** de Carabineros de Chile.

- **Generado por:** `etl_robo_con_violencia.py`
- **Cargado a la BD por:** `carga_robo_con_violencia.py` → tabla `robo_con_violencia_stop`
- **Fuente:** Geoportal STOP de Carabineros de Chile (`https://stop.carabineros.cl`), endpoint `POST /serviceCall4/{bbox}/EVE_ROB_VI/{zoom}/{date_desde}/{date_hasta}` con ventana móvil oficial de los últimos 90 días y resolución de grilla máxima (`zoom = 15`, hexágonos de `150 m`).
- **Recorte comunal:** Los hexágonos devueltos por el *bounding box* se filtran espacialmente contra el polígono administrativo oficial de la comuna de **Maipú** (OpenStreetMap / Nominatim), conservando únicamente aquellos cuyo centroide o vértices pertenecen a la comuna.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Polygon` (6 lados) por hexágono con delitos registrados.

## Bloque `metadata`

| Campo | Tipo | Descripción |
|---|---|---|
| `fuente` | texto | Nombre y URL de la plataforma oficial (`STOP - Carabineros de Chile`) |
| `endpoint` | texto | Endpoint interno consultado (`serviceCall4`) |
| `codigo_delito` | texto | Código interno de STOP para Robos con Violencia (`EVE_ROB_VI`) |
| `delito` | texto | Glosa del delito (`Robos con violencia`) |
| `comuna`, `region` | texto | `Maipú`, `Región Metropolitana de Santiago` |
| `crs` | texto | Sistema de referencia espacial (`EPSG:4326 (WGS84)`) |
| `tamanio_hexagono_m` | entero | Tamaño del hexágono en metros (`150`) |
| `periodo_fecha_min`, `periodo_fecha_max` | texto (`YYYY-MM-DD`) | Fechas mínima y máxima de los eventos policiales incluidos en la ventana de 90 días |
| `bbox_consulta` | arreglo de 4 flotantes | `[min_lon, min_lat, max_lon, max_lat]` consultado |
| `total_hexagonos_maipu` | entero | Total de hexágonos con robos con violencia dentro de Maipú (`431`) |
| `total_robos_con_violencia_maipu` | entero | Suma total de robos con violencia en los hexágonos de Maipú (`687`) |
| `leyenda_jenks` | arreglo de objetos | Rangos de quiebres naturales (Jenks) y colores entregados por STOP |
| `fecha_extraccion` | texto (ISO 8601) | Fecha y hora de ejecución del ETL |

## Propiedades de cada `Feature` (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador único determinístico del hexágono en Maipú (clave única en la BD) |
| `stop_id` | texto | Índice correlativo entregado por la respuesta de STOP |
| `comuna` | texto | `Maipú` |
| `region` | texto | `Región Metropolitana de Santiago` |
| `codigo_delito` | texto | `EVE_ROB_VI` |
| `tipo_delito` | texto | `Robo con violencia` |
| `cantidad` | entero | Cantidad de casos policiales de robo con violencia registrados dentro del hexágono en los últimos 90 días |
| `severidad` | texto | Nivel de concentración según quiebres naturales de Jenks: `baja` (1-3), `media` (4-7), `alta` (8-12) o `muy_alta` (13+) |
| `rango_jenks` | texto | Etiqueta del rango de la leyenda oficial de STOP (p. ej. `"1 - 3"`, `"4 - 7"`, `"8 - 12"`, `"13 - 20"`) |
| `color` | texto | Color RGBA de relleno asignado por STOP según la densidad delictual |
| `color_border` | texto | Color RGBA del borde del hexágono |
| `fecha_min` | texto (`YYYY-MM-DD`) | Fecha del primer robo con violencia registrado en ese hexágono dentro del período |
| `fecha_max` | texto (`YYYY-MM-DD`) | Fecha del robo con violencia más reciente registrado en ese hexágono |
| `tamanio_hexagono_m` | entero | Diámetro/lado de agregación del hexágono en metros (`150`) |
| `centroide_lon`, `centroide_lat` | flotante | Coordenadas `[longitud, latitud]` del centroide del hexágono |
| `fuente` | texto | `STOP Carabineros de Chile` |
