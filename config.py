"""
Workplace Monitoring Configuration
Supports multiple RTSP cameras via .env file
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List, Optional

# Load environment variables
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Project paths
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "workplace.db"


@dataclass
class CameraConfig:
    """Configuration for a single camera"""
    id: int
    name: str
    url: str


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
            
            # Handle authentication if provided
            url = value
            rtsp_user = os.getenv('RTSP_USER')
            rtsp_password = os.getenv('RTSP_PASSWORD')
            
            if rtsp_user and rtsp_password and 'rtsp://' in url:
                # Insert credentials into URL: rtsp://user:pass@host:port/path
                url = url.replace('rtsp://', f'rtsp://{rtsp_user}:{rtsp_password}@')
            
            cameras.append(CameraConfig(
                id=camera_id,
                name=camera_name,
                url=url
            ))
    
    # Sort by ID
    cameras.sort(key=lambda c: c.id)
    
    return cameras


# Load cameras
CAMERAS = load_cameras_from_env()

# Detection settings
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
DETECTION_CONFIDENCE = float(os.getenv("DETECTION_CONFIDENCE", "0.5"))
PERSON_CLASS_ID = 0  # COCO class 0 = person

# Occupancy Engine settings (in seconds)
ENTRY_THRESHOLD = float(os.getenv("ENTRY_THRESHOLD", "3.0"))
EXIT_THRESHOLD = float(os.getenv("EXIT_THRESHOLD", "10.0"))

# Display settings
WINDOW_NAME = "Workplace Monitoring"
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
    print("📹 CAMERA CONFIGURATION")
    print("=" * 50)
    
    if not CAMERAS:
        print("⚠️  No cameras configured!")
        print("   Create .env file from .env.example")
    else:
        for cam in CAMERAS:
            # Hide password in URL for display
            display_url = re.sub(r'://[^:]+:[^@]+@', '://***:***@', cam.url)
            print(f"  Camera {cam.id}: {cam.name}")
            print(f"           URL: {display_url}")
    
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print_config()
