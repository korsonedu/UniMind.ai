# ── Stage 1: Frontend build ──
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Backend ──
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy built frontend into Django static
COPY --from=frontend-build /app/frontend/dist ./backend/static/

# Collect static
WORKDIR /app/backend
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Default: gunicorn + uvicorn hybrid (Django ASGI)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "school_system.asgi:application"]
