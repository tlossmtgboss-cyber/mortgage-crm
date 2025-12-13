# Supervisor Configuration

This directory contains Supervisor configuration files for managing PURL system services.

## Overview

Supervisor is a process control system that allows you to monitor and control multiple processes on Unix-like systems. These configurations are useful for production deployments where you need reliable process management.

## Files

| File | Description |
|------|-------------|
| `purl_services.conf` | Main configuration for PURL-related services |

## Services Managed

1. **purl_api** - Main FastAPI server (Uvicorn with 4 workers)
2. **purl_event_processor** - Background event processor
3. **purl_worker** - Celery worker for async tasks
4. **purl_beat** - Celery beat for scheduled tasks

## Installation

### Prerequisites

```bash
# Install supervisor
sudo apt-get install supervisor  # Debian/Ubuntu
# or
sudo yum install supervisor      # CentOS/RHEL
# or
pip install supervisor           # Using pip
```

### Setup

1. Copy configuration to supervisor conf.d:
```bash
sudo cp purl_services.conf /etc/supervisor/conf.d/
```

2. Create log directory:
```bash
sudo mkdir -p /var/log/purl
sudo chown app:app /var/log/purl
```

3. Reload supervisor:
```bash
sudo supervisorctl reread
sudo supervisorctl update
```

## Usage

### Start all PURL services:
```bash
sudo supervisorctl start purl:*
```

### Stop all PURL services:
```bash
sudo supervisorctl stop purl:*
```

### Restart all PURL services:
```bash
sudo supervisorctl restart purl:*
```

### Check status:
```bash
sudo supervisorctl status purl:*
```

### View logs:
```bash
# API logs
sudo tail -f /var/log/purl/api.log

# Worker logs
sudo tail -f /var/log/purl/worker.log

# Event processor logs
sudo tail -f /var/log/purl/event_processor.log
```

### Individual service control:
```bash
# Start specific service
sudo supervisorctl start purl:purl_api

# Stop specific service
sudo supervisorctl stop purl:purl_worker

# Restart specific service
sudo supervisorctl restart purl:purl_beat
```

## Configuration Customization

### Adjust for your environment

Before deploying, update the following in `purl_services.conf`:

1. **Paths** - Update `/home/app/` to match your deployment path
2. **User** - Change `user=app` to your application user
3. **Workers** - Adjust `--workers 4` based on your CPU cores
4. **Concurrency** - Adjust Celery `--concurrency=4` as needed

### Example modifications:

```ini
; For a different deployment path
directory=/opt/mortgage-crm/backend
command=/opt/mortgage-crm/venv/bin/uvicorn main:app ...

; For more API workers (recommended: 2 * CPU cores + 1)
command=... --workers 9

; For fewer Celery workers on limited resources
command=... --concurrency=2
```

## Monitoring

### Supervisor Web Interface (optional)

Add to `/etc/supervisor/supervisord.conf`:
```ini
[inet_http_server]
port=127.0.0.1:9001
username=admin
password=yourpassword
```

Then access at `http://localhost:9001`

### Health Checks

The API server exposes a health endpoint:
```bash
curl http://localhost:8000/health
```

## Troubleshooting

### Service won't start

1. Check logs:
```bash
sudo tail -50 /var/log/purl/api_error.log
```

2. Verify paths exist:
```bash
ls -la /home/app/backend/
ls -la /home/app/venv/bin/
```

3. Test command manually:
```bash
sudo -u app /home/app/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

### Permission issues

```bash
# Fix ownership
sudo chown -R app:app /home/app/backend
sudo chown -R app:app /var/log/purl

# Fix permissions
chmod 755 /home/app/backend
chmod 644 /home/app/backend/*.py
```

### Celery connection issues

Verify Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

Check CELERY_BROKER_URL in environment.

## Railway/Docker Alternative

If deploying on Railway or using Docker, you may not need Supervisor. Instead:

- **Railway**: Use Procfile or railway.json
- **Docker**: Use multi-container docker-compose

Example `Procfile`:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A tasks.celery_app worker --loglevel=INFO
beat: celery -A tasks.celery_app beat --loglevel=INFO
```
