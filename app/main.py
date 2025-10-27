from fastapi import FastAPI, HTTPException, Request, Form, Depends, UploadFile, File, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, ValidationError
from sqlalchemy.orm import Session
from app.models import EventLog, User as DBUser
from app.db import SessionLocal, create_db, get_db
from app import zapier
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
from app.app import leads, active_loans, portfolio, tasks, calendar
from app import assistant

# Authentication configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(
    title="Mortgage CRM API",
    description="Complete CRM system for mortgage lead and loan management",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mortgage-crm-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility logging
def log_event(db: Session, event_type: str, message: str, severity: str = "INFO", details: Optional[dict] = None):
    try:
        payload = {
            "eventType": event_type,
            "message": message,
            "severity": severity,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        # Store in DB if available
        try:
            log = EventLog(
                event_type=event_type,
                message=message,
                severity=severity,
                details=json.dumps(details or {}),
                created_at=datetime.utcnow(),
            )
            db.add(log)
            db.commit()
        except Exception as db_err:
            print("[LOG][DB-ERROR]", db_err)
        # Always print to stdout for quick debugging
        print("[LOG]", json.dumps(payload))
    except Exception as e:
        print("[LOG][FALLBACK-ERROR]", e)

# Password utilities
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Pydantic models for auth
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    username: Optional[str] = None

class UserLogin(BaseModel):
    identifier: str
    password: str

# Root
@app.get("/")
def read_root():
    return {"message": "Mortgage CRM Backend is running"}

# ---------------------- AUTH ENDPOINTS WITH DETAILED LOGGING ----------------------

@app.post("/api/users/register")
async def register_user(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8") if raw_body else ""
    try:
        log_event(db, "register_attempt", "Incoming register request payload", details={"raw": body_text})
        data = await request.json()
        try:
            user_in = UserRegister(**data)
        except ValidationError as ve:
            log_event(db, "register_validation_error", "Pydantic validation failed", severity="ERROR", details={"errors": ve.errors(), "data": data})
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Validation error", "errors": ve.errors()})
        
        existing = db.query(DBUser).filter(DBUser.email == user_in.email).first()
        if existing:
            log_event(db, "register_conflict", "Email already registered", severity="WARNING", details={"email": user_in.email})
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed = get_password_hash(user_in.password)
        # Set username from payload, fallback to email if not provided
        username = user_in.username if user_in.username else user_in.email
        user = DBUser(email=user_in.email, hashed_password=hashed, full_name=user_in.full_name, username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
        log_event(db, "register_success", "User registered successfully", details={"user_id": user.id, "email": user.email, "username": username})
        return {"message": "User registered successfully", "user_id": user.id}
    except HTTPException as he:
        log_event(db, "register_http_exception", "HTTPException during register", severity="ERROR", details={"status_code": he.status_code, "detail": he.detail})
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log_event(db, "register_exception", "Unhandled exception during register", severity="ERROR", details={"error": str(e), "trace": tb, "raw": body_text})
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})

@app.post("/api/users/login")
async def login_user(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8") if raw_body else ""
    try:
        log_event(db, "login_attempt", "Incoming login request payload", details={"raw": body_text})
        data = await request.json()
        try:
            creds = UserLogin(**data)
        except ValidationError as ve:
            log_event(db, "login_validation_error", "Pydantic validation failed", severity="ERROR", details={"errors": ve.errors(), "data": data})
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Validation error", "errors": ve.errors()})
        
        # Find user by identifier (first by email, then by username)
        user = db.query(DBUser).filter(DBUser.email == creds.identifier).first()
        if not user:
            user = db.query(DBUser).filter(DBUser.username == creds.identifier).first()
        
        if not user:
            log_event(db, "login_user_not_found", "No user found for identifier", severity="WARNING", details={"identifier": creds.identifier})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if not verify_password(creds.password, user.hashed_password):
            log_event(db, "login_bad_password", "Password verification failed", severity="WARNING", details={"user_id": user.id, "email": user.email})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        access_token = create_access_token({"sub": str(user.id)})
        log_event(db, "login_success", "User logged in successfully", details={"user_id": user.id})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as he:
        log_event(db, "login_http_exception", "HTTPException during login", severity="ERROR", details={"status_code": he.status_code, "detail": he.detail})
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log_event(db, "login_exception", "Unhandled exception during login", severity="ERROR", details={"error": str(e), "trace": tb, "raw": body_text})
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"})

# ---------------------- OTHER ROUTES (existing code) ----------------------
# Mount static, include routers, assistant endpoints, lead/loan endpoints, etc.
# NOTE: Retain existing implementations below. If these were present earlier in the file,
# they should remain unchanged. If this file already had implementations, ensure you merge
# the new logging for auth endpoints with the existing definitions rather than duplicate.

# Include routers
app.include_router(leads.router, prefix="/api")
app.include_router(active_loans.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")

# You may have additional endpoints below such as email/SMS/call; leaving them as-is.
