from datetime import datetime, timezone
from app.database.database import Base
from sqlalchemy import Column, DateTime, Integer, String, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    middle_name = Column(String, index=True, nullable=True)
    last_name = Column(String, index=True)
    suffix = Column(String, index=True, nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    birthdate = Column(Date, nullable=True)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="user")
    barangay = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    push_notifications_enabled = Column(Boolean, default=False)
    full_address = Column(String, nullable=True)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    location_updated_at = Column(DateTime(timezone=True), nullable=True)
    id_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)
    front_id = Column(String, nullable=True)
    back_id = Column(String, nullable=True)
    selfie_with_id = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_administrator = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True)
    is_suspended = Column(Boolean, default=False)
    can_submit_complaints = Column(Boolean, default=True)
    reject_counter = Column(Integer, default=0)
    is_restricted_until = Column(DateTime(timezone=True), nullable=True)
    clerk_user_id = Column(String(255), unique=True, nullable=True)
    
    
    barangay_member = relationship("BarangayMember", back_populates="user", uselist=False)
    barangay_account = relationship("BarangayAccount", back_populates="user", uselist=False)
    events = relationship("Event", back_populates="uploader", cascade="all, delete-orphan")
    complaint = relationship("Complaint", back_populates="user", cascade="all, delete-orphan")
    attachment = relationship("Attachment", back_populates="uploader", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    announcements = relationship("Announcement", back_populates="uploader", cascade="all, delete-orphan")
    app_feedbacks = relationship("AppFeedback", back_populates="user", cascade="all, delete-orphan")
    incidents = relationship(
    "IncidentModel",
    back_populates="lgu_account",
    foreign_keys="[IncidentModel.lgu_account_id]"
)
    responses = relationship("Response", back_populates="user", cascade="all, delete-orphan")
    post_incident_feedbacks = relationship("PostIncidentFeedback", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("ComplaintLogs", back_populates="updated_by_user", cascade="all, delete-orphan")
    resolver_incidents = relationship(
    "IncidentModel",
    back_populates="resolver",
    foreign_keys="[IncidentModel.resolver_id]"
)
    push_tokens = relationship("PushToken", back_populates="user", cascade="all, delete-orphan")
    user_devices = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")
    push_subscriptions = relationship("PushSubscription", back_populates="user", cascade="all, delete-orphan")