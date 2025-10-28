from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime, timedelta
import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.db import get_db, Base, engine
from app.models import Lead as LeadModel, User as UserModel, Appointment as AppointmentModel
import logging
from app.zapier import zapier_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mortgage CRM API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Zapier router
app.include_router(zapier_router, prefix="/api")

# Create tables
Base.metadata.create_all(bind=engine)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pydantic models
class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    
    class Config:
        # Allow using 'username' as an alias for 'email' for backward compatibility
        fields = {'email': {'alias': 'username'}}

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    email: str
    role: str
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class Lead(BaseModel):
    name: str
    email: str
    phone: str
    loan_amount: Optional[float] = None
    status: Optional[str] = "new"
    
class LeadResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    loan_amount: Optional[float]
    status: str
    created_at: datetime
    user_id: int
    
    class Config:
        from_attributes = True

class AppointmentCreate(BaseModel):
    lead_id: int
    appointment_date: datetime
    notes: Optional[str] = None

class AppointmentResponse(BaseModel):
    id: int
    lead_id: int
    appointment_date: datetime
    notes: Optional[str]
    created_at: datetime
    user_id: int
    
    class Config:
        from_attributes = True

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

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
    
    user = db.query(UserModel).filter(UserModel.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: UserModel = Depends(get_current_user)):
    return current_user

# Routes
@app.get("/")
async def root():
    return {"message": "Mortgage CRM API", "status": "running"}

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists by email
    db_user = db.query(UserModel).filter(UserModel.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username (email) already exists
    db_user_by_username = db.query(UserModel).filter(UserModel.username == user.email).first()
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user with email as username
    hashed_password = get_password_hash(user.password)
    new_user = UserModel(
        username=user.email,  # Use email as username
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role="user"  # Use string instead of UserRole.USER
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=UserResponse)
async def read_users_me(current_user: UserModel = Depends(get_current_active_user)):
    return current_user

@app.post("/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead: Lead,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db_lead = LeadModel(
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        loan_amount=lead.loan_amount,
        status=lead.status,
        user_id=current_user.id
    )
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    return db_lead

@app.get("/leads", response_model=List[LeadResponse])
async def get_leads(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    leads = db.query(LeadModel).filter(LeadModel.user_id == current_user.id).all()
    return leads

@app.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    lead = db.query(LeadModel).filter(
        LeadModel.id == lead_id,
        LeadModel.user_id == current_user.id
    ).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return lead

@app.put("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead: Lead,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db_lead = db.query(LeadModel).filter(
        LeadModel.id == lead_id,
        LeadModel.user_id == current_user.id
    ).first()
    
    if not db_lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    db_lead.name = lead.name
    db_lead.email = lead.email
    db_lead.phone = lead.phone
    db_lead.loan_amount = lead.loan_amount
    db_lead.status = lead.status
    
    db.commit()
    db.refresh(db_lead)
    return db_lead

@app.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db_lead = db.query(LeadModel).filter(
        LeadModel.id == lead_id,
        LeadModel.user_id == current_user.id
    ).first()
    
    if not db_lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    db.delete(db_lead)
    db.commit()
    return None

@app.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    appointment: AppointmentCreate,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify lead exists and belongs to user
    lead = db.query(LeadModel).filter(
        LeadModel.id == appointment.lead_id,
        LeadModel.user_id == current_user.id
    ).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    db_appointment = AppointmentModel(
        lead_id=appointment.lead_id,
        appointment_date=appointment.appointment_date,
        notes=appointment.notes,
        user_id=current_user.id
    )
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@app.get("/appointments", response_model=List[AppointmentResponse])
async def get_appointments(
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    appointments = db.query(AppointmentModel).filter(
        AppointmentModel.user_id == current_user.id
    ).all()
    return appointments

@app.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    appointment = db.query(AppointmentModel).filter(
        AppointmentModel.id == appointment_id,
        AppointmentModel.user_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    return appointment

@app.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int,
    current_user: UserModel = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    db_appointment = db.query(AppointmentModel).filter(
        AppointmentModel.id == appointment_id,
        AppointmentModel.user_id == current_user.id
    ).first()
    
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    db.delete(db_appointment)
    db.commit()
    return None
