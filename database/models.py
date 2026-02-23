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
    places = relationship("Place", back_populates="employee", foreign_keys="[Place.employee_id]")
    client_visits = relationship("ClientVisit", back_populates="employee")
    
    def __repr__(self):
        return f"<Employee(id={self.id}, name='{self.name}')>"


class Place(Base):
    """Workplace/desk zone (ROI)"""
    __tablename__ = "places"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # Сотрудник в этой зоне
    linked_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # Для client зон: какому сотруднику приписывать клиентов
    name = Column(String(100), nullable=False)  # e.g., "Место 1"
    zone_type = Column(String(20), default="employee")  # "employee" или "client"
    roi_coordinates = Column(JSON, nullable=False)  # List of [x, y] points
    status = Column(String(20), default="VACANT")  # VACANT, OCCUPIED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="places")
    employee = relationship("Employee", back_populates="places", foreign_keys=[employee_id])
    linked_employee = relationship("Employee", foreign_keys=[linked_employee_id])  # No back_populates
    sessions = relationship("Session", back_populates="place")
    client_visits = relationship("ClientVisit", back_populates="place")
    
    def __repr__(self):
        return f"<Place(id={self.id}, name='{self.name}', zone_type='{self.zone_type}')>"


class Session(Base):
    """Work session record (for employees)"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="SET NULL"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    branch_id = Column(Integer, nullable=True)  # Cloud branch ID for multi-branch
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    session_date = Column(Date, default=date.today)
    is_synced = Column(Integer, default=0)  # 0=False, 1=True
    is_checkpoint = Column(Integer, default=0)  # 0=finished, 1=active checkpoint
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    place = relationship("Place", back_populates="sessions")
    employee = relationship("Employee")
    
    def __repr__(self):
        return f"<Session(id={self.id}, place_id={self.place_id}, duration={self.duration_seconds}s, synced={self.is_synced})>"


class ClientVisit(Base):
    """Client visit record (for client zones with ByteTrack)"""
    __tablename__ = "client_visits"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    place_id = Column(Integer, ForeignKey("places.id", ondelete="SET NULL"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # Сотрудник, который обслужил
    branch_id = Column(Integer, nullable=True)  # Cloud branch ID for multi-branch
    track_id = Column(Integer, nullable=False)  # ByteTrack ID
    visit_date = Column(Date, default=date.today)
    enter_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    is_synced = Column(Integer, default=0)  # 0=False, 1=True
    is_checkpoint = Column(Integer, default=0)  # 0=finished, 1=active checkpoint
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    place = relationship("Place", back_populates="client_visits")
    employee = relationship("Employee", back_populates="client_visits")
    
    def __repr__(self):
        return f"<ClientVisit(id={self.id}, track_id={self.track_id}, synced={self.is_synced})>"

