"""Carga salida/puntos_criticos_fiscalia.geojson en la tabla puntos_criticos_fiscalia."""
from db import cargar_puntos

COLUMNAS = [
    "nombre", "tipo_delito", "severidad", "fuente", "fuente_url", "pagina_informe",
    "cita", "cita_verificada", "periodo", "separacion_vias_m",
]

if __name__ == "__main__":
    cargar_puntos("puntos_criticos_fiscalia.geojson", "puntos_criticos_fiscalia", COLUMNAS, "nombre")
