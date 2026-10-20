# puntos_criticos_fiscalia.geojson

Puntos críticos de **encerronas** en la Región Metropolitana, descritos en el *Reporte de Fenómenos Criminales N°5 – Robo violento de vehículos* (Fiscalía Nacional, datos 2020-2025) y en la nota de Emol del 26-06-2026.

- **Generado por:** `etl_puntos_criticos_fiscalia.py`
- **Cargado a la BD por:** `carga_puntos_criticos_fiscalia.py` → tabla `puntos_criticos_fiscalia`
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Point` por punto.

## Cómo se obtienen las coordenadas

El informe solo nombra intersecciones de autopistas (sección 5.4, páginas impresas 22-24); no trae coordenadas, y su contenido no cambia. Por eso el ETL **no consulta ninguna fuente al ejecutarse**: el catálogo de puntos está fijo en el script (`PUNTOS`) y el archivo se genera sin acceso a red. Las citas se verificaron una vez contra el PDF, y las coordenadas se obtuvieron una vez desde OpenStreetMap, tomando el **punto medio entre los dos nodos más cercanos** de las dos vías que se cruzan. Las autopistas no comparten nodo en sus enlaces (están a distinto nivel), así que la ubicación es **aproximada**: `separacion_vias_m` indica qué tan cerca quedaron las dos vías (valores bajos = más confiable, `0` = el punto de Emol, que ya viene como intersección de calles).

El archivo tiene 6 puntos: 5 de la Fiscalía y 1 de Emol (San Bernardo).

Los puntos de la Fiscalía son **intersecciones de la Región Metropolitana**, no solo de Maipú: el informe no lista puntos específicos de esa comuna.

## Propiedades

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | texto | Intersección, p. ej. `Vespucio Sur con Ruta 5` (clave única en la BD) |
| `tipo_delito` | texto | Siempre `encerrona` por ahora |
| `severidad` | texto o `null` | `alta` (el informe habla de "concentración importante" o "alta densidad"), `media` ("menor") o `baja` ("menor aún"). `null` si la fuente no la gradúa (caso de Emol) |
| `fuente` | texto | `fiscalia` o `emol` |
| `fuente_url` | texto | URL del documento |
| `pagina_informe` | entero o `null` | Índice de página en el PDF (1 = portada; corresponde a la página impresa 23) donde se cita el punto |
| `cita` | texto | Frase del informe (o descripción del hecho en el caso de Emol) que respalda el punto |
| `cita_verificada` | booleano | `true` si la cita fue contrastada con el PDF del informe al construir el catálogo (hoy `true` en todos los puntos); el ETL no vuelve a verificarla al ejecutarse |
| `periodo` | texto | Período de los datos: `2020-2025` o la fecha del hecho |
| `separacion_vias_m` | entero | Distancia en metros entre las dos vías en el punto calculado |
