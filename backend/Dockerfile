FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    poppler-utils \
    libcairo2-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application - force rebuild 2025-12-28T10:50:00Z
COPY . .

# Expose port
EXPOSE 8080

# Default CMD - Railway's RAILWAY_START_COMMAND env var will override this
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
