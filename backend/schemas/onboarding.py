from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, Dict, Any
from datetime import datetime
import re

from utils.validators import validate_nmls


class BusinessHours(BaseModel):
    """Business hours for each day of the week"""
    monday: Optional[Dict[str, Any]] = Field(default={"open": "09:00", "close": "17:00"})
    tuesday: Optional[Dict[str, Any]] = Field(default={"open": "09:00", "close": "17:00"})
    wednesday: Optional[Dict[str, Any]] = Field(default={"open": "09:00", "close": "17:00"})
    thursday: Optional[Dict[str, Any]] = Field(default={"open": "09:00", "close": "17:00"})
    friday: Optional[Dict[str, Any]] = Field(default={"open": "09:00", "close": "17:00"})
    saturday: Optional[Dict[str, Any]] = Field(default={"closed": True})
    sunday: Optional[Dict[str, Any]] = Field(default={"closed": True})


class Step1Data(BaseModel):
    """Schema for Step 1 registration data"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str
    nmls_number: str
    business_address: str = Field(..., min_length=1, max_length=500)
    current_role: str = Field(..., min_length=1, max_length=100)
    business_hours: BusinessHours
    email_verified: Optional[bool] = False
    phone_verified: Optional[bool] = False

    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number format"""
        # Remove all non-digit characters
        cleaned = re.sub(r'\D', '', v)
        if len(cleaned) != 10:
            raise ValueError('Phone number must be 10 digits')
        return v

    @validator('nmls_number')
    def validate_nmls_number(cls, v):
        """Validate NMLS number format (5-12 digits)."""
        result = validate_nmls(v)
        if result is None:
            raise ValueError('Invalid NMLS format. Must be 5-12 digits.')
        return result


class OnboardingProgressResponse(BaseModel):
    """Response schema for onboarding progress"""
    id: int
    user_id: int
    current_step: int
    step_1_data: Optional[Dict[str, Any]]
    step_2_data: Optional[Dict[str, Any]]
    step_3_data: Optional[Dict[str, Any]]
    step_4_data: Optional[Dict[str, Any]]
    step_5_data: Optional[Dict[str, Any]]
    step_6_data: Optional[Dict[str, Any]]
    step_7_data: Optional[Dict[str, Any]]
    step_8_data: Optional[Dict[str, Any]]
    step_9_data: Optional[Dict[str, Any]]
    step_10_data: Optional[Dict[str, Any]]
    completed_at: Optional[datetime]
    last_updated: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class VerifyCodeRequest(BaseModel):
    """Request to verify a 6-digit code"""
    code: str

    @validator('code')
    def validate_code(cls, v):
        """Validate code is 6 digits"""
        if not v.isdigit() or len(v) != 6:
            raise ValueError('Code must be a 6-digit number')
        return v


class SendVerificationRequest(BaseModel):
    """Request to send verification email or SMS"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number if provided"""
        if v:
            cleaned = re.sub(r'\D', '', v)
            if len(cleaned) != 10:
                raise ValueError('Phone number must be 10 digits')
        return v
