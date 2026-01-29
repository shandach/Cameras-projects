"""
ROI (Region of Interest) Manager
Manages workplace zones and checks person presence
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import db


@dataclass
class ROI:
    """Region of Interest (workplace zone)"""
    id: int
    name: str
    points: List[Tuple[int, int]]  # Polygon points
    status: str = "VACANT"
    
    def contains_point(self, point: Tuple[int, int]) -> bool:
        """Check if a point is inside the polygon"""
        if len(self.points) < 3:
            return False
        
        # Convert points to proper format for cv2.pointPolygonTest
        # pts must be numpy array with shape (N, 1, 2) or (N, 2)
        pts = np.array(self.points, dtype=np.int32).reshape((-1, 1, 2))
        
        # point must be a tuple of floats
        point_float = (float(point[0]), float(point[1]))
        
        result = cv2.pointPolygonTest(pts, point_float, False)
        return result >= 0  # >= 0 means inside or on edge
    
    def get_polygon_array(self) -> np.ndarray:
        """Get polygon as numpy array for drawing"""
        return np.array(self.points, dtype=np.int32)


class ROIManager:
    """Manages multiple ROI zones"""
    
    def __init__(self):
        self.rois: Dict[int, ROI] = {}
        self.next_id = 1
        self._load_from_db()
    
    def _load_from_db(self):
        """Load ROIs from database"""
        try:
            places = db.get_all_places()
            for place in places:
                roi = ROI(
                    id=place["id"],
                    name=place["name"],
                    points=[tuple(p) for p in place["roi_coordinates"]],
                    status=place.get("status", "VACANT")
                )
                self.rois[roi.id] = roi
                self.next_id = max(self.next_id, roi.id + 1)
            
            print(f"📍 Loaded {len(self.rois)} ROI zones from database")
        except Exception as e:
            print(f"⚠️ Failed to load ROIs from database: {e}")
    
    def add_roi(self, points: List[Tuple[int, int]], name: str = None) -> ROI:
        """
        Add a new ROI zone
        
        Args:
            points: List of (x, y) polygon points
            name: Optional name, defaults to "Место N"
        
        Returns:
            Created ROI object
        """
        if name is None:
            name = f"Место {self.next_id}"
        
        # Save to database
        try:
            place = db.save_place(name=name, roi_coordinates=list(points))
            roi_id = place.id
        except Exception as e:
            print(f"⚠️ Failed to save ROI to database: {e}")
            roi_id = self.next_id
            self.next_id += 1
        
        roi = ROI(id=roi_id, name=name, points=list(points))
        self.rois[roi_id] = roi
        
        print(f"✅ Added ROI: {roi.name} with {len(points)} points")
        return roi
    
    def delete_roi(self, roi_id: int) -> bool:
        """Delete ROI by ID"""
        if roi_id in self.rois:
            db.delete_place(roi_id)
            del self.rois[roi_id]
            print(f"🗑️ Deleted ROI {roi_id}")
            return True
        return False
    
    def get_roi(self, roi_id: int) -> Optional[ROI]:
        """Get ROI by ID"""
        return self.rois.get(roi_id)
    
    def get_all_rois(self) -> List[ROI]:
        """Get all ROIs"""
        return list(self.rois.values())
    
    def check_presence(self, person_centers: List[Tuple[int, int]]) -> Dict[int, bool]:
        """
        Check which ROIs have a person present
        
        Args:
            person_centers: List of (x, y) center points of detected persons
        
        Returns:
            Dict mapping ROI ID to presence bool
        """
        presence = {}
        
        for roi_id, roi in self.rois.items():
            is_occupied = False
            for center in person_centers:
                if roi.contains_point(center):
                    is_occupied = True
                    break
            presence[roi_id] = is_occupied
        
        return presence
    
    def update_status(self, roi_id: int, status: str):
        """Update ROI status"""
        if roi_id in self.rois:
            self.rois[roi_id].status = status
    
    def draw_rois(self, frame: np.ndarray, 
                  occupied_color: Tuple[int, int, int] = (0, 0, 255),
                  vacant_color: Tuple[int, int, int] = (0, 255, 0)) -> np.ndarray:
        """
        Draw ROI zones on frame
        
        Args:
            frame: BGR image
            occupied_color: Color for occupied zones (BGR)
            vacant_color: Color for vacant zones (BGR)
        
        Returns:
            Frame with drawn ROIs
        """
        overlay = frame.copy()
        
        for roi in self.rois.values():
            pts = roi.get_polygon_array()
            
            # Choose color based on status
            if roi.status == "OCCUPIED":
                color = occupied_color
            else:
                color = vacant_color
            
            # Draw filled polygon with transparency
            cv2.fillPoly(overlay, [pts], color)
            
            # Draw polygon outline
            cv2.polylines(frame, [pts], True, color, 2)
            
            # Calculate centroid for label
            M = cv2.moments(pts)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                cx, cy = pts[0][0], pts[0][1]
            
            # Draw name and status
            label = f"{roi.name}"
            cv2.putText(
                frame, label, (cx - 40, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
            cv2.putText(
                frame, roi.status, (cx - 40, cy + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
            )
        
        # Blend overlay
        alpha = 0.3
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        
        return frame


if __name__ == "__main__":
    # Test ROI Manager
    print("Testing ROIManager...")
    
    manager = ROIManager()
    
    # Add test ROI
    test_points = [(100, 100), (300, 100), (300, 300), (100, 300)]
    roi = manager.add_roi(test_points, "Test Zone")
    
    # Test contains point
    print(f"Point (200, 200) in zone: {roi.contains_point((200, 200))}")  # True
    print(f"Point (400, 400) in zone: {roi.contains_point((400, 400))}")  # False
    
    # Test presence check
    presence = manager.check_presence([(200, 200)])
    print(f"Presence check: {presence}")
    
    print("ROIManager test complete")
