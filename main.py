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
- ENTER: Finish ROI drawing (then C=Client, E=Employee)
- ESC: Cancel drawing
- X: Delete last ROI (Undo)
- Z: Clear ALL ROIs for current camera
- Right-Click: Delete specific ROI
- S: Toggle stats panel
- H: Toggle help panel
- F: Toggle Fullscreen
- W: Toggle View All cameras (for drawing ROIs)
- D: Next camera
- A: Previous camera
- Q: Quit
"""
import cv2
import sys
from pathlib import Path
import time
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from config import (CAMERAS, ROI_COLOR_OCCUPIED, ROI_COLOR_VACANT, print_config,
                    AUTO_CYCLE_INTERVAL, AUTO_CYCLE_PAUSE_DURATION,
                    FULLSCREEN_MODE)
from core.stream_handler import StreamHandler
from core.detector import PersonDetector
from core.roi_manager import ROIManager
from core.occupancy_engine import OccupancyEngine
from core.sync_service import sync_service
from gui.roi_editor import ROIEditor, create_mouse_callback
from gui.display import draw_timer_overlay, draw_stats_panel, draw_help_panel, format_duration, draw_employee_stats_overlay
from database.db import db


class CameraMonitor:
    """Monitor for a single camera"""
    
    def __init__(self, camera_config, detector: PersonDetector):
        """
        Initialize camera monitor
        
        Args:
            camera_config: CameraConfig from .env
            detector: Shared YOLOv8 body detector instance
        """
        self.config = camera_config
        self.detector = detector
        # self.head_detector removed (using single YOLOv8s)
        
        # Get or create camera in database
        self.db_camera = db.get_or_create_camera(camera_config)
        self.camera_db_id = self.db_camera.id
        
        # Initialize components
        self.stream = StreamHandler(camera_config)
        self.roi_manager = ROIManager(self.camera_db_id)
        self.occupancy_engine = OccupancyEngine()
        self.roi_editor = ROIEditor(f"Camera {camera_config.id}")
        
        self.is_connected = False
        
        # CPU Optimization: Frame Skipping
        self.frame_skip_counter = 0
        self.SKIP_FRAMES = 2  # Process 1, Skip 2 (Effective 1/3 FPS for detection)
        # We store the *results* of detection to redraw them on skipped frames
        self.last_detections = []
    
    def connect(self) -> bool:
        """Connect to camera stream"""
        # StreamHandler.start() now launches a thread
        self.is_connected = self.stream.start()
        return self.is_connected
    
    def disconnect(self):
        """Disconnect from camera"""
        self.stream.stop()
        self.is_connected = False
    
    def process_frame(self, frame):
        """Process a single frame"""
        # Optimization: Frame Skipping
        self.frame_skip_counter += 1
        run_detection = (self.frame_skip_counter % (self.SKIP_FRAMES + 1) == 0)
        
        if run_detection:
            # 1. Detect persons (Single YOLOv8s model)
            detections = self.detector.detect(frame)
            
            # Save for next frames
            self.last_detections = detections
            
        else:
            # Skip detection, reuse last results (but redraw them on new frame)
            detections = self.last_detections
        
        # Extract centers for ROI presence check
        person_centers = [det.center for det in detections]
        
        # Check presence in ROIs (We do this EVERY frame to keep UI responsive)
        presence = self.roi_manager.check_presence(person_centers)
        
        # Update occupancy engine for ALL zones (Employee & Client)
        for roi in self.roi_manager.get_all_rois():
            is_present = presence.get(roi.id, False)
            
            # Use unified engine for both types
            self.occupancy_engine.update(
                zone_id=roi.id, 
                is_person_present=is_present,
                zone_type=roi.zone_type,
                linked_employee_id=roi.linked_employee_id
            )
            
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
                # Draw Client Timer Overlay
                status = self.occupancy_engine.get_zone_status(roi.id)
                if status in ["OCCUPIED", "CHECKING_EXIT"]:
                    from config import CLIENT_ENTRY_THRESHOLD
                    from gui.display import format_duration
                    
                    # Get elapsed time from engine
                    elapsed = self.occupancy_engine.get_zone_time(roi.id)
                    
                    if elapsed >= CLIENT_ENTRY_THRESHOLD:
                        pts = roi.get_polygon_array()
                        M = cv2.moments(pts)
                        if M["m00"] != 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"]) + 50
                            
                            time_str = format_duration(elapsed)
                            
                            # Color: Green if occupied, Yellow if checking exit (grace)
                            color = (0, 255, 0) if status == "OCCUPIED" else (0, 255, 255)
                            
                            cv2.putText(
                                frame, time_str, (cx - 40, cy),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
                            )
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
            employee_name = employee['name'] if employee else f"Place {roi.id}"
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
                'client_service_time': client_stats['total_service_time'],
                'roi_points': roi.points  # Pass polygon points for positioning
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
        
    def shutdown(self):
        """Shutdown monitor resources"""
        # Save any active sessions
        self.occupancy_engine.shutdown()
        # Stop stream
        self.disconnect()


class WorkplaceMonitor:
    """Main application - manages multiple cameras"""
    
    def __init__(self):
        print("\n WORKPLACE MONITORING SYSTEM - MULTI-CAMERA")
        print("=" * 50)
        
        # Print configuration
        print_config()
        
        if not CAMERAS:
            print("❌ No cameras configured!")
            print("   1. Copy .env.example to .env")
            print("   2. Add your RTSP camera URLs")
            sys.exit(1)
        
        # Shared detector (one YOLO instance for all cameras)
        print("[INFO] Loading YOLO detector...")
        self.detector = PersonDetector()
        
        # Create camera monitors
        self.cameras: list[CameraMonitor] = []
        for cam_config in CAMERAS:
            monitor = CameraMonitor(cam_config, self.detector)
            self.cameras.append(monitor)
            print(f"[CAM] Camera {cam_config.id}: {cam_config.name}")
        
        # Current camera index
        self.current_camera_idx = 0
        self.background_processing_idx = 0  # For Round-Robin background processing
        
        # Auto-cycle disabled by default (Manual mode: A/D keys)
        self.auto_cycle_enabled = False
        self.auto_cycle_direction = 1  # 1 = forward, -1 = backward
        self.last_cycle_time = 0.0
        self.auto_cycle_paused_until = 0.0  # Timestamp when pause ends
        
        # Fullscreen state
        # Fullscreen state (Loaded from .env, default False for debugging)
        self.is_fullscreen = FULLSCREEN_MODE
        
        # UI state
        self.show_stats = False
        self.show_help = False  # Start without help in production
        self.view_all_mode = False  # W key: show all cameras (including without ROIs)
        self.running = False
        self.window_name = "Workplace Monitoring"
        
        # OSD message state (for on-screen confirmations)
        self._osd_message = None
        self._osd_expire_time = 0
    
    @property
    def current_camera(self) -> CameraMonitor:
        return self.cameras[self.current_camera_idx]
    
    def run(self):
        """Main application loop"""
        # Start Sync Service (Background)
        sync_service.start()

        # Connect ONLY cameras that have ROI zones (Lazy Connection)
        connected_count = 0
        print("[INFO] Connecting cameras with ROI zones...")
        for camera in self.cameras:
            has_rois = len(camera.roi_manager.get_all_rois()) > 0
            if has_rois:
                time.sleep(0.1)
                if camera.connect():
                    print(f"[OK] Connected to {camera.config.name}")
                    connected_count += 1
                else:
                    print(f"[FAIL] Failed to connect to {camera.config.name}")
            else:
                print(f"[SKIP] {camera.config.name} — no ROI zones, not connecting")
        
        # Even if 0 cameras connected, we still run the UI (to show error screens)
        if connected_count == 0:
            print("⚠️ No cameras with ROI zones. Press W to view all cameras and draw zones.")
        
        # No predefined ROI import — user draws manually
        
        # Create fullscreen window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        if self.is_fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.setMouseCallback(
            self.window_name, 
            self._handle_mouse
        )
        
        self.running = True
        self.last_cycle_time = time.time()
        
        # Set initial camera to one with ROIs
        self._set_initial_camera()
        
        print("\n Monitoring started! Press 'H' for help, 'Q' to quit\n")
        
        try:
            while self.running:
                display_frame = None
                
                # ---------------------------------------------------------
                # Processing Loop
                # ---------------------------------------------------------
                display_frame = None
                
                # 1. READ frames from ALL cameras (non-blocking now thanks to threads)
                # We need fresh frames for display when switching, even if not detections
                frames = {}
                for i, camera in enumerate(self.cameras):
                    if not camera.is_connected:
                        continue
                    ret, frame = camera.stream.read_frame()
                    if ret:
                        frames[camera.camera_db_id] = frame
                        
                        # If this is the current camera, save for display
                        if i == self.current_camera_idx:
                            display_frame = frame.copy()
                            
                # 2. RUN DETECTION / TRACKING
                for camera in self.cameras:
                    if camera.camera_db_id not in frames:
                        continue
                        
                    # OPTIMIZATION: Process only if ROIs exist
                    if not camera.roi_manager.get_all_rois():
                        continue
                        
                    frame = frames[camera.camera_db_id]
                    
                    # Run AI detection (YOLO)
                    processed_frame, person_count = camera.process_frame(frame)
                    
                    # If this was Current Camera, update display frame
                    if camera == self.current_camera:
                        display_frame = processed_frame

                        # Draw person count
                        cv2.putText(
                            display_frame, f"Persons: {person_count}", (10, display_frame.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
                        )
                
                # 3. UI OVERLAYS (on display frame only)
                if display_frame is not None:
                    # Draw camera info
                    self._draw_camera_info(display_frame)
                    
                    # Draw UI panels
                    if self.show_stats:
                        stats = self.current_camera.get_stats()
                        display_frame = draw_stats_panel(display_frame, stats)
                    
                    if self.show_help:
                        display_frame = draw_help_panel(display_frame)
                    
                    # Draw ROI editor
                    if self.current_camera.roi_editor.is_drawing:
                        display_frame = self.current_camera.roi_editor.draw_current(display_frame)
                    
                    # Draw OSD (on-screen messages)
                    self._draw_osd(display_frame)

                # Display current camera frame
                if display_frame is not None:
                    cv2.imshow(self.window_name, display_frame)
                else:
                    # If camera is offline/connecting, show status frame instead of freezing
                    status_frame = self._create_error_frame("No Signal / Reconnecting...")
                    # Add camera info if possible
                    if self.cameras:
                        self._draw_camera_info(status_frame)
                    cv2.imshow(self.window_name, status_frame)
                
                # Auto-cycle cameras (ping-pong)
                self._auto_cycle()
                
                # Handle keyboard
                self._handle_keyboard()
        
        except KeyboardInterrupt:
            print("\n[WARN] Interrupted by user")
        
        finally:
            print("\n[INFO] Shutting down application...")
            # Stop Sync Service
            sync_service.stop()
            
            for camera in self.cameras:
                camera.shutdown()
            cv2.destroyAllWindows()
            print(" Monitoring stopped")
    
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
        

        
        return frame
    
    def _auto_cycle(self):
        """Auto-cycle cameras in ping-pong mode"""
        if not self.auto_cycle_enabled:
            return
        if len(self.cameras) <= 1:
            return
        
        now = time.time()
        
        # Check if paused (manual override)
        if now < self.auto_cycle_paused_until:
            return
        
        # Check if it's time to switch
        if now - self.last_cycle_time < AUTO_CYCLE_INTERVAL:
            return
        
        self.last_cycle_time = now
        
        # Ping-pong: reverse direction at boundaries
        next_idx = self.current_camera_idx + self.auto_cycle_direction
        
        if next_idx >= len(self.cameras):
            self.auto_cycle_direction = -1
            next_idx = self.current_camera_idx - 1
        elif next_idx < 0:
            self.auto_cycle_direction = 1
            next_idx = self.current_camera_idx + 1
        
        self.current_camera_idx = next_idx
        
        # Update mouse callback
        cv2.setMouseCallback(
            self.window_name,
            self._handle_mouse
        )
    
    def _switch_camera(self, delta: int):
        """Switch to another camera — skips cameras without ROIs (unless View All mode)"""
        if self.view_all_mode:
            # View All: cycle through ALL cameras
            self.current_camera_idx = (self.current_camera_idx + delta) % len(self.cameras)
        else:
            # Normal: cycle only cameras with ROIs
            viewable = self._get_viewable_indices()
            if not viewable:
                print("⚠️ No cameras with ROI zones. Press W to view all cameras.")
                return
            try:
                pos = viewable.index(self.current_camera_idx)
            except ValueError:
                pos = 0
            pos = (pos + delta) % len(viewable)
            self.current_camera_idx = viewable[pos]
        
        # Auto-connect if camera is not connected yet (View All mode)
        camera = self.current_camera
        if not camera.is_connected:
            print(f"🔌 Connecting to {camera.config.name}...")
            camera.connect()
        
        # Pause auto-cycle for 30 seconds
        self.auto_cycle_paused_until = time.time() + AUTO_CYCLE_PAUSE_DURATION
        
        # Update mouse callback for new camera's ROI editor
        cv2.setMouseCallback(
            self.window_name,
            self._handle_mouse
        )
        
        rois_count = len(camera.roi_manager.get_all_rois())
        mode_str = "[VIEW ALL]" if self.view_all_mode else ""
        print(f"👀 {mode_str} {camera.config.name} ({rois_count} ROIs)")
    
    def _get_viewable_indices(self):
        """Get indices of cameras that have ROI zones"""
        return [i for i, cam in enumerate(self.cameras) 
                if len(cam.roi_manager.get_all_rois()) > 0]
    
    def _set_initial_camera(self):
        """Set initial camera to first one with ROIs"""
        viewable = self._get_viewable_indices()
        if viewable:
            self.current_camera_idx = viewable[0]
            print(f"📷 Initial view: {self.current_camera.config.name} ({len(viewable)} cameras with ROIs)")
        else:
            print("⚠️ No cameras have ROI zones. Draw ROIs to start monitoring.")
    
    def _show_osd(self, message: str, duration: float = 3.0):
        """Show on-screen display message"""
        self._osd_message = message
        self._osd_expire_time = time.time() + duration
    
    def _draw_osd(self, frame):
        """Draw OSD message if active"""
        if self._osd_message and time.time() < self._osd_expire_time:
            h, w = frame.shape[:2]
            text = self._osd_message
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            x = (w - tw) // 2
            y = h - 60
            cv2.rectangle(frame, (x - 10, y - th - 10), (x + tw + 10, y + 10), (0, 0, 0), -1)
            cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 200), 2)
        elif self._osd_message:
            self._osd_message = None
    
    def _handle_keyboard(self):
        """Handle keyboard input"""
        key = cv2.waitKey(1) & 0xFF
        camera = self.current_camera
        
        if key == ord('q') or key == ord('Q'):
            # Save all drawn zones to DB and JSON before quitting
            print("\n💾 Saving all zones...")
            for cam in self.cameras:
                cam.roi_manager.save_all_to_storage()
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
        
        elif key == ord('x') or key == ord('X'):
            # Delete last ROI (Moved from D)
            rois = camera.roi_manager.get_all_rois()
            if rois:
                camera.roi_manager.delete_roi(rois[-1].id)
                print("🗑️ ROI deleted")
            else:
                 print("ℹ️ No ROIs to delete")
        
        elif key == ord('d') or key == ord('D'):
             # Next camera (manual)
            if len(self.cameras) > 1:
                self._switch_camera(1)
        
        elif key == ord('a') or key == ord('A'):
            # Previous camera (manual)
            if len(self.cameras) > 1:
                self._switch_camera(-1)

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

        elif key == ord('l') or key == ord('L'):
            # Link LAST Client Zone to next Employee Zone (Cycle through zone IDs)
            rois = camera.roi_manager.get_all_rois()
            if rois:
                target_roi = rois[-1]
                
                if target_roi.zone_type == 'client':
                    # Get all employee zone IDs from ALL cameras  
                    all_employee_zone_ids = []
                    for cam in self.cameras:
                        for r in cam.roi_manager.get_all_rois():
                            if r.zone_type == 'employee':
                                all_employee_zone_ids.append(r.id)
                    all_employee_zone_ids.sort()
                    
                    if not all_employee_zone_ids:
                        print("⚠️ Нет зон сотрудников для привязки!")
                        self._show_osd("No employee zones to link!", 3)
                    else:
                        current_id = target_roi.linked_employee_id
                        
                        if current_id is None or current_id not in all_employee_zone_ids:
                            new_id = all_employee_zone_ids[0]
                        else:
                            idx = all_employee_zone_ids.index(current_id)
                            new_id = all_employee_zone_ids[(idx + 1) % len(all_employee_zone_ids)]
                        
                        target_roi.linked_employee_id = new_id
                        db.update_roi_link(target_roi.id, new_id)
                        camera.roi_manager._save_to_json()
                        
                        msg = f"Client #{target_roi.id} -> Zone #{new_id}"
                        print(f"🔗 {msg}")
                        self._show_osd(msg, 3)
                else:
                    print("⚠️ Привязка только для CLIENT зон!")
                    self._show_osd("Press L on a CLIENT zone", 2)
                
        elif key == ord('z') or key == ord('Z'):
             # Clear all ROIs for current camera (moved from C)
            camera.roi_manager.delete_all_rois()
            print("🧹 All ROIs cleared for current camera")
        
        elif key == ord('s') or key == ord('S'):
            self.show_stats = not self.show_stats
        
        elif key == ord('h') or key == ord('H'):
            self.show_help = not self.show_help
        
        elif key == ord('f') or key == ord('F'):
            # Toggle fullscreen
            self.is_fullscreen = not self.is_fullscreen
            if self.is_fullscreen:
                cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            else:
                cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        
        elif key == ord('w') or key == ord('W'):
            # Toggle View All mode (show all cameras including ones without ROIs)
            self.view_all_mode = not self.view_all_mode
            if self.view_all_mode:
                print("🌐 VIEW ALL MODE: Showing all cameras (A/D to browse, draw ROIs as needed)")
            else:
                # Switch back to filtered mode — jump to first camera with ROIs
                self._set_initial_camera()
                print("📷 FILTERED MODE: Showing only cameras with ROI zones")
    
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

    def _handle_mouse(self, event, x, y, flags, param):
        """Handle mouse events - delegate to ROI editor or handle deletion"""
        camera = self.current_camera
        
        # Priority 1: Drawing mode
        if camera.roi_editor.is_drawing:
            camera.roi_editor.handle_mouse(event, x, y, flags, param)
            return

        # Priority 2: Right Click -> Delete ROI under cursor
        if event == cv2.EVENT_RBUTTONDOWN:
            print(f"🖱️ Right Click at ({x}, {y})")
            roi = camera.roi_manager.get_roi_at_point(x, y)
            if roi:
                print(f"   Found ROI: {roi.name} (ID: {roi.id})")
                camera.roi_manager.delete_roi(roi.id)
                print(f"🗑️ Deleted ROI '{roi.name}'")
            else:
                print("ℹ️ No ROI under cursor to delete")


def main():
    """Entry point"""
    print("=" * 50)
    print(" WORKPLACE MONITORING SYSTEM")
    print("=" * 50)
    print(" Multi-Camera RTSP Version")
    print(" Real-time presence detection with time tracking")
    print("=" * 50)
    
    monitor = WorkplaceMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
