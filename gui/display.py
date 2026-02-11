"""
Display utilities for rendering status and time overlays
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import Dict, Tuple
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TEXT_COLOR, FONT_SCALE, LINE_THICKNESS


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS"""
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=int(seconds))
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def draw_timer_overlay(frame: np.ndarray, 
                       roi_timers: Dict[int, float],
                       roi_positions: Dict[int, Tuple[int, int]]) -> np.ndarray:
    """
    Draw timer overlay for each ROI
    
    Args:
        frame: BGR image
        roi_timers: Dict mapping ROI ID to elapsed seconds
        roi_positions: Dict mapping ROI ID to (x, y) position for timer display
    
    Returns:
        Frame with timer overlays
    """
    for roi_id, seconds in roi_timers.items():
        if roi_id not in roi_positions:
            continue
        
        x, y = roi_positions[roi_id]
        time_str = format_duration(seconds)
        
        # Draw timer background
        (text_w, text_h), _ = cv2.getTextSize(
            time_str, cv2.FONT_HERSHEY_SIMPLEX, FONT_SCALE, LINE_THICKNESS
        )
        cv2.rectangle(
            frame,
            (x - 5, y - text_h - 5),
            (x + text_w + 5, y + 5),
            (0, 0, 0), -1
        )
        
        # Draw timer text
        cv2.putText(
            frame, time_str, (x, y),
            cv2.FONT_HERSHEY_SIMPLEX, FONT_SCALE, (0, 255, 255), LINE_THICKNESS
        )
    
    return frame


def draw_stats_panel(frame: np.ndarray, stats: Dict) -> np.ndarray:
    """
    Draw statistics panel
    
    Args:
        frame: BGR image
        stats: Dict with statistics to display
    
    Returns:
        Frame with stats panel
    """
    # Panel background
    panel_height = 120
    panel_width = 250
    
    overlay = frame.copy()
    cv2.rectangle(overlay, (10, 10), (10 + panel_width, 10 + panel_height), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
    
    y_offset = 35
    line_height = 25
    
    for key, value in stats.items():
        text = f"{key}: {value}"
        cv2.putText(
            frame, text, (20, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEXT_COLOR, 1
        )
        y_offset += line_height
    
    return frame


def draw_help_panel(frame: np.ndarray) -> np.ndarray:
    """Draw keyboard controls help panel"""
    h, w = frame.shape[:2]
    
    help_text = [
        "Controls:",
        "R - Draw new ROI",
        "D - Delete last ROI",
        "C - Clear all ROIs",
        "N/P - Next/Prev camera",
        "S - Show stats",
        "ENTER - Finish ROI",
        "ESC - Cancel",
        "Q - Quit"
    ]
    
    # Panel background
    panel_width = 180
    panel_height = len(help_text) * 22 + 20
    x = w - panel_width - 10
    y = 10
    
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + panel_width, y + panel_height), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
    
    for i, text in enumerate(help_text):
        cv2.putText(
            frame, text, (x + 10, y + 25 + i * 22),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, TEXT_COLOR, 1
        )
    
    return frame


def draw_employee_stats_overlay(frame: np.ndarray, 
                                roi_stats: Dict[int, dict],
                                roi_positions: Dict[int, Tuple[int, int]]) -> np.ndarray:
    """
    Draw employee statistics inside each ROI zone, top-right corner.
    Each employee gets their own mini-panel anchored inside their zone.
    """
    if not roi_stats:
        return frame
    
    for roi_id, stats in roi_stats.items():
        if roi_id not in roi_positions:
            continue
        
        cx, cy = roi_positions[roi_id]
        
        name = stats.get('employee_name', f'Place {roi_id}')
        work_time = stats.get('work_time', 0)
        client_count = stats.get('client_count', 0)
        service_time = stats.get('client_service_time', 0)
        
        # Use ROI polygon to find bounding box
        roi_pts = stats.get('roi_points', None)
        if roi_pts is not None and len(roi_pts) > 0:
            pts_array = np.array(roi_pts)
            min_x = int(np.min(pts_array[:, 0]))
            max_x = int(np.max(pts_array[:, 0]))
            min_y = int(np.min(pts_array[:, 1]))
            max_y = int(np.max(pts_array[:, 1]))
        else:
            min_x = cx - 90
            max_x = cx + 90
            min_y = cy - 50
            max_y = cy + 50
        
        # Panel dimensions
        line_height = 18
        panel_width = 170
        panel_height = line_height * 4 + 12
        
        # Scale panel if ROI is too small
        roi_w = max_x - min_x
        roi_h = max_y - min_y
        if panel_width > roi_w - 8:
            panel_width = max(100, roi_w - 8)
        if panel_height > roi_h - 8:
            panel_height = max(50, roi_h - 8)
        
        # Position: INSIDE the ROI, top-right corner with padding
        panel_x = max_x - panel_width - 4
        panel_y = min_y + 4
        
        # Ensure we stay inside the ROI bounds
        panel_x = max(min_x + 2, panel_x)
        panel_y = max(min_y + 2, panel_y)
        
        # Clamp to frame bounds
        frame_h, frame_w = frame.shape[:2]
        panel_x = max(0, min(panel_x, frame_w - panel_width))
        panel_y = max(0, min(panel_y, frame_h - panel_height))
        
        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (panel_x, panel_y),
            (panel_x + panel_width, panel_y + panel_height),
            (20, 20, 20), -1
        )
        frame = cv2.addWeighted(overlay, 0.8, frame, 0.2, 0)
        
        # Border
        cv2.rectangle(
            frame,
            (panel_x, panel_y),
            (panel_x + panel_width, panel_y + panel_height),
            (0, 200, 200), 1
        )
        
        # Text
        tx = panel_x + 5
        ty = panel_y + 14
        
        # Name (yellow)
        cv2.putText(frame, name, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        ty += line_height
        
        # Work time
        cv2.putText(frame, f"Time: {format_duration(work_time)}", (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        ty += line_height
        
        # Client count
        cv2.putText(frame, f"Clients: {client_count}", (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 150), 1)
        ty += line_height
        
        # Service time
        cv2.putText(frame, f"Service: {format_duration(service_time)}", (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
    
    return frame

