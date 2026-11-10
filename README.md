# ALGORITMOS-DE-RUTEO

Ruteo de drones policiales que patrullan los puntos críticos de encerronas en Maipú, considerando metadatos (focos de delito, iluminación, tráfico y forma de las vías) y amenazas (lluvia, viento y robos recientes).

## Ejecutar

Requisitos: Docker con Docker Compose y una consola bash (Linux, macOS o Git Bash en Windows).

```bash
cp .env.example .env     # opcional: API keys de TomTom/Mapillary y licencia WLS de Gurobi
./main.sh
```

`main.sh` hace todo el proceso:
1. Levanta PostGIS y pgRouting.
2. Corre los ETL y las cargas de infraestructura, metadatos y amenazas.
3. Calcula la probabilidad de falla.
4. Levanta la API y la web, y verifica que se calculen las 4 rutas.

| Servicio | URL |
|---|---|
| Web (Fase 3) | http://localhost:8080 |
| Escenario de ejemplo (punto 9) | http://localhost:8080/#demo |
| Documentación de la API | http://localhost:8080/api/docs |
| Web estática de la Fase 2 | http://localhost:8080/visualizador_dijkstra.html |
| pgAdmin | http://localhost:5050 |

Si una API externa no responde, los ETL nuevos conservan el último GeoJSON versionado, así que el proyecto se puede replicar igual.

## Estructura

| Carpeta | Contenido |
|---|---|
| `00 - DB` | `init.sql` (esquema completo), `dijkstra.sql` (grafo aéreo base de la Fase 2), diagrama |
| `01 - Infraestructura` | Comisarías y puntos críticos |
| `02 - Metadata` | STOP 90 días, luminarias Mapillary, formas viales Overpass, tráfico TomTom |
| `03 - Amenazas` | Lluvia y viento (Open-Meteo), STOP 7 días y **`probabilidad_falla.py`** |
| `04 - Web` | `index.html` (Leaflet, consume la API), `nginx.conf` (proxy `/api`), `escenario_demo.md` |
| `05 - API` | FastAPI: grafo de visibilidad, 4 técnicas de ruteo, resiliencia, simulación. Ver su `README.md` |

## Requisitos de la Fase 3 y dónde se cumplen

| Punto | Dónde |
|---|---|
| 1. Ejecución replicable | `main.sh` + `docker-compose.yml` |
| 2. Infraestructura realista | Grafo de visibilidad que rodea zonas de amenaza caídas (`05 - API/README.md` §1) |
| 3. Parámetros del usuario | Web, secciones 1–2: base, circuito o punto, destinos, autonomía, velocidad, altura, riesgo máximo, umbrales, pesos |
| 4. Capas activables | Web, sección 3: un checkbox por amenaza y metadato (dibuja y considera en el cálculo); popups con el detalle |
| 5. Probabilidad de falla | `03 - Amenazas/probabilidad_falla.py` y `.md`; tablas `probabilidad_falla_*` |
| 6. Cuatro técnicas | `05 - API/app/tecnicas.py`: pgr_dijkstra (distancia), Gurobi (MILP), pgr_dijkstra (parámetros), algoritmo genético. Cada una se puede activar o desactivar en la web |
| 7. Fallas aleatorias 0–100 | Web, sección 5; `POST /api/simular-fallas` |
| 8. Métrica de resiliencia | R = Π(1 − p) de las zonas que toca la ruta, más Monte Carlo; se muestra en la leyenda y tabla con el algoritmo y el tiempo de cómputo |
| 9. Caso de ejemplo | `04 - Web/escenario_demo.md` y `#demo` |
