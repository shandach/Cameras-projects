"""
Workplace Monitoring System - Main Entry Point

Real-time video monitoring with:
- YOLOv8 person detection
- Interactive ROI zone editing
- Occupancy tracking with time logic
- SQLite session storage

Controls:
- R: Start drawing new ROI zone
- ENTER: Finish ROI drawing
- ESC: Cancel drawing
- D: Delete last ROI
- S: Toggle stats panel
- H: Toggle help panel
- Q: Quit
"""
import cv2
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import WINDOW_NAME, ROI_COLOR_OCCUPIED, ROI_COLOR_VACANT
from core.stream_handler import StreamHandler
from core.detector import PersonDetector
from core.roi_manager import ROIManager
from core.occupancy_engine import OccupancyEngine
from gui.roi_editor import ROIEditor, create_mouse_callback
from gui.display import draw_timer_overlay, draw_stats_panel, draw_help_panel, format_duration


class WorkplaceMonitor:
    """Main application class"""
    
    def __init__(self):
        print("🏢 Workplace Monitoring System")
        print("=" * 40)
        
        # Initialize components
        self.stream = StreamHandler()
        self.detector = PersonDetector()
        self.roi_manager = ROIManager()
        self.occupancy_engine = OccupancyEngine()
        self.roi_editor = ROIEditor(WINDOW_NAME)
        
        # UI state
        self.show_stats = False
        self.show_help = True
        self.running = False
    
    def run(self):
        """Main application loop"""
        # Start video capture
        if not self.stream.start():
            print("❌ Failed to start video capture")
            return
        
        # Create window and set mouse callback
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, create_mouse_callback(self.roi_editor))
        
        self.running = True
        print("\n🎬 Monitoring started! Press 'H' for help, 'Q' to quit\n")
        
        try:
            while self.running:
                # Capture frame
                ret, frame = self.stream.read_frame()
                if not ret:
                    print("⚠️ Failed to read frame, retrying...")
                    continue
                
                # Process frame
                frame = self._process_frame(frame)
                
                # Display
                cv2.imshow(WINDOW_NAME, frame)
                
                # Handle keyboard
                self._handle_keyboard()
        
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted by user")
        
        finally:
            self.stream.stop()
            cv2.destroyAllWindows()
            print("👋 Monitoring stopped")
    
    def _process_frame(self, frame):
        """Process a single frame"""
        # 1. Detect persons
        detections = self.detector.detect(frame)
        person_centers = [d.center for d in detections]
        
        # 2. Check presence in ROIs
        presence = self.roi_manager.check_presence(person_centers)
        
        # 3. Update occupancy engine for each ROI
        for roi in self.roi_manager.get_all_rois():
            is_present = presence.get(roi.id, False)
            self.occupancy_engine.update(roi.id, is_present)
            
            # Update ROI status for display
            status = self.occupancy_engine.get_zone_status(roi.id)
            self.roi_manager.update_status(roi.id, status)
        
        # 4. Draw ROIs with status colors
        frame = self.roi_manager.draw_rois(
            frame, 
            occupied_color=ROI_COLOR_OCCUPIED,
            vacant_color=ROI_COLOR_VACANT
        )
        
        # 5. Draw person detections
        frame = self.detector.draw_detections(frame, detections)
        
        # 6. Draw timers
        roi_timers = {}
        roi_positions = {}
        for roi in self.roi_manager.get_all_rois():
            timer = self.occupancy_engine.get_zone_time(roi.id)
            if timer > 0:
                roi_timers[roi.id] = timer
                # Get centroid position
                pts = roi.get_polygon_array()
                M = cv2.moments(pts)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + 35
                    roi_positions[roi.id] = (cx - 40, cy)
        
        frame = draw_timer_overlay(frame, roi_timers, roi_positions)
        
        # 7. Draw ROI editor overlay if drawing
        if self.roi_editor.is_drawing:
            frame = self.roi_editor.draw_current(frame)
        
        # 8. Draw UI panels
        if self.show_stats:
            stats = self._get_stats()
            frame = draw_stats_panel(frame, stats)
        
        if self.show_help:
            frame = draw_help_panel(frame)
        
        # 9. Draw detection count
        cv2.putText(
            frame, f"Persons: {len(detections)}", (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
        )
        
        return frame
    
    def _get_stats(self):
        """Get current statistics"""
        rois = self.roi_manager.get_all_rois()
        occupied = sum(1 for r in rois if r.status == "OCCUPIED")
        total_time = sum(self.occupancy_engine.get_zone_time(r.id) for r in rois)
        
        return {
            "Zones": len(rois),
            "Occupied": occupied,
            "Vacant": len(rois) - occupied,
            "Total Time": format_duration(total_time)
        }
    
    def _handle_keyboard(self):
        """Handle keyboard input"""
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q') or key == ord('Q'):
            # Quit
            self.running = False
        
        elif key == ord('r') or key == ord('R'):
            # Start ROI drawing
            self.roi_editor.start_drawing()
        
        elif key == 13:  # Enter
            # Finish ROI drawing
            if self.roi_editor.is_drawing:
                points = self.roi_editor.finish_roi()
                if points:
                    self.roi_manager.add_roi(points)
        
        elif key == 27:  # Escape
            # Cancel ROI drawing
            if self.roi_editor.is_drawing:
                self.roi_editor.cancel_drawing()
        
        elif key == ord('d') or key == ord('D'):
            # Delete last ROI
            rois = self.roi_manager.get_all_rois()
            if rois:
                last_roi = rois[-1]
                self.roi_manager.delete_roi(last_roi.id)
        
        elif key == ord('s') or key == ord('S'):
            # Toggle stats
            self.show_stats = not self.show_stats
        
        elif key == ord('h') or key == ord('H'):
            # Toggle help
            self.show_help = not self.show_help


def main():
    """Entry point"""
    print("""
╔══════════════════════════════════════════╗
║  🏢  WORKPLACE MONITORING SYSTEM  🏢     ║
║  ────────────────────────────────────    ║
║  Real-time presence detection            ║
║  with time tracking                      ║
╚══════════════════════════════════════════╝
    """)
    
    monitor = WorkplaceMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
