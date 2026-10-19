# tomtom_trafico.geojson

Segmentos de flujo vehicular en tiempo real (**velocidad actual vs. velocidad de flujo libre**) en las autopistas, enlaces y arterias principales de la **Comuna de Maipú y alrededores**, extraídos desde **TomTom Traffic Flow API v4**.

- **Generado por:** `etl_tomtom_trafico.py`
- **Cargado a la BD por:** `carga_tomtom_trafico.py` → tabla `tomtom_trafico`
- **Fuente:** TomTom Traffic Services v4 (`https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json`).
- **Justificación en el modelo de ruteo:** Cuando la velocidad actual cae por debajo de la velocidad de flujo libre (congestión, cuellos de botella en enlaces de autopistas o detenciones), los vehículos quedan expuestos y sin maniobrabilidad, aumentando la probabilidad de sufrir robos con violencia o encerronas (**menor velocidad = mayor riesgo de delito**).
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (`EPSG:4326`), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `LineString` por tramo vial entregado por TomTom.

## Propiedades (`properties`)

| Campo | Tipo | Descripción |
|---|---|---|
| `segment_id` | texto | Identificador único determinístico del segmento vial de TomTom (clave única en la BD) |
| `corredor_vial` | texto | Nombre de la autopista, enlace o avenida muestreada en Maipú |
| `comuna` | texto | `Maipú` |
| `frc` | texto | *Functional Road Class* de TomTom (`FRC0` autopista principal a `FRC7` vía local) |
| `velocidad_actual_kmh` | flotante | Velocidad promedio actual observada en el segmento en km/h (`currentSpeed`) |
| `velocidad_flujo_libre_kmh` | flotante | Velocidad de referencia sin congestión en el segmento en km/h (`freeFlowSpeed`) |
| `diferencia_velocidad_kmh` | flotante | Pérdida de velocidad respecto al flujo libre (`velocidad_flujo_libre_kmh - velocidad_actual_kmh`) |
| `razon_velocidad` | flotante | Cociente `velocidad_actual_kmh / velocidad_flujo_libre_kmh` (`1.0` = flujo libre; valores menores indican congestión) |
| `indice_congestion` | flotante | Nivel de congestión relativo `1 - razon_velocidad` (`0.0` sin congestión; cercano a `1.0` tráfico detenido) |
| `tiempo_actual_seg` | entero | Tiempo estimado actual para recorrer el segmento en segundos (`currentTravelTime`) |
| `tiempo_flujo_libre_seg` | entero | Tiempo estimado en condiciones de flujo libre en segundos (`freeFlowTravelTime`) |
| `demora_seg` | entero | Retraso adicional en segundos respecto al flujo libre |
| `confianza` | flotante | Nivel de confianza de la medición en tiempo real entregado por TomTom (`0.0` a `1.0`) |
| `cierre_vial` | booleano | `true` si el tramo se encuentra cerrado al tránsito (`roadClosure`) |
| `nivel_riesgo_trafico` | texto | Clasificación de exposición delictual por velocidad: `alto`, `medio` o `bajo` |
| `factor_riesgo_trafico` | flotante | Ponderador normalizado (`0.0` a `1.0`) que combina congestión y baja velocidad absoluta |
| `punto_consulta_lat`, `punto_consulta_lon` | flotante | Coordenadas `(latitud, longitud)` del punto de muestreo consultado |
| `vertices_count` | entero | Cantidad de vértices que componen la polilínea del tramo |
