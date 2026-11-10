# zonas_restringidas_overpass.geojson

Este archivo contiene las **zonas de exclusión aérea permanentes** para el dron en Maipú y sus alrededores. Forman parte de la infraestructura: definen por dónde **no** puede pasar ninguna ruta (punto 2).

- **Generado por:** `etl_zonas_restringidas_overpass.py`
- **Cargado a la BD por:** `carga_zonas_restringidas.py`, en la tabla `zonas_restringidas` (se reemplaza completa). La zona de exclusión `geom` se calcula en PostGIS ampliando la geometría de OSM con `radio_exclusion_m` (`ST_Buffer` sobre `geography`).
- **Fuente:** OpenStreetMap vía Overpass API. Se buscan `aeroway=aerodrome|heliport|helipad`, `landuse=military`, `military=*` y `amenity=prison` en el rectángulo `(-33.62, -70.95)` a `(-33.42, -70.68)`.
- **Uso:** la API de ruteo las trata como obstáculos duros del grafo de visibilidad. Ninguna de las 4 técnicas las cruza.
- **Respaldo:** si Overpass no responde, se conserva el archivo anterior, que está versionado en el repositorio.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84. Las geometrías son `Point` (helipuertos mapeados como nodo), `Polygon` (vías cerradas), `LineString` o `MultiPolygon` (relaciones).

## Campos

| Campo | Descripción |
|---|---|
| `osm_ref` | `node/<id>`, `way/<id>` o `relation/<id>` en OSM |
| `tipo` | `aerodromo`, `helipuerto`, `militar` o `carcel` |
| `nombre` | Nombre en OSM (puede ser nulo) |
| `motivo` | Norma o razón de la restricción |
| `radio_exclusion_m` | Distancia que se agrega alrededor de la geometría |
| `fuente` | `OpenStreetMap via Overpass API` |

## Radios de exclusión

| Tipo | Radio por defecto | Variable de entorno | Motivo |
|---|---|---|---|
| Aeródromo | 1000 m | `RADIO_AERODROMO_M` | DAN 151: prohibido operar RPA cerca de aeródromos |
| Helipuerto | 150 m | `RADIO_HELIPUERTO_M` | Helipuertos de hospitales y clínicas (p. ej. Clínica Indisa Maipú) |
| Militar | 50 m | `RADIO_MILITAR_M` | Espacio aéreo restringido |
| Cárcel | 50 m | `RADIO_CARCEL_M` | Sobrevuelo prohibido |

## Bloque `metadata`

Incluye `fuente`, `descripcion`, `crs`, `bbox_consulta`, `radios_exclusion_m`, `fecha_extraccion_utc` y `total_zonas`.
