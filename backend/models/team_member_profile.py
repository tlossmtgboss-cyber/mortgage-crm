"""
Team Member Profile Model
Complete team member profile with all 29 fields from specification
"""

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Text, Boolean, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


class TeamMemberProfile(Base):
    """
    Team Member Profile - Internal staff profiles
    Total fields: 29
    """
    __tablename__ = "team_member_profiles"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # ==================== BASIC INFORMATION (8 fields) ====================
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    photo_url = Column(Text)
    employee_id = Column(String(50), unique=True, index=True)
    start_date = Column(Date)
    department = Column(String(100))
    manager = Column(String(255))

    # ==================== KPIs (4 fields) ====================
    loans_processed = Column(Integer, default=0)
    avg_close_time = Column(Numeric(6, 2))  # Average days to close
    satisfaction_score = Column(Numeric(4, 2))  # Customer satisfaction score
    volume = Column(Numeric(15, 2))  # Total loan volume processed

    # ==================== NOTES (2 fields) ====================
    meeting_notes = Column(Text)
    general_notes = Column(Text)

    # ==================== DISC PERSONALITY PROFILE (5 fields) ====================
    disc_d = Column(Integer)  # Dominance score (0-100)
    disc_i = Column(Integer)  # Influence score (0-100)
    disc_s = Column(Integer)  # Steadiness score (0-100)
    disc_c = Column(Integer)  # Conscientiousness score (0-100)
    disc_summary = Column(Text)  # Summary of DISC profile

    # ==================== PERSONAL INFORMATION (7 fields) ====================
    birthday = Column(Date)
    anniversary = Column(Date)  # Work anniversary
    spouse_name = Column(String(255))
    children = Column(Text)  # Comma-separated or JSON
    hobbies = Column(Text)
    emergency_contact = Column(String(255))
    emergency_phone = Column(String(20))

    # ==================== GOALS & DEVELOPMENT (6 fields) ====================
    career_goals = Column(Text)
    q1_goals = Column(Text)
    q2_goals = Column(Text)
    q3_goals = Column(Text)
    q4_goals = Column(Text)
    development_areas = Column(Text)

    # ==================== STATUS & TRACKING ====================
    role = Column(String(100))  # 'loan_officer', 'processor', 'underwriter', 'closer', 'admin'
    status = Column(String(50), default='active')  # 'active', 'inactive', 'on_leave'
    tags = Column(ARRAY(String))

    # ==================== METADATA ====================
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_email_sync = Column(DateTime)
    last_performance_review = Column(DateTime)
    data_sources = Column(ARRAY(String))

    # Soft delete
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    # ==================== RELATIONSHIPS ====================
    email_interactions = relationship("EmailInteraction", back_populates="team_member")

    def __repr__(self):
        return f"<TeamMemberProfile {self.name} ({self.role})>"

    def calculate_disc_primary(self):
        """Calculate primary DISC type"""
        scores = {
            'D': self.disc_d or 0,
            'I': self.disc_i or 0,
            'S': self.disc_s or 0,
            'C': self.disc_c or 0
        }
        return max(scores, key=scores.get) if any(scores.values()) else None

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'photo_url': self.photo_url,
            'employee_id': self.employee_id,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'department': self.department,
            'manager': self.manager,
            'role': self.role,
            'loans_processed': self.loans_processed,
            'avg_close_time': float(self.avg_close_time) if self.avg_close_time else None,
            'satisfaction_score': float(self.satisfaction_score) if self.satisfaction_score else None,
            'volume': float(self.volume) if self.volume else None,
            'meeting_notes': self.meeting_notes,
            'general_notes': self.general_notes,
            'disc_d': self.disc_d,
            'disc_i': self.disc_i,
            'disc_s': self.disc_s,
            'disc_c': self.disc_c,
            'disc_summary': self.disc_summary,
            'disc_primary': self.calculate_disc_primary(),
            'birthday': self.birthday.isoformat() if self.birthday else None,
            'anniversary': self.anniversary.isoformat() if self.anniversary else None,
            'spouse_name': self.spouse_name,
            'children': self.children,
            'hobbies': self.hobbies,
            'emergency_contact': self.emergency_contact,
            'emergency_phone': self.emergency_phone,
            'career_goals': self.career_goals,
            'q1_goals': self.q1_goals,
            'q2_goals': self.q2_goals,
            'q3_goals': self.q3_goals,
            'q4_goals': self.q4_goals,
            'development_areas': self.development_areas,
            'status': self.status,
            'tags': self.tags,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
