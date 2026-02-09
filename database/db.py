"""
Database connection and utilities
Supports multiple cameras
"""
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession
from database.models import Base, Camera, Place, Session
from config import DATABASE_PATH, DATABASE_DIR, CameraConfig


class Database:
    """SQLite database manager"""
    
    def __init__(self):
        # Ensure database directory exists
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create engine
        self.engine = create_engine(
            f"sqlite:///{DATABASE_PATH}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> DBSession:
        """Get database session"""
        return self.SessionLocal()
    
    # ============ Camera Operations ============
    
    def get_or_create_camera(self, config: CameraConfig) -> Camera:
        """Get existing camera or create new one"""
        with self.get_session() as session:
            camera = session.query(Camera).filter(
                Camera.external_id == config.id
            ).first()
            
            if camera:
                # Update if changed
                camera.name = config.name
                camera.rtsp_url = config.url
                session.commit()
            else:
                # Create new
                camera = Camera(
                    external_id=config.id,
                    name=config.name,
                    rtsp_url=config.url
                )
                session.add(camera)
                session.commit()
                session.refresh(camera)
            
            # Extract values before session closes to avoid DetachedInstanceError
            camera_id = camera.id
            camera_external_id = camera.external_id
            camera_name = camera.name
            camera_rtsp_url = camera.rtsp_url
        
        # Return a new detached Camera with extracted values
        detached_camera = Camera(
            id=camera_id,
            external_id=camera_external_id,
            name=camera_name,
            rtsp_url=camera_rtsp_url
        )
        # Manually set the id since it's normally auto-generated
        detached_camera.id = camera_id
        return detached_camera
    
    def get_camera_by_external_id(self, external_id: int) -> Optional[Camera]:
        """Get camera by external ID"""
        with self.get_session() as session:
            return session.query(Camera).filter(
                Camera.external_id == external_id
            ).first()
    
    # ============ Place Operations ============
    
    def save_place(self, camera_id: int, name: str, roi_coordinates: list) -> Place:
        """Save a new place/zone"""
        with self.get_session() as session:
            place = Place(
                camera_id=camera_id,
                name=name, 
                roi_coordinates=roi_coordinates
            )
            session.add(place)
            session.commit()
            session.refresh(place)
            return place
    
    def get_places_for_camera(self, camera_id: int) -> List[dict]:
        """Get all places for a specific camera"""
        with self.get_session() as session:
            places = session.query(Place).filter(
                Place.camera_id == camera_id
            ).all()
            return [
                {
                    "id": p.id,
                    "camera_id": p.camera_id,
                    "name": p.name,
                    "roi_coordinates": p.roi_coordinates,
                    "status": p.status
                }
                for p in places
            ]
    
    def get_all_places(self) -> List[dict]:
        """Get all places"""
        with self.get_session() as session:
            places = session.query(Place).all()
            return [
                {
                    "id": p.id,
                    "camera_id": p.camera_id,
                    "name": p.name,
                    "roi_coordinates": p.roi_coordinates,
                    "status": p.status
                }
                for p in places
            ]
    
    def delete_place(self, place_id: int) -> bool:
        """Delete a place by ID"""
        with self.get_session() as session:
            place = session.query(Place).filter(Place.id == place_id).first()
            if place:
                session.delete(place)
                session.commit()
                return True
            return False
    
    def delete_places_for_camera(self, camera_id: int) -> int:
        """Delete all places for a camera, returns count deleted"""
        with self.get_session() as session:
            count = session.query(Place).filter(
                Place.camera_id == camera_id
            ).delete()
            session.commit()
            return count
    
    # ============ Session Operations ============
    
    def save_session(self, place_id: int, start_time: datetime, 
                     end_time: datetime, duration_seconds: float) -> Session:
        """Save a work session"""
        with self.get_session() as session:
            work_session = Session(
                place_id=place_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                session_date=date.today()
            )
            session.add(work_session)
            session.commit()
            session.refresh(work_session)
            return work_session
    
    def get_sessions_for_date(self, target_date: date) -> List[dict]:
        """Get all sessions for a specific date"""
        with self.get_session() as session:
            sessions = session.query(Session).filter(
                Session.session_date == target_date
            ).all()
            return [
                {
                    "id": s.id,
                    "place_id": s.place_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration_seconds": s.duration_seconds
                }
                for s in sessions
            ]
    
    def get_sessions_for_camera(self, camera_id: int, target_date: date = None) -> List[dict]:
        """Get sessions for all places of a camera"""
        with self.get_session() as session:
            query = session.query(Session).join(Place).filter(
                Place.camera_id == camera_id
            )
            if target_date:
                query = query.filter(Session.session_date == target_date)
            
            sessions = query.all()
            return [
                {
                    "id": s.id,
                    "place_id": s.place_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration_seconds": s.duration_seconds
                }
                for s in sessions
            ]
            
    def get_total_time_for_day(self, place_id: int, target_date: date) -> float:
        """Get total duration for a place on a specific date"""
        from sqlalchemy import func
        with self.get_session() as session:
            total = session.query(func.sum(Session.duration_seconds)).filter(
                Session.place_id == place_id,
                Session.session_date == target_date
            ).scalar()
            return total if total else 0.0


# Global database instance
db = Database()
