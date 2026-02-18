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
from database.models import Base, Camera, Place, Session, Employee, ClientVisit
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
        
        # Auto-migrate: check for new columns
        from database.migrator import update_schema
        try:
            update_schema(self.engine, Base)
        except Exception as e:
            print(f"[WARN] Auto-migration failed: {e}")
        
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
    
    def save_place(self, camera_id: int, name: str, roi_coordinates: list,
                   zone_type: str = "employee", linked_employee_id: int = None,
                   employee_id: int = None) -> Place:
        """Save a new place/zone"""
        with self.get_session() as session:
            place = Place(
                camera_id=camera_id,
                name=name, 
                roi_coordinates=roi_coordinates,
                zone_type=zone_type,
                linked_employee_id=linked_employee_id,
                employee_id=employee_id
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
                    "status": p.status,
                    "zone_type": p.zone_type,
                    "employee_id": p.employee_id,
                    "linked_employee_id": p.linked_employee_id
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
    
    def update_roi_type(self, place_id: int, zone_type: str):
        """Update the zone type of a place"""
        with self.get_session() as session:
            place = session.query(Place).filter(Place.id == place_id).first()
            if place:
                place.zone_type = zone_type
                session.commit()

    def update_roi_link(self, place_id: int, linked_employee_id: int):
        """Update the linked employee for a client zone"""
        with self.get_session() as session:
            place = session.query(Place).filter(Place.id == place_id).first()
            if place:
                place.linked_employee_id = linked_employee_id
                session.commit()
    
    # ============ Session Operations ============
    
    def save_session(self, place_id: int, start_time: datetime, 
                     end_time: datetime, duration_seconds: float,
                     employee_id: int = None) -> Session:
        """Save a work session, linked directly to employee"""
        with self.get_session() as session:
            work_session = Session(
                place_id=place_id,
                employee_id=employee_id,
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
    
    def get_total_time_for_employee_day(self, employee_id: int, target_date: date) -> float:
        """Get total duration for an employee on a specific date (across ALL zones)"""
        from sqlalchemy import func
        with self.get_session() as session:
            total = session.query(func.sum(Session.duration_seconds)).filter(
                Session.employee_id == employee_id,
                Session.session_date == target_date
            ).scalar()
            return total if total else 0.0
    
    # ============ Employee Operations ============
    
    def get_employee_by_place(self, place_id: int) -> Optional[dict]:
        """Get employee assigned to a place/zone"""
        with self.get_session() as session:
            place = session.query(Place).filter(Place.id == place_id).first()
            if place and place.employee_id:
                employee = session.query(Employee).filter(
                    Employee.id == place.employee_id
                ).first()
                if employee:
                    return {
                        'id': employee.id,
                        'name': employee.name,
                        'position': employee.position
                    }
            return None
    
    def get_all_employees(self) -> List[dict]:
        """Get all active employees"""
        with self.get_session() as session:
            employees = session.query(Employee).filter(
                Employee.is_active == 1
            ).all()
            return [
                {'id': e.id, 'name': e.name, 'position': e.position}
                for e in employees
            ]
    
    def create_employee(self, name: str, position: str = None) -> int:
        """Create a new employee, return ID"""
        with self.get_session() as session:
            employee = Employee(name=name, position=position)
            session.add(employee)
            session.commit()
            return employee.id
    
    def assign_employee_to_place(self, place_id: int, employee_id: int):
        """Assign an employee to a place/zone"""
        with self.get_session() as session:
            place = session.query(Place).filter(Place.id == place_id).first()
            if place:
                place.employee_id = employee_id
                session.commit()
    
    # ============ Client Visit Operations ============
    
    def save_client_visit(self, place_id: int, employee_id: int, track_id: int,
                          enter_time: datetime, exit_time: datetime, 
                          duration_seconds: float) -> int:
        """Save a completed client visit"""
        with self.get_session() as session:
            visit = ClientVisit(
                place_id=place_id,
                employee_id=employee_id,
                track_id=track_id,
                visit_date=enter_time.date(),
                enter_time=enter_time,
                exit_time=exit_time,
                duration_seconds=duration_seconds
            )
            session.add(visit)
            session.commit()
            return visit.id
    
    def get_client_stats_for_employee(self, employee_id: int, target_date: date) -> dict:
        """Get client statistics for an employee on a specific date"""
        from sqlalchemy import func
        with self.get_session() as session:
            # Count clients
            client_count = session.query(func.count(ClientVisit.id)).filter(
                ClientVisit.employee_id == employee_id,
                ClientVisit.visit_date == target_date
            ).scalar() or 0
            
            # Total service time
            total_time = session.query(func.sum(ClientVisit.duration_seconds)).filter(
                ClientVisit.employee_id == employee_id,
                ClientVisit.visit_date == target_date
            ).scalar() or 0.0
            
            return {
                'client_count': client_count,
                'total_service_time': total_time
            }
    

    def get_client_stats_for_place(self, place_id: int, target_date: date) -> dict:
        """Get client statistics for a place on a specific date"""
        from sqlalchemy import func
        with self.get_session() as session:
            # Count clients
            client_count = session.query(func.count(ClientVisit.id)).filter(
                ClientVisit.place_id == place_id,
                ClientVisit.visit_date == target_date
            ).scalar() or 0
            
            # Total service time
            total_time = session.query(func.sum(ClientVisit.duration_seconds)).filter(
                ClientVisit.place_id == place_id,
                ClientVisit.visit_date == target_date
            ).scalar() or 0.0
            
            return {
                'client_count': client_count,
                'total_service_time': total_time
            }

    # ============ Sync Operations ============

    def get_unsynced_sessions(self, limit: int = 50) -> List[dict]:
        """Get sessions pending synchronization"""
        with self.get_session() as session:
            records = session.query(Session).filter(
                Session.is_synced == 0
            ).limit(limit).all()
            
            return [
                {
                    "id": r.id,
                    "place_id": r.place_id,
                    "employee_id": r.employee_id,
                    "start_time": r.start_time.isoformat(),
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration_seconds": r.duration_seconds,
                    "type": "session"
                }
                for r in records
            ]

    def get_unsynced_client_visits(self, limit: int = 50) -> List[dict]:
        """Get client visits pending synchronization"""
        with self.get_session() as session:
            records = session.query(ClientVisit).filter(
                ClientVisit.is_synced == 0
            ).limit(limit).all()
            
            return [
                {
                    "id": r.id,
                    "place_id": r.place_id,
                    "employee_id": r.employee_id,
                    "track_id": r.track_id,
                    "enter_time": r.enter_time.isoformat(),
                    "exit_time": r.exit_time.isoformat() if r.exit_time else None,
                    "duration_seconds": r.duration_seconds,
                    "type": "client_visit"
                }
                for r in records
            ]

    def mark_as_synced(self, table_type: str, record_ids: List[int]):
        """Mark records as synced"""
        if not record_ids:
            return
            
        model = Session if table_type == "session" else ClientVisit
        
        with self.get_session() as session:
            session.query(model).filter(
                model.id.in_(record_ids)
            ).update({"is_synced": 1}, synchronize_session=False)
            session.commit()


    def seed_employees_from_config(self, workplace_owners: dict):
        """
        Create employees from WORKPLACE_OWNERS config if they don't exist.
        Uses workplace_id as a stable identifier.
        
        Args:
            workplace_owners: {workplace_id: operator_name, ...}
        """
        existing = self.get_all_employees()
        existing_names = {e['name'] for e in existing}
        
        created = 0
        for wp_id, name in workplace_owners.items():
            if name not in existing_names:
                self.create_employee(name=name, position="Оператор")
                created += 1
        
        if created:
            print(f"👥 Создано {created} операторов из конфигурации")
        else:
            print(f"👥 Все {len(workplace_owners)} операторов уже в БД")


# Global database instance
db = Database()

