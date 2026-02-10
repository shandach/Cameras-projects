"""
Workplace Monitoring System - Multi-Camera Version

Real-time video monitoring with:
- Multiple RTSP camera support via .env
- YOLOv8 person detection
- Interactive ROI zone editing
- Occupancy tracking with time logic
- SQLite session storage

Controls:
- R: Start drawing new ROI zone
- ENTER: Finish ROI drawing
- ESC: Cancel drawing
- D: Delete last ROI
- C: Clear all ROIs for current camera
- S: Toggle stats panel
- H: Toggle help panel
- N: Next camera
- P: Previous camera
- Q: Quit
"""
import cv2
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from config import CAMERAS, ROI_COLOR_OCCUPIED, ROI_COLOR_VACANT, print_config
from core.stream_handler import StreamHandler
from core.detector import PersonDetector, PoseDetector, TrackingDetector
from core.roi_manager import ROIManager
from core.occupancy_engine import OccupancyEngine
from gui.roi_editor import ROIEditor, create_mouse_callback
from gui.display import draw_timer_overlay, draw_stats_panel, draw_help_panel, format_duration, draw_employee_stats_overlay
from database.db import db


class CameraMonitor:
    """Monitor for a single camera"""
    
    def __init__(self, camera_config, detector: PersonDetector, pose_detector: PoseDetector):
        """
        Initialize camera monitor
        
        Args:
            camera_config: CameraConfig from .env
            detector: Shared YOLOv8 detector instance
            pose_detector: Shared MediaPipe Pose detector (backup)
        """
        self.config = camera_config
        self.detector = detector
        self.pose_detector = pose_detector  # Резервный детектор
        
        # Get or create camera in database
        self.db_camera = db.get_or_create_camera(camera_config)
        self.camera_db_id = self.db_camera.id
        
        # Initialize components
        self.stream = StreamHandler(camera_config)
        self.roi_manager = ROIManager(self.camera_db_id)
        self.occupancy_engine = OccupancyEngine()
        self.roi_editor = ROIEditor(f"Camera {camera_config.id}")
        
        self.is_connected = False
    
    def connect(self) -> bool:
        """Connect to camera stream"""
        self.is_connected = self.stream.start()
        return self.is_connected
    
    def disconnect(self):
        """Disconnect from camera"""
        self.stream.stop()
        self.is_connected = False
    
    def process_frame(self, frame):
        """Process a single frame"""
        # Detect persons with YOLO (primary detector)
        detections = self.detector.detect(frame)
        person_centers = [d.center for d in detections]
        
        # If YOLO didn't detect anyone, try MediaPipe Pose (backup)
        used_backup = False
        if not person_centers:
            pose_centers = self.pose_detector.detect(frame)
            if pose_centers:
                person_centers = pose_centers
                used_backup = True
        
        # Check presence in ROIs
        presence = self.roi_manager.check_presence(person_centers)
        
        # Update occupancy engine
        for roi in self.roi_manager.get_all_rois():
            is_present = presence.get(roi.id, False)
            self.occupancy_engine.update(roi.id, is_present)
            
            # Update ROI status for display
            status = self.occupancy_engine.get_zone_status(roi.id)
            self.roi_manager.update_status(roi.id, status)
        
        # Draw ROIs
        frame = self.roi_manager.draw_rois(
            frame, 
            occupied_color=ROI_COLOR_OCCUPIED,
            vacant_color=ROI_COLOR_VACANT
        )
        
        # Draw person detections
        frame = self.detector.draw_detections(frame, detections)
        
        # Draw employee stats overlay
        roi_stats = {}
        roi_positions = {}
        today = date.today()
        
        for roi in self.roi_manager.get_all_rois():
            # Skip client zones - they have their own visual indicator
            if roi.zone_type == "client":
                continue
                
            # Get ROI center position
            pts = roi.get_polygon_array()
            M = cv2.moments(pts)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                roi_positions[roi.id] = (cx, cy)
            
            # Get employee info
            employee = db.get_employee_by_place(roi.id)
            employee_name = employee['name'] if employee else f"Место {roi.id}"
            employee_id = employee['id'] if employee else None
            
            # Get work time (daily total)
            work_time = self.occupancy_engine.get_total_daily_time(roi.id)
            
            # Get client stats
            if employee_id:
                client_stats = db.get_client_stats_for_employee(employee_id, today)
            else:
                client_stats = db.get_client_stats_for_place(roi.id, today)
            
            roi_stats[roi.id] = {
                'employee_name': employee_name,
                'work_time': work_time,
                'client_count': client_stats['client_count'],
                'client_service_time': client_stats['total_service_time']
            }
        
        frame = draw_employee_stats_overlay(frame, roi_stats, roi_positions)
        
        # Draw ROI editor overlay if drawing
        if self.roi_editor.is_drawing:
            frame = self.roi_editor.draw_current(frame)
        
        return frame, len(detections)
    
    def get_stats(self) -> dict:
        """Get current statistics"""
        rois = self.roi_manager.get_all_rois()
        occupied = sum(1 for r in rois if r.status == "OCCUPIED")
        
        # USE DAILY TOTAL
        total_time = sum(self.occupancy_engine.get_total_daily_time(r.id) for r in rois)
        # total_time = sum(self.occupancy_engine.get_zone_time(r.id) for r in rois)
        
        return {
            "Camera": self.config.name,
            "Zones": len(rois),
            "Occupied": occupied,
            "Vacant": len(rois) - occupied,
            "Total Time": format_duration(total_time)
        }


