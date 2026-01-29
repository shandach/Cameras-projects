"""
Interactive ROI Editor using OpenCV mouse events
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ROI_COLOR_DRAWING, TEXT_COLOR


class ROIEditor:
    """Interactive polygon ROI editor"""
    
    def __init__(self, window_name: str = "ROI Editor"):
        self.window_name = window_name
        self.current_points: List[Tuple[int, int]] = []
        self.is_drawing = False
        self.on_roi_complete: Optional[Callable] = None
        
    def start_drawing(self):
        """Start drawing a new ROI"""
        self.current_points = []
        self.is_drawing = True
        print("🎨 ROI Drawing mode: Click to add points, press ENTER to finish")
    
    def stop_drawing(self):
        """Stop drawing mode"""
        self.is_drawing = False
        self.current_points = []
    
    def add_point(self, x: int, y: int):
        """Add a point to current polygon"""
        if self.is_drawing:
            self.current_points.append((x, y))
            print(f"   Point {len(self.current_points)}: ({x}, {y})")
    
    def finish_roi(self) -> Optional[List[Tuple[int, int]]]:
        """
        Finish current ROI drawing
        
        Returns:
            List of points if valid ROI (4+ points), None otherwise
        """
        if len(self.current_points) >= 4:
            points = self.current_points.copy()
            self.current_points = []
            self.is_drawing = False
            return points
        else:
            print("⚠️ Need at least 4 points for a valid ROI")
            return None
    
    def cancel_drawing(self):
        """Cancel current drawing"""
        self.current_points = []
        self.is_drawing = False
        print("❌ ROI drawing cancelled")
    
    def draw_current(self, frame: np.ndarray) -> np.ndarray:
        """
        Draw current polygon being created
        
        Args:
            frame: BGR image
        
        Returns:
            Frame with current polygon drawn
        """
        if not self.current_points:
            return frame
        
        pts = np.array(self.current_points, dtype=np.int32)
        
        # Draw lines between points
        for i in range(len(self.current_points) - 1):
            cv2.line(
                frame, 
                self.current_points[i], 
                self.current_points[i + 1],
                ROI_COLOR_DRAWING, 2
            )
        
        # Draw points
        for i, pt in enumerate(self.current_points):
            cv2.circle(frame, pt, 5, ROI_COLOR_DRAWING, -1)
            cv2.putText(
                frame, str(i + 1), (pt[0] + 10, pt[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1
            )
        
        # Draw polygon preview if 3+ points
        if len(self.current_points) >= 3:
            cv2.polylines(frame, [pts], True, ROI_COLOR_DRAWING, 1)
        
        # Draw instruction
        if self.is_drawing:
            cv2.putText(
                frame, f"Drawing ROI: {len(self.current_points)} points (ENTER to finish, ESC to cancel)",
                (10, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 2
            )
        
        return frame
    
    def handle_mouse(self, event: int, x: int, y: int, flags: int, param):
        """OpenCV mouse callback handler"""
        if event == cv2.EVENT_LBUTTONDOWN and self.is_drawing:
            self.add_point(x, y)


def create_mouse_callback(editor: ROIEditor):
    """Create mouse callback for OpenCV window"""
    def callback(event, x, y, flags, param):
        editor.handle_mouse(event, x, y, flags, param)
    return callback
