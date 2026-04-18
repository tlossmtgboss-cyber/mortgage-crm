FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install agent worker dependencies (lightweight — no full backend deps)
COPY aria/requirements.lock ./aria/requirements.lock
RUN pip install --no-cache-dir -r aria/requirements.lock

RUN pip install --no-cache-dir \
    'livekit-api>=1.1.0' \
    'livekit-agents~=1.5' \
    'livekit-plugins-deepgram~=1.5' \
    'livekit-plugins-anthropic~=1.5' \
    'livekit-plugins-cartesia~=1.5'

# Copy only what the agent worker needs (build context = backend/)
COPY aria/ ./aria/
COPY agents/__init__.py agents/aria_backend_client.py agents/aria_prompts.py agents/aria_config.py ./agents/

ENTRYPOINT ["python", "-m", "aria.voice_agent", "start"]
