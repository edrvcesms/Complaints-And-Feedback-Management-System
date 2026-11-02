from app.database.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, ForeignKey, Float, Index, Table
from sqlalchemy.orm import relationship
from datetime import datetime, timezone


complaint_barangay_members = Table(
    "complaint_barangay_members",
    Base.metadata,
    Column("complaint_id", ForeignKey("complaint.id", ondelete="CASCADE"), primary_key=True),
    Column("barangay_member_id", ForeignKey("barangay_members.id", ondelete="CASCADE"), primary_key=True),
)


class Complaint(Base):
    __tablename__ = "complaint"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    barangay_id = Column(Integer, ForeignKey("barangay.id"), nullable=False, index=True)
    barangay_account_id = Column(Integer, ForeignKey("barangay_account.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False, index=True)
    rejection_category_id = Column(Integer, ForeignKey("rejection_categories.id"), nullable=True, index=True)
    barangay_member_id = Column(Integer, ForeignKey("barangay_members.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    location_details = Column(String, nullable=True)

    status = Column(String, nullable=True, index=True)

    forwarded_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.now(timezone.utc))
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    hearing_date = Column(DateTime(timezone=True), nullable=True)
    is_rejected_by_lgu = Column(Boolean, default=False, nullable=True)
    has_feedback = Column(Boolean, default=False, nullable=False)
    user = relationship("User", back_populates="complaint")
    barangay = relationship("Barangay", back_populates="complaint")
    barangay_account = relationship("BarangayAccount", back_populates="complaint")
    category = relationship("Category", back_populates="complaint")
    images = relationship("ComplaintImage", back_populates="complaint")
    attachment = relationship("Attachment", back_populates="complaint")
    feedback = relationship("Feedback", back_populates="complaint")
    notifications = relationship("Notification", back_populates="complaint")
    logs = relationship("ComplaintLogs", back_populates="complaint", cascade="all, delete-orphan")
    rejection_category = relationship("RejectionCategory", back_populates="complaint")
    referrals = relationship("CaseReferral", back_populates="complaint")
    barangay_members = relationship(
        "BarangayMember",
        secondary=complaint_barangay_members,
        back_populates="complaints",
    )

   
    incident_links = relationship(
        "IncidentComplaintModel",
        back_populates="complaint",
        cascade="all, delete-orphan"
    )