# Voice Cloning Service - XTTS v2
# GPU-accelerated voice cloning and synthesis

FROM nvidia/cuda:12.1-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV XTTS_MODEL_DIR=/models/xtts
ENV VOICE_SAMPLES_DIR=/data/voice_samples
ENV OUTPUT_DIR=/data/outputs

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /models /data/voice_samples /data/outputs

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Pre-download XTTS model (optional, makes startup faster)
# RUN python3 -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"

# Copy application code
COPY main.py .

# Expose port
EXPOSE 5501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5501/health || exit 1

# Run the service
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5501"]
