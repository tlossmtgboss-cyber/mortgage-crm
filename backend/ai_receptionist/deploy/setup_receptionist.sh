#!/bin/bash
# =============================================================================
# PERENNIA AI - AI RECEPTIONIST DEPLOYMENT SETUP
# =============================================================================
# Creates a complete standalone deployment package for the AI Receptionist
#
# Usage: ./setup_receptionist.sh [output_dir]
# =============================================================================

set -e

OUTPUT_DIR="${1:-./ai_receptionist_deploy}"

echo "=========================================="
echo "Perennia AI - AI Receptionist Setup"
echo "=========================================="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Create directory structure
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

# =============================================================================
# .env.example
# =============================================================================
cat > .env.example << 'EOF'
# =============================================================================
# PERENNIA AI RECEPTIONIST - ENVIRONMENT CONFIGURATION
# =============================================================================

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/perennia

# Twilio Configuration
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+15551234567

# Speech-to-Text (choose one)
STT_PROVIDER=deepgram  # deepgram or whisper

# Deepgram
DEEPGRAM_API_KEY=your_deepgram_key

# OpenAI (for Whisper STT and TTS)
OPENAI_API_KEY=your_openai_key

# Text-to-Speech (choose one)
TTS_PROVIDER=elevenlabs  # elevenlabs or openai

# ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=your_voice_id

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# Company Configuration
COMPANY_NAME=Perennia Mortgage
RECEPTIONIST_NAME=Sarah
GREETING_MESSAGE=Thank you for calling {company_name}. This is {receptionist_name}, your AI assistant. How may I help you today?

# Feature Flags
ENABLE_CALL_RECORDING=true
ENABLE_SENTIMENT_ANALYSIS=true
ENABLE_REAL_TIME_COACHING=false
EOF

echo "✓ Created .env.example"

# =============================================================================
# requirements.txt
# =============================================================================
cat > requirements.txt << 'EOF'
# Perennia AI Receptionist Requirements
# =====================================

# Core Framework
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-dotenv>=1.0.0
pydantic>=2.5.0

# Database
sqlalchemy>=2.0.0
asyncpg>=0.29.0
psycopg2-binary>=2.9.0

# HTTP Client
httpx>=0.25.0
aiohttp>=3.9.0

# WebSocket
websockets>=12.0

# Twilio
twilio>=8.10.0

# Audio Processing
numpy>=1.24.0

# Speech-to-Text
deepgram-sdk>=3.0.0

# Text-to-Speech
elevenlabs>=0.3.0

# OpenAI (for Whisper and TTS)
openai>=1.3.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0

# Utilities
python-multipart>=0.0.6
python-jose[cryptography]>=3.3.0
EOF

echo "✓ Created requirements.txt"

# =============================================================================
# Dockerfile
# =============================================================================
cat > Dockerfile << 'EOF'
# =============================================================================
# PERENNIA AI RECEPTIONIST - DOCKER IMAGE
# =============================================================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

echo "✓ Created Dockerfile"

# =============================================================================
# docker-compose.yml
# =============================================================================
cat > docker-compose.yml << 'EOF'
# =============================================================================
# PERENNIA AI RECEPTIONIST - DOCKER COMPOSE
# =============================================================================
version: '3.8'

services:
  receptionist:
    build: .
    container_name: perennia-receptionist
    ports:
      - "${APP_PORT:-8000}:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
      - TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
      - TWILIO_PHONE_NUMBER=${TWILIO_PHONE_NUMBER}
      - STT_PROVIDER=${STT_PROVIDER:-deepgram}
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
      - TTS_PROVIDER=${TTS_PROVIDER:-elevenlabs}
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      - ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - COMPANY_NAME=${COMPANY_NAME:-Perennia Mortgage}
      - RECEPTIONIST_NAME=${RECEPTIONIST_NAME:-Sarah}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - perennia-network

  db:
    image: postgres:15-alpine
    container_name: perennia-db
    environment:
      - POSTGRES_USER=${DB_USER:-perennia}
      - POSTGRES_PASSWORD=${DB_PASSWORD:-perennia_secure_password}
      - POSTGRES_DB=${DB_NAME:-perennia}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "${DB_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-perennia}"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - perennia-network

  redis:
    image: redis:7-alpine
    container_name: perennia-redis
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - perennia-network

volumes:
  postgres_data:
  redis_data:

networks:
  perennia-network:
    driver: bridge
EOF

echo "✓ Created docker-compose.yml"

# =============================================================================
# init.sql
# =============================================================================
cat > init.sql << 'EOF'
-- =============================================================================
-- PERENNIA AI RECEPTIONIST - DATABASE INITIALIZATION
-- =============================================================================

