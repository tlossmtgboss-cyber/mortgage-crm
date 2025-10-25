from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class EventLog(Base):
    __tablename__ = 'event_logs'
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, index=True)  # "SMS", "CALL", "EMAIL"
    from_number = Column(String)
    body_or_status = Column(String)
    ts = Column(DateTime, default=datetime.datetime.utcnow)
