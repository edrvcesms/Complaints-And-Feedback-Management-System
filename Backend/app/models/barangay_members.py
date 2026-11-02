from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database.database import Base

class BarangayMember(Base):
    __tablename__ = 'barangay_members'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    barangay_id = Column(Integer, ForeignKey('barangay.id'), nullable=False)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    start_of_duty = Column(DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc))
    end_of_duty = Column(DateTime(timezone=True), nullable=True, default=None)
    
    @property
    def is_on_duty(self) -> bool:
        """Check if the barangay member is currently on duty."""
        now = datetime.now(timezone.utc)
        if self.start_of_duty is None:
            return False

        start_of_duty = self.start_of_duty
        if start_of_duty.tzinfo is None:
            start_of_duty = start_of_duty.replace(tzinfo=timezone.utc)
        else:
            start_of_duty = start_of_duty.astimezone(timezone.utc)

        end_of_duty = self.end_of_duty
        if end_of_duty is not None:
            if end_of_duty.tzinfo is None:
                end_of_duty = end_of_duty.replace(tzinfo=timezone.utc)
            else:
                end_of_duty = end_of_duty.astimezone(timezone.utc)

        return start_of_duty <= now and (end_of_duty is None or now <= end_of_duty)
    
    user = relationship("User", back_populates="barangay_member")
    
    barangay = relationship("Barangay", back_populates="barangay_members")
    incidents = relationship(
        "IncidentModel",
        secondary="incident_barangay_members",
        back_populates="barangay_members",
    )
    complaints = relationship(
        "Complaint",
        secondary="complaint_barangay_members",
        back_populates="barangay_members",
    )
    responses = relationship(
        "Response",
        secondary="response_barangay_members",
        back_populates="barangay_members",
    )
    