# robo_con_violencia_semanal_centroides.geojson

Centroide de cada hexágono de `robo_con_violencia_semanal_hexagonos.geojson` (robos con violencia de los últimos 7 días, STOP): un punto por hexágono, para cruzar la amenaza con la red vial (pgRouting) sin trabajar con polígonos. Los polígonos y su color están en el archivo de hexágonos; este solo duplica lo mínimo para usarlo de forma independiente.

- **Generado por:** `etl_robo_con_violencia_semanal.py`
- **Cargado a la BD por:** `carga_robo_con_violencia_semanal_centroides.py` → tabla `robo_con_violencia_semanal_centroides`. Debe cargarse **después** de los hexágonos: `hex_id` es clave foránea a `robo_con_violencia_semanal_hexagonos` (con `ON DELETE CASCADE`). La tabla se reemplaza completa en cada carga.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Point` por hexágono. Tiene el mismo bloque `metadata` que el archivo de hexágonos (ver `robo_con_violencia_semanal_hexagonos.md`).

El centroide es el promedio de los seis vértices del hexágono, redondeado a 6 decimales, y es idéntico al del mismo `hex_id` en `robo_con_violencia_centroides` (metadata, 90 días).

## Propiedades de cada `Feature`

| Campo | Tipo | Descripción |
|---|---|---|
| `hex_id` | texto | Identificador del hexágono al que pertenece (clave única y foránea en la BD; mismo `hex_id` que en la capa de 90 días) |
| `cantidad` | entero | Casos de robo con violencia del hexágono en la ventana de 7 días |
| `nivel` | entero | Posición del rango de la leyenda de esta consulta; **no comparable** con el `nivel` de la capa de 90 días |
| `niveles_total` | entero | Cantidad de rangos de la leyenda de esta consulta |
| `color` | texto | Color `rgba(...)` del rango, el mismo del hexágono |
