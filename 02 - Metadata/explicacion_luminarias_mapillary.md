# Documentación y Estructura del Archivo `luminarias_mapillary.json`

## 1. Propósito del Archivo en el Problema de Ruteo
Este archivo almacena en formato **GeoJSON (`FeatureCollection`)** el catastro georreferenciado de **luminarias públicas (`object--street-light`)** detectadas mediante visión por computador en la **Comuna de Maipú, Región Metropolitana, Chile**, utilizando la **API Graph v4 de Mapillary**.

En el contexto del algoritmo de ruteo:
- **Zonas iluminadas**: Aristas (calles/pasajes) que cuentan con luminarias cercanas dentro de su radio de cobertura (`25 m`) presentan menor riesgo de delitos nocturnos y, por tanto, reciben una bonificación o menor penalización en su función de costo.
- **Zonas sin luz (+ Delitos)**: Aristas sin presencia de luminarias cercanas se identifican como tramos oscuros con mayor vulnerabilidad delictual, incrementando el peso/costo de transitar por dichas vías.

---

## 2. Estructura General del JSON (GeoJSON `FeatureCollection`)

El archivo raíz es un objeto JSON con tres claves principales:

| Campo Raíz | Tipo | Descripción |
| :--- | :--- | :--- |
| `type` | `string` | Tipo de objeto GeoJSON estándar. Valor fijo: `"FeatureCollection"`. |
| `metadata` | `object` | Metadatos de trazabilidad sobre la consulta a la API, zona geográfica y resumen estadístico de la extracción. |
| `features` | `array<object>` | Lista de objetos `Feature` GeoJSON; cada elemento representa una luminaria única georreferenciada. |

---

## 3. Detalle del Bloque `metadata`

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `string` | Nombre del proveedor de datos (`"Mapillary Graph API v4"`). |
| `endpoint` | `string` | URL del endpoint consultado (`"https://graph.mapillary.com/map_features"`). |
| `filtro_objeto` | `string` | Clase semántica filtrada en la API (`"object--street-light"`). |
| `descripcion` | `string` | Explicación del propósito del dataset en el modelo de ruteo. |
| `comuna` | `string` | Comuna de estudio (`"Maipú"`). |
| `region` | `string` | Región administrativa (`"Región Metropolitana de Santiago, Chile"`). |
| `sistema_referencia` | `string` | Sistema de coordenadas espaciales utilizado (`"EPSG:4326 (WGS 84)"`). |
| `bbox` | `object` | Límites geográficos consultados (`min_lon`, `min_lat`, `max_lon`, `max_lat` en grados decimales). |
| `fecha_extraccion_utc` | `string` (ISO 8601) | Fecha y hora exacta (UTC) en que se ejecutó la extracción. |
| `total_luminarias` | `integer` | Cantidad total de luminarias únicas extraídas sin duplicados. |
| `resumen_confianza` | `object` | Conteo de luminarias según su nivel de confianza (`ALTA`, `MEDIA`, `BAJA`). |

---

## 4. Detalle de cada Elemento en `features[]`

Cada elemento dentro del arreglo `features` posee la estructura estándar GeoJSON:

### 4.1 Campos de Nivel Superior del `Feature`
| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `type` | `string` | Valor fijo `"Feature"`. |
| `id` | `string` | Identificador único global del objeto (`map_feature`) en Mapillary. |
| `geometry.type` | `string` | Tipo de geometría espacial. Valor fijo: `"Point"`. |
| `geometry.coordinates` | `array<number>` | Coordenadas en formato `[longitud, latitud]` (estándar GeoJSON WGS84 / EPSG:4326). |

### 4.2 Campos dentro de `properties`
| Propiedad | Tipo | Descripción y Significado de cada Valor |
| :--- | :--- | :--- |
| `mapillary_id` | `string` | ID único de la luminaria en Mapillary (clave primaria natural para carga en BD). |
| `object_value` | `string` | Categoría del objeto detectado (`"object--street-light"`). |
| `object_type` | `string` | Tipo de detección en Mapillary (`"panoptic"` o `"point"`). |
| `comuna` | `string` | Comuna a la que pertenece el registro (`"Maipú"`). |
| `region` | `string` | Región a la que pertenece el registro (`"Región Metropolitana de Santiago"`). |
| `latitud` | `number (float)` | Latitud geográfica en grados decimales (WGS84). |
| `longitud` | `number (float)` | Longitud geográfica en grados decimales (WGS84). |
| `aligned_direction` | `number (float)` \| `null` | Orientación estimada de la luminaria en grados acimutales (`0°` a `360°`, donde `0°` es Norte). |
| `first_seen_at` | `string` (ISO 8601) | Fecha y hora de la primera imagen en que Mapillary detectó esta luminaria. |
| `last_seen_at` | `string` (ISO 8601) | Fecha y hora de la última imagen en que Mapillary confirmó la presencia de la luminaria. |
| `detections_count` | `integer` | Número de capturas fotográficas independientes que respaldan la triangulación de la luminaria. |
| `sample_image_ids` | `array<string>` | Lista de hasta 5 IDs de imágenes de Mapillary donde se observa la luminaria (permite auditoría visual). |
| `confianza_deteccion` | `string` | Clasificación de certeza basada en `detections_count`:<br>- `"ALTA"`: $\ge 5$ imágenes<br>- `"MEDIA"`: $2$ a $4$ imágenes<br>- `"BAJA"`: $1$ imagen |
| `factor_iluminacion` | `number (float)` | Ponderador normalizado (`0.5`, `0.75` o `1.0`) utilizado para ponderar la calidad de iluminación sobre las aristas cercanas del grafo vial. |
| `radio_cobertura_m` | `number (float)` | Radio de influencia lumínica estimado en metros (`25.0` m) para cruzar espacialmente (`ST_DWithin`) con las aristas de la red vial en PostGIS. |
| `impacto_seguridad` | `string` | Glosa descriptiva del efecto del registro sobre el modelo de riesgo delictual nocturno. |

---

## 5. Ejemplo de un Registro Individual (`Feature`)

```json
{
  "type": "Feature",
  "id": "534540949421156",
  "geometry": {
    "type": "Point",
    "coordinates": [
      -70.74515,
      -33.50013
    ]
  },
  "properties": {
    "mapillary_id": "534540949421156",
    "object_value": "object--street-light",
    "object_type": "panoptic",
    "comuna": "Maipú",
    "region": "Región Metropolitana de Santiago",
    "latitud": -33.50013,
    "longitud": -70.74515,
    "aligned_direction": 169.08609824482,
    "first_seen_at": "2024-11-18T12:38:01+0000",
    "last_seen_at": "2024-11-18T12:38:01+0000",
    "detections_count": 7,
    "sample_image_ids": [
      "1084771756533438",
      "2112108702542007",
      "1031174372115994",
      "503033559424240",
      "1519997261888635"
    ],
    "confianza_deteccion": "ALTA",
    "factor_iluminacion": 1.0,
    "radio_cobertura_m": 25.0,
    "impacto_seguridad": "Presencia de luminaria reduce riesgo nocturno de delito en un radio de 25m; aristas sin luminarias cercanas se clasifican como zonas oscuras (+riesgo delictual)."
  }
}
```
