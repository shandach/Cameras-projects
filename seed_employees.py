"""
Seed script: Create employees and assign them to zones (places).
Zone IDs match rois.json. Employee IDs are auto-generated.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from database.db import db
from database.models import Employee, Place, Camera, Session, ClientVisit


def seed():
    with db.get_session() as session:
        # 1. Clear old data
        session.query(ClientVisit).delete()
        session.query(Session).delete()
        session.query(Place).delete()
        session.query(Employee).delete()
        session.commit()
        print("🗑️  Cleared old employees, places, sessions, client_visits")

        # 2. Zone → Employee name mapping (from user)
        zone_employee_map = {
            # Camera 1 (Zones 1-5)
            1: 'Operator 10',
            2: 'Operator 6',
            3: 'Operator 7',
            4: 'Operator 8',
            5: 'Operator 9',
            # Camera 3 (Zone 10)
            10: 'Operator 3',
            # Camera 6 (Zones 6-7)
            6: 'Operator 11',
            7: 'Operator 13',
            # Camera 7 (Zone 9)
            9: 'Operator 2',
            # Camera 10 (Zone 8)
            8: 'Operator 1',
        }

        # Zone → Camera mapping (from rois.json)
        zone_camera_map = {
            1: 1, 2: 1, 3: 1, 4: 1, 5: 1,   # Camera 1
            10: 3,                              # Camera 3
            6: 6, 7: 6,                         # Camera 6
            9: 7,                                # Camera 7
            8: 10,                               # Camera 10
        }

        # 3. Create employees and places
        zone_to_employee_id = {}

        for zone_id, emp_name in zone_employee_map.items():
            # Create employee
            emp = Employee(name=emp_name, position="Оператор")
            session.add(emp)
            session.flush()  # Get auto-generated employee.id

            camera_id = zone_camera_map[zone_id]

            # Create place (employee zone)
            place = Place(
                id=zone_id,
                camera_id=camera_id,
                employee_id=emp.id,
                name=f"Зона #{zone_id}",
                zone_type="employee",
                roi_coordinates=[]
            )
            session.add(place)

            zone_to_employee_id[zone_id] = emp.id
            print(f"  ✅ Zone {zone_id} (Camera {camera_id}) → {emp_name} (employee_id={emp.id})")

        session.commit()

        # 4. Verify
        print(f"\n📊 Created {len(zone_employee_map)} employees and places")
        print("\n=== ИТОГОВАЯ ТАБЛИЦА ===")
        print(f"{'Zone':>6} | {'Camera':>6} | {'Employee':>15} | {'Emp ID':>6}")
        print("-" * 45)
        for zone_id in sorted(zone_employee_map.keys()):
            emp_name = zone_employee_map[zone_id]
            emp_id = zone_to_employee_id[zone_id]
            cam_id = zone_camera_map[zone_id]
            print(f"{zone_id:>6} | {cam_id:>6} | {emp_name:>15} | {emp_id:>6}")


if __name__ == "__main__":
    seed()
