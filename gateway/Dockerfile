# Stage 1: Build React SPA
FROM node:22-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Unprivileged Nginx Gateway
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /build/dist /usr/share/nginx/html

EXPOSE 8080
