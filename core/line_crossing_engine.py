"""
Line Crossing Engine — Stable-side history-based people counting
Adapted for `workplace-monitoring`.

Since `PersonDetector` in this project doesn't have a built-in tracker (like ByteTrack),
this engine includes a lightweight Euclidean distance tracker to assign consistent `track_id`s
to detections across frames, allowing the stable-side logic to work.
"""
import time
import logging
from collections import deque, defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple, List, Optional
from datetime import datetime
import math
import cv2

# Logging setup
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("line_crossing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_DIR / "crossing_events.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)


class LineCrossingEngine:
    """
    Counts people crossing a line in a specified direction.
    Includes a simple centroid tracker to assign IDs to YOLOv10s detections.
    """

    DEFAULT_HISTORY_SIZE = 7       
    DEFAULT_COOLDOWN_SEC = 1.5     
    DEFAULT_LINE_TOLERANCE = 5.0   
    DEFAULT_TRACKING_MAX_DIST = 100.0  # max pixels to link detection to track
    DEFAULT_TRACKING_ANCHOR = 'bottom' # 'center' or 'bottom'

    def __init__(self, camera_id: str, line_start: Tuple[int, int], line_end: Tuple[int, int],
                 direction: str = 'down',
                 history_size: int = None,
                 cooldown_seconds: float = None,
                 line_tolerance: float = None,
                 tracking_anchor: str = None):
        
        self.camera_id = camera_id
        self.line_start = line_start
        self.line_end = line_end
        self.direction = direction

        # Configs
        self.history_size = history_size or self.DEFAULT_HISTORY_SIZE
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else self.DEFAULT_COOLDOWN_SEC
        self.line_tolerance = line_tolerance if line_tolerance is not None else self.DEFAULT_LINE_TOLERANCE
        self.tracking_anchor_type = tracking_anchor or self.DEFAULT_TRACKING_ANCHOR

        # Line math
        self.lx = float(line_end[0] - line_start[0])
        self.ly = float(line_end[1] - line_start[1])
        self._in_from, self._in_to = self._compute_in_sides()

        # Engine State
        self.side_history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=self.history_size))
        self.last_count_time_per_id: Dict[int, float] = {}
        self.counted_ids: Set[int] = set()
        self.total_count: int = 0

        # Built-in lightweight tracker state
        self.next_track_id = 0
        # mapping track_id -> (last_x, last_y)
        self.tracked_objects: Dict[int, Tuple[int, int]] = {} 
        # mapping track_id -> frames since last seen
        self.track_ages: Dict[int, int] = {}

    def _get_side(self, point: Tuple[int, int]) -> int:
        px = float(point[0]) - self.line_start[0]
        py = float(point[1]) - self.line_start[1]
        cross = self.lx * py - self.ly * px
        if abs(cross) < self.line_tolerance:
            return 0
        return 1 if cross > 0 else -1

    def _compute_in_sides(self) -> Tuple[int, int]:
        mx = (self.line_start[0] + self.line_end[0]) / 2.0
        my = (self.line_start[1] + self.line_end[1]) / 2.0
        offset = 50
        offsets = {
            'down':  (0,  offset), 'up':    (0, -offset),
            'right': ( offset, 0), 'left':  (-offset, 0),
        }
        dx, dy = offsets.get(self.direction, (0, offset))
        test_point = (mx + dx, my + dy)
        target_side = self._get_side(test_point)
        if target_side == 0:
            test_point = (mx + dx * 10, my + dy * 10)
            target_side = self._get_side(test_point)
        if target_side == 0:
            target_side = 1
        return (-target_side, target_side)

    def _get_stable_side(self, track_id: int, exclude_last: bool = False) -> Optional[int]:
        if track_id not in self.side_history:
            return None
        history = list(self.side_history[track_id])
        if exclude_last and len(history) > 1:
            history = history[:-1]
        non_zero = [s for s in history if s != 0]
        if not non_zero:
            return None
        return max(set(non_zero), key=non_zero.count)

    def _track_detections(self, detections) -> List[dict]:
        """
        Lightweight centroid tracker. Matches `PersonDetector` detections to track_ids.
        Returns a list of dicts: {'id': int, 'anchor': (x,y), 'bbox': (x1,y1,x2,y2)}
        """
        assigned_detections = []
        if not detections:
            # age all existing tracks
            for tid in list(self.track_ages.keys()):
                self.track_ages[tid] += 1
                if self.track_ages[tid] > 5: # max age
                    self.tracked_objects.pop(tid, None)
                    self.track_ages.pop(tid, None)
            return []

        # Convert detections to anchors
        input_anchors = []
        for det in detections:
            if hasattr(det, 'bbox'):
                x1, y1, x2, y2 = det.bbox
            else:
                x1, y1, x2, y2 = det['bbox']
            
            if self.tracking_anchor_type == 'bottom':
                ax = int((x1 + x2) / 2)
                ay = int(y2)
            else: # center
                ax = int((x1 + x2) / 2)
                ay = int((y1 + y2) / 2)
            input_anchors.append({'bbox': (x1, y1, x2, y2), 'anchor': (ax, ay)})

        # Match to existing tracks
        # Very simple greedy matcher
        used_tracks = set()
        
        for det in input_anchors:
            min_dist = float('inf')
            best_track_id = None
            ax, ay = det['anchor']

            for tid, (tx, ty) in self.tracked_objects.items():
                if tid in used_tracks: continue
                dist = math.hypot(tx - ax, ty - ay)
                if dist < min_dist and dist < self.DEFAULT_TRACKING_MAX_DIST:
                    min_dist = dist
                    best_track_id = tid
            
            if best_track_id is not None:
                # Update existing track
                self.tracked_objects[best_track_id] = (ax, ay)
                self.track_ages[best_track_id] = 0
                used_tracks.add(best_track_id)
                assigned_detections.append({'id': best_track_id, 'anchor': (ax, ay), 'bbox': det['bbox']})
            else:
                # New track
                new_id = self.next_track_id
                self.next_track_id += 1
                self.tracked_objects[new_id] = (ax, ay)
                self.track_ages[new_id] = 0
                used_tracks.add(new_id)
                assigned_detections.append({'id': new_id, 'anchor': (ax, ay), 'bbox': det['bbox']})

        # Remove old tracks
        for tid in list(self.tracked_objects.keys()):
            if tid not in used_tracks:
                self.track_ages[tid] += 1
                if self.track_ages[tid] > 5:
                    self.tracked_objects.pop(tid, None)
                    self.track_ages.pop(tid, None)
                    self.side_history.pop(tid, None)

        return assigned_detections

    def update(self, detections: list, current_time: float = None) -> List[int]:
        now = current_time or time.time()
        new_crossings = []

        # 1. Track detections
        tracked_dets = self._track_detections(detections)

        # 2. Process side histories and crossings
        for tdet in tracked_dets:
            tid = tdet['id']
            anchor = tdet['anchor']

            current_side = self._get_side(anchor)
            self.side_history[tid].append(current_side)

            if tid in self.counted_ids:
                continue
            if len(self.side_history[tid]) < 2:
                continue

            prev_stable = self._get_stable_side(tid, exclude_last=True)
            curr_stable = self._get_stable_side(tid, exclude_last=False)

            if prev_stable is None or curr_stable is None or prev_stable == curr_stable:
                continue

            # CROSSING DETECTED
            if prev_stable == self._in_from and curr_stable == self._in_to:
                last_time = self.last_count_time_per_id.get(tid, 0)
                if now - last_time < self.cooldown_seconds:
                    continue

                self.counted_ids.add(tid)
                self.total_count += 1
                self.last_count_time_per_id[tid] = now
                new_crossings.append(tid)

                logger.info(f"CROSSING: Cam {self.camera_id} | Track {tid} | Total: {self.total_count}")

        return new_crossings

    def draw_line_and_stats(self, frame, draw_stats: bool = True):
        """Draws the transparent line, direction arrow, and (optionally) the total count."""
        # Draw dotted/semi-transparent line
        overlay = frame.copy()
        cv2.line(overlay, self.line_start, self.line_end, (255, 0, 0), 3)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        # Draw direction arrow
        mx = int((self.line_start[0] + self.line_end[0]) / 2)
        my = int((self.line_start[1] + self.line_end[1]) / 2)
        offset = 40
        dx, dy = 0, 0
        if self.direction == 'down': dy = offset
        elif self.direction == 'up': dy = -offset
        elif self.direction == 'right': dx = offset
        elif self.direction == 'left': dx = -offset

        end_pt = (mx + dx, my + dy)
        cv2.arrowedLine(frame, (mx, my), end_pt, (0, 0, 255), 3, tipLength=0.3)
        cv2.putText(frame, "IN", (end_pt[0] + 5, end_pt[1] + 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if draw_stats:
            # Draw Crossing Count
            text = f"Crossings: {self.total_count}"
            cv2.rectangle(frame, (10, 50), (250, 90), (0, 0, 0), -1)
            cv2.putText(frame, text, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        
        return frame
