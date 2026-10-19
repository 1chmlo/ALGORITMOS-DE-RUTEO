# cortes_ruta_tomtom.geojson

Cortes de ruta totales activos (**Road Closed**, categoría `iconCategory = 8`) en la **Región Metropolitana y Comuna de Maipú**, extraídos en tiempo real desde **TomTom Traffic Incidents API v5**.

- **Generado por:** `etl_cortes_ruta_tomtom.py`
- **Cargado a la BD por:** `carga_cortes_ruta_tomtom.py` → tabla `cortes_ruta_tomtom`
- **Fuente:** TomTom Traffic Services v5 (`https://api.tomtom.com/traffic/services/5/incidentDetails`), filtrado por `categoryFilter=8` (*Road Closed*) y `timeValidityFilter=present`.
- **Rol como amenaza (falla) en el modelo de ruteo:** Un corte de ruta total representa una falla o bloqueo físico activo sobre la red vial, impidiendo el flujo vehicular por las aristas intersectadas o forzando desvíos hacia vías secundarias potencialmente más vulnerables.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `LineString` por tramo vial cerrado.

## Propiedades (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `incident_id` | texto | Identificador único global del incidente en TomTom (clave única en la BD) |
| `icon_category` | entero | Categoría del incidente según estándar TomTom (`8` = *Road Closed* / Corte de ruta total) |
| `tipo_amenaza` | texto | Glosa descriptiva (`Corte de ruta total`) |
| `descripcion_evento` | texto | Descripción entregada por TomTom en español (p. ej. `Cerrado`) |
| `codigo_evento` | entero | Código estándar ALERT-C / TomTom del evento (p. ej. `401` = vía cerrada) |
| `magnitud_retraso` | entero | Magnitud de impacto según escala TomTom (`4` = cierre / indefinido) |
| `desde_via` | texto o `null` | Nombre de la calle o intersección donde comienza el corte (`from`) |
| `hasta_via` | texto o `null` | Nombre de la calle o intersección donde termina el corte (`to`) |
| `numeros_ruta` | texto o `null` | Códigos de ruta asociados si aplica (`roadNumbers`) |
| `longitud_m` | flotante | Extensión del tramo vial cortado en metros (`length`) |
| `retraso_seg` | entero o `null` | Retraso reportado en segundos (`null` cuando el cierre es total) |
| `probabilidad` | texto | Certeza del incidente reportada por TomTom (`certain`, `probable`, etc.) |
| `validez_temporal` | texto | Estado temporal del corte (`present`) |
| `fecha_inicio` | texto (ISO 8601) o `null` | Fecha y hora de inicio del corte de ruta (`startTime`) |
| `fecha_fin` | texto (ISO 8601) o `null` | Fecha y hora estimada de término del corte (`endTime`) |
| `en_maipu` | booleano | `true` si el tramo cortado se ubica dentro de Maipú o sus accesos directos |
| `bloqueo_total` | booleano | `true` (indica que la arista afectada no es transitable) |
| `centroide_lon`, `centroide_lat` | flotante | Coordenadas `[longitud, latitud]` del punto medio del corte |
| `fuente` | texto | `TomTom Traffic Incidents API v5` |
