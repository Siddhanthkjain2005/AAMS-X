# Multi-stage build: Node builds the production frontend, Python serves API + static + data.

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN NODE_OPTIONS=--max-old-space-size=1536 npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/ backend/
COPY data/ data/
COPY --from=frontend /app/frontend/dist frontend/dist
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
