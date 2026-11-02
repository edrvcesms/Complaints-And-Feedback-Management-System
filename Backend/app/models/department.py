from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime, timezone
from sqlalchemy.orm import relationship
from app.database.database import Base

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    abbreviation = Column(String, unique=True, index=True)
    description = Column(String)
    office_address = Column(String)
    contact_number = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    referrals = relationship("CaseReferral", back_populates="department")
