# Stage 1: build the browser app. This stage's Node tools and node_modules are
# not copied into the final image; only the generated dist/ files are kept.
FROM node:24-slim AS frontend-build

WORKDIR /app/frontend
# Use the same pnpm version recorded by the frontend project.
RUN npm install --global pnpm@11.13.1

# Docker COPY sources are relative to the repository-root build context.
# Copy manifests first so dependency installation can be cached until these change.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# Now copy the frontend source and compile it into /app/frontend/dist.
COPY frontend/ ./
RUN pnpm build

# -----------------------------------------------------------------------------
# Stage 2: the smaller runtime image. It has Python/Django, but not Node or the
# frontend build tools. The host Caddy service forwards HTTP traffic to Gunicorn here.
FROM python:3.13-slim AS app

# Uploaded files live on a persistent VPS volume mounted at /data/media.
# Optional GCS storage can still be selected explicitly at runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production \
    MEDIA_STORAGE_BACKEND=filesystem \
    MEDIA_ROOT=/data/media

WORKDIR /app/backend

# Copy the dependency manifest from the repo-root build context into the current
# directory (/app/backend), then install those Python packages into this image.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the Django project into /app/backend. `backend/` is the source path in the
# repo; `./` is the current WORKDIR inside this image. This puts manage.py at
# /app/backend/manage.py so the startup commands below run from the right place.
COPY backend/ ./

# Django settings look for the frontend at BASE_DIR.parent / frontend / dist.
# With BASE_DIR=/app/backend, that is /app/frontend/dist, so copy the build from
# stage 1 to precisely that sibling directory.
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Compose publishes this only on host loopback for Caddy.
# PORT remains configurable for other container environments.
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /data/media /app/backend/staticfiles \
    && chown -R app:app /data /app/backend/staticfiles
USER app

EXPOSE 8000

# scripts/deploy-vps.sh runs migrations once per release against PostgreSQL.
# Collect Django's own static files at runtime, then serve requests. This keeps
# schema changes out of every web-process startup and avoids concurrent migrate
# calls when the service is scaled.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - --access-logformat '%(h)s %(m)s %(s)s %(L)s'"]
