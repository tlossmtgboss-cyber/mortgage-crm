from fastapi import FastAPI, HTTPException, Request, Form, Depends, UploadFile, File, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mortgage-crm-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Register all API routers
app.include_router(zapier.router)
app.include_router(leads.router)
app.include_router(active_loans.router)
app.include_router(portfolio.router)
app.include_router(tasks.router)
app.include_router(calendar.router)
app.include_router(assistant.router)

@app.on_event("startup")
def on_startup():
    create_db()

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/crm.html")

def log_event(db: Session, event_type, from_number, body_or_status):
    entry = EventLog(event_type=event_type, from_number=from_number, body_or_status=body_or_status)
    db.add(entry)
    db.commit()

# Authentication Models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "user"

# Authentication helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user_from_db(db: Session, username: str):
    """Fetch user from database by username"""
    return db.query(DBUser).filter(DBUser.username == username).first()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    # Fetch user from database
    db_user = get_user_from_db(db, username=username)
    if db_user is None:
        raise credentials_exception
    
    return User(
        username=db_user.username,
        email=db_user.email,
        full_name=db_user.full_name,
        disabled=False
    )

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# Authentication endpoints
@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Authenticate user from database
    db_user = get_user_from_db(db, form_data.username)
    if not db_user or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), email: str = Form(...), db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = get_user_from_db(db, username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = db.query(DBUser).filter(DBUser.email == email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user in database
    hashed_password = get_password_hash(password)
    new_user = DBUser(
        username=username,
        email=email,
        hashed_password=hashed_password,
        full_name=username  # Default full_name to username
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": "User registered successfully",
        "username": new_user.username,
        "email": new_user.email
    }

# New JSON-based registration endpoint for frontend
@app.post("/api/users/register")
async def register_json(request: RegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = get_user_from_db(db, request.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    existing_email = db.query(DBUser).filter(DBUser.email == request.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user in database
    hashed_password = get_password_hash(request.password)
    new_user = DBUser(
        username=request.username,
        email=request.email,
        hashed_password=hashed_password,
        full_name=request.username,  # Default full_name to username
        role=request.role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": "User registered successfully",
        "username": new_user.username,
        "email": new_user.email
    }

@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.get("/protected")
async def protected_route(current_user: User = Depends(get_current_active_user)):
    return {"message": f"Hello {current_user.username}, you have access to this protected route!"}

# --- Email (SMTP2GO) ---
SMTP2GO_API_KEY = os.getenv("SMTP2GO_API_KEY")
SMTP2GO_SENDER = os.getenv("SMTP2GO_SENDER")

@app.post("/send-email")
async def send_email(
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    cc: str = Form(None),
    bcc: str = Form(None),
    html_body: str = Form(None),
    attachments: list[UploadFile] = File(default_factory=list)
):
    url = "https://api.smtp2go.com/v3/email/send"
    payload = {
        "api_key": SMTP2GO_API_KEY,
        "to": [addr.strip() for addr in to.split(",")],
        "sender": SMTP2GO_SENDER,
        "subject": subject,
        "text_body": body
    }
    if cc:
        payload["cc"] = [addr.strip() for addr in cc.split(",")]
    if bcc:
        payload["bcc"] = [addr.strip() for addr in bcc.split(",")]
    if html_body:
        payload["html_body"] = html_body
    if attachments:
        payload["attachments"] = []
        for upload in attachments:
            file_data = await upload.read()
            b64content = base64.b64encode(file_data).decode()
            payload["attachments"].append({
                "filename": upload.filename,
                "content": b64content
            })
    response = requests.post(url, json=payload)
    resp_json = response.json()
    if response.status_code == 200 and resp_json.get("data", {}).get("succeeded"):
        return JSONResponse(content={"detail": "Email sent successfully", "smtp2go": resp_json})
    else:
        raise HTTPException(status_code=400, detail={"smtp2go": resp_json})

# --- SMS / Call (Twilio) ---
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

class SmsReq(BaseModel):
    to: str
    body: str

@app.post("/send-sms")
def send_sms(req: SmsReq, db: Session = Depends(get_db)):
    msg = twilio_client.messages.create(
        body=req.body,
        from_=TWILIO_NUMBER,
        to=req.to
    )
    log_event(db, "SMS", req.to, req.body)
    if msg.error_code:
        raise HTTPException(status_code=400, detail=msg.error_message)
    return {"sid": msg.sid}

class CallReq(BaseModel):
    to: str

@app.post("/make-call")
def make_call(req: CallReq, db: Session = Depends(get_db)):
    call = twilio_client.calls.create(
        to=req.to,
        from_=TWILIO_NUMBER,
        url="https://handler.twilio.com/twiml/EH..."  # Replace with your TwiML URL!
    )
    log_event(db, "CALL", req.to, "call initiated")
    if call.error_code:
        raise HTTPException(status_code=400, detail=call.error_message)
    return {"sid": call.sid}
