# Perennia AI Receptionist - Deployment Package

One-command deployment for the AI Receptionist system.

## Quick Start

```bash
# 1. Make deploy script executable
chmod +x deploy.sh

# 2. Run interactive setup
./deploy.sh --setup

# 3. Start with ngrok (development)
./deploy.sh --ngrok

# OR deploy with Docker (production)
./deploy.sh --docker
```

## Files Included

| File | Description |
|------|-------------|
| `deploy.sh` | Main deployment script |
| `main.py` | Application entry point |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Full stack deployment |
| `nginx.conf` | Production reverse proxy |
| `init.sql` | Database initialization |
| `.env.example` | Environment template |

## Deployment Options

### Option 1: Local Development (with ngrok)

```bash
# Interactive setup + ngrok tunnel
./deploy.sh --setup
./deploy.sh --ngrok
```

This will:
1. Create virtual environment
2. Install dependencies
3. Start ngrok tunnel
4. Auto-configure Twilio webhook
5. Start the server

### Option 2: Docker (Production)

```bash
# Build and run
./deploy.sh --docker

# Or with full stack (DB + Redis + Nginx)
docker-compose up -d
```

### Option 3: Manual

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your values

# Run server
python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `./deploy.sh --setup` | Interactive setup |
| `./deploy.sh --check` | Check configuration |
| `./deploy.sh --local` | Run locally |
| `./deploy.sh --ngrok` | Run with ngrok |
| `./deploy.sh --docker` | Deploy with Docker |
| `./deploy.sh --compose` | Deploy full stack |
| `./deploy.sh --webhook` | Configure Twilio |
| `./deploy.sh --health` | Health check |
| `./deploy.sh --test-call` | Make test call |

## Required API Keys

| Service | Purpose | Get From |
|---------|---------|----------|
| Twilio | Voice calls | https://console.twilio.com |
| Anthropic | LLM (Claude) | https://console.anthropic.com |
| Deepgram | Speech-to-text | https://console.deepgram.com |
| ElevenLabs | Text-to-speech | https://elevenlabs.io |

## Twilio Webhook Configuration

After deployment, configure your Twilio phone number:

1. Go to https://console.twilio.com
2. Navigate to Phone Numbers → Manage → Active numbers
3. Click your number
4. Set Voice Configuration:
   - **Voice URL**: `https://your-domain.com/voice/inbound`
   - **Method**: POST

Or run `./deploy.sh --webhook` to auto-configure.

## Testing

```bash
# Test without phone (simulation)
python main.py --simulate

# Run test scenario
python main.py --test

# Make actual test call
./deploy.sh --test-call
```

## Production Checklist

- [ ] SSL certificate configured
- [ ] Environment variables set
- [ ] Twilio webhook configured
- [ ] Database initialized
- [ ] Health check passing
- [ ] Monitoring configured
- [ ] Backup strategy in place

## Support

For issues, check:
- Twilio debugger: https://console.twilio.com/debugger
- Server health: `curl https://your-domain.com/health`
- Logs: `docker-compose logs -f`
