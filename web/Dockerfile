# AAMS-X frontend: Vite build served by nginx.

FROM node:22-alpine AS build
WORKDIR /app

# Lockfile first so `npm ci` is cached independently of the source.
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Baked in at build time. Only VITE_* reaches the browser, and none of it is secret.
ARG VITE_API_BASE=/api
ARG VITE_WS_BASE=
ENV VITE_API_BASE=$VITE_API_BASE VITE_WS_BASE=$VITE_WS_BASE
RUN npm run build


FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
