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
