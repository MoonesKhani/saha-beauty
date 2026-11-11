# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt backend/requirements-postgres.txt backend/constraints.txt ./backend/
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; python -m pip install --no-cache-dir -r backend/requirements-postgres.txt && python -m pip check
COPY backend ./backend
COPY database ./database
COPY frontend ./frontend
COPY assets ./assets
COPY *.html ./
RUN python frontend/build.py && useradd --create-home --uid 10001 saha && mkdir -p /app/var && chown -R saha:saha /app
USER saha
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=4)"
CMD ["python","-m","uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000"]
