FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FALES_DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends ngspice && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY vendor ./vendor
COPY web ./web
RUN useradd --uid 10001 --create-home fales && mkdir /data && chown fales:fales /data
USER fales
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "32"]
