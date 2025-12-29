# Lip Sync Service - Wav2Lip
# GPU-accelerated lip synchronization

FROM nvidia/cuda:12.1-runtime-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV WAV2LIP_DIR=/app/Wav2Lip
ENV WAV2LIP_CHECKPOINT=/models/wav2lip_gan.pth
ENV FACE_DETECT_MODEL=/models/s3fd.pth
ENV OUTPUT_DIR=/data/outputs
ENV TEMP_DIR=/tmp/lipsync

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /models /data/outputs /tmp/lipsync

WORKDIR /app

# Clone Wav2Lip repository
RUN git clone https://github.com/Rudrabha/Wav2Lip.git

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install Wav2Lip dependencies
RUN pip3 install --no-cache-dir \
    batch-face \
    numba==0.48

# Download model checkpoints (optional - can mount instead)
# RUN wget -O /models/wav2lip_gan.pth "https://..."
# RUN wget -O /models/s3fd.pth "https://..."

# Copy application code
COPY main.py .

# Expose port
EXPOSE 5502

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5502/health || exit 1

# Run the service
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5502"]
