"""
Database models for Workplace Monitoring
Supports multiple cameras
"""
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, JSON, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Camera(Base):
    """IP Camera configuration"""
    __tablename__ = "cameras"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(Integer, unique=True, nullable=False)  # ID from .env (CAMERA_1, CAMERA_2, etc.)
    name = Column(String(200), nullable=False)
    rtsp_url = Column(String(500), nullable=False)
    is_active = Column(Integer, default=1)  # SQLite doesn't have boolean
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    places = relationship("Place", back_populates="camera")
    
    def __repr__(self):
        return f"<Camera(id={self.id}, name='{self.name}')>"


class Employee(Base):
    """Employee information"""
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # ФИО сотрудника
    position = Column(String(100), nullable=True)  # Должность (кассир, менеджер и т.д.)
    is_active = Column(Integer, default=1)  # Активен ли сотрудник
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    places = relationship("Place", back_populates="employee")
    
    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}')>"


class Place(Base):
    """Workplace/desk zone (ROI)"""
    __tablename__ = "places"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # Привязка к сотруднику
    name = Column(String(100), nullable=False)  # e.g., "Место 1"
    roi_coordinates = Column(JSON, nullable=False)  # List of [x, y] points
    status = Column(String(20), default="VACANT")  # VACANT, OCCUPIED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="places")
    employee = relationship("Employee", back_populates="places")
    sessions = relationship("Session", back_populates="place")
    
    def __repr__(self):
        return f"<Place(id={self.id}, name='{self.name}', camera_id={self.camera_id})>"


class Session(Base):
    """Work session record"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    place_id = Column(Integer, ForeignKey("places.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    session_date = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    place = relationship("Place", back_populates="sessions")
    
    def __repr__(self):
        return f"<Session(id={self.id}, place_id={self.place_id}, duration={self.duration_seconds}s)>"
