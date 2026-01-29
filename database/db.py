"""
Database connection and utilities
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession
from database.models import Base, Place, Session
from config import DATABASE_PATH, DATABASE_DIR


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
    
    def save_place(self, name: str, roi_coordinates: list) -> Place:
        """Save a new place/zone"""
        with self.get_session() as session:
            place = Place(name=name, roi_coordinates=roi_coordinates)
            session.add(place)
            session.commit()
            session.refresh(place)
            return place
    
    def get_all_places(self) -> list:
        """Get all places"""
        with self.get_session() as session:
            places = session.query(Place).all()
            # Detach from session
            return [
                {
                    "id": p.id,
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
    
    def save_session(self, place_id: int, start_time, end_time, duration_seconds: float) -> Session:
        """Save a work session"""
        from datetime import date
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
    
    def get_sessions_for_date(self, target_date) -> list:
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


# Global database instance
db = Database()
