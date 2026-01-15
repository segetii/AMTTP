# ═══════════════════════════════════════════════════════════════════════════════
# AMTTP Full Platform Dockerfile
# Deploys: Flutter Web + Next.js Dashboard + Backend Services
# ═══════════════════════════════════════════════════════════════════════════════
#
# Build: docker build -t amttp-platform .
# Run:   docker run -p 80:80 -p 3004:3004 -p 8007:8007 amttp-platform
#
# ═══════════════════════════════════════════════════════════════════════════════

# Stage 1: Build Flutter Web App
FROM instrumentisto/flutter:3.24 AS flutter-builder

WORKDIR /app/flutter
COPY frontend/amttp_app/pubspec.yaml frontend/amttp_app/pubspec.lock ./
RUN flutter pub get

COPY frontend/amttp_app/ .
RUN flutter build web --release --web-renderer html --base-href /

# Stage 2: Build Next.js Dashboard
FROM node:20-alpine AS nextjs-builder

WORKDIR /app/nextjs
COPY frontend/frontend/package*.json ./
RUN npm ci --production=false

COPY frontend/frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Stage 3: Final Production Image
FROM node:20-alpine AS production

# Install required packages
RUN apk add --no-cache \
    nginx \
    python3 \
    py3-pip \
    py3-setuptools \
    supervisor \
    curl \
    && rm -rf /var/cache/apk/*

# Create virtual environment for Python to avoid conflicts
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    httpx==0.26.0 \
    pydantic==2.5.3 \
    python-dotenv==1.0.0 \
    aiohttp==3.9.1 \
    pymongo==4.6.1 \
    redis==5.0.1

WORKDIR /app

# Copy Flutter build
COPY --from=flutter-builder /app/flutter/build/web /var/www/flutter

# Copy Next.js standalone build
COPY --from=nextjs-builder /app/nextjs/.next/standalone /app/nextjs/
COPY --from=nextjs-builder /app/nextjs/.next/static /app/nextjs/.next/static
COPY --from=nextjs-builder /app/nextjs/public /app/nextjs/public

# Copy Python backend services
COPY backend/compliance-service/*.py /app/backend/compliance/
COPY backend/compliance-service/requirements.txt /app/backend/compliance/

# Install backend-specific requirements if they exist
RUN if [ -f /app/backend/compliance/requirements.txt ]; then \
    pip install --no-cache-dir -r /app/backend/compliance/requirements.txt || true; \
    fi

# Copy nginx config
COPY docker/nginx.conf /etc/nginx/nginx.conf

# Copy supervisor config
COPY docker/supervisord.conf /etc/supervisord.conf

# Create log directories
RUN mkdir -p /var/log/nginx /var/log/supervisor /var/run/nginx

# Expose ports
EXPOSE 80 3004 8002 8004 8005 8006 8007

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Start all services
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
