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
| `lluvia` | Celda del modelo Open-Meteo (unión de sus hexágonos) | `i = min(1, precip_max / umbral_mm_h)`, `q = prob_max/100`, `p = 1 − (1 − i)(1 − peso_probabilidad·q)` | `umbral_mm_h = 2`, `peso_probabilidad = 0.25` |
| `viento` | Celda del modelo Open-Meteo | `r = max(viento_max/umbral_kmh, rafaga_max/umbral_rafaga_kmh)`, `p = clamp((r − inicio)/(1 − inicio))` | `43.2 km/h`, `43.2 km/h`, `inicio_riesgo = 0.67` |

Por qué cada amenaza afecta al dron:
- **Lluvia:** si supera el umbral, la falla es segura. La sola probabilidad de lluvia aporta a lo más un 25 % (el pronóstico es incierto).
- **Viento:** p crece linealmente desde el 67 % del umbral (≈ 29 km/h) hasta el umbral (43,2 km/h).

Los robos con violencia de 7 días **ya no son una amenaza** del modelo: generaban decenas de zonas blandas que inflaban el grafo sin representar un riesgo para el dron. Los robos de 90 días siguen como *metadato de vigilancia*, que es otro uso. Los datos y el ETL de 7 días se conservan en `03 - Amenazas`, pero la API no los consulta.

**Agrupación por celda:** los hexágonos de lluvia y viento que caen en la misma celda del modelo meteorológico (de 9 a 13 km) reciben exactamente el mismo pronóstico. Son **un solo evento**, no eventos independientes, así que se agrupan en una zona. Sin esta agrupación, una ruta que cruza 5 hexágonos con la misma lluvia la pagaría 5 veces.

**Enlaces y nodos**, suponiendo zonas independientes:

```
p_k(elemento) = 1 − Π_{zonas z de la amenaza k que toca} (1 − p_z)
p(elemento)   = 1 − Π_k (1 − p_k(elemento))      ← fila 'total'
```

## Fuentes de los valores por defecto (DJI Dock 3 + Matrice 4D)

| Parámetro | Valor | Origen |
|---|---|---|
| `umbral_mm_h` | 2 mm/h | FAQ oficial de DJI: el Dock 3 "puede seguir operando con normalidad" con lluvia máxima de 2 mm/h. <https://enterprise.dji.com/dock-3/faq> |
| `umbral_kmh`, `umbral_rafaga_kmh` | 43,2 km/h (12 m/s) | Manual de la aeronave DJI Matrice serie 4D con Dock 3 v1.2, sección 3.1: no pilotar con viento superior a 12 m/s. Coincide con la ficha técnica (resistencia al viento 12 m/s). <https://dl.djicdn.com/downloads/DJI_Dock_3/UM/20250610/DJI_Matrice_4D_Series_User_Manual_DJI_Dock_3_v1.2_es.pdf> · <https://enterprise.dji.com/dock-3/specs> |
| `inicio_riesgo` | 0,67 | Supuesto de diseño: regla práctica de volar con viento ≤ 2/3 del máximo (guías divulgativas, no oficiales). |
| `peso_probabilidad` | 0,25 | Supuesto del modelo, sin fuente externa. |

Otros datos del manual (sección «Índice de protección IP de la aeronave», p. 25, y sección 3.1): la aeronave es IP55 en condiciones de laboratorio, ese índice no es permanente, no se debe volar si las precipitaciones superan 100 mm en 24 h y no se debe pilotar con nieve, lluvia moderada ni niebla. El manual no da la intensidad de la «lluvia moderada». El estándar de la AMS fija el tope de lluvia ligera en 2,5 mm/h (<https://glossary.ametsoc.org/wiki/rain/>), de modo que los 2 mm/h de DJI están dentro de la lluvia ligera; esa comparación es una observación, no una definición de DJI.

El IP55/IP56 no se puede convertir a mm/h: la norma IEC 60529 define el ensayo por caudal de agua sobre la carcasa (por ejemplo, IPX5: boquilla de 6,3 mm y 12,5 L/min), no por intensidad de lluvia.

## probabilidad_falla_zonas.geojson

Contiene un `Feature` (`Polygon`/`MultiPolygon`) por zona con p > 0.

| Campo | Descripción |
|---|---|
| `zona_id` | `<amenaza>:<origen_id>` |
| `amenaza` | `lluvia` o `viento` |
| `origen_id` | Celda del modelo (lluvia, viento) o `hex_id` STOP |
| `p` | Probabilidad de falla |
| `detalle` | Valores que originan p (precipitación, viento, robos) |

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
