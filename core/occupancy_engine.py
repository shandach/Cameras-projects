"""
Occupancy Engine - Time tracking and status logic

Implements the state machine:
- VACANT → CHECKING_ENTRY (person enters)
- CHECKING_ENTRY → OCCUPIED (stays 3+ sec) → timer starts
- CHECKING_ENTRY → VACANT (leaves < 3 sec)
- OCCUPIED → CHECKING_EXIT (person leaves) → timer paused
- CHECKING_EXIT → OCCUPIED (returns ≤ 10 sec) → timer continues
- CHECKING_EXIT → VACANT (gone > 10 sec) → session saved to DB
"""
import time
import sys
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ENTRY_THRESHOLD, EXIT_THRESHOLD
from database.db import db


class ZoneState(Enum):
    """Zone occupancy states"""
    VACANT = "VACANT"
    CHECKING_ENTRY = "CHECKING_ENTRY"
    OCCUPIED = "OCCUPIED"
    CHECKING_EXIT = "CHECKING_EXIT"


@dataclass
class ZoneTracker:
    """Tracks state and time for a single zone"""
    zone_id: int
    state: ZoneState = ZoneState.VACANT
    
    # Entry tracking
    entry_start_time: Optional[float] = None
    
    # Exit tracking
    exit_start_time: Optional[float] = None
    
    # Timer tracking
    timer_start_time: Optional[float] = None
    accumulated_time: float = 0.0  # Time accumulated before pause
    
    # Session tracking
    session_start: Optional[datetime] = None
    
    def get_elapsed_time(self) -> float:
        """Get total elapsed time for current session"""
        if self.timer_start_time is None:
            return self.accumulated_time
        
        current_time = time.time() - self.timer_start_time
        return self.accumulated_time + current_time
    
    def get_display_status(self) -> str:
        """Get human-readable status for display"""
        if self.state == ZoneState.VACANT:
            return "VACANT"
        else:
            return "OCCUPIED"
    
    def get_display_color(self) -> str:
        """Get color status: occupied = red, vacant = green"""
        return "OCCUPIED" if self.state != ZoneState.VACANT else "VACANT"


