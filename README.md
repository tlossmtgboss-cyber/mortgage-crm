# Mortgage CRM

A FastAPI-based CRM system for managing mortgage leads with AI-powered assistant capabilities.

## Features

- User authentication with JWT tokens
- Protected API endpoints
- AI assistant integration for lead management
- PostgreSQL database backend
- Zapier integration support

## Prerequisites

- Python 3.8+
- PostgreSQL database
- pip (Python package manager)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/tlossmtgboss-cyber/mortgage-crm.git
   cd mortgage-crm
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your settings:
   ```env
   DATABASE_URL=postgresql://user:password@localhost/mortgage_crm
   SECRET_KEY=your-secret-key-here
   OPENAI_API_KEY=your-openai-api-key
   ```

4. **Initialize the database**
   
   The application will automatically create tables on first run.

5. **Run the application**
   ```bash
   uvicorn app.main:app --reload
   ```
   
   The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Authentication

### 1. Register a New User

```bash
curl -X POST "http://localhost:8000/api/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "securepassword123",
    "full_name": "Admin User"
  }'
```

### 2. Login to Obtain Bearer Token

```bash
curl -X POST "http://localhost:8000/api/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "securepassword123"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Use Bearer Token for Protected Endpoints

```bash
curl -X POST "http://localhost:8000/api/assistant" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me all leads from this month"
  }'
```

## Testing

See the `/tests` directory for automated test scripts:

- `test_auth_flow.py` - Pytest script for authentication flow
- `test_auth_flow.sh` - Shell script using curl for authentication
- `test_assistant.py` - Pytest script for testing the assistant endpoint

### Running Tests

**Python/Pytest:**
```bash
pytest tests/test_auth_flow.py -v
pytest tests/test_assistant.py -v
```

**Shell/curl:**
```bash
chmod +x tests/test_auth_flow.sh
./tests/test_auth_flow.sh
```

## Project Structure

```
mortgage-crm/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application entry point
│   ├── auth.py           # Authentication endpoints and logic
│   ├── assistant.py      # AI assistant endpoints
│   ├── models.py         # Database models
│   ├── db.py             # Database connection
│   └── zapier.py         # Zapier integration
├── static/               # Static files
├── tests/                # Test scripts
│   ├── test_auth_flow.py
│   ├── test_auth_flow.sh
│   └── test_assistant.py
├── .env.example          # Example environment variables
├── requirements.txt      # Python dependencies
├── Procfile              # Heroku deployment configuration
└── README.md             # This file
```

## Deployment

This application is configured for deployment on Heroku using the included `Procfile`.

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:hobby-dev
git push heroku main
```

## License

MIT License

## Support

For issues and questions, please open an issue on GitHub.
