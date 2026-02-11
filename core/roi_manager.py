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
        Initialize ROI manager for a specific camera.
        Prioritizes loading from 'rois.json' for portability.
        """
        self.camera_id = camera_id
        self.rois: Dict[int, ROI] = {}
        self.json_path = "rois.json"
        
        # 1. Try to load from JSON (Primary Source)
        loaded_from_json = self._load_from_json()
        
        # 2. If JSON is empty or missing for this camera, try DB (Fallback)
        if not loaded_from_json:
            print(f"📂 Camera {self.camera_id}: No ROIs in JSON, checking DB...")
            self._load_from_db()
            # If we found something in DB, save it to JSON for next time
            if self.rois:
                self._save_to_json()
        
        # 3. Sync JSON to DB (Ensure DB matches JSON for tracking)
        # This handles the case where we moved JSON to a new PC with empty DB
        self._sync_json_to_db()

    def _load_from_json(self) -> bool:
        """Load ROIs from JSON file"""
        import json
        import os
        
        if not os.path.exists(self.json_path):
            return False
            
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cam_key = str(self.camera_id)
            if cam_key not in data or not data[cam_key]:
                return False
                
            for item in data[cam_key]:
                roi = ROI(
                    id=item["id"],
                    camera_id=self.camera_id,
                    name=item["name"],
                    points=[tuple(p) for p in item["points"]],
                    status="VACANT",
                    zone_type=item.get("zone_type", "employee"),
                    employee_id=item.get("employee_id"),
                    linked_employee_id=item.get("linked_employee_id")
                )
                self.rois[roi.id] = roi
            
            print(f"� Camera {self.camera_id}: Loaded {len(self.rois)} ROIs from {self.json_path}")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to load from JSON: {e}")
            return False

    def _save_to_json(self):
        """Save all ROIs to JSON (Preserving other cameras)"""
        import json
        import os
        
        # Load existing data to preserve other cameras
        data = {}
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        
        # Update THIS camera's data
        cam_key = str(self.camera_id)
        data[cam_key] = []
        
        for roi in self.rois.values():
            data[cam_key].append({
                "id": roi.id,
                "name": roi.name,
                "points": roi.points,
                "zone_type": roi.zone_type,
                "employee_id": roi.employee_id,
                "linked_employee_id": roi.linked_employee_id
            })
            
        # Write back
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            # print(f"💾 ROIs saved to {self.json_path}")
        except Exception as e:
            print(f"⚠️ Failed to save JSON: {e}")

    def _sync_json_to_db(self):
        """
        Ensure all loaded ROIs exist in DB.
        Useful when migrating to a clean DB/PostgreSQL using only rois.json.
        """
        # Get existing IDs in DB to avoid duplicates
        existing_places = db.get_places_for_camera(self.camera_id)
        existing_ids = {p['id'] for p in existing_places}
        
        for roi in self.rois.values():
            if roi.id not in existing_ids:
                print(f"🔄 Syncing ROI '{roi.name}' to DB...")
                # We force the ID to match JSON ID to keep consistency
                # Note: This assumes DB ID strategy allows manual ID or we rely on name matching
                # For SQLite autoincrement, we usually let DB assign ID. 
                # BUT for portability, if we want to keep relations, we might need to be careful.
                # Here we just re-create the place.
                try:
                    # Check if ID exists (handled by set above), if not create
                    # If ID collision is possible on new DB, handled by DB logic usually
                    # Ideally we'd use UUIDs, but here lets trust the JSON ID if possible or let DB re-assign
                    # To be safe and simple: Let's re-save using db.save_place which might create NEW ID
                    # If we truly want to restore, we should probably update the ID in JSON to match new DB ID?
                    # Or just insert.
                    
                    # Implementation detail: db.save_place creates new if not exists
                    # We will use save_place logic.
                    # Warning: This might create duplicates if we strictly rely on ID.
                    # Let's check by NAME + Config to simulate "Restoring"
                    pass 
                    # Actually, simply saving it is enough for now.
                    # If it's not in DB, we add it. 
                    # Wait, if we add it, DB gives new ID. We must update current ROI object with new ID?
                    # No, keep JSON ID for now? 
                    # Better approach: If JSON has ID 5, and DB is empty. 
                    # We insert. DB gives ID 1. 
                    # Tracking data refers to ID 5... mismatch.
                    # Ideally, when migrating, we migrate EVERYTHING including historical data.
                    # For just ROIs:
                    # Let's assume on migration we start fresh.
                    # So we push to DB, get new ID, update our runtime object.
                    
                    new_place = db.save_place(
                        camera_id=self.camera_id,
                        name=roi.name,
                        roi_coordinates=roi.points,
                        zone_type=roi.zone_type,
                        linked_employee_id=roi.linked_employee_id,
                        employee_id=roi.employee_id
                    )
                    # Update ROI ID to match global DB ID
                    if new_place.id != roi.id:
                        print(f"   ⚠️ ID changed from {roi.id} to {new_place.id} during sync")
                        # This invalidates the old ID in JSON, but ensures DB consistency
                        # We should probably update the key in self.rois
                        del self.rois[roi.id]
                        roi.id = new_place.id
                        self.rois[roi.id] = roi
                        # And Trigger a JSON save at the end to reflect new IDs
                        self.must_save_json = True
                        
                except Exception as e:
                    print(f"⚠️ Sync failed for {roi.name}: {e}")
        
        if getattr(self, "must_save_json", False):
             self._save_to_json()


    def _load_from_db(self):
        """Load ROIs from database (Fallback)"""
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
            
            if self.rois:
                print(f"database Camera {self.camera_id}: Loaded {len(self.rois)} ROI zones from DB")
        except Exception as e:
            print(f"⚠️ Camera {self.camera_id}: Failed to load ROIs from DB: {e}")
    
    def add_roi(self, points: List[Tuple[int, int]], name: str = None, 
                zone_type: str = "employee", linked_employee_id: int = None) -> ROI:
        """Add a new ROI zone"""
        place_count = len(self.rois) + 1
        if name is None:
            name = f"Client {place_count}" if zone_type == "client" else f"Place {place_count}"
        
        # 1. Save to DB first to get a valid ID
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
            roi_id = place_count # Fallback ID if DB fails
        
        roi = ROI(
            id=roi_id, 
            camera_id=self.camera_id,
            name=name, 
            points=list(points),
            zone_type=zone_type,
            linked_employee_id=linked_employee_id
        )
        self.rois[roi_id] = roi
        
        # 2. Save to JSON
        self._save_to_json()
        
        zone_label = "employee" if zone_type == "employee" else f"client→emp#{linked_employee_id}"
        print(f"✅ Camera {self.camera_id}: Added ROI '{roi.name}' ({zone_label})")
        return roi
    
    def delete_roi(self, roi_id: int) -> bool:
        """Delete ROI by ID"""
        if roi_id in self.rois:
            # Delete from DB
            db.delete_place(roi_id)
            # Delete from Memory
            del self.rois[roi_id]
            # Update JSON
            self._save_to_json()
            
            print(f"🗑️ Camera {self.camera_id}: Deleted ROI {roi_id}")
            return True
        return False
    
    def delete_all_rois(self) -> int:
        """Delete all ROIs for this camera"""
        count = db.delete_places_for_camera(self.camera_id)
        self.rois.clear()
        self._save_to_json()
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
            
            # Calculate centroid for status label
            M = cv2.moments(pts)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                cx, cy = pts[0][0], pts[0][1]
            
            # Draw status at center of zone (no name - stats panel shows it)
            cv2.putText(
                frame, roi.status, (cx - 40, cy + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
            )
        
        # Blend overlay
        alpha = 0.3
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        
        return frame
    
    def import_predefined_rois(self, predefined_rois: list, ref_res: tuple, 
                                frame_res: tuple, employee_ids: list = None) -> int:
        """
        Import pre-defined ROI zones from config, scaling coordinates.
        Skips if ROIs already exist for this camera.
        
        Args:
            predefined_rois: List of polygon coordinate lists [[(x,y), ...], ...]
            ref_res: Reference resolution (width, height) from config
            frame_res: Actual frame resolution (width, height)
            employee_ids: Optional list of employee IDs to assign to each ROI
            
        Returns:
            Number of ROIs imported
        """
        # Skip if ROIs already exist
        if len(self.rois) > 0:
            return 0
        
        if not predefined_rois:
            return 0
        
        # Calculate scale factors
        scale_x = frame_res[0] / ref_res[0]
        scale_y = frame_res[1] / ref_res[1]
        
        imported = 0
        for i, roi_points in enumerate(predefined_rois):
            # Scale coordinates
            scaled_points = [
                (int(x * scale_x), int(y * scale_y)) 
                for x, y in roi_points
            ]
            
            # Assign employee if available
            emp_id = employee_ids[i] if employee_ids and i < len(employee_ids) else None
            
            name = f"Место {i + 1}"
            
            # Save to database
            try:
                place = db.save_place(
                    camera_id=self.camera_id,
                    name=name,
                    roi_coordinates=list(scaled_points),
                    zone_type="employee",
                    employee_id=emp_id
                )
                
                roi = ROI(
                    id=place.id,
                    camera_id=self.camera_id,
                    name=name,
                    points=list(scaled_points),
                    zone_type="employee",
                    employee_id=emp_id
                )
                self.rois[roi.id] = roi
                imported += 1
            except Exception as e:
                print(f"⚠️ Failed to import ROI {i+1}: {e}")
        
        if imported:
            print(f"📍 Camera {self.camera_id}: Imported {imported} predefined ROIs")
            self._save_to_json()  # Backup after import
        
        return imported
