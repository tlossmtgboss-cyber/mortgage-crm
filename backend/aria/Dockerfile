FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

RUN pip install --no-cache-dir \
    'livekit-api>=1.1.0' \
    'livekit-agents~=1.5' \
    'livekit-plugins-deepgram~=1.5' \
    'livekit-plugins-anthropic~=1.5' \
    'livekit-plugins-cartesia~=1.5' \
    'livekit-plugins-silero~=1.5'

COPY . .

ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["python", "voice_agent.py", "start"]