class OccupancyEngine:
    """
    Manages occupancy state and time tracking for multiple zones
    
    Timing logic per TZ:
    - 3 second entry confirmation
    - 10 second exit grace period
    """
    
    def __init__(self):
        self.trackers: Dict[int, ZoneTracker] = {}
        self.on_session_complete: Optional[Callable] = None
    
    def get_or_create_tracker(self, zone_id: int) -> ZoneTracker:
        """Get or create tracker for a zone"""
        if zone_id not in self.trackers:
            self.trackers[zone_id] = ZoneTracker(zone_id=zone_id)
        return self.trackers[zone_id]
    
    def update(self, zone_id: int, is_person_present: bool, zone_type: str = "employee", linked_employee_id: int = None):
        """
        Update zone state based on person presence and zone type
        
        Args:
            zone_id: ID of the zone
            is_person_present: Whether a person is currently detected in zone
            zone_type: "employee" or "client"
            linked_employee_id: For client zones, the employee who gets credit
        """
        tracker = self.get_or_create_tracker(zone_id)
        current_time = time.time()
        
        # Determine thresholds based on zone type
        from config import ENTRY_THRESHOLD, EXIT_THRESHOLD, CLIENT_ENTRY_THRESHOLD, CLIENT_EXIT_THRESHOLD
        
        if zone_type == "client":
            entry_thresh = CLIENT_ENTRY_THRESHOLD
            exit_thresh = CLIENT_EXIT_THRESHOLD
        else:
            entry_thresh = ENTRY_THRESHOLD
            exit_thresh = EXIT_THRESHOLD
        
        if tracker.state == ZoneState.VACANT:
            if is_person_present:
                # Person entered - start entry check
                tracker.state = ZoneState.CHECKING_ENTRY
                tracker.entry_start_time = current_time
                print(f"🚶 Zone {zone_id} ({zone_type}): Person entered, checking for {entry_thresh} seconds...")
        
        elif tracker.state == ZoneState.CHECKING_ENTRY:
            if is_person_present:
                # Check if person stayed long enough
                elapsed = current_time - tracker.entry_start_time
                if elapsed >= entry_thresh:
                    # Confirmed entry - start timer FROM ENTRY TIME
                    tracker.state = ZoneState.OCCUPIED
                    tracker.timer_start_time = tracker.entry_start_time
                    tracker.accumulated_time = 0.0
                    tracker.session_start = datetime.now() - timedelta(seconds=entry_thresh)
                    print(f"✅ Zone {zone_id}: Entry confirmed, timer started")
            else:
                # Person left before confirmation
                tracker.state = ZoneState.VACANT
                tracker.entry_start_time = None
                print(f"👋 Zone {zone_id}: Person left before confirmation")
        
        elif tracker.state == ZoneState.OCCUPIED:
            if not is_person_present:
                # Person left - pause timer and start exit check
                if tracker.timer_start_time:
                    tracker.accumulated_time += (current_time - tracker.timer_start_time)
                    tracker.timer_start_time = None
                
                tracker.state = ZoneState.CHECKING_EXIT
                tracker.exit_start_time = current_time
                print(f"⏸️ Zone {zone_id}: Person left, waiting {exit_thresh}s grace...")
        
        elif tracker.state == ZoneState.CHECKING_EXIT:
            if is_person_present:
                # Person returned - resume timer
                tracker.state = ZoneState.OCCUPIED
                tracker.timer_start_time = current_time
                tracker.exit_start_time = None
                print(f"🔄 Zone {zone_id}: Person returned, timer resumed")
            else:
                # Check if grace period expired
                elapsed = current_time - tracker.exit_start_time
                if elapsed >= exit_thresh:
                    # Session complete - save to DB
                    self._complete_session(tracker, zone_type, linked_employee_id)
    
    def _complete_session(self, tracker: ZoneTracker, zone_type: str = "employee", linked_employee_id: int = None):
        """Complete and save a session (Work Session or Client Visit)"""
        duration = tracker.accumulated_time
        
        print(f"📝 Zone {tracker.zone_id}: Session complete - {duration:.1f} seconds")
        
        # Save to database if valid
        if tracker.session_start and duration > 0:
            try:
                if zone_type == "client":
                    # === CLIENT VISIT ===
                    if linked_employee_id:
                        # We use 0 for track_id since we tracked "any person"
                        db.save_client_visit(
                            place_id=tracker.zone_id,
                            employee_id=linked_employee_id,
                            track_id=0,
                            enter_time=tracker.session_start,
                            exit_time=datetime.now(),
                            duration_seconds=duration
                        )
                        # Calc net service time (minus threshold) for display
                        from config import CLIENT_ENTRY_THRESHOLD
                        net_time = max(0, duration - CLIENT_ENTRY_THRESHOLD)
                        print(f"💾 Client Visit saved: Linked to Emp#{linked_employee_id} ({net_time:.0f}s net)")
                    else:
                        print(f"⚠️ Client Visit IGNORED: Zone {tracker.zone_id} has no linked employee!")
                        
                else:
                    # === EMPLOYEE SESSION ===
                    # Look up employee assigned to this zone
                    employee = db.get_employee_by_place(tracker.zone_id)
                    employee_id = employee['id'] if employee else None
                    
                    db.save_session(
                        place_id=tracker.zone_id,
                        start_time=tracker.session_start,
                        end_time=datetime.now(),
                        duration_seconds=duration,
                        employee_id=employee_id
                    )
                    emp_name = employee['name'] if employee else 'N/A'
                    print(f"💾 Work Session saved: {emp_name} ({duration:.0f}s)")
                    
            except Exception as e:
                print(f"⚠️ Failed to save session: {e}")
        
        # Reset tracker
        tracker.state = ZoneState.VACANT
        tracker.entry_start_time = None
        tracker.exit_start_time = None
        tracker.timer_start_time = None
        tracker.accumulated_time = 0.0
        tracker.session_start = None
        
        # Callback
        if self.on_session_complete:
            self.on_session_complete(tracker.zone_id, duration)
    
    def get_zone_status(self, zone_id: int) -> str:
        """Get display status for zone"""
        tracker = self.get_or_create_tracker(zone_id)
        return tracker.get_display_status()
    
    def get_zone_time(self, zone_id: int) -> float:
        """Get elapsed time for current session only"""
        tracker = self.get_or_create_tracker(zone_id)
        return tracker.get_elapsed_time()
        
    def get_total_daily_time(self, zone_id: int) -> float:
        """Get total accumulated time for today (historical + current session).
        Uses employee_id if zone has an assigned employee (cross-zone total).
        Falls back to place_id if no employee assigned.
        """
        # Check if zone has an assigned employee
        employee = db.get_employee_by_place(zone_id)
        
        if employee:
            # Query by employee_id — includes ALL zones this employee worked in
            historical_total = db.get_total_time_for_employee_day(
                employee['id'], date.today()
            )
        else:
            # Fallback: query by place_id only
            historical_total = db.get_total_time_for_day(zone_id, date.today())
        
        # Add current session time
        current_session = self.get_zone_time(zone_id)
        
        return historical_total + current_session
    
    def get_all_timers(self) -> Dict[int, float]:
        """Get all zone timers"""
        return {
            zone_id: tracker.get_elapsed_time()
            for zone_id, tracker in self.trackers.items()
        }
    
    def is_zone_occupied(self, zone_id: int) -> bool:
        """Check if zone is visually occupied (red)"""
        tracker = self.get_or_create_tracker(zone_id)
        return tracker.state != ZoneState.VACANT

    def force_save_session(self, tracker: ZoneTracker):
        """Force save current session state (e.g., on shutdown)"""
        # Calculate time up to NOW
        current_time = time.time()
        
        # If timer was running, add up the time
        if tracker.timer_start_time:
            tracker.accumulated_time += (current_time - tracker.timer_start_time)
            tracker.timer_start_time = None # Stop timer
            
        duration = tracker.accumulated_time
        
        # Only save if there's a valid session start and some duration
        if tracker.session_start and duration > 1.0: # Filter noise < 1s
            print(f"💾 Saving active session on shutdown (Zone {tracker.zone_id})...")
            try:
                # Look up employee
                employee = db.get_employee_by_place(tracker.zone_id)
                employee_id = employee['id'] if employee else None
                
                db.save_session(
                    place_id=tracker.zone_id,
                    start_time=tracker.session_start,
                    end_time=datetime.now(),
                    duration_seconds=duration,
                    employee_id=employee_id
                )
                print(f"✅ Saved active session: {duration:.1f}s")
            except Exception as e:
                print(f"⚠️ Failed to save shutdown session: {e}")
                
    def shutdown(self):
        """Gracefully shut down engine and save all active sessions"""
        print("\n🛑 OccupancyEngine shutting down...")
        saved_count = 0
        for zone_id, tracker in self.trackers.items():
            if tracker.state in [ZoneState.OCCUPIED, ZoneState.CHECKING_EXIT]:
                self.force_save_session(tracker)
                saved_count += 1
        print(f"🏁 OccupancyEngine shutdown complete. Saved {saved_count} active sessions.")


if __name__ == "__main__":
    # Test Occupancy Engine
    import time
    
    print("Testing OccupancyEngine...")
    engine = OccupancyEngine()
    
    zone_id = 1
    
    # Simulate: person enters
    print("\n--- Person enters ---")
    for i in range(5):
        engine.update(zone_id, is_person_present=True)
        print(f"Status: {engine.get_zone_status(zone_id)}, Time: {engine.get_zone_time(zone_id):.1f}s")
        time.sleep(1)
    
    # Simulate: person leaves
    print("\n--- Person leaves ---")
    for i in range(12):
        engine.update(zone_id, is_person_present=False)
        print(f"Status: {engine.get_zone_status(zone_id)}, Time: {engine.get_zone_time(zone_id):.1f}s")
        time.sleep(1)
    
    print("\nTest complete")
