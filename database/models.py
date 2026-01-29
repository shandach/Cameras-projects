"""
Database models for Workplace Monitoring
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, JSON, Float
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Place(Base):
    """Workplace/desk zone"""
    __tablename__ = "places"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # e.g., "Место 1"
    roi_coordinates = Column(JSON, nullable=False)  # List of [x, y] points
    status = Column(String(20), default="VACANT")  # VACANT, OCCUPIED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Place(id={self.id}, name='{self.name}', status='{self.status}')>"


class Session(Base):
    """Work session record"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    place_id = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    session_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Session(id={self.id}, place_id={self.place_id}, duration={self.duration_seconds}s)>"
