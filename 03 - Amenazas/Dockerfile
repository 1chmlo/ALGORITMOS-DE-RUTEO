FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV OUT_DIR=/app/salidas PYTHONUNBUFFERED=1
