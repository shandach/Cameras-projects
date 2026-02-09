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

sys.path.insert(0, str(Path(__file__).parent))

from config import CAMERAS, ROI_COLOR_OCCUPIED, ROI_COLOR_VACANT, print_config
from core.stream_handler import StreamHandler
from core.detector import PersonDetector, PoseDetector
from core.roi_manager import ROIManager
from core.occupancy_engine import OccupancyEngine
from gui.roi_editor import ROIEditor, create_mouse_callback
from gui.display import draw_timer_overlay, draw_stats_panel, draw_help_panel, format_duration
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
        
        # Draw timers
        roi_timers = {}
        roi_positions = {}
        for roi in self.roi_manager.get_all_rois():
            # USE DAILY TOTAL instead of current session
            timer = self.occupancy_engine.get_total_daily_time(roi.id)
            # timer = self.occupancy_engine.get_zone_time(roi.id)
            
            if timer > 0:
                roi_timers[roi.id] = timer
                pts = roi.get_polygon_array()
                M = cv2.moments(pts)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + 35
                    roi_positions[roi.id] = (cx - 40, cy)
        
        frame = draw_timer_overlay(frame, roi_timers, roi_positions)
        
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
        
        # Shared backup detector (MediaPipe Pose for when YOLO fails)
        self.pose_detector = PoseDetector()
        
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
        # Connect to first camera
        if not self.current_camera.connect():
            print("❌ Failed to connect to camera")
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
                camera = self.current_camera
                
                # Read frame
                ret, frame = camera.stream.read_frame()
                if not ret:
                    # Show reconnecting message
                    frame = self._create_error_frame("Reconnecting...")
                else:
                    # Process frame
                    frame, person_count = camera.process_frame(frame)
                    
                    # Draw person count
                    cv2.putText(
                        frame, f"Persons: {person_count}", (10, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
                    )
                
                # Draw camera info
                self._draw_camera_info(frame)
                
                # Draw UI panels
                if self.show_stats:
                    stats = camera.get_stats()
                    frame = draw_stats_panel(frame, stats)
                
                if self.show_help:
                    frame = draw_help_panel(frame)
                
                # Display
                cv2.imshow(self.window_name, frame)
                
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
    
    def _switch_camera(self, delta: int):
        """Switch to another camera"""
        self.current_camera.disconnect()
        
        self.current_camera_idx = (self.current_camera_idx + delta) % len(self.cameras)
        
        # Update mouse callback for new camera's ROI editor
        cv2.setMouseCallback(
            self.window_name,
            create_mouse_callback(self.current_camera.roi_editor)
        )
        
        self.current_camera.connect()
        print(f"📹 Switched to: {self.current_camera.config.name}")
    
    def _handle_keyboard(self):
        """Handle keyboard input"""
        key = cv2.waitKey(1) & 0xFF
        camera = self.current_camera
        
        if key == ord('q') or key == ord('Q'):
            self.running = False
        
        elif key == ord('r') or key == ord('R'):
            camera.roi_editor.start_drawing()
        
        elif key == 13:  # Enter
            if camera.roi_editor.is_drawing:
                points = camera.roi_editor.finish_roi()
                if points:
                    camera.roi_manager.add_roi(points)
        
        elif key == 27:  # Escape
            if camera.roi_editor.is_drawing:
                camera.roi_editor.cancel_drawing()
        
        elif key == ord('d') or key == ord('D'):
            rois = camera.roi_manager.get_all_rois()
            if rois:
                camera.roi_manager.delete_roi(rois[-1].id)
        
        elif key == ord('c') or key == ord('C'):
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
