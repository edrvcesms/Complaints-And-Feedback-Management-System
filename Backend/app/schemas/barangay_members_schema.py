from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Literal

class BarangayMemberLocation(BaseModel):
    latitude: str | None = None
    longitude: str | None = None
    location_updated_at: datetime | None = None

    @field_validator("location_updated_at")
    @classmethod
    def normalize_location_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    class Config:
        from_attributes = True

class BarangayMemberBase(BaseModel):
    id: int
    barangay_id: int
    name: str
    position: str

    class Config:
        from_attributes = True
    
class BarangayMemberCreate(BaseModel):
    name: str = Field(min_length=1)
    position: Literal[
        "Punong Barangay",
        "Pangkat ng Tagapagkasundo",
        "Lupong Tagapamayapa",
        "Kagawad (Peace & Order)",
        "Barangay Tanod",
    ]
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("name", "position")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 UTF-8 bytes.")
        return value
    

class BarangayDutyUpdate(BaseModel):
    start_of_duty: datetime
    end_of_duty: datetime | None = None


class BarangayMemberDuty(BaseModel):
    name: str
    position: str
    start_of_duty: datetime | None
    end_of_duty: datetime | None
    is_on_duty: bool

    class Config:
        from_attributes = True


class BarangayMemberFullData(BaseModel):
    id: int
    user_id: int | None = None
    barangay_id: int
    name: str
    position: str
    user: BarangayMemberLocation | None = None

    class Config:
        from_attributes = True
    