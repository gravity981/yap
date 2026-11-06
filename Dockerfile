# syntax=docker/dockerfile:1
# Production image (spec 5.1, 5.7): the backend serving the built frontend. The version
# is fixed at build time and cannot be changed afterwards. Build it with
# scripts/build-image.sh (locally) or the CI and release workflows.

# Base images: pinned, at least two weeks old when chosen; Node as in CI and devcontainer.
# Written out in FROM, so Dependabot can update them (.github/dependabot.yml).
FROM node:26.12.0-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The version build args are declared only where they are used: every RUN after an ARG
# depends on its value, and the version changes with every build, so declared earlier
# they would invalidate the dependency layers each time.
# The same version as the backend is compiled into the frontend (vite.config.ts)
ARG APP_VERSION
RUN APP_VERSION="${APP_VERSION}" npm run build \
    && node scripts/third-party-licenses.mjs dist/third-party-licenses.txt

FROM python:3.14.7-slim-bookworm
LABEL org.opencontainers.image.title="yap" \
      org.opencontainers.image.description="Investment strategy management: theses, policies, portfolios, rebalancing" \
      org.opencontainers.image.source="https://github.com/gravity981/yap"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod \
    STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////var/lib/yap/app.db

# An unprivileged user; the database volume and the backup folder belong to it
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /var/lib/yap /backups \
    && chown app:app /var/lib/yap /backups

WORKDIR /app
# Dependencies first, so code changes do not reinstall them
COPY backend/pyproject.toml backend/pyproject.toml
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('backend/pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
COPY backend/yap backend/yap
RUN pip install --no-cache-dir --no-deps ./backend && rm -rf backend
COPY --from=frontend /build/frontend/dist /app/static

# The version last, so it does not invalidate the layers above (see the frontend stage)
ARG APP_VERSION
ARG APP_COMMIT
RUN test -n "${APP_VERSION}" && test -n "${APP_COMMIT}" \
    || { echo "APP_VERSION and APP_COMMIT are required build arguments" >&2; exit 1; }
LABEL org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${APP_COMMIT}"
ENV APP_VERSION="${APP_VERSION}" \
    APP_COMMIT="${APP_COMMIT}"
RUN printf '%s\n' "${APP_VERSION}" > /app/VERSION

USER app
VOLUME /var/lib/yap
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "--factory", "yap.api.app:create_app_from_env", \
     "--host", "0.0.0.0", "--port", "8000"]
