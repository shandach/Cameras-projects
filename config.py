"""
Workplace Monitoring Configuration
"""
import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "workplace.db"

# Camera settings
CAMERA_INDEX = 0  # 0 = default Mac webcam
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# RTSP settings (for IP cameras)
RTSP_URL = os.getenv("RTSP_URL", None)  # e.g., "rtsp://192.168.1.100:554/stream"

# Detection settings
YOLO_MODEL = "yolov8n.pt"  # nano model for speed
DETECTION_CONFIDENCE = 0.5
PERSON_CLASS_ID = 0  # COCO class 0 = person

# Occupancy Engine settings (in seconds)
ENTRY_THRESHOLD = 3.0   # Time person must stay to start timer
EXIT_THRESHOLD = 10.0   # Time to wait before marking as VACANT

# Display settings
WINDOW_NAME = "Workplace Monitoring"
ROI_COLOR_VACANT = (0, 255, 0)      # Green
ROI_COLOR_OCCUPIED = (0, 0, 255)   # Red
ROI_COLOR_DRAWING = (255, 255, 0)  # Cyan
TEXT_COLOR = (255, 255, 255)       # White
FONT_SCALE = 0.6
LINE_THICKNESS = 2
