# Multi-stage Dockerfile for LitExtract.
# Stage 1: build the Vite/React frontend.
# Stage 2: assemble the Python runtime + the prebuilt frontend, served by FastAPI.
#
# Works for:
#   - Hugging Face Spaces (PORT=7860)
#   - Render / Fly.io / Railway / any PaaS that respects $PORT
#   - Local self-host:  docker build -t litextract . && docker run -p 7860:7860 litextract

# ---------- Stage 1: frontend build ----------
FROM node:20-slim AS frontend-build

WORKDIR /frontend

# Install deps with the exact versions from the lockfile.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Build the static bundle. Output: /frontend/dist
COPY frontend/ ./
RUN npm run build


# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim AS runtime

# Avoid Python writing pyc files & buffer stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages: build tools for any deps that need wheels compiled,
# plus libgomp1 (NumPy/scikit-style libs sometimes link against it).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so source-only changes don't invalidate the layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application source. .dockerignore filters out node_modules, .env,
# db, input, build artefacts, etc.
COPY . .

# Pull in the prebuilt frontend bundle from stage 1.
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Create the writable runtime dirs (uploads, SQLite). On HF Spaces these
# are EPHEMERAL — wiped on container restart. That's fine for a public
# demo; durable persistence requires Render Disk / Fly Volume / etc.
RUN mkdir -p /app/input /app/db /app/.rag_cache

# Non-root user — Hugging Face Spaces in particular expects this.
# UID 1000 is conventional and matches HF's expected user.
RUN useradd -m -u 1000 user && \
    chown -R user:user /app
USER user

# HF Spaces uses 7860 by default. Render/Fly/Railway pass PORT via env.
ENV PORT=7860
EXPOSE 7860

# Healthcheck for orchestrators that support it (compose, swarm, etc.).
# HF Spaces ignores it; harmless either way.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# Use shell form so $PORT expands at runtime, not at build.
CMD uvicorn api.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="*"
