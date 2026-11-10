# elevacion_terreno_hexagonos.geojson

Este archivo contiene la **elevación del terreno** sobre una grilla de hexágonos de 500 m. Sirve para que ninguna ruta atraviese un cerro más alto que el techo de vuelo del dron (punto 2, restricción por altitud).

- **Generado por:** `etl_elevacion_terreno.py`
- **Cargado a la BD por:** `carga_elevacion_terreno.py`, en la tabla `elevacion_terreno_hexagonos` (se reemplaza completa)
- **Fuente:** Open-Meteo Elevation API (`https://api.open-meteo.com/v1/elevation`), con el DEM Copernicus GLO-90 (90 m). Es gratis y no pide API key. Se consultan 100 coordenadas por solicitud, con pausas para respetar el límite de 600 llamadas por minuto.
- **Grilla:** hexágonos pointy-top de 500 m (del centro al vértice) sobre el rectángulo `(-70.93, -33.60)` a `(-70.68, -33.44)`, unos 700 hexágonos. El radio se configura con `ELEVACION_RADIO_HEX_M`. Se mide la elevación en el centro de cada hexágono.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84, un `Polygon` por hexágono.

## Uso en el ruteo

El dron vuela a altitud constante:

```
techo = elevación de la base de despegue + altura_vuelo_m
```

`altura_vuelo_m` la elige el usuario en la web, con 120 m por defecto, que es el máximo sobre el suelo según la DAN 151. La API marca como obstáculo todo hexágono con `elevacion_m ≥ techo − 30 m` (margen vertical de seguridad). Con la base 1 (489 m s.n.m.) y 120 m de altura, el techo queda en 609 m. Así se bloquean los cerros del poniente (Lo Aguirre, Lomas de Lo Aguirre), que llegan a unos 1000 m, mientras la llanura de Maipú está entre 420 y 520 m.

La misma grilla se usa como **grilla de metadatos** (valor de vigilancia por hexágono) en la API.

## Campos

| Campo | Descripción |
|---|---|
| `hex_id` | `hex_elev_<fila>_<col>`, estable mientras no cambien el rectángulo ni el radio |
| `centro_lon`, `centro_lat` | Punto consultado |
| `elevacion_m` | Elevación del terreno en m s.n.m. |
| `tamanio_hexagono_m` | Radio del hexágono |
| `fuente` | `Open-Meteo Elevation API (Copernicus GLO-90)` |

## Bloque `metadata`

Incluye `fuente`, `endpoint`, `descripcion`, `crs`, `bbox_consulta`, `tamanio_hexagono_m`, `elevacion_min_m`, `elevacion_max_m`, `fecha_extraccion_utc` y `total_hexagonos`.
