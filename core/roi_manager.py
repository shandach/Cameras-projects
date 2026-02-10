"""
ROI (Region of Interest) Manager
Manages workplace zones for a specific camera
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
    camera_id: int
    name: str
    points: List[Tuple[int, int]]  # Polygon points
    status: str = "VACANT"
    zone_type: str = "employee"  # "employee" or "client"
    employee_id: int = None  # For employee zones
    linked_employee_id: int = None  # For client zones: which employee gets credit
    
    def contains_point(self, point: Tuple[int, int]) -> bool:
        """Check if a point is inside the polygon"""
        if len(self.points) < 3:
            return False
        
        # Convert points to proper format for cv2.pointPolygonTest
        pts = np.array(self.points, dtype=np.int32).reshape((-1, 1, 2))
        
        # point must be a tuple of floats
        point_float = (float(point[0]), float(point[1]))
        
        result = cv2.pointPolygonTest(pts, point_float, False)
        return result >= 0
    
    def get_polygon_array(self) -> np.ndarray:
        """Get polygon as numpy array for drawing"""
        return np.array(self.points, dtype=np.int32)


class ROIManager:
    """Manages ROI zones for a specific camera"""
    
    def __init__(self, camera_id: int):
        """
        Initialize ROI manager for a specific camera
        
        Args:
            camera_id: Database ID of the camera
        """
        self.camera_id = camera_id
        self.rois: Dict[int, ROI] = {}
        self._load_from_db()
    
    def _load_from_db(self):
        """Load ROIs from database for this camera"""
        try:
            places = db.get_places_for_camera(self.camera_id)
            for place in places:
                roi = ROI(
                    id=place["id"],
                    camera_id=place["camera_id"],
                    name=place["name"],
                    points=[tuple(p) for p in place["roi_coordinates"]],
                    status=place.get("status", "VACANT"),
                    zone_type=place.get("zone_type", "employee"),
                    employee_id=place.get("employee_id"),
                    linked_employee_id=place.get("linked_employee_id")
                )
                self.rois[roi.id] = roi
            
            print(f"📍 Camera {self.camera_id}: Loaded {len(self.rois)} ROI zones")
        except Exception as e:
            print(f"⚠️ Camera {self.camera_id}: Failed to load ROIs: {e}")
    
    def add_roi(self, points: List[Tuple[int, int]], name: str = None, 
                zone_type: str = "employee", linked_employee_id: int = None) -> ROI:
        """
        Add a new ROI zone for this camera
        
        Args:
            points: List of (x, y) polygon points
            name: Optional name, defaults to "Место N" or "Клиент N"
            zone_type: "employee" or "client"
            linked_employee_id: For client zones, which employee gets credit
        """
        place_count = len(self.rois) + 1
        if name is None:
            if zone_type == "client":
                name = f"Клиент {place_count}"
            else:
                name = f"Место {place_count}"
        
        # Save to database
        try:
            place = db.save_place(
                camera_id=self.camera_id,
                name=name, 
                roi_coordinates=list(points),
                zone_type=zone_type,
                linked_employee_id=linked_employee_id
            )
            roi_id = place.id
        except Exception as e:
            print(f"⚠️ Failed to save ROI to database: {e}")
            roi_id = place_count
        
        roi = ROI(
            id=roi_id, 
            camera_id=self.camera_id,
            name=name, 
            points=list(points),
            zone_type=zone_type,
            linked_employee_id=linked_employee_id
        )
        self.rois[roi_id] = roi
        
        zone_label = "employee" if zone_type == "employee" else f"client→emp#{linked_employee_id}"
        print(f"✅ Camera {self.camera_id}: Added ROI '{roi.name}' ({zone_label}) with {len(points)} points")
        return roi
    
    def delete_roi(self, roi_id: int) -> bool:
        """Delete ROI by ID"""
        if roi_id in self.rois:
            db.delete_place(roi_id)
            del self.rois[roi_id]
            print(f"🗑️ Camera {self.camera_id}: Deleted ROI {roi_id}")
            return True
        return False
    
    def delete_all_rois(self) -> int:
        """Delete all ROIs for this camera"""
        count = db.delete_places_for_camera(self.camera_id)
        self.rois.clear()
        print(f"🗑️ Camera {self.camera_id}: Deleted {count} ROIs")
        return count
    
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
        Draw ROI zones on frame with different colors for employee/client zones
        """
        overlay = frame.copy()
        
        for roi in self.rois.values():
            pts = roi.get_polygon_array()
            
            # Choose color based on zone_type and status
            if roi.zone_type == "client":
                # Client zones: Yellow (occupied) / Cyan (vacant)
                if roi.status == "OCCUPIED":
                    color = (0, 255, 255)  # Yellow
                else:
                    color = (255, 255, 0)  # Cyan
            else:
                # Employee zones: Red (occupied) / Green (vacant)
                if roi.status == "OCCUPIED":
                    color = occupied_color  # Red
                else:
                    color = vacant_color  # Green
            
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
            
            # Draw name with zone type indicator
            zone_prefix = "👥" if roi.zone_type == "client" else "👤"
            label = f"{zone_prefix} {roi.name}"
            cv2.putText(
                frame, label, (cx - 50, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
            
            # Draw status for employee zones only
            if roi.zone_type == "employee":
                cv2.putText(
                    frame, roi.status, (cx - 40, cy + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
                )
        
        # Blend overlay
        alpha = 0.3
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        
        return frame
