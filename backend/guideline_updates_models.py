"""
Database Models for Guideline Updates Tracking
Store guideline updates from all 5 sources (Fannie Mae, Freddie Mac, FHA, VA, USDA)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Index
from database import Base


class GuidelineUpdate(Base):
    """Track guideline updates from all sources"""
    __tablename__ = 'guideline_updates'

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)  # fannie_mae, freddie_mac, fha, va, usda
    title = Column(String(500), nullable=False)
    section_code = Column(String(100))
    description = Column(Text)
    url = Column(String(1000), nullable=False)
    published_date = Column(DateTime, nullable=False)
    scraped_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_new = Column(Boolean, default=True)
    content_hash = Column(String(64), unique=True, index=True)

    __table_args__ = (
        Index('idx_source_published', 'source', 'published_date'),
        Index('idx_is_new', 'is_new'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'title': self.title,
            'section_code': self.section_code,
            'description': self.description,
            'url': self.url,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'scraped_date': self.scraped_date.isoformat() if self.scraped_date else None,
            'is_new': self.is_new
        }


class UserUpdateView(Base):
    """Track which updates each user has viewed"""
    __tablename__ = 'user_update_views'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    update_id = Column(Integer, nullable=False, index=True)
    viewed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_user_update', 'user_id', 'update_id'),
    )
