"""
ROI (Region of Interest) Manager
Manages workplace zones for a specific camera
Fixed sequential numbering with gap-filling.
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
    points: List[Tuple[int, int]]
    status: str = "VACANT"
    zone_type: str = "employee"       # "employee" or "client"
    employee_id: int = None           # Employee assigned to this zone
    linked_employee_id: int = None    # For client zones: which employee gets credit

    def contains_point(self, point: Tuple[int, int]) -> bool:
        """Check if a point is inside the polygon"""
        if len(self.points) < 3:
            return False
        
        pts = np.array(self.points, dtype=np.int32)
        result = cv2.pointPolygonTest(pts, point, False)
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
            
            print(f"📄 Camera {self.camera_id}: Loaded {len(self.rois)} ROIs from {self.json_path}")
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
        except Exception as e:
            print(f"⚠️ Failed to save JSON: {e}")

    def _sync_json_to_db(self):
        """
        Ensure all loaded ROIs exist in DB with MATCHING IDs and data.
        INSERTs missing zones, UPDATEs existing zones if data differs.
        """
        existing_places = db.get_places_for_camera(self.camera_id)
        existing_map = {p['id']: p for p in existing_places}
        
        for roi in list(self.rois.values()):
            if roi.id not in existing_map:
                # INSERT: zone not in DB
                print(f"🔄 Syncing ROI '{roi.name}' (ID:{roi.id}) to DB...")
                try:
                    db.save_place_with_id(
                        place_id=roi.id,
                        camera_id=self.camera_id,
                        name=roi.name,
                        roi_coordinates=roi.points,
                        zone_type=roi.zone_type,
                        linked_employee_id=roi.linked_employee_id,
                        employee_id=roi.employee_id
                    )
                    print(f"   ✅ Synced '{roi.name}' with ID {roi.id}")
                except Exception as e:
                    print(f"   ⚠️ Sync failed for {roi.name}: {e}")
            else:
                # UPDATE: zone exists — check if data changed
                db_place = existing_map[roi.id]
                needs_update = (
                    roi.name != db_place.get('name') or
                    roi.zone_type != db_place.get('zone_type', 'employee') or
                    roi.linked_employee_id != db_place.get('linked_employee_id') or
                    roi.employee_id != db_place.get('employee_id') or
                    roi.points != [tuple(p) for p in db_place.get('roi_coordinates', [])]
                )
                if needs_update:
                    try:
                        db.update_place(
                            place_id=roi.id,
                            name=roi.name,
                            roi_coordinates=roi.points,
                            zone_type=roi.zone_type,
                            linked_employee_id=roi.linked_employee_id,
                            employee_id=roi.employee_id
                        )
                        print(f"   🔄 Updated '{roi.name}' (ID:{roi.id}) in DB")
                    except Exception as e:
                        print(f"   ⚠️ Update failed for {roi.name}: {e}")

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
                print(f"🗄️ Camera {self.camera_id}: Loaded {len(self.rois)} ROI zones from DB")
        except Exception as e:
            print(f"⚠️ Camera {self.camera_id}: Failed to load ROIs from DB: {e}")
    
    def add_roi(self, points: List[Tuple[int, int]], name: str = None, 
                zone_type: str = "employee", linked_employee_id: int = None) -> ROI:
        """Add a new ROI zone to MEMORY only (not saved until Q is pressed).
        Uses fixed sequential ID with gap-filling.
        """
        # Get next available ID considering both DB and memory
        roi_id = self._get_next_available_id()
        
        if name is None:
            name = f"Зона #{roi_id}"
        
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
        print(f"📝 Camera {self.camera_id}: Added '{roi.name}' (ID:{roi_id}, {zone_label}) [IN MEMORY]")
        return roi
    
    def _get_next_available_id(self) -> int:
        """Get next available ID considering both DB and memory zones"""
        # Get all existing IDs from DB (single query)
        all_db_places = db.get_all_places()
        db_ids = {p['id'] for p in all_db_places}
        
        # Merge with memory IDs
        all_ids = db_ids | set(self.rois.keys())
        
        if not all_ids:
            return 1
        
        # Find first gap starting from 1
        for candidate in range(1, max(all_ids) + 2):
            if candidate not in all_ids:
                return candidate
    
    def save_all_to_storage(self):
        """Save ALL current memory zones to DB and JSON.
        Called when user presses Q to confirm zones.
        INSERTs new zones, UPDATEs existing zones if data changed.
        """
        saved_count = 0
        updated_count = 0
        
        # Get existing DB state for this camera
        existing_places = db.get_places_for_camera(self.camera_id)
        existing_map = {p['id']: p for p in existing_places}
        
        for roi in self.rois.values():
            if roi.id not in existing_map:
                # INSERT new zone
                try:
                    db.save_place_with_id(
                        place_id=roi.id,
                        camera_id=self.camera_id,
                        name=roi.name,
                        roi_coordinates=roi.points,
                        zone_type=roi.zone_type,
                        linked_employee_id=roi.linked_employee_id,
                        employee_id=roi.employee_id
                    )
                    saved_count += 1
                except Exception as e:
                    print(f"⚠️ Failed to save zone #{roi.id}: {e}")
            else:
                # UPDATE existing zone if data changed
                db_place = existing_map[roi.id]
                needs_update = (
                    roi.name != db_place.get('name') or
                    roi.zone_type != db_place.get('zone_type', 'employee') or
                    roi.linked_employee_id != db_place.get('linked_employee_id') or
                    roi.employee_id != db_place.get('employee_id') or
                    roi.points != [tuple(p) for p in db_place.get('roi_coordinates', [])]
                )
                if needs_update:
                    try:
                        db.update_place(
                            place_id=roi.id,
                            name=roi.name,
                            roi_coordinates=roi.points,
                            zone_type=roi.zone_type,
                            linked_employee_id=roi.linked_employee_id,
                            employee_id=roi.employee_id
                        )
                        updated_count += 1
                    except Exception as e:
                        print(f"⚠️ Failed to update zone #{roi.id}: {e}")
        
        # Save to JSON
        self._save_to_json()
        
        if saved_count > 0 or updated_count > 0:
            print(f"💾 Camera {self.camera_id}: {saved_count} new + {updated_count} updated zones → DB + JSON")
        
        return saved_count + updated_count
    
    def delete_roi(self, roi_id: int) -> bool:
        """Delete ROI by ID (keeps historical data in sessions/visits)"""
        if roi_id in self.rois:
            # Delete from DB
            db.delete_place(roi_id)
            # Delete from Memory
            del self.rois[roi_id]
            # Update JSON
            self._save_to_json()
            
            print(f"🗑️ Camera {self.camera_id}: Deleted ROI #{roi_id}")
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
        Draw ROI zones on frame with zone numbers and linkage info
        """
        overlay = frame.copy()
        
        # Collect all ROI centers for drawing link lines
        roi_centers = {}
        
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
            
            # Calculate centroid
            M = cv2.moments(pts)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
            else:
                cx, cy = pts[0][0], pts[0][1]
            
            roi_centers[roi.id] = (cx, cy)
            
            # --- Zone Label ---
            if roi.zone_type == "client":
                if roi.linked_employee_id:
                    label = f"Client #{roi.id} -> Zone #{roi.linked_employee_id}"
                else:
                    label = f"Client #{roi.id} (no link)"
            else:
                label = f"Zone #{roi.id}"
            
            # Draw label with background
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            label_x = cx - tw // 2
            label_y = cy - 10
            cv2.rectangle(frame, (label_x - 3, label_y - th - 3), 
                         (label_x + tw + 3, label_y + 3), (0, 0, 0), -1)
            cv2.putText(frame, label, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Draw status below label
            cv2.putText(frame, roi.status, (cx - 35, cy + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
        # --- Draw Connection Lines ---
        for roi in self.rois.values():
            if roi.zone_type == "client" and roi.linked_employee_id:
                # Find the linked employee zone
                linked_id = roi.linked_employee_id
                if roi.id in roi_centers and linked_id in roi_centers:
                    pt1 = roi_centers[roi.id]
                    pt2 = roi_centers[linked_id]
                    # Draw dashed line (approximated with dotted segments)
                    self._draw_dashed_line(frame, pt1, pt2, (0, 200, 255), 2, 10)
                    # Draw arrow head
                    self._draw_arrowhead(frame, pt1, pt2, (0, 200, 255))
        
        # Blend overlay
        alpha = 0.3
        frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
        
        return frame
    
    @staticmethod
    def _draw_dashed_line(frame, pt1, pt2, color, thickness, dash_len):
        """Draw a dashed line between two points"""
        x1, y1 = pt1
        x2, y2 = pt2
        dist = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        if dist == 0:
            return
        dx = (x2 - x1) / dist
        dy = (y2 - y1) / dist
        
        num_dashes = int(dist / (dash_len * 2))
        for i in range(num_dashes + 1):
            start_d = i * dash_len * 2
            end_d = min(start_d + dash_len, dist)
            sx = int(x1 + dx * start_d)
            sy = int(y1 + dy * start_d)
            ex = int(x1 + dx * end_d)
            ey = int(y1 + dy * end_d)
            cv2.line(frame, (sx, sy), (ex, ey), color, thickness)
    
    @staticmethod
    def _draw_arrowhead(frame, pt1, pt2, color, size=15):
        """Draw arrowhead at pt2 pointing from pt1"""
        x1, y1 = pt1
        x2, y2 = pt2
        angle = np.arctan2(y2 - y1, x2 - x1)
        
        p1 = (int(x2 - size * np.cos(angle - np.pi/6)),
              int(y2 - size * np.sin(angle - np.pi/6)))
        p2 = (int(x2 - size * np.cos(angle + np.pi/6)),
              int(y2 - size * np.sin(angle + np.pi/6)))
        
        cv2.fillPoly(frame, [np.array([pt2, p1, p2])], color)

    def import_predefined_rois(self, predefined_rois: list, ref_res: tuple, 
                                frame_res: tuple, employee_ids: list = None) -> int:
        """
        Import pre-defined ROI zones from config, scaling coordinates.
        Skips if ROIs already exist for this camera.
        Uses fixed sequential IDs.
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
            
            # Use fixed ID system
            roi_id = self._get_next_available_id()
            name = f"Зона #{roi_id}"
            
            try:
                db.save_place_with_id(
                    place_id=roi_id,
                    camera_id=self.camera_id,
                    name=name,
                    roi_coordinates=list(scaled_points),
                    zone_type="employee",
                    employee_id=emp_id
                )
                
                roi = ROI(
                    id=roi_id,
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
            self._save_to_json()
        
        return imported

    def get_roi_at_point(self, x: int, y: int) -> Optional[ROI]:
        """Get ROI containing the point (x, y)"""
        # Check in reverse order (topmost first)
        for roi in sorted(self.rois.values(), key=lambda r: r.id, reverse=True):
            if roi.contains_point((x, y)):
                return roi
        return None
