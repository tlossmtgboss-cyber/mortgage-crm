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
