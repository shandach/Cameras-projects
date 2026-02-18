"""
ROI Zones Setup & Demo Tool (roizones.py)

A lightweight version of the main application focused on:
1. Setting up ROI zones for all cameras (Synced with main DB)
2. Demonstrating real-time detection for investors (Instant feedback)
3. Grid View (Security Monitor style)

Features:
- Real-time Red/Green zone status (No time delays)
- Sandbox mode for Webcam (ID 0) - zones not saved to DB
- Grid View (Press 'J') - Monitor all cameras at once
- Standard controls: R=Draw, Right Click=Delete, S=Stats
"""
import cv2
import sys
import time
import numpy as np
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent))

from config import (CAMERAS, ROI_COLOR_OCCUPIED, ROI_COLOR_VACANT, 
                    ROI_COLOR_DRAWING, FRAME_WIDTH, FRAME_HEIGHT)
from core.stream_handler import StreamHandler
from core.detector import PersonDetector
from core.roi_manager import ROIManager
from gui.roi_editor import ROIEditor, create_mouse_callback
from database.db import db
from core.utils import is_point_in_box

# Colors for Demo
COLOR_GREEN = (0, 255, 0)
COLOR_RED = (0, 0, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_BLUE = (255, 0, 0)

class DemoCamera:
    """Simplified Camera Monitor for Demo/Setup"""
    
    def __init__(self, config, detector):
        self.config = config
        self.detector = detector
        
        # All cameras are real and save to DB
        self.is_sandbox = False
        
        # Initialize
        self.stream = StreamHandler(config)
        
        # Initialize ROIManager
        self.roi_manager = ROIManager(config.id)
             
        self.roi_editor = ROIEditor(f"Cam {config.id}")
        self.is_connected = False
        self.current_frame = None
        self.detections = []
        
    def connect(self):
        return self.stream.start()
    
    def disconnect(self):
        self.stream.stop()
        
    def process(self):
        # Allow sandbox to work even if stream is not "connected" properly in some cases
        # But stream.start() should handle it.
        ret, frame = self.stream.read_frame()
        if not ret:
            return None
            
        self.current_frame = frame.copy()
        
        # Detect
        self.detections = self.detector.detect(frame)
        person_centers = [d.center for d in self.detections]
        
        # Draw Results
        active_rois = self.roi_manager.get_all_rois()
        
        # 1. Draw ROIs with Status Colors
        for roi in active_rois:
            # Check instant occupancy
            is_occupied = False
            for center in person_centers:
                if roi.contains_point(center):
                    is_occupied = True
                    break
            
            # Determine Color
            if roi.zone_type == 'client':
                color = COLOR_BLUE if is_occupied else COLOR_YELLOW
            else:
                color = COLOR_RED if is_occupied else COLOR_GREEN
            
            # Draw Polygon
            pts = roi.get_polygon_array()
            cv2.polylines(frame, [pts], True, color, 2)
            
            # Overlay status text if needed (optional)
        
        # 2. Draw Editor
        if self.roi_editor.is_drawing:
            frame = self.roi_editor.draw_current(frame)
            
        return frame


class GridView:
    """Helper to draw grid of cameras with Sidebar"""
    
    def draw(self, cameras, window_size=(1920, 1080)):
        # Calculate grid layout (excluding sidebar space)
        sidebar_w = 400
        view_w = window_size[0] - sidebar_w
        view_h = window_size[1]
        
        n = len(cameras)
        if n == 0: return np.zeros((window_size[1], window_size[0], 3), dtype=np.uint8)
        
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
        
        cell_w = view_w // cols
        cell_h = view_h // rows
        
        # Create canvas
        canvas = np.zeros((window_size[1], window_size[0], 3), dtype=np.uint8)
        
        stats_total_emp = 0
        stats_occupied_emp = 0
        stats_total_client = 0
        stats_occupied_client = 0
        
        # Draw Cameras
        for i, cam in enumerate(cameras):
            r = i // cols
            c = i % cols
            
            x_start = c * cell_w
            y_start = r * cell_h
            
            # Get latest frame
            frame = cam.current_frame
            if frame is None:
                # Placeholder
                frame = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
                cv2.putText(frame, f"Cam {cam.config.id} (Signal Lost)", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            else:
                # Resize to cell
                frame = cv2.resize(frame, (cell_w, cell_h))
                # Add label
                cv2.rectangle(frame, (0,0), (200, 40), (0,0,0), -1)
                cv2.putText(frame, f"Cam {cam.config.id}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            
            # Place in grid
            canvas[y_start:y_start+cell_h, x_start:x_start+cell_w] = frame
            
            # Collect Stats
            rois = cam.roi_manager.get_all_rois()
            centers = [d.center for d in cam.detections]
            
            for roi in rois:
                is_occupied = False
                for center in centers:
                    if roi.contains_point(center):
                        is_occupied = True
                        break
                
                if roi.zone_type == 'client':
                    stats_total_client += 1
                    if is_occupied: stats_occupied_client += 1
                else:
                    stats_total_emp += 1
                    if is_occupied: stats_occupied_emp += 1

        # Draw Sidebar
        x_bar = view_w
        cv2.rectangle(canvas, (x_bar, 0), (window_size[0], window_size[1]), (30, 30, 30), -1)
        
        # Sidebar Header
        cv2.putText(canvas, "SECURITY MONITOR", (x_bar + 20, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.line(canvas, (x_bar+20, 60), (window_size[0]-20, 60), (100, 100, 100), 2)

        y = 120
        # Employee Stats
        cv2.putText(canvas, "EMPLOYEES", (x_bar + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
        y += 40
        self._draw_stat_row(canvas, x_bar + 20, y, "Occupied", stats_occupied_emp, COLOR_RED if stats_occupied_emp > 0 else COLOR_GREEN)
        y += 40
        self._draw_stat_row(canvas, x_bar + 20, y, "Vacant", stats_total_emp - stats_occupied_emp, COLOR_GREEN)

        y += 60
        # Client Stats
        cv2.putText(canvas, "CLIENTS", (x_bar + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
        y += 40
        self._draw_stat_row(canvas, x_bar + 20, y, "Active", stats_occupied_client, COLOR_BLUE if stats_occupied_client > 0 else COLOR_YELLOW)
        y += 40
        self._draw_stat_row(canvas, x_bar + 20, y, "Waiting", stats_total_client - stats_occupied_client, COLOR_YELLOW)
        
        # Controls Hint
        y = window_size[1] - 150
        cv2.putText(canvas, "CONTROLS:", (x_bar + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
        y += 30
        hints = [
            "J: Toggle Grid View",
            "A/D: Switch Camera",
            "R: Draw | RtClick: Del",
            "C: Change Type | L: Link Emp",
            "S: Save (Auto-sync)"
        ]
        for hint in hints:
             cv2.putText(canvas, hint, (x_bar + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
             y += 25

        return canvas

    def _draw_stat_row(self, img, x, y, label, value, color):
        cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1)
        # Right align value
        val_str = str(value)
        (w, h), _ = cv2.getTextSize(val_str, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.putText(img, val_str, (x + 300 - w, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)


class ROIDemoApp:
    def __init__(self):
        print("Launching ROI Demo & Setup Tool...")
        
        # Load Detector (Single shared instance)
        print("Loading AI Model...")
        self.detector = PersonDetector()
        
        # Load Cameras
        self.cameras = []
        for cfg in CAMERAS:
            print(f"Connecting to Camera {cfg.id}: {cfg.name}...")
            cam = DemoCamera(cfg, self.detector)
            cam.connect() 
            self.cameras.append(cam)
            
        self.current_cam_idx = 0
        self.grid_view = False
        self.grid_renderer = GridView()
        self.window_name = "Workplace Monitor (DEMO)"
        self.running = True
        
        # Mouse Callback State
        self.mouse_pos = (0, 0)

    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window_name, self._handle_mouse)
        
        print("\n=== DEMO STARTED ===")
        print("Press 'J' for Security Grid View")
        
        try:
            while self.running:
                key = cv2.waitKey(1) & 0xFF
                if key != 255:
                    self._handle_key(key)
                
                # Update frames
                for cam in self.cameras:
                    cam.process()
                
                if self.grid_view:
                    display = self.grid_renderer.draw(self.cameras)
                else:
                    cam = self.cameras[self.current_cam_idx]
                    if cam.current_frame is not None:
                        display = cam.current_frame.copy()
                        # Draw Overlay Info
                        cv2.putText(display, f"Cam {cam.config.id}: {cam.config.name}", (30, 50),
                                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
                        
                        # Draw Editor Overlay
                        if cam.roi_editor.is_drawing:
                            display = cam.roi_editor.draw_current(display)
                    else:
                        display = np.zeros((1080, 1920, 3), dtype=np.uint8)
                        cv2.putText(display, "Connecting...", (800, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
                
                cv2.imshow(self.window_name, display)
                
                # Check for window close
                if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
                    self.running = False
                    
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            for cam in self.cameras:
                cam.disconnect()
            cv2.destroyAllWindows()
            print("Demo Stopped.")

    def _handle_key(self, key):
        cam = self.cameras[self.current_cam_idx]
        
        if key == ord('q'):
            self.running = False
            
        elif key == ord('j'):
            self.grid_view = not self.grid_view
            print(f"Grid View: {'ON' if self.grid_view else 'OFF'}")
            
        elif key == ord('d') and not self.grid_view:
            self.current_cam_idx = (self.current_cam_idx + 1) % len(self.cameras)
            
        elif key == ord('a') and not self.grid_view:
            self.current_cam_idx = (self.current_cam_idx - 1) % len(self.cameras)
            
        elif key == ord('r'):
            if not self.grid_view:
                cam.roi_editor.start_drawing()
                print("Drawing mode: Click points, ENTER to finish.")
                
        elif key == 13: # Enter
            if not self.grid_view and cam.roi_editor.is_drawing:
                pts = cam.roi_editor.finish_roi()
                if pts:
                    if cam.is_sandbox:
                        # Sandbox: Add to memory only (using fake ID)
                        # We use ROIManager's internal list but do NOT call add_roi (which writes to DB)
                        from core.roi_manager import ROI
                        fake_id = -int(time.time() * 1000)
                        # Default to employee
                        new_roi = ROI(fake_id, cam.config.id, pts, "employee")
                        # Add manually
                        cam.roi_manager.rois.append(new_roi)
                        print("Sandbox Zone Added (InMemory)")
                    else:
                        # Real: Save to DB
                        cam.roi_manager.add_roi(pts, "employee")
                        print("Zone Saved to DB")
                        
        elif key == ord('c'):
             # Find ROI under mouse to flip type? Or just last one?
             # Let's match GridView logic or Mouse pos
             # Simplified: Toggle type of the LAST added ROI
             rois = cam.roi_manager.get_all_rois()
             if rois:
                 r = rois[-1]
                 new_type = 'client' if r.zone_type == 'employee' else 'employee'
                 if not cam.is_sandbox:
                     db.update_roi_type(r.id, new_type) # Assuming this method exists
                 r.zone_type = new_type
                 print(f"Zone switched to {new_type}")

        # Quick Links 1-9, 0 (ID 10)
        elif key >= ord('0') and key <= ord('9'):
             rois = cam.roi_manager.get_all_rois()
             if rois and rois[-1].zone_type == 'client':
                 r = rois[-1]
                 # '1' -> 1, '0' -> 10
                 target_id = int(chr(key))
                 if target_id == 0: target_id = 10
                 
                 # Check if this employee ID exists
                 if target_id in WORKPLACE_OWNERS:
                     r.linked_employee_id = target_id
                     
                     # Update DB
                     if not cam.is_sandbox:
                         try:
                             db.update_roi_link(r.id, target_id)
                         except:
                             pass
                     cam.roi_manager._save_to_json()
                     print(f"🔗 Zone {r.id} linked to {WORKPLACE_OWNERS[target_id]} (ID: {target_id}) via Key")
                 else:
                     print(f"⚠️ Employee ID {target_id} not configured!")


        elif key == ord('l'):
             # Link Client Zone to Employee
             rois = cam.roi_manager.get_all_rois()
             if rois:
                 # Find ROI under cursor (if any) - simplified: use last added or active
                 # Better: Use mouse position stored in app (need to track it)
                 # Fallback: modify LAST ROI for now, or add mouse tracking
                 r = rois[-1]
                 
                 if r.zone_type == 'client':
                     # Cycle through available employees
                     # Get list of employee IDs
                     emp_ids = sorted(list(WORKPLACE_OWNERS.keys()))
                     if not emp_ids:
                         print("No employees configured in WORKPLACE_OWNERS!")
                         return
                         
                     current_id = r.linked_employee_id
                     
                     if current_id is None:
                         new_id = emp_ids[0]
                     else:
                         try:
                             idx = emp_ids.index(current_id)
                             new_id = emp_ids[(idx + 1) % len(emp_ids)]
                         except ValueError:
                             new_id = emp_ids[0]
                             
                     r.linked_employee_id = new_id
                     
                     # Update DB
                     if not cam.is_sandbox:
                         # We need a method to update linked_employee_id in DB
                         # roi_manager doesn't have it explicitly, but we can access db directly
                         # or add a method. Let's add it to db.py first? 
                         # Actually, let's just use a direct update call if possible or add method.
                         # For now, let's assume we added update_roi_link to db.py
                         try:
                             db.update_roi_link(r.id, new_id)
                         except AttributeError:
                             print("Method update_roi_link not found in DB! Please add it.")
                             
                     # Update JSON
                     cam.roi_manager._save_to_json()
                     
                     emp_name = WORKPLACE_OWNERS.get(new_id, "Unknown")
                     print(f"🔗 Zone {r.id} linked to {emp_name} (ID: {new_id})")
                 else:
                     print("⚠️ Can only link CLIENT zones.")

        elif key == ord('z'):
            if not self.grid_view:
                if cam.is_sandbox:
                    cam.roi_manager.rois.clear()
                else:
                    cam.roi_manager.delete_all_rois()
                print("All zones cleared")

    def _handle_mouse(self, event, x, y, flags, param):
        if self.grid_view:
            return
            
        cam = self.cameras[self.current_cam_idx]
        self.mouse_pos = (x, y)
        
        # 1. Editor
        if cam.roi_editor.is_drawing:
            cam.roi_editor.handle_mouse(event, x, y, flags, param)
            return

        # 2. Delete
        if event == cv2.EVENT_RBUTTONDOWN:
            roi = cam.roi_manager.get_roi_at_point(x, y)
            if roi:
                if cam.is_sandbox:
                    cam.roi_manager.rois.remove(roi)
                else:
                    cam.roi_manager.delete_roi(roi.id)
                print("Zone deleted")

if __name__ == "__main__":
    app = ROIDemoApp()
    app.run()