class WorkplaceMonitor:
    """Main application - manages multiple cameras"""
    
    def __init__(self):
        print("\n🏢 WORKPLACE MONITORING SYSTEM - MULTI-CAMERA")
        print("=" * 50)
        
        # Print configuration
        print_config()
        
        if not CAMERAS:
            print("❌ No cameras configured!")
            print("   1. Copy .env.example to .env")
            print("   2. Add your RTSP camera URLs")
            sys.exit(1)
        
        # Shared detector (one YOLO instance for all cameras)
        print("🤖 Loading YOLO detector...")
        self.detector = PersonDetector()
        
        # Tracking detector for client zones (ByteTrack)
        print("🎯 Loading ByteTrack tracker...")
        self.tracking_detector = TrackingDetector()
        
        # Shared backup detector (MediaPipe Pose for when YOLO fails)
        self.pose_detector = PoseDetector()
        
        # Client tracking state: {(camera_id, roi_id): {track_id: {'enter_time': datetime, 'last_seen': datetime}}}
        self.client_tracking = {}
        
        # Create camera monitors
        self.cameras: list[CameraMonitor] = []
        for cam_config in CAMERAS:
            monitor = CameraMonitor(cam_config, self.detector, self.pose_detector)
            self.cameras.append(monitor)
            print(f"📹 Camera {cam_config.id}: {cam_config.name}")
        
        # Current camera index
        self.current_camera_idx = 0
        
        # UI state
        self.show_stats = False
        self.show_help = True
        self.running = False
        self.window_name = "Workplace Monitoring"
    
    @property
    def current_camera(self) -> CameraMonitor:
        return self.cameras[self.current_camera_idx]
    
    def run(self):
        """Main application loop"""
        # Connect to ALL cameras
        connected_count = 0
        print("🔌 Connecting to all cameras...")
        for camera in self.cameras:
            if camera.connect():
                print(f"✅ Connected to {camera.config.name}")
                connected_count += 1
            else:
                print(f"❌ Failed to connect to {camera.config.name}")
        
        if connected_count == 0:
            print("❌ No cameras connected. Exiting.")
            return
        
        # Create window
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(
            self.window_name, 
            create_mouse_callback(self.current_camera.roi_editor)
        )
        
        self.running = True
        print("\n🎬 Monitoring started! Press 'H' for help, 'Q' to quit\n")
        
        try:
            while self.running:
                display_frame = None
                
                # Process ALL cameras
                for i, camera in enumerate(self.cameras):
                    if not camera.is_connected:
                        continue
                        
                    # Read frame
                    ret, frame = camera.stream.read_frame()
                    if not ret:
                        if i == self.current_camera_idx:
                            display_frame = self._create_error_frame(f"Connection lost: {camera.config.name}")
                        continue
                    
                    # Process frame (employee zones detection)
                    # Note: Running YOLO for every camera every frame might be heavy
                    processed_frame, person_count = camera.process_frame(frame)
                    
                    # Process client zones with ByteTrack
                    processed_frame = self._process_client_zones(processed_frame, camera)
                    
                    # If this is the current camera, prepare for display
                    if i == self.current_camera_idx:
                        display_frame = processed_frame.copy()
                        
                        # Draw person count on display frame
                        cv2.putText(
                            display_frame, f"Persons: {person_count}", (10, display_frame.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
                        )
                        
                        # Draw camera info
                        self._draw_camera_info(display_frame)
                        
                        # Draw UI panels
                        if self.show_stats:
                            stats = camera.get_stats()
                            display_frame = draw_stats_panel(display_frame, stats)
                        
                        if self.show_help:
                            display_frame = draw_help_panel(display_frame)
                        
                        # Draw ROI editor overlay if drawing
                        if self.roi_editor.is_drawing:
                            display_frame = self.roi_editor.draw_current(display_frame)

                # Display current camera frame
                if display_frame is not None:
                    cv2.imshow(self.window_name, display_frame)
                
                # Handle keyboard
                self._handle_keyboard()
        
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted by user")
        
        finally:
            for camera in self.cameras:
                camera.disconnect()
            cv2.destroyAllWindows()
            print("👋 Monitoring stopped")
    
    def _create_error_frame(self, message: str):
        """Create error/status frame"""
        import numpy as np
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.putText(
            frame, message, (500, 360),
            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3
        )
        return frame
    
    def _draw_camera_info(self, frame):
        """Draw current camera info"""
        camera = self.current_camera
        text = f"[{self.current_camera_idx + 1}/{len(self.cameras)}] {camera.config.name}"
        
        cv2.rectangle(frame, (0, 0), (len(text) * 12 + 20, 35), (0, 0, 0), -1)
        cv2.putText(
            frame, text, (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
        )
    
    def _process_client_zones(self, frame, camera: CameraMonitor):
        """Process client zones with ByteTrack tracking - single client per zone"""
        from datetime import datetime
        from config import CLIENT_ENTRY_THRESHOLD
        from gui.display import format_duration
        
        # Get client zones
        client_zones = [roi for roi in camera.roi_manager.get_all_rois() 
                       if roi.zone_type == "client"]
        
        if not client_zones:
            return frame
        
        # Run tracking detection
        detections = self.tracking_detector.detect(frame)
        
        now = datetime.now()
        camera_id = camera.camera_db_id
        
        for roi in client_zones:
            zone_key = (camera_id, roi.id)
            
            # Initialize zone state: {'active_client': track_id or None, 'clients': {track_id: data}}
            if zone_key not in self.client_tracking:
                self.client_tracking[zone_key] = {
                    'active_client': None,  # Currently tracked client
                    'clients': {}  # All clients in zone with their data
                }
            
            zone_state = self.client_tracking[zone_key]
            
            # Find all clients currently in this zone with their centers
            clients_in_zone = []
            for det in detections:
                if roi.contains_point(det.center):
                    clients_in_zone.append({
                        'track_id': det.track_id,
                        'center': det.center
                    })
                    
                    # Update or add client data
                    if det.track_id not in zone_state['clients']:
                        zone_state['clients'][det.track_id] = {
                            'enter_time': now,
                            'last_seen': now
                        }
                    else:
                        zone_state['clients'][det.track_id]['last_seen'] = now
            
            current_track_ids = [c['track_id'] for c in clients_in_zone]
            
            # Check if active client left
            if zone_state['active_client'] is not None:
                if zone_state['active_client'] not in current_track_ids:
                    # Active client left - save if >60s
                    track_id = zone_state['active_client']
                    if track_id in zone_state['clients']:
                        track_data = zone_state['clients'][track_id]
                        duration = (track_data['last_seen'] - track_data['enter_time']).total_seconds()
                        
                        if duration >= CLIENT_ENTRY_THRESHOLD:
                            employee_id = roi.linked_employee_id
                            if employee_id:
                                db.save_client_visit(
                                    place_id=roi.id,
                                    employee_id=employee_id,
                                    track_id=track_id,
                                    enter_time=track_data['enter_time'],
                                    exit_time=track_data['last_seen'],
                                    duration_seconds=duration
                                )
                                service_time = duration - CLIENT_ENTRY_THRESHOLD
                                print(f"✅ Client #{track_id} → emp#{employee_id}: обслуживание {int(service_time)}s")
                        
                        del zone_state['clients'][track_id]
                    
                    zone_state['active_client'] = None
            
            # Remove other clients that left (not active)
            tracks_to_remove = [tid for tid in zone_state['clients'] 
                               if tid not in current_track_ids and tid != zone_state['active_client']]
            for tid in tracks_to_remove:
                del zone_state['clients'][tid]
            
            # If no active client, pick the first one in zone
            if zone_state['active_client'] is None and clients_in_zone:
                # Pick first client (by track_id as proxy for arrival order)
                first_client = min(clients_in_zone, key=lambda c: c['track_id'])
                zone_state['active_client'] = first_client['track_id']
            
            # Draw timer for active client (only after 60s verification)
            if zone_state['active_client'] is not None:
                track_id = zone_state['active_client']
                track_data = zone_state['clients'].get(track_id)
                
                if track_data:
                    elapsed = (now - track_data['enter_time']).total_seconds()
                    
                    pts = roi.get_polygon_array()
                    M = cv2.moments(pts)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"]) + 50
                        
                        if elapsed >= CLIENT_ENTRY_THRESHOLD:
                            # Show timer starting from 00:01:00
                            display_time = elapsed  # Total time including verification
                            time_str = format_duration(display_time)
                            cv2.putText(
                                frame, time_str, (cx - 40, cy),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
                            )
                        # During verification (0-60s) - show nothing
        
        # Draw tracking detections on frame
        frame = self.tracking_detector.draw_detections(frame, detections)
        
        return frame
    
    def _switch_camera(self, delta: int):
        """Switch to another camera (view only)"""
        # No disconnect needed - all cameras keep running
        
        self.current_camera_idx = (self.current_camera_idx + delta) % len(self.cameras)
        
        # Update mouse callback for new camera's ROI editor
        cv2.setMouseCallback(
            self.window_name,
            create_mouse_callback(self.current_camera.roi_editor)
        )
        
        print(f"👀 Viewing: {self.current_camera.config.name}")
    
    def _handle_keyboard(self):
        """Handle keyboard input"""
        key = cv2.waitKey(1) & 0xFF
        camera = self.current_camera
        
        if key == ord('q') or key == ord('Q'):
            self.running = False
        
        elif key == ord('r') or key == ord('R'):
            # Start drawing - will ask for zone type when finished
            camera.roi_editor.start_drawing()
            print("🔲 Drawing ROI... Press ENTER when done, then E=employee or C=client")
        
        elif key == 13:  # Enter
            if camera.roi_editor.is_drawing:
                points = camera.roi_editor.finish_roi()
                if points:
                    # Store points temporarily, wait for zone type selection
                    self._pending_roi_points = points
                    self._waiting_zone_type = True
                    print("📋 ROI saved. Press: E=employee zone, C=client zone")
        
        elif key == ord('e') or key == ord('E'):
            # Employee zone
            if hasattr(self, '_waiting_zone_type') and self._waiting_zone_type:
                self._save_roi_with_type("employee")
            else:
                print("ℹ️ Draw ROI first (R), then press E for employee zone")
        
        elif key >= ord('0') and key <= ord('9'):
            # Select employee for client zone linking (1-9 = employees 1-9, 0 = employee 10)
            if hasattr(self, '_waiting_employee_link') and self._waiting_employee_link:
                digit = int(chr(key))
                employee_idx = 9 if digit == 0 else digit - 1  # 0 means 10th, 1-9 means 1st-9th
                employees = db.get_all_employees()
                if employee_idx < len(employees):
                    self._link_and_save_client_zone(employees[employee_idx]['id'])
                else:
                    print(f"❌ Сотрудник #{employee_idx + 1} не найден")
        
        elif key == 27:  # Escape
            if camera.roi_editor.is_drawing:
                camera.roi_editor.cancel_drawing()
            if hasattr(self, '_waiting_zone_type'):
                self._waiting_zone_type = False
                self._pending_roi_points = None
                print("❌ ROI cancelled")
        
        elif key == ord('d') or key == ord('D'):
            rois = camera.roi_manager.get_all_rois()
            if rois:
                camera.roi_manager.delete_roi(rois[-1].id)
        
        elif key == ord('c') or key == ord('C'):
            # Check if waiting for zone type
            if hasattr(self, '_waiting_zone_type') and self._waiting_zone_type:
                # Client zone - need to link to employee
                employees = db.get_all_employees()
                if employees:
                    print("👤 Выберите сотрудника (1-9, 0=10):")
                    for i, emp in enumerate(employees[:10]):
                        key_hint = 0 if i == 9 else i + 1  # 1-9 for first 9, 0 for 10th
                        print(f"   {key_hint}: {emp['name']}")
                    self._waiting_employee_link = True
                    self._waiting_zone_type = False  # Important: switch state to prevent conflicts
                else:
                    print("⚠️ Сотрудники не найдены в БД. Создаём зону без привязки.")
                    self._save_roi_with_type("client", linked_employee_id=None)
            else:
                # Clear all ROIs for current camera
                camera.roi_manager.delete_all_rois()
        
        elif key == ord('s') or key == ord('S'):
            self.show_stats = not self.show_stats
        
        elif key == ord('h') or key == ord('H'):
            self.show_help = not self.show_help
        
        elif key == ord('n') or key == ord('N'):
            # Next camera
            if len(self.cameras) > 1:
                self._switch_camera(1)
        
        elif key == ord('p') or key == ord('P'):
            # Previous camera
            if len(self.cameras) > 1:
                self._switch_camera(-1)
    
    def _save_roi_with_type(self, zone_type: str, linked_employee_id: int = None):
        """Save ROI with specified zone type"""
        camera = self.current_camera
        if hasattr(self, '_pending_roi_points') and self._pending_roi_points:
            camera.roi_manager.add_roi(
                self._pending_roi_points, 
                zone_type=zone_type,
                linked_employee_id=linked_employee_id
            )
            self._pending_roi_points = None
            self._waiting_zone_type = False
            print(f"✅ ROI saved as {zone_type} zone")
    
    def _link_and_save_client_zone(self, employee_id: int):
        """Save client zone linked to employee"""
        self._save_roi_with_type("client", linked_employee_id=employee_id)
        self._waiting_employee_link = False
        print(f"✅ Client zone linked to employee ID {employee_id}")


def main():
    """Entry point"""
    print("""
╔══════════════════════════════════════════════════╗
║  🏢  WORKPLACE MONITORING SYSTEM  🏢             ║
║  ──────────────────────────────────────────      ║
║  Multi-Camera RTSP Version                       ║
║  Real-time presence detection with time tracking ║
╚══════════════════════════════════════════════════╝
    """)
    
    monitor = WorkplaceMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
