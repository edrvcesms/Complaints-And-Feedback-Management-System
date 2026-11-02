from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import List, Optional
from .complaint_schema import ComplaintOut
from .response_schema import ResponseSchema
from .category_schema import CategoryModel
from .barangay_schema import BarangayModel


class IncidentBaseModel(BaseModel):
    title: str
    description: str
    barangay_id: int
    category_id: int
    status: Optional[str] = None
    complaint_count: int
    severity_level: str
    response_id: Optional[int] = None

class IncidentComplaintClusterModel(BaseModel):
    id: int
    complaint_id: int
    incident_id: int
    similarity_score: float
    linked_at: datetime
    complaint: ComplaintOut

    class Config:
        from_attributes = True

class IncidentData(IncidentBaseModel):
    id: int
    severity_score: float
    first_reported_at: datetime
    last_reported_at: datetime
    hearing_count: Optional[int] = 0
    hearing_date: Optional[datetime] = None
    is_hearing_successful: Optional[bool] = None
    category: Optional[CategoryModel] = None
    barangay: Optional[BarangayModel] = None
    complaint_clusters: List[IncidentComplaintClusterModel] = []
    has_new_complaints: Optional[bool] = False
    new_complaint_count: Optional[int] = 0
    hearing_date: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_resolvable: bool = True
    responses: Optional[List[ResponseSchema]] = None

    @field_validator("is_resolvable", mode="before")
    @classmethod
    def default_unset_resolvability(cls, value: Optional[bool]) -> bool:
        return value is not False

    class Config:
        from_attributes = True
        
class IncidentOut(BaseModel):
    id: int
    title: str
    description: str
    barangay_id: int
    barangay: Optional[BarangayModel] = None
    category_id: int
    status: Optional[str] = None
    complaint_count: int
    severity_level: str
    hearing_count: Optional[int] = 0
    hearing_date: Optional[datetime] = None
    is_hearing_successful: Optional[bool] = None
    category: Optional[CategoryModel] = None   
    complaint_count: int
    complaint_clusters: List[IncidentComplaintClusterModel] = []
    has_new_complaints: Optional[bool] = False
    new_complaint_count: Optional[int] = 0
    first_reported_at: datetime
    last_reported_at: datetime
    is_resolvable: bool = True

    @field_validator("is_resolvable", mode="before")
    @classmethod
    def default_unset_resolvability(cls, value: Optional[bool]) -> bool:
        return value is not False

    class Config:
        from_attributes = True
