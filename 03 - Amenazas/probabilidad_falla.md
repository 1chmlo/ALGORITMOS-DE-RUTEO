# probabilidad_falla_zonas.geojson y probabilidad_falla_grafo.geojson

Este archivo calcula la **probabilidad de falla** del dron para cada amenaza, por zona, enlace y nodo (punto 5).

- **Generado por:** `probabilidad_falla.py` (se ejecuta en `main.sh` después de cargar todas las amenazas)
- **Cargado a la BD por:** el mismo script, en las tablas `probabilidad_falla_zonas`, `probabilidad_falla_aristas` y `probabilidad_falla_nodos` (se reemplazan completas)
- **Usado por:** la API de ruteo (`05 - API`), que importa el módulo y recalcula las probabilidades con los parámetros que el usuario elige en la web
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`)

## Modelo

Cada amenaza se convierte en zonas (polígonos) con una probabilidad p ∈ [0, 1]: la probabilidad de que el dron no complete la misión si cruza la zona.

| Amenaza | Zona | Fórmula | Parámetros por defecto |
|---|---|---|---|
| `lluvia` | Celda del modelo Open-Meteo (unión de sus hexágonos) | `i = min(1, precip_max / umbral_mm_h)`, `q = prob_max/100`, `p = 1 − (1 − i)(1 − peso_probabilidad·q)` | `umbral_mm_h = 0.5`, `peso_probabilidad = 0.25` |
| `viento` | Celda del modelo Open-Meteo | `r = max(viento_max/umbral_kmh, rafaga_max/umbral_rafaga_kmh)`, `p = clamp((r − inicio)/(1 − inicio))` | `36 km/h`, `43 km/h`, `inicio_riesgo = 0.7` |
| `robo_7d` | Hexágono STOP de 7 días | `p = p_max · nivel / niveles_total` | `p_max = 0.3` |
| `cortes` | Corte TomTom con un radio de 150 m | `p = min(0.95, p_base + p_por_magnitud · magnitud_retraso)` | `0.15`, `0.1` |

Por qué cada amenaza afecta al dron:
- **Lluvia:** si supera el umbral, la falla es segura. La sola probabilidad de lluvia aporta a lo más un 25 % (el pronóstico es incierto).
- **Viento:** p crece linealmente desde el 70 % del umbral hasta el umbral.
- **Robo 7 días:** riesgo de ataque o de inhibidores de señal, que se usan en encerronas.
- **Cortes de ruta:** indican una operación de emergencia en la vía, y la DAN 151 prohíbe sobrevolar emergencias y multitudes.

**Agrupación por celda:** los hexágonos de lluvia y viento que caen en la misma celda del modelo meteorológico (de 9 a 13 km) reciben exactamente el mismo pronóstico. Son **un solo evento**, no eventos independientes, así que se agrupan en una zona. Sin esta agrupación, una ruta que cruza 5 hexágonos con la misma lluvia la pagaría 5 veces.

**Enlaces y nodos**, suponiendo zonas independientes:

```
p_k(elemento) = 1 − Π_{zonas z de la amenaza k que toca} (1 − p_z)
p(elemento)   = 1 − Π_k (1 − p_k(elemento))      ← fila 'total'
```

## probabilidad_falla_zonas.geojson

Contiene un `Feature` (`Polygon`/`MultiPolygon`) por zona con p > 0.

| Campo | Descripción |
|---|---|
| `zona_id` | `<amenaza>:<origen_id>` |
| `amenaza` | `lluvia`, `viento`, `robo_7d` o `cortes` |
| `origen_id` | Celda del modelo (lluvia, viento), `hex_id` STOP o `incident_id` TomTom |
| `p` | Probabilidad de falla |
| `detalle` | Valores que originan p (precipitación, viento, robos, descripción del corte) |

## probabilidad_falla_grafo.geojson

Contiene la probabilidad de falla de cada **arista** (`LineString`) y cada **nodo** (`Point`) del grafo aéreo base (`aristas_aereas`, `nodos_aereos`).

| Campo | Descripción |
|---|---|
| `elemento` | `arista` o `nodo` |
| `id` | Id de la arista o del nodo |
| `source`, `target`, `largo_m` | Solo en aristas |
| `p_falla` | Objeto `{amenaza: p}` con una entrada por amenaza que lo toca, más `total` (combinada) |

En la BD, `probabilidad_falla_aristas(arista_id, amenaza, p_falla, zonas)` y `probabilidad_falla_nodos(nodo_id, amenaza, p_falla, zonas)` guardan lo mismo, más la cantidad de zonas que toca.

## Bloque `metadata`

Incluye `descripcion`, `crs` y `parametros` (los valores por defecto con que se calculó).
