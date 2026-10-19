# robo_con_violencia_centroides.geojson

Centroide de cada hexágono de `robo_con_violencia_hexagonos.geojson`: un punto por hexágono, para cruzar los robos con violencia con la red vial (pgRouting) sin trabajar con polígonos. Los polígonos y su color están en el archivo de hexágonos; este archivo solo duplica lo mínimo para usarlo de forma independiente.

- **Generado por:** `etl_robo_con_violencia.py`
- **Cargado a la BD por:** `carga_robo_con_violencia_centroides.py` → tabla `robo_con_violencia_centroides`. Debe cargarse **después** de los hexágonos: `hex_id` es clave foránea a `robo_con_violencia_hexagonos` (con `ON DELETE CASCADE`). La tabla se reemplaza completa en cada carga.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Point` por hexágono. Tiene el mismo bloque `metadata` que el archivo de hexágonos (ver `robo_con_violencia_hexagonos.md`).

El centroide es el promedio de los seis vértices del hexágono, redondeado a 6 decimales; cae siempre dentro de su hexágono.

## Propiedades de cada `Feature`

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador del hexágono al que pertenece (clave única y foránea en la BD) |
| `cantidad` | entero | Casos de robo con violencia del hexágono en el período |
| `nivel` | entero | Posición del rango de la leyenda de STOP: 1 es el más bajo y `niveles_total` el más alto |
| `niveles_total` | entero | Cantidad de rangos de la leyenda (hoy 5) |
| `color` | texto | Color `rgba(...)` del rango, el mismo del hexágono |
