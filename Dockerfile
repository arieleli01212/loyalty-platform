# Stage 1 — build the React dashboard
FROM node:20-alpine AS frontend
WORKDIR /build

COPY frontend-dashboard/package.json frontend-dashboard/package-lock.json ./
RUN npm ci

COPY frontend-dashboard/ ./
# In production the frontend talks to the same origin as the API, so leave
# VITE_API_BASE empty — the api client falls back to relative URLs.
ENV VITE_API_BASE=""
RUN npm run build
# Output: /build/dist

# Stage 2 — Python runtime
FROM python:3.11-slim

WORKDIR /app

# System deps for asyncpg / Pillow are already in the slim base; nothing extra needed.

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Copy the built frontend into ./static — main.py serves from this path.
COPY --from=frontend /build/dist ./static

# Render injects $PORT at runtime; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
