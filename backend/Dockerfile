FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    poppler-utils \
    libcairo2-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application - force rebuild 2025-12-28T10:50:00Z
COPY . .

# Expose port
EXPOSE 8080

# Health check for Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:8080/health/live || exit 1

# Create python alias if needed and run start script
RUN ln -sf /usr/bin/python3 /usr/bin/python || true

# Use start.py script for proper PORT handling and migrations
CMD ["python3", "start.py"]
# Force rebuild 1768653977
