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
            
            # Apply ROI Template if available
            if camera_id in ROI_TEMPLATES:
                tmpl = ROI_TEMPLATES[camera_id]
                cam_config.predefined_rois = tmpl["rois"]
                cam_config.ref_res = tmpl["ref_res"]
                
            cameras.append(cam_config)
    
    cameras.sort(key=lambda c: c.id)
    return cameras


# ═══════════════════════════════════════════════════
# Default Configuration (Fallback if .env is missing)
# ═══════════════════════════════════════════════════

# NOTE: Real camera URLs should be in .env file for security.
# Example: CAMERA_1_URL=rtsp://admin:pass@192.168.1.100:554/...

# ═══════════════════════════════════════════════════
# PREDEFINED ROI TEMPLATES (Auto-Restore Source)
# Extended with Reference Resolution for correct scaling
# ═══════════════════════════════════════════════════

ROI_TEMPLATES = {
    1: {
        "ref_res": (2560, 1440),
        "rois": [
            [(50, 650), (250, 400), (460, 492), (244, 682)],
            [(306, 732), (508, 518), (674, 620), (430, 808)],
            [(546, 858), (770, 606), (906, 710), (732, 980)],
            [(1540, 452), (1318, 566), (1512, 1006), (1740, 802)],
            [(1844, 624), (1554, 414), (1676, 294), (1900, 486)],
            [(1720, 286), (1812, 190), (2010, 358), (1900, 420)],
        ]
    },
    6: {
        "ref_res": (2560, 1440),
        "rois": [
            [(422, 548), (640, 336), (788, 484), (508, 654)],
            [(604, 742), (896, 506), (1148, 692), (788, 932)],
            [(916, 1040), (1246, 756), (1584, 984), (1214, 1334)],
        ]
    },
    7: {
        "ref_res": (3200, 1800),
        "rois": [
            [(1062, 802), (1940, 357), (2515, 1190), (1580, 1637)],
        ]
    },
    10: {
        "ref_res": (3200, 1800),
        "rois": [
            [(680, 1230), (1500, 407), (2452, 1080), (1922, 1787)],
        ]
    }
}

DEFAULT_CAMERAS = []


# ═══════════════════════════════════════════════════
# Operators from WORKPLACE_OWNERS (real employees)
# Maps workplace_id -> operator name
# ═══════════════════════════════════════════════════

WORKPLACE_OWNERS = {
    # Camera 01 (IDs 1-6)
    1: 'Operator 5',
    2: 'Operator 6',
    3: 'Operator 7',
    4: 'Operator 8',
    5: 'Operator 9',
    6: 'Operator 10',
    # Camera 03 (ID 7)
    7: 'Operator 3',
    # Camera 06 (IDs 8-10)
    8: 'Operator 11',
    9: 'Operator 12',
    10: 'Operator 13',
    # Camera 07 (ID 11)
    11: 'Operator 2',
    # Camera 10 (ID 12)
    12: 'Operator 1',
}


# Load cameras: prefer .env, fallback to DEFAULT_CAMERAS
CAMERAS = load_cameras_from_env()
if not CAMERAS:
    print("[WARN] No cameras found in .env! Using defaults.")
    CAMERAS = DEFAULT_CAMERAS
    # If still empty (because we removed hardcoded ones), add a dummy one or warn user
    if not CAMERAS:
         print("[WARN] No cameras configured. Please check .env file.")


# Detection settings
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
DETECTION_CONFIDENCE = float(os.getenv("DETECTION_CONFIDENCE", "0.5"))
PERSON_CLASS_ID = 0  # COCO class 0 = person

# Occupancy Engine settings (in seconds)
# Employee zones
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", "3.0"))  # 3 sec check
EXIT_THRESHOLD = float(os.getenv("EXIT_THRESHOLD", "30.0"))   # 30 sec grace period

# Client zones
CLIENT_ENTRY_THRESHOLD = float(os.getenv("CLIENT_ENTRY_THRESHOLD", "60.0"))  # 1 min check
CLIENT_EXIT_THRESHOLD = float(os.getenv("CLIENT_EXIT_THRESHOLD", "10.0"))    # 10 sec grace

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
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "1280"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "720"))


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
            rois_count = len(cam.predefined_rois) if cam.predefined_rois else 0
            if rois_count:
                print(f"           ROIs: {rois_count} predefined")
    
    print(f"\n  Total cameras: {len(CAMERAS)}")
    print(f"  Total operators: {len(WORKPLACE_OWNERS)}")
    print(f"  Auto-cycle: {AUTO_CYCLE_INTERVAL}s (ping-pong)")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print_config()
