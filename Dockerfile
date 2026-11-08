# syntax=docker/dockerfile:1
# Production image: frontend build + backend, single container (design.md Decisão 5).

FROM node:20.18.1-slim@sha256:b2c8e0eb8a6aeeae33b2711f8f516003e27ee45804e270468d937b3214f2f0cc AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STATIC_DIR=/app/static DATA_DIR=/app/data INBOX_DIR=/app/inbox PROFILES_DIR=/app/profiles \
    SECRETS_FILE=/run/secrets/pdf-passwords.yaml HOST=0.0.0.0 PORT=8080 TZ=America/Sao_Paulo
WORKDIR /app
COPY backend/pyproject.toml /app/backend/
COPY backend/src /app/backend/src
RUN pip install -q --no-cache-dir --upgrade pip==26.2 setuptools==84.1.0 \
    && pip install -q --no-cache-dir /app/backend && rm -rf /app/backend
COPY --from=frontend /build/dist /app/static
COPY profiles/examples /app/profiles-examples
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data /app/inbox /app/profiles && chown -R app:app /app/data
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2).status == 200 else 1)"
CMD ["python", "-m", "expense_tracker"]
