from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime, timezone
from sqlalchemy.orm import relationship
from app.database.database import Base

class CaseReferral(Base):
    __tablename__ = "case_referrals"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaint.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    designated_officer = Column(String, nullable=True) # Person who will send the case to a department from lgu
    designated_officer_position = Column(String, nullable=True) # Position of the designated officer
    reason_for_referral = Column(String, nullable=True) # Reason for referring the case to another department
    requested_action = Column(String, nullable=True) # Action requested from the department to which the case is referred
    reference_number = Column(String, nullable=True) # Reference number for tracking the case referral
    receiving_officer = Column(String, nullable=True) # Person who will receive the case referral
    receiving_officer_position = Column(String, nullable=True) # Position of the receiving officer
    letter_date = Column(DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc)) # Date of the referral letter
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    complaint = relationship("Complaint", back_populates="referrals")
    department = relationship("Department", back_populates="referrals")