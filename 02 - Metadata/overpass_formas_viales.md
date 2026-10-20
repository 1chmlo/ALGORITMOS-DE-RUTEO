# overpass_formas_viales.geojson

Morfología y geometría de carreteras, autopistas, enlaces de salida/entrada (`*_link`), rotondas y curvas pronunciadas en **Maipú y sus corredores viales** (Autopista del Sol / Ruta 78, Américo Vespucio Sur, Camino a Melipilla, Av. Pajaritos, Camino a Rinconada).

- **Generado por:** `etl_overpass_formas_viales.py`
- **Cargado a la BD por:** `carga_overpass_formas_viales.py` → tabla `overpass_formas_viales`
- **Fuente:** OpenStreetMap mediante **Overpass API** (`https://overpass-api.de/api/interpreter`), filtrando vías de categoría `motorway`, `motorway_link`, `trunk`, `trunk_link`, `primary`, `primary_link`, `secondary` y `secondary_link`.
- **Justificación en el modelo de ruteo:** Estudios criminológicos en EE.UU. y el análisis espacial de encerronas en la RM demuestran que los robos violentos de vehículos se concentran en **salidas/enlaces de autopistas, rotondas y curvas cerradas**, donde la geometría obliga a disminuir la velocidad y reduce las vías de escape.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `LineString` por tramo vial.

## Bloque `metadata`

El archivo trae, además de los `features`, un bloque `metadata` en la raíz:

| Campo | Tipo | Descripción |
|---|---|---|
| `fuente` | texto | `OpenStreetMap via Overpass API` |
| `descripcion` | texto | Propósito del dataset en el modelo de ruteo |
| `bbox_sur_oeste_norte_este` | arreglo de 4 flotantes | Ventana consultada, **en el orden de Overpass** `[sur_lat, oeste_lon, norte_lat, este_lon]` (`[-33.56, -70.825, -33.465, -70.705]`). Ojo: no es el orden `[min_lon, min_lat, max_lon, max_lat]` de los otros archivos |
| `crs` | texto | Sistema de referencia (`EPSG:4326 (WGS84)`) |
| `total_tramos` | entero | Cantidad de tramos viales (`Feature`) del archivo |
| `resumen_formas_viales` | objeto | Conteo de tramos por `forma_vial` (`recta`, `salida_recta`, `salida_curva`, `curva_pronunciada`, `rotonda`) |
| `fecha_extraccion_utc` | texto ISO 8601 | Cuándo se ejecutó el ETL |

## Propiedades (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `osm_id` | entero | Identificador único del `way` en OpenStreetMap (clave única en la BD) |
| `nombre` | texto | Nombre de la vía o código de ruta (p. ej. `Autopista del Sol`, `Avenida Américo Vespucio`) |
| `ref_via` | texto o `null` | Numeración oficial de la ruta (`78`, `70`, `CH-76`, etc.) |
| `highway` | texto | Clasificación OSM de la vía (`motorway`, `motorway_link`, `trunk`, `primary`, `secondary`, etc.) |
| `junction` | texto o `null` | Tipo de intersección especial si corresponde (`roundabout`, `circular`, etc.) |
| `comuna` | texto | `Maipú` |
| `oneway` | booleano | `true` si la vía tiene sentido único de circulación |
| `lanes` | entero o `null` | Cantidad de pistas reportadas en OSM |
| `maxspeed_kmh` | entero o `null` | Velocidad máxima legal reportada en km/h |
| `es_enlace_salida` | booleano | `true` si corresponde a una rampa, salida o enlace de incorporación (`*_link`) |
| `es_curva_pronunciada` | booleano | `true` si el ángulo máximo de giro $\ge 25^\circ$, el giro acumulado $\ge 45^\circ$ o el índice de sinuosidad $\ge 1.12$ |
| `forma_vial` | texto | Clasificación morfológica del tramo: `salida_curva`, `rotonda`, `salida_recta`, `curva_pronunciada` o `recta` |
| `longitud_m` | flotante | Longitud real del tramo en metros calculada mediante distancia Haversine sobre sus vértices |
| `distancia_recta_m` | flotante | Distancia en línea recta en metros entre el nodo inicial y el nodo final del tramo |
| `indice_sinuosidad` | flotante | Razón $\text{longitud\_m} / \text{distancia\_recta\_m}$ ($\ge 1.0$; valores mayores indican mayor curvatura o lazo) |
| `angulo_giro_max_grados` | flotante | Mayor cambio de rumbo entre segmentos consecutivos del tramo ($0^\circ$ a $180^\circ$) |
| `angulo_giro_total_grados` | flotante | Suma acumulada de los cambios de rumbo a lo largo del tramo |
| `factor_riesgo_geom` | flotante | Ponderador normalizado (`0.0` a `1.0`) del riesgo de encerrona asociado a la geometría del tramo |
| `centroide_lon`, `centroide_lat` | flotante | Coordenadas `[longitud, latitud]` del punto medio del tramo |
