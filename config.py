"""
Workplace Monitoring Configuration
Supports 16 RTSP cameras from NVR
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import timezone, timedelta, datetime as dt_class

# ============================================
# TIMEZONE: Tashkent (UTC+5)
# ============================================
TASHKENT_TZ = timezone(timedelta(hours=5))

def tashkent_now():
    """Get current time in Tashkent (UTC+5), returned as naive datetime for DB compatibility"""
    return dt_class.now(tz=TASHKENT_TZ).replace(tzinfo=None)

# Load environment variables
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Force TCP transport for RTSP (more stable on WiFi)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Project paths
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "workplace.db"


@dataclass
class CameraConfig:
    """Configuration for a single camera"""
    id: int
    name: str
    url: str
    ref_res: Optional[Tuple[int, int]] = None  # Reference resolution for ROI scaling
    predefined_rois: List[list] = field(default_factory=list)  # Pre-defined ROI polygons


def load_cameras_from_env() -> List[CameraConfig]:
    """
    Load camera configurations from environment variables.
    
    Format:
        CAMERA_1_URL=rtsp://...
        CAMERA_1_NAME=Camera Name
    """
    cameras = []
    
    # Find all CAMERA_X_URL patterns
    camera_pattern = re.compile(r'^CAMERA_(\d+)_URL$')
    
    for key, value in os.environ.items():
        match = camera_pattern.match(key)
        if match and value:
            camera_id = int(match.group(1))
            camera_name = os.getenv(f'CAMERA_{camera_id}_NAME', f'Camera {camera_id}')
            
            url = value
            rtsp_user = os.getenv('RTSP_USER')
            rtsp_password = os.getenv('RTSP_PASSWORD')
            
            if rtsp_user and rtsp_password and 'rtsp://' in url and '@' not in url:
                url = url.replace('rtsp://', f'rtsp://{rtsp_user}:{rtsp_password}@')
            
            cam_config = CameraConfig(
                id=camera_id,
                name=camera_name,
                url=url
            )
                
            cameras.append(cam_config)
    
    cameras.sort(key=lambda c: c.id)
    return cameras


DEFAULT_CAMERAS = []


# Load cameras: prefer .env, fallback to DEFAULT_CAMERAS
CAMERAS = load_cameras_from_env()
if not CAMERAS:
    print("[WARN] No cameras found in .env! Using defaults.")
    CAMERAS = DEFAULT_CAMERAS
    # If still empty (because we removed hardcoded ones), add a dummy one or warn user
    if not CAMERAS:
         print("[WARN] No cameras configured. Please check .env file.")


# Detection settings
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8s.pt")  # Switched to Small model for better accuracy
DETECTION_CONFIDENCE = float(os.getenv("DETECTION_CONFIDENCE", "0.35"))
PERSON_CLASS_ID = 0  # COCO class 0 = person

# Occupancy Engine settings (in seconds)
# Employee zones
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", "3.0"))  # 3 sec check
EXIT_THRESHOLD = float(os.getenv("EXIT_THRESHOLD", "30.0"))   # 30 sec grace period

# Client zones
CLIENT_ENTRY_THRESHOLD = float(os.getenv("CLIENT_ENTRY_THRESHOLD", "30.0"))  # 30 sec check
CLIENT_EXIT_THRESHOLD = float(os.getenv("CLIENT_EXIT_THRESHOLD", "3.0"))    # 3 sec grace

# Checkpoint interval (save active sessions to DB periodically)
CHECKPOINT_INTERVAL = float(os.getenv("CHECKPOINT_INTERVAL", "60.0"))  # 1 min = 60 sec

# Work hours (Tashkent timezone UZT +5)
WORK_START = os.getenv("WORK_START", "08:45")
WORK_END = os.getenv("WORK_END", "18:15")

# Auto-cycle settings
AUTO_CYCLE_INTERVAL = float(os.getenv("AUTO_CYCLE_INTERVAL", "10.0"))  # seconds between switches
AUTO_CYCLE_PAUSE_DURATION = 30.0  # seconds to pause after manual switch

# Display settings
WINDOW_NAME = "Workplace Monitoring"
FULLSCREEN_MODE = os.getenv("FULLSCREEN_MODE", "false").lower() == "true"
ROI_COLOR_VACANT = (0, 255, 0)      # Green
ROI_COLOR_OCCUPIED = (0, 0, 255)    # Red
ROI_COLOR_DRAWING = (255, 255, 0)   # Cyan
TEXT_COLOR = (255, 255, 255)        # White
FONT_SCALE = 0.6
LINE_THICKNESS = 2

# Frame settings
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "1920"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "1080"))


def print_config():
    """Print current configuration"""
    print("\n" + "=" * 50)
    print("[INFO] CAMERA CONFIGURATION")
    print("=" * 50)
    
    if not CAMERAS:
        print("[WARN]  No cameras configured!")
    else:
        for cam in CAMERAS:
            display_url = re.sub(r'://[^:]+:[^@]+@', '://***:***@', cam.url)
            print(f"  Camera {cam.id}: {cam.name}")
            print(f"           URL: {display_url}")
    
    print(f"\n  Total cameras: {len(CAMERAS)}")
    print(f"  Auto-cycle: {AUTO_CYCLE_INTERVAL}s (ping-pong)")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print_config()
