from fastapi import FastAPI, HTTPException, Request, Form, Depends, UploadFile, File, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, ValidationError, ConfigDict
from sqlalchemy.orm import Session
from models import EventLog, User as DBUser
from db import SessionLocal, create_db, get_db
try:
    import zapier
except ImportError:
    zapier = None
from twilio.rest import Client as TwilioClient
import requests
import os
import base64
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional
import traceback
import json

# Import new API routers
try:
    from app import leads, active_loans, portfolio, tasks, calendar
except ImportError:
    leads = active_loans = portfolio = tasks = calendar = None

try:
    import assistant
except ImportError:
    assistant = None

# Authentication configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(
    title="Mortgage CRM API",
    description="Complete CRM system for mortgage lead and loan management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models with modern ConfigDict
class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool

class UserLogin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    identifier: str  # Can be username or email
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class SMSRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    to: str
    message: str

# Utility functions
def log_event(db: Session, event_type: str, message: str, severity: str = "INFO", details: dict = None):
    """Log events to the database"""
    try:
        event_log = EventLog(
            event_type=event_type,
            from_number="system",
            body_or_status=message
        )
        db.add(event_log)
        db.commit()
    except Exception as e:
        print(f"Failed to log event: {e}")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_by_username(db: Session, username: str):
    return db.query(DBUser).filter(DBUser.username == username).first()

def get_user_by_email(db: Session, email: str):
    return db.query(DBUser).filter(DBUser.email == email).first()

def authenticate_user(db: Session, identifier: str, password: str):
    # Try to find user by username or email
    user = get_user_by_username(db, identifier)
    if not user:
        user = get_user_by_email(db, identifier)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

# Routes
@app.get("/")
async def root():
    """Health check endpoint that returns JSON"""
    return {"status": "ok", "message": "Mortgage CRM API is running"}

@app.post("/api/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        # Check if user already exists
        existing_user = get_user_by_username(db, user_data.username)
        if existing_user:
            log_event(db, "register_failed", "Username already exists", "WARNING", {"username": user_data.username})
            raise HTTPException(status_code=400, detail="Username already registered")
        
        existing_email = get_user_by_email(db, user_data.email)
        if existing_email:
            log_event(db, "register_failed", "Email already exists", "WARNING", {"email": user_data.email})
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        db_user = DBUser(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name or "",
            role="user"
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        log_event(db, "register_success", "User registered successfully", details={"user_id": db_user.id})
        return db_user
        
    except HTTPException:
        raise
    except Exception as e:
        log_event(db, "register_exception", "Unhandled exception during registration", "ERROR", {"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/login", response_model=Token)
async def login_user(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login user and return access token"""
    try:
        user = authenticate_user(db, user_data.identifier, user_data.password)
        if not user:
            log_event(db, "login_failed", "Invalid credentials", "WARNING", {"identifier": user_data.identifier})
            raise HTTPException(status_code=401, detail="Incorrect username/email or password")
        
        if not user.is_active:
            log_event(db, "login_failed", "Inactive user attempted login", "WARNING", {"user_id": user.id})
            raise HTTPException(status_code=400, detail="Inactive user")
        
        access_token = create_access_token({"sub": str(user.id)})
        log_event(db, "login_success", "User logged in successfully", details={"user_id": user.id})
        return {"access_token": access_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        log_event(db, "login_exception", "Unhandled exception during login", "ERROR", {"error": str(e)})
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/send-sms")
async def send_sms(sms_data: SMSRequest, db: Session = Depends(get_db)):
    """
    Send an SMS via Twilio.
    Expects TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in environment.
    """
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([account_sid, auth_token, from_number]):
            log_event(db, "sms_config_error", "Missing Twilio configuration", severity="ERROR")
            raise HTTPException(status_code=500, detail="Twilio not configured")
        
        client = TwilioClient(account_sid, auth_token)
        message = client.messages.create(
            body=sms_data.message,
            from_=from_number,
            to=sms_data.to
        )
        
        log_event(db, "sms_sent", f"SMS sent successfully to {sms_data.to}", details={"message_sid": message.sid})
        return {"success": True, "message_sid": message.sid}
        
    except Exception as e:
        log_event(db, "sms_error", "Failed to send SMS", severity="ERROR", details={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")

# Include routers if they exist
if leads:
    app.include_router(leads.router, prefix="/api")
if active_loans:
    app.include_router(active_loans.router, prefix="/api")
if portfolio:
    app.include_router(portfolio.router, prefix="/api")
if tasks:
    app.include_router(tasks.router, prefix="/api")
if calendar:
    app.include_router(calendar.router, prefix="/api")
if assistant:
    app.include_router(assistant.router, prefix="/api")

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    create_db()

# Main entry point for running the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
