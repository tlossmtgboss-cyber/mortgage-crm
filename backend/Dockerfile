FROM python:3.11-slim

# Build cache buster - change this value to force full rebuild
ARG CACHE_DATE=2026-05-02-imessage-fix
RUN echo "Build timestamp: ${CACHE_DATE}"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    poppler-utils \
    libcairo2-dev \
    pkg-config \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy pinned requirements lockfile for reproducible builds
COPY requirements.lock .

# Install Python dependencies from lockfile
RUN pip install --no-cache-dir -r requirements.lock

# Copy application
COPY . .

# Create non-root user for security (container escape prevention)
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --home-dir /app appuser && \
    chown -R appuser:appgroup /app

# Expose port
EXPOSE 8080

# Health check for Railway - using /health/live which doesn't require DB
# Increased timeouts to handle slow startup on Railway
HEALTHCHECK --interval=30s --timeout=60s --start-period=300s --retries=15 \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Create python alias if needed and run start script
RUN ln -sf /usr/bin/python3 /usr/bin/python || true

# Switch to non-root user
USER appuser

# Use start.py script for proper PORT handling and migrations
CMD ["python3", "start.py"]
