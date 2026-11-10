# Contexto de construcción: raíz del repositorio (ver docker-compose.yml), para poder copiar
# el modelo de probabilidad de falla que vive en 03 - Amenazas.
FROM python:3.12-slim
WORKDIR /app
COPY ["05 - API/requirements.txt", "./"]
RUN pip install --no-cache-dir -r requirements.txt
COPY ["05 - API/app/", "./"]
COPY ["03 - Amenazas/probabilidad_falla.py", "./"]
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
