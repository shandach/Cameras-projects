
import sys
import os
from datetime import date, timedelta
from pathlib import Path
from sqlalchemy import text, func

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import db
from database.models import Employee, ClientVisit

def show_employee_visits():
    print("\n🔍 CHECKING CLIENT VISITS BY EMPLOYEE\n")
    
    with db.get_session() as session:
        # 1. List All Active Employees
        employees = session.query(Employee).filter(Employee.is_active == 1).all()
        
        if not employees:
            print("❌ No active employees found in database.")
            return

        print("Select an Employee to view stats:")
        print("-" * 40)
        for emp in employees:
            # Count total visits for context
            count = session.query(func.count(ClientVisit.id)).filter(ClientVisit.employee_id == emp.id).scalar()
            print(f"[{emp.id}] {emp.name} ({emp.position}) - Total Visits: {count}")
        print("-" * 40)
        
        # 2. Ask User for ID
        try:
            choice = input("\nEnter Employee ID (or just press Enter for ALL): ").strip()
        except KeyboardInterrupt:
            return

        query = session.query(ClientVisit).join(Employee)
        
        if choice:
            emp_id = int(choice)
            query = query.filter(ClientVisit.employee_id == emp_id)
            print(f"\n📋 VISITS FOR EMPLOYEE ID {emp_id}:")
        else:
            print("\n📋 ALL CLIENT VISITS:")
            
        # Sort by latest
        visits = query.order_by(ClientVisit.enter_time.desc()).limit(20).all()
        
        if not visits:
            print("   (No visits found)")
        else:
            print(f"{'ID':<5} {'Date':<12} {'Time':<10} {'Duration':<10} {'Employee'}")
            print("-" * 60)
            for v in visits:
                dur_str = f"{int(v.duration_seconds)}s"
                time_str = v.enter_time.strftime("%H:%M:%S")
                emp_name = v.employee.name if v.employee else "Unknown"
                print(f"{v.id:<5} {v.visit_date} {time_str:<10} {dur_str:<10} {emp_name}")
                
        print("\n✅ Done.")

if __name__ == "__main__":
    show_employee_visits()
