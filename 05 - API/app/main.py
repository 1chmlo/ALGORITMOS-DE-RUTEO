"""API de ruteo de drones (Fase 3). Documentación interactiva en /api/docs."""
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

import datos
import probabilidad_falla as pf
import servicio
import tecnicas as tc

app = FastAPI(title="API de ruteo de drones - Maipú", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=2000)
# Permite abrir 04 - Web/index.html directamente (file:// o Live Server) contra :8000
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AmenazaSimulada(BaseModel):
    tipo: str = "lluvia"
    lon: float
    lat: float
    radio_m: float = Field(1000, gt=0, le=10000)
    p: float = Field(1.0, ge=0, le=1)


class Consulta(BaseModel):
    modo: Literal["circuito", "punto"] = "circuito"
    origen: int = 1
    destinos: list[int] = [4, 5, 6, 7, 8, 9]
    # Restricciones del usuario (aplicación: dron policial de patrullaje)
    bateria_km: float = Field(25, gt=0, description="Autonomía máxima del dron")
    velocidad_kmh: float = Field(60, gt=0)
    altura_vuelo_m: float = Field(120, gt=0, le=500, description="Altura sobre la base de despegue")
    riesgo_max: float = Field(0.6, ge=0, le=1, description="Probabilidad máxima aceptada de que la misión falle")
    umbral_falla: float = Field(0.7, ge=0, le=1, description="p desde la que una zona se considera caída (modelo probabilístico)")
    umbral_blando: float = Field(0.15, ge=0, le=1, description="p desde la que se agregan waypoints para rodear la zona")
    modelo: Literal["ponderado", "probabilistico"] = "probabilistico"
    # Capas que se consideran en el cálculo
    amenazas: list[str] = list(pf.AMENAZAS)
    metadatos: list[str] = list(datos.METADATOS)
    restricciones_estaticas: bool = True
    # Pesos del costo
    peso_riesgo: float = Field(2.0, ge=0, description="β: metros equivalentes (×1000) por unidad de -ln(1-p)")
    peso_metadatos: float = Field(0.3, ge=0, description="γ: recargo por volar sobre zonas de poco valor de vigilancia")
    pesos_amenazas: dict[str, float] = {}
    pesos_metadatos: dict[str, float] = {}
    params_amenazas: dict[str, dict[str, float]] = {}
    amenazas_simuladas: list[AmenazaSimulada] = []
    tecnicas: list[str] = list(tc.TECNICAS)
    semilla: int = 42
    simulaciones_mc: int = Field(2000, ge=0, le=20000)
    incluir_grafo: bool = True
    gurobi_tiempo_s: float = Field(20, gt=0, le=120)


def _cfg(c: Consulta):
    cfg = c.model_dump()
    cfg["tecnicas"] = [t for t in cfg["tecnicas"] if t in tc.TECNICAS]
    return cfg


@app.get("/api/salud")
def salud():
    return {"ok": True, "nodos": len(datos.nodos())}


@app.get("/api/config")
def config():
    return {
        "amenazas": list(pf.AMENAZAS), "metadatos": list(datos.METADATOS),
        "params_amenazas": pf.PARAMS_DEFECTO, "tecnicas": tc.TECNICAS,
        "defecto": Consulta().model_dump(),
    }


@app.get("/api/capas/{nombre}")
def capas(nombre: str):
    fc = datos.capa(nombre)
    if fc is None:
        raise HTTPException(404, f"Capa desconocida: {nombre}")
    return fc


@app.post("/api/rutas")
def rutas(c: Consulta):
    try:
        return servicio.limpiar(servicio.resolver(_cfg(c)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/simular-fallas")
def simular(c: Consulta):
    try:
        return servicio.simular(_cfg(c))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/recargar")
def recargar():
    """Vacía la caché (después de volver a correr los ETL)."""
    datos.cache.limpiar()
    return {"ok": True}
