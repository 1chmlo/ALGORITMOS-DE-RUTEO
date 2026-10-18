# comisarias.geojson

Unidades de Carabineros de la **Región Metropolitana** (comisarías, subcomisarías, tenencias, retenes, avanzadas y tenencias de carreteras).

- **Generado por:** `etl_comisarias.py`
- **Cargado a la BD por:** `carga_comisarias.py` → tabla `comisarias`
- **Fuente:** servidor ArcGIS del Ministerio de Desarrollo Social y Familia, capa *Carabineros* de `RED_PROTECCION_SOCIAL/SSEGURIDAD/MapServer/3`, filtrada por `cod_reg = 13`. El mismo servidor tiene capas de PDI (id 2) y Bomberos (id 1) que no se usan aún.
- **Formato:** GeoJSON `FeatureCollection`, CRS WGS84 (EPSG:4326), coordenadas `[longitud, latitud]`. Un `Feature` de tipo `Point` por unidad.

## Propiedades

| Campo | Tipo | Descripción |
|---|---|---|
| `objectid` | entero | Id del registro en el servidor ArcGIS (clave única en la BD) |
| `codigo_unidad` | texto | Código institucional de la unidad (`uni_cod`), p. ej. `15001` |
| `nombre` | texto | Nombre de la unidad, p. ej. `25A. COM. MAIPU` |
| `tipo_unidad` | texto | `Comisaría`, `Subcomisaría`, `Tenencia`, `Retén`, `Tenencia de Carreteras` o `Avanzada` |
| `direccion` | texto | Dirección completa |
| `cod_region`, `region` | entero, texto | Código y nombre de la región |
| `cod_provincia`, `provincia` | entero, texto | Código y nombre de la provincia |
| `cod_comuna`, `comuna` | entero, texto | Código (CUT) y nombre de la comuna |
| `prefectura` | texto | Prefectura de la que depende |
| `zona` | texto | Zona de Carabineros de la que depende |
| `anio_creacion` | entero | Año del campo `hecho` de la fuente (año del registro de la unidad); `null` si no viene |
| `vigente` | booleano | `true` si `vigencia = 1` en la fuente |
