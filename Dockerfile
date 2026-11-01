# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,target=/run/secrets/ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle npm ci --strict-ssl=true; else npm ci --strict-ssl=true; fi
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH" \
    APP_ENVIRONMENT=production AUTH_MODE=oidc STORAGE_DIR=/var/lib/invoiceguard
RUN --mount=type=secret,id=ca_bundle,target=/run/secrets/ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then apt-get -o Acquire::https::CaInfo=/run/secrets/ca_bundle update; else apt-get update; fi && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng ca-certificates && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=ca_bundle,target=/run/secrets/ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then PIP_CERT=/run/secrets/ca_bundle pip install --no-cache-dir uv==0.12.23; else pip install --no-cache-dir uv==0.12.23; fi
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=ca_bundle,target=/run/secrets/ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then SSL_CERT_FILE=/run/secrets/ca_bundle uv sync --frozen --no-dev; else uv sync --frozen --no-dev; fi
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN chmod -R a+rX /app && useradd --uid 10001 --create-home app && mkdir -p /var/lib/invoiceguard && chown app:app /var/lib/invoiceguard
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health/ready',timeout=3)"
CMD ["sh","-c","exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
