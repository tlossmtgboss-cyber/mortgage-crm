# Agentic AI Mortgage CRM - Backend

Complete FastAPI backend for mortgage CRM with AI automation features.

## Features

- **Complete CRUD Operations** for all entities:
  - Leads (with AI scoring)
  - Loans (with AI insights)
  - AI Tasks
  - Referral Partners
  - MUM Clients (Manage, Upsell, Maintain)
  - Activities

- **Authentication & Security**:
  - JWT token-based auth
  - Password hashing with bcrypt
  - Role-based access control

- **AI Features**:
  - Automatic lead scoring
  - Loan risk assessment
  - Predictive insights
  - Task automation

- **Analytics**:
  - Conversion funnel
  - Pipeline metrics
  - Performance tracking

## Quick Start

### Option 1: With Docker (Easiest)

```bash
# Start PostgreSQL database
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Run the server
python main.py
```

### Option 2: Manual Setup

#### 1. Install PostgreSQL

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Download from https://www.postgresql.org/download/windows/

#### 2. Create Database

```bash
# Login to PostgreSQL
psql postgres

# Create database and user
CREATE DATABASE agentic_crm;
CREATE USER postgres WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE agentic_crm TO postgres;
\q
```

#### 3. Setup Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 4. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env and update values
nano .env
```

Update at minimum:
- `DATABASE_URL` - Your PostgreSQL connection string
- `SECRET_KEY` - Generate with: `openssl rand -hex 32`
- `OPENAI_API_KEY` - (Optional) For AI features

#### 5. Run the Server

```bash
python main.py
```

The API will be available at:
- API: http://localhost:8000
- Interactive Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Default Demo Account

```
Email: demo@example.com
Password: demo123
```

## API Endpoints

### Authentication
- `POST /token` - Login and get JWT token
- `POST /api/v1/register` - Register new user

### Leads
- `GET /api/v1/leads/` - List all leads
- `POST /api/v1/leads/` - Create new lead
- `GET /api/v1/leads/{id}` - Get lead details
- `PATCH /api/v1/leads/{id}` - Update lead
- `DELETE /api/v1/leads/{id}` - Delete lead

### Loans
- `GET /api/v1/loans/` - List all loans
- `POST /api/v1/loans/` - Create new loan
- `GET /api/v1/loans/{id}` - Get loan details
- `PATCH /api/v1/loans/{id}` - Update loan
- `DELETE /api/v1/loans/{id}` - Delete loan

### AI Tasks
- `GET /api/v1/tasks/` - List all tasks
- `POST /api/v1/tasks/` - Create new task
- `GET /api/v1/tasks/{id}` - Get task details
- `PATCH /api/v1/tasks/{id}` - Update task
- `DELETE /api/v1/tasks/{id}` - Delete task

### Referral Partners
- `GET /api/v1/referral-partners/` - List all partners
- `POST /api/v1/referral-partners/` - Create partner
- `GET /api/v1/referral-partners/{id}` - Get partner details
- `PATCH /api/v1/referral-partners/{id}` - Update partner
- `DELETE /api/v1/referral-partners/{id}` - Delete partner

### MUM Clients
- `GET /api/v1/mum-clients/` - List all MUM clients
- `POST /api/v1/mum-clients/` - Create MUM client
- `GET /api/v1/mum-clients/{id}` - Get client details
- `PATCH /api/v1/mum-clients/{id}` - Update client
- `DELETE /api/v1/mum-clients/{id}` - Delete client

### Activities
- `GET /api/v1/activities/` - List activities
- `POST /api/v1/activities/` - Create activity
- `DELETE /api/v1/activities/{id}` - Delete activity

### Analytics
- `GET /api/v1/dashboard` - Dashboard overview
- `GET /api/v1/analytics/conversion-funnel` - Conversion metrics
- `GET /api/v1/analytics/pipeline` - Pipeline analytics

## Testing with cURL

### 1. Register a User
```bash
curl -X POST "http://localhost:8000/api/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "test123",
    "full_name": "Test User"
  }'
```

### 2. Login
```bash
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123"
```

Save the `access_token` from response.

### 3. Create a Lead
```bash
curl -X POST "http://localhost:8000/api/v1/leads/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Lead",
    "email": "lead@example.com",
    "phone": "555-1234",
    "credit_score": 720,
    "preapproval_amount": 400000
  }'
```

### 4. Get Dashboard
```bash
curl -X GET "http://localhost:8000/api/v1/dashboard" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Database Migrations (Future)

To setup Alembic for database migrations:

```bash
# Initialize Alembic
alembic init alembic

# Create a migration
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

## Development

### Run in Development Mode
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Run Tests
```bash
pytest
```

### Code Formatting
```bash
pip install black isort
black .
isort .
```

## Production Deployment

### Environment Variables
Ensure these are set in production:
- `DATABASE_URL` - Production database URL
- `SECRET_KEY` - Strong random secret
- `ENVIRONMENT=production`

### Run with Gunicorn
```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Docker Deployment
```bash
# Build image
docker build -t mortgage-crm-backend .

# Run container
docker run -p 8000:8000 --env-file .env mortgage-crm-backend
```

## Troubleshooting

### Database Connection Issues
```bash
# Check if PostgreSQL is running
pg_isready

# Check connection
psql -U postgres -d agentic_crm
```

### Port Already in Use
```bash
# Find process on port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Import Errors
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

## API Documentation

Visit http://localhost:8000/docs for interactive API documentation (Swagger UI).

## Support

For issues or questions:
1. Check the API docs at `/docs`
2. Review the logs for error messages
3. Ensure database is running and accessible
4. Verify environment variables are set correctly

## License

Proprietary - All rights reserved