-- Call Logs Table
CREATE TABLE IF NOT EXISTS call_logs (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(64) UNIQUE NOT NULL,
    from_number VARCHAR(32),
    to_number VARCHAR(32),
    direction VARCHAR(16) DEFAULT 'inbound',
    status VARCHAR(32) DEFAULT 'initiated',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    recording_url TEXT,
    transcript TEXT,
    sentiment_score DECIMAL(3,2),
    caller_id INTEGER REFERENCES contacts(id),
    loan_officer_id INTEGER REFERENCES users(id),
    transferred_to INTEGER REFERENCES users(id),
    transfer_reason TEXT,
    outcome VARCHAR(64),
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Call Events Table (for detailed call tracking)
CREATE TABLE IF NOT EXISTS call_events (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    event_data JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Callback Requests Table
CREATE TABLE IF NOT EXISTS callback_requests (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id),
    caller_name VARCHAR(128),
    caller_phone VARCHAR(32) NOT NULL,
    reason TEXT,
    urgency VARCHAR(16) DEFAULT 'normal',
    assigned_to INTEGER REFERENCES users(id),
    status VARCHAR(32) DEFAULT 'pending',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Voice Messages Table
CREATE TABLE IF NOT EXISTS voice_messages (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id),
    from_number VARCHAR(32),
    to_user_id INTEGER REFERENCES users(id),
    recording_url TEXT,
    transcript TEXT,
    duration_seconds INTEGER,
    is_urgent BOOLEAN DEFAULT false,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_call_logs_call_sid ON call_logs(call_sid);
CREATE INDEX IF NOT EXISTS idx_call_logs_from_number ON call_logs(from_number);
CREATE INDEX IF NOT EXISTS idx_call_logs_started_at ON call_logs(started_at);
CREATE INDEX IF NOT EXISTS idx_call_logs_status ON call_logs(status);
CREATE INDEX IF NOT EXISTS idx_call_events_call_log_id ON call_events(call_log_id);
CREATE INDEX IF NOT EXISTS idx_callback_requests_status ON callback_requests(status);
CREATE INDEX IF NOT EXISTS idx_voice_messages_to_user_id ON voice_messages(to_user_id);
CREATE INDEX IF NOT EXISTS idx_voice_messages_is_read ON voice_messages(is_read);

-- Updated at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
DROP TRIGGER IF EXISTS update_call_logs_updated_at ON call_logs;
CREATE TRIGGER update_call_logs_updated_at
    BEFORE UPDATE ON call_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_callback_requests_updated_at ON callback_requests;
CREATE TRIGGER update_callback_requests_updated_at
    BEFORE UPDATE ON callback_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO perennia;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO perennia;

COMMIT;
EOF

echo "✓ Created init.sql"

# =============================================================================
# main.py - Application Entry Point
# =============================================================================
cat > main.py << 'EOF'
"""
================================================================================
PERENNIA AI RECEPTIONIST - MAIN APPLICATION
================================================================================
FastAPI application entry point with Twilio webhook and WebSocket endpoints.
================================================================================
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_db():
    """Database session context manager."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import AI Receptionist components
try:
    from ai_receptionist import (
        create_receptionist,
        create_audio_processor,
        handle_voice_stream_websocket,
        AIReceptionist,
    )
    AI_RECEPTIONIST_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AI Receptionist module not available: {e}")
    AI_RECEPTIONIST_AVAILABLE = False

# Global receptionist instance
receptionist: Optional[AIReceptionist] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global receptionist

    logger.info("Starting Perennia AI Receptionist...")

    if AI_RECEPTIONIST_AVAILABLE:
        receptionist = create_receptionist(
            company_name=os.getenv("COMPANY_NAME", "Perennia Mortgage"),
            receptionist_name=os.getenv("RECEPTIONIST_NAME", "Sarah"),
        )
        logger.info("AI Receptionist initialized")

    yield

    logger.info("Shutting down Perennia AI Receptionist...")
    if receptionist:
        # Cleanup if needed
        pass


# Create FastAPI app
app = FastAPI(
    title="Perennia AI Receptionist",
    description="AI-powered voice receptionist for mortgage companies",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — explicit origins, no wildcards
_ALLOWED_ORIGINS = [
    origin for origin in [
        os.getenv("FRONTEND_URL", "https://app.perenniaai.com"),
        os.getenv("API_URL", "https://api.perenniaai.com"),
    ] if origin
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "perennia-ai-receptionist",
        "timestamp": datetime.utcnow().isoformat(),
        "ai_receptionist_available": AI_RECEPTIONIST_AVAILABLE,
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Perennia AI Receptionist",
        "version": "1.0.0",
        "status": "running",
    }


# =============================================================================
# TWILIO VOICE WEBHOOKS
# =============================================================================

class TwilioVoiceRequest(BaseModel):
    """Twilio voice webhook request."""
    CallSid: str
    From: str
    To: str
    CallStatus: Optional[str] = None
    Direction: Optional[str] = None


@app.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming voice call from Twilio."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")

    logger.info(f"Incoming call: {call_sid} from {from_number}")

    # Get WebSocket URL for media stream
    host = request.headers.get("host", "localhost:8000")
    ws_url = f"wss://{host}/voice/stream/{call_sid}"

    # Generate TwiML response
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="CallSid" value="{call_sid}"/>
            <Parameter name="From" value="{from_number}"/>
            <Parameter name="To" value="{to_number}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@app.post("/voice/status")
async def handle_call_status(request: Request):
    """Handle call status updates from Twilio."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus")

    logger.info(f"Call status update: {call_sid} -> {call_status}")

    # Update call log in database
    try:
        with get_db() as db:
            # Map Twilio status to our status
            ended_statuses = ["completed", "busy", "failed", "no-answer", "canceled"]
            update_data = {"status": call_status}

            if call_status in ended_statuses:
                update_data["ended_at"] = datetime.utcnow()
                # Get duration if available
                duration = form_data.get("CallDuration")
                if duration:
                    update_data["duration_seconds"] = int(duration)

            db.execute(
                text("""
                    UPDATE call_logs
                    SET status = :status,
                        ended_at = COALESCE(:ended_at, ended_at),
                        duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE call_sid = :call_sid
                """),
                {
                    "call_sid": call_sid,
                    "status": call_status,
                    "ended_at": update_data.get("ended_at"),
                    "duration_seconds": update_data.get("duration_seconds"),
                }
            )
            db.commit()
            logger.info(f"Updated call log for {call_sid}")
    except Exception as e:
        logger.error(f"Failed to update call log: {e}")

    return {"status": "received"}


# =============================================================================
# WEBSOCKET MEDIA STREAM
# =============================================================================

@app.websocket("/voice/stream/{call_sid}")
async def voice_stream(websocket: WebSocket, call_sid: str):
    """Handle Twilio Media Stream WebSocket connection."""
    await websocket.accept()
    logger.info(f"WebSocket connected for call: {call_sid}")

    try:
        if AI_RECEPTIONIST_AVAILABLE:
            async with create_audio_processor() as processor:
                await handle_voice_stream_websocket(
                    websocket=websocket,
                    audio_processor=processor,
                    receptionist=receptionist,
                )
        else:
            # Fallback: just acknowledge messages
            while True:
                data = await websocket.receive_text()
                # Echo acknowledgment

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call: {call_sid}")
    except Exception as e:
        logger.error(f"WebSocket error for call {call_sid}: {e}")
    finally:
        logger.info(f"WebSocket session ended for call: {call_sid}")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/api/calls")
async def get_recent_calls(limit: int = 20):
    """Get recent call logs."""
    try:
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT id, call_sid, from_number, to_number, direction,
                           status, started_at, ended_at, duration_seconds,
                           outcome, notes, created_at
                    FROM call_logs
                    ORDER BY started_at DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            )
            calls = [dict(row._mapping) for row in result.fetchall()]

            # Get total count
            count_result = db.execute(text("SELECT COUNT(*) FROM call_logs"))
            total = count_result.scalar()

            return {
                "calls": [
                    {
                        **call,
                        "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
                        "ended_at": call["ended_at"].isoformat() if call.get("ended_at") else None,
                        "created_at": call["created_at"].isoformat() if call.get("created_at") else None,
                    }
                    for call in calls
                ],
                "total": total
            }
    except Exception as e:
        logger.error(f"Failed to get recent calls: {e}")
        return {"calls": [], "total": 0, "error": str(e)}


@app.get("/api/calls/{call_sid}")
async def get_call_details(call_sid: str):
    """Get details for a specific call."""
    try:
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT id, call_sid, from_number, to_number, direction,
                           status, started_at, ended_at, duration_seconds,
                           recording_url, transcript, sentiment_score,
                           caller_id, loan_officer_id, transferred_to,
                           transfer_reason, outcome, notes, metadata,
                           created_at, updated_at
                    FROM call_logs
                    WHERE call_sid = :call_sid
                """),
                {"call_sid": call_sid}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Call not found")

            call = dict(row._mapping)

            # Get call events
            events_result = db.execute(
                text("""
                    SELECT event_type, event_data, timestamp
                    FROM call_events
                    WHERE call_log_id = :call_id
                    ORDER BY timestamp ASC
                """),
                {"call_id": call["id"]}
            )
            events = [dict(e._mapping) for e in events_result.fetchall()]

            return {
                **call,
                "started_at": call["started_at"].isoformat() if call.get("started_at") else None,
                "ended_at": call["ended_at"].isoformat() if call.get("ended_at") else None,
                "created_at": call["created_at"].isoformat() if call.get("created_at") else None,
                "updated_at": call["updated_at"].isoformat() if call.get("updated_at") else None,
                "events": [
                    {
                        **event,
                        "timestamp": event["timestamp"].isoformat() if event.get("timestamp") else None,
                    }
                    for event in events
                ],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/callbacks")
async def get_pending_callbacks():
    """Get pending callback requests."""
    try:
        with get_db() as db:
            result = db.execute(
                text("""
                    SELECT cr.id, cr.call_log_id, cr.caller_name, cr.caller_phone,
                           cr.reason, cr.urgency, cr.assigned_to, cr.status,
                           cr.scheduled_at, cr.notes, cr.created_at,
                           cl.call_sid, cl.from_number
                    FROM callback_requests cr
                    LEFT JOIN call_logs cl ON cl.id = cr.call_log_id
                    WHERE cr.status = 'pending'
                    ORDER BY
                        CASE cr.urgency
                            WHEN 'urgent' THEN 1
                            WHEN 'high' THEN 2
                            WHEN 'normal' THEN 3
                            WHEN 'low' THEN 4
                            ELSE 5
                        END,
                        cr.created_at ASC
                """)
            )
            callbacks = [dict(row._mapping) for row in result.fetchall()]

            # Get total count of pending callbacks
            count_result = db.execute(
                text("SELECT COUNT(*) FROM callback_requests WHERE status = 'pending'")
            )
            total = count_result.scalar()

            return {
                "callbacks": [
                    {
                        **cb,
                        "scheduled_at": cb["scheduled_at"].isoformat() if cb.get("scheduled_at") else None,
                        "created_at": cb["created_at"].isoformat() if cb.get("created_at") else None,
                    }
                    for cb in callbacks
                ],
                "total": total
            }
    except Exception as e:
        logger.error(f"Failed to get pending callbacks: {e}")
        return {"callbacks": [], "total": 0, "error": str(e)}


@app.get("/api/metrics")
async def get_metrics():
    """Get receptionist metrics."""
    if receptionist:
        return receptionist.get_metrics()
    return {"status": "receptionist_not_available"}


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
EOF

echo "✓ Created main.py"

# =============================================================================
# README.md
# =============================================================================
cat > README.md << 'EOF'
# Perennia AI Receptionist

AI-powered voice receptionist for mortgage companies, integrating with Twilio for real-time voice handling.

## Features

- **Real-time Speech Processing**: Deepgram STT with sub-300ms latency
- **Natural Voice Synthesis**: ElevenLabs TTS with human-like voice
- **CRM Integration**: Access to 160+ Perennia mortgage tools
- **Intelligent Routing**: Automatic caller identification and call routing
- **Appointment Scheduling**: Book appointments directly during calls
- **Callback Management**: Create and track callback requests

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run with Docker

```bash
docker-compose up -d
```

### 3. Configure Twilio

Set your Twilio webhook URLs:
- **Voice URL**: `https://your-domain.com/voice/incoming`
- **Status Callback**: `https://your-domain.com/voice/status`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | Yes |
| `DEEPGRAM_API_KEY` | Deepgram API key for STT | Yes* |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for TTS | Yes* |
| `OPENAI_API_KEY` | OpenAI API key (alternative STT/TTS) | Optional |

*Required based on provider selection

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/voice/incoming` | POST | Twilio voice webhook |
| `/voice/stream/{call_sid}` | WS | Media stream WebSocket |
| `/api/calls` | GET | List recent calls |
| `/api/callbacks` | GET | List pending callbacks |
| `/api/metrics` | GET | Get system metrics |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Twilio Voice                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   AI Receptionist                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Audio     │  │    Call     │  │       Tool          │ │
│  │  Processor  │◄─┤   Handler   │◄─┤     Executor        │ │
│  │ (STT/TTS)   │  │  (WebSocket)│  │  (160+ CRM Tools)   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Perennia CRM                             │
│        (Loans, Contacts, Leads, Documents, etc.)           │
└─────────────────────────────────────────────────────────────┘
```

## Development

### Run locally

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
python main.py
```

### Run tests

```bash
pytest backend/ai_receptionist/tests/ -v
```

## License

Proprietary - Perennia AI
EOF

echo "✓ Created README.md"

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Created files:"
echo "  - .env.example"
echo "  - requirements.txt"
echo "  - Dockerfile"
echo "  - docker-compose.yml"
echo "  - init.sql"
echo "  - main.py"
echo "  - README.md"
echo ""
echo "Next steps:"
echo "  1. cd $OUTPUT_DIR"
echo "  2. cp .env.example .env"
echo "  3. Edit .env with your API keys"
echo "  4. docker-compose up -d"
echo ""
echo "For development without Docker:"
echo "  1. pip install -r requirements.txt"
echo "  2. python main.py"
echo ""
