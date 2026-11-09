from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    suffix: Optional[str] = None
    age: Optional[int] = None
    birthdate: Optional[datetime] = None
    phone_number: Optional[str] = None
    gender: Optional[str] = None
    barangay: Optional[str] = None
    full_address: Optional[str] = None
    zip_code: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None

class UserPersonalData(UserBase):
    pass

class UserData(UserBase):
    id: int
    email: EmailStr
    role: str
    is_administrator: bool
    profile_image: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    push_notifications_enabled: Optional[bool] = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    barangay: Optional[str] = None
    full_address: Optional[str] = None
    is_verified: Optional[bool] = None
    zip_code: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    location_updated_at: Optional[datetime] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    clerk_user_id: Optional[str] = None
    front_id: Optional[str] = None
    back_id: Optional[str] = None
    selfie_with_id: Optional[str] = None
    is_suspended: Optional[bool] = None
    can_submit_complaints: Optional[bool] = None
    reject_counter: Optional[int] = None
    model_config = {
        "from_attributes": True,  
        "populate_by_name": True,
        "extra": "ignore" 
    }

class VerifyEmailData(BaseModel):
    email: EmailStr

class ChangePasswordData(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str
    confirm_new_password: str

class ResetPasswordData(BaseModel):
    email: EmailStr
    new_password: str
    confirm_new_password: str

class OTPData(BaseModel):
    email: EmailStr
    otp: str

class UserLocationData(BaseModel):
    latitude: str
    longitude: str