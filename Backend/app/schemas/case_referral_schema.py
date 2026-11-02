from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DepartmentPublic(BaseModel):
    id: int
    name: str
    abbreviation: Optional[str] = None
    description: Optional[str] = None
    office_address: Optional[str] = None
    contact_number: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class CaseReferralBase(BaseModel):
    complaint_id: int
    department_id: int
    designated_officer: Optional[str] = None
    designated_officer_position: Optional[str] = None
    reason_for_referral: Optional[str] = None
    requested_action: Optional[str] = None
    reference_number: Optional[str] = None
    receiving_officer: Optional[str] = None
    receiving_officer_position: Optional[str] = None
    letter_date: Optional[datetime] = None


class CaseReferralCreate(CaseReferralBase):
    pass


class CaseReferralUpdate(BaseModel):
    department_id: Optional[int] = None
    designated_officer: Optional[str] = None
    designated_officer_position: Optional[str] = None
    reason_for_referral: Optional[str] = None
    requested_action: Optional[str] = None
    reference_number: Optional[str] = None
    receiving_officer: Optional[str] = None
    receiving_officer_position: Optional[str] = None
    letter_date: Optional[datetime] = None


class CaseReferralOut(CaseReferralBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    department: Optional[DepartmentPublic] = None

    class Config:
        from_attributes = True
