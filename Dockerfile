FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY src/ ./src/

# data/ is intentionally excluded — mount locally or set WEATHER_DATA_PATH / STATIONS_DATA_PATH
# to gs://your-bucket/... for Cloud Run

EXPOSE 8080

# Cloud Run injects $PORT at runtime (default 8080). exec replaces the shell
# so the process receives SIGTERM directly on shutdown.
CMD ["sh", "-c", "exec shiny run --host 0.0.0.0 --port ${PORT:-8080} app.py"]
