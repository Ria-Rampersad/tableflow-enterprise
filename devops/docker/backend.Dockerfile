# ---- TableFlow backend (FastAPI) ---------------------------------------------
# Build context: repository root  ->  docker build -f devops/docker/backend.Dockerfile .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY backend/requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM base AS runtime
RUN useradd --create-home --uid 10001 tableflow
COPY --from=deps /install /usr/local
COPY backend/app ./app
COPY database/migrations /app/database/migrations
COPY devops/docker/backend-entrypoint.sh /entrypoint.sh
ENV MIGRATIONS_DIR=/app/database/migrations
RUN chmod +x /entrypoint.sh && chown -R tableflow /app
USER tableflow
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/ready').status==200 else 1)"
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--workers", "2"]
