"""
Interactive Line Editor using OpenCV mouse events
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ROI_COLOR_DRAWING, TEXT_COLOR

class LineEditor:
    """Interactive line editor"""
    
    def __init__(self, window_name: str = "Line Editor"):
        self.window_name = window_name
        self.current_points: List[Tuple[int, int]] = []
        self.is_drawing = False
        
    def start_drawing(self):
        """Start drawing a new line"""
        self.current_points = []
        self.is_drawing = True
        print("📏 Line Drawing mode: Click 2 points, press ENTER to finish")
    
    def stop_drawing(self):
        self.is_drawing = False
        self.current_points = []
    
    def add_point(self, x: int, y: int):
        if self.is_drawing:
            if len(self.current_points) < 2:
                self.current_points.append((x, y))
                print(f"   Point {len(self.current_points)}: ({x}, {y})")
    
    def finish_line(self) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        if len(self.current_points) >= 2:
            pts = (self.current_points[0], self.current_points[1])
            self.current_points = []
            self.is_drawing = False
            return pts
        else:
            print("⚠️ Need exactly 2 points for a line")
            return None
    
    def cancel_drawing(self):
        self.current_points = []
        self.is_drawing = False
        print("❌ Line drawing cancelled")
    
    def draw_current(self, frame: np.ndarray, mouse_x: int = -1, mouse_y: int = -1) -> np.ndarray:
        if not self.is_drawing:
            return frame
        
        # Draw points
        for i, pt in enumerate(self.current_points):
            cv2.circle(frame, pt, 5, ROI_COLOR_DRAWING, -1)
            cv2.putText(
                frame, str(i + 1), (pt[0] + 10, pt[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1
            )
        
        # Draw line segment
        if len(self.current_points) == 1 and mouse_x >= 0 and mouse_y >= 0:
            cv2.line(frame, self.current_points[0], (mouse_x, mouse_y), ROI_COLOR_DRAWING, 2)
        elif len(self.current_points) == 2:
            cv2.line(frame, self.current_points[0], self.current_points[1], ROI_COLOR_DRAWING, 2)
        
        cv2.putText(
            frame, f"Drawing Line: {len(self.current_points)}/2 points (ENTER to finish)",
            (10, frame.shape[0] - 50),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 2
        )
        return frame
    
    def handle_mouse(self, event: int, x: int, y: int, flags: int, param):
        if event == cv2.EVENT_LBUTTONDOWN and self.is_drawing:
            self.add_point(x, y)
