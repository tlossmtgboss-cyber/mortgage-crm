# Pipeline 360 Voice OS - Backend

AI-powered voice orchestrator for mortgage CRM with real-time STT, LLM, and TTS pipeline.

## Quick Start

### Prerequisites

- Node.js 18+
- PostgreSQL 15+
- Redis 7+
- Twilio account
- API keys for: Deepgram, ElevenLabs, OpenAI

### Installation

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env
# Edit .env with your actual values

# Run database migrations
# (Run the schema.sql in your PostgreSQL database)

# Build TypeScript
npm run build

# Start development server
npm run dev

# Or start production server
npm start
```

### Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f voice-orchestrator

# Stop services
docker-compose down
```

## Architecture

```
voice_os/
├── ai/
│   └── llm.ts                 # LLM client (OpenAI, Anthropic)
├── crm/
│   └── client.ts              # CRM API integration
├── monitoring/
│   ├── index.ts               # Monitoring setup
│   └── metrics.ts             # Prometheus metrics
├── state/
│   └── manager.ts             # Call state management
├── telephony/
│   └── twilio.ts              # Twilio integration
├── tools/
│   └── executor.ts            # CRM tool execution
├── utils/
│   └── logger.ts              # Winston logger
├── voice/
│   ├── stt.ts                 # Speech-to-text
│   └── tts.ts                 # Text-to-speech
├── index.ts                   # Main server
├── orchestrator.ts            # Voice orchestration engine
└── package.json
```

## Features

### Core Voice Pipeline
- ✅ Real-time STT (Deepgram Nova-2)
- ✅ Streaming LLM (GPT-4, Claude)
- ✅ Real-time TTS (ElevenLabs)
- ✅ Twilio Media Streams integration
- ✅ WebSocket bidirectional audio

### CRM Integration
- ✅ 9 production tools
- ✅ Contact identification
- ✅ Lead creation
- ✅ Appointment scheduling
- ✅ Task management
- ✅ Document requests
- ✅ Escalation handling

### Monitoring & Observability
- ✅ Prometheus metrics
- ✅ Grafana dashboards
- ✅ Winston logging
- ✅ Health checks
- ✅ Error tracking

## API Endpoints

### Voice Webhooks
- `POST /api/voice/twilio/inbound` - Handle inbound calls
- `POST /api/voice/twilio/status` - Call status callbacks
- `POST /api/voice/twilio/recording` - Recording callbacks
- `WS /api/voice/stream` - Media stream WebSocket

### Call Management
- `POST /api/voice/calls/outbound` - Initiate outbound call
- `GET /api/voice/calls/:callId` - Get call details
- `GET /api/voice/calls` - List calls

### Monitoring
- `GET /health` - Health check
- `GET /ready` - Readiness probe
- `GET /live` - Liveness probe
- `GET /metrics` - Prometheus metrics

## Environment Variables

See `.env.example` for all available configuration options.

### Critical Variables

```env
# CRM Integration
CRM_API_URL=https://your-backend.railway.app
CRM_API_KEY=your-api-key

# Twilio
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token

# Voice Services
DEEPGRAM_API_KEY=your-key
ELEVENLABS_API_KEY=your-key
OPENAI_API_KEY=your-key
```

## Development

```bash
# Run in development mode with hot reload
npm run dev

# Run tests
npm test

# Run integration tests
npm run test:integration

# Lint code
npm run lint

# Format code
npm run format
```

## Deployment

### Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link project
railway link

# Deploy
railway up
```

### Kubernetes

```bash
# Apply deployment
kubectl apply -f k8s/

# Check status
kubectl get pods -n voice-os

# View logs
kubectl logs -f deployment/voice-orchestrator -n voice-os
```

## Monitoring

### Prometheus
Access at `http://localhost:9090`

### Grafana
Access at `http://localhost:3000`
- Default login: admin / admin (change in production)

### Logs
```bash
# Docker logs
docker-compose logs -f voice-orchestrator

# Local logs
tail -f logs/combined.log
tail -f logs/error.log
```

## Troubleshooting

### High Latency

```bash
# Check STT latency
curl http://localhost:8080/metrics | grep stt_latency

# Check LLM latency
curl http://localhost:8080/metrics | grep llm_latency

# Check TTS latency
curl http://localhost:8080/metrics | grep tts_latency
```

### Calls Not Connecting

1. Check Twilio webhook configuration
2. Verify environment variables
3. Check logs for errors
4. Test health endpoint

### Memory Leaks

```bash
# Monitor memory usage
docker stats voice-orchestrator

# Check for leaked WebSocket connections
curl http://localhost:8080/metrics | grep websocket_connections
```

## Performance Tuning

### Concurrency

```env
# Increase concurrent calls
MAX_CONCURRENT_CALLS=200

# Adjust Redis connection pool
REDIS_MAX_CONNECTIONS=50
```

### Latency Optimization

- Use regional endpoints for STT/TTS
- Enable HTTP/2 for LLM requests
- Implement request batching
- Use connection pooling

## Security

### Production Checklist

- [ ] Change all default passwords
- [ ] Generate strong encryption keys
- [ ] Enable HTTPS/WSS
- [ ] Configure firewall rules
- [ ] Set up VPN for database
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Review PII handling
- [ ] Enable audit logging

## License

Proprietary - TL Development, LLC

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/voice-os/issues
- Email: support@your-domain.com
