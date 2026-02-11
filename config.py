"""
Workplace Monitoring Configuration
All 16 RTSP cameras configured directly (NVR 192.168.100.100)

При запуске напрямую (python config.py) — полноэкранный просмотр камер:
  → / D    — следующая камера
  ← / A    — предыдущая камера
  1-9, 0   — камера 1-10
  F        — полный экран / окно
  Q / ESC  — выход
"""
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List

# Project paths
BASE_DIR = Path(__file__).parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "workplace.db"


@dataclass
class CameraConfig:
    """Configuration for a single camera"""
    id: int
    name: str
    url: str


# ============================================================
# All 16 RTSP camera sources (Hikvision NVR)
# ============================================================
CAMERAS = [
    CameraConfig(id=1,  name="Camera 01", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/101"),
    CameraConfig(id=2,  name="Camera 02", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/201"),
    CameraConfig(id=3,  name="Camera 03", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/301"),
    CameraConfig(id=4,  name="Camera 04", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/401"),
    CameraConfig(id=5,  name="Camera 05", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/501"),
    CameraConfig(id=6,  name="Camera 06", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/601"),
    CameraConfig(id=7,  name="Camera 07", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/701"),
    CameraConfig(id=8,  name="Camera 08", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/801"),
    CameraConfig(id=9,  name="Camera 09", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/901"),
    CameraConfig(id=10, name="Camera 10", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1001"),
    CameraConfig(id=11, name="Camera 11", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1101"),
    CameraConfig(id=12, name="Camera 12", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1201"),
    CameraConfig(id=13, name="Camera 13", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1301"),
    CameraConfig(id=14, name="Camera 14", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1401"),
    CameraConfig(id=15, name="Camera 15", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1501"),
    CameraConfig(id=16, name="Camera 16", url="rtsp://admin:a1234567@192.168.100.100:554/Streaming/Channels/1601"),
]

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
WORK_START = os.getenv("WORK_START", "08:45")  # Start time
WORK_END = os.getenv("WORK_END", "18:15")      # End time - client IDs reset after this

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
    else:
        for cam in CAMERAS:
            display_url = re.sub(r'://[^:]+:[^@]+@', '://***:***@', cam.url)
            print(f"  Camera {cam.id}: {cam.name}")
            print(f"           URL: {display_url}")
    
    print("=" * 50 + "\n")


# ============================================================
# Camera Viewer (запускается при python config.py)
# ============================================================
if __name__ == "__main__":
    import cv2
    import time
    import numpy as np

    def run_viewer():
        VIEWER_WINDOW = "Camera Viewer"
        KEY_ESC = 27
        KEY_LEFT = 2424832
        KEY_RIGHT = 2555904

        def _info_frame(text, w=1280, h=720):
            """Чёрный кадр с текстом по центру."""
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            ts = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
            cv2.putText(frame, text, ((w - ts[0]) // 2, (h + ts[1]) // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 255), 2)
            return frame

        def _draw_overlay(frame, idx, total):
            """Полоска с номером камеры и навигацией."""
            h, w = frame.shape[:2]
            cam = CAMERAS[idx]

            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 70), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

            label = f"[{cam.id:02d}/{total}]  {cam.name}"
            cv2.putText(frame, label, (20, 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 2)

            hint = "<< A/Left  |  D/Right >>"
            hs = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 1)[0]
            cv2.putText(frame, hint, (w - hs[0] - 20, 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)

            bar_y = h - 8
            seg = w / total
            cv2.rectangle(frame, (0, bar_y), (w, h), (40, 40, 40), -1)
            cv2.rectangle(frame, (int(idx * seg), bar_y),
                          (int((idx + 1) * seg), h), (0, 255, 0), -1)
            return frame

        def _open_cam(idx):
            """Открывает RTSP камеру по индексу."""
            cam = CAMERAS[idx]
            print(f"\n>>> {cam.name}  ({cam.url})")
            cv2.imshow(VIEWER_WINDOW, _info_frame(f"Connecting to {cam.name}..."))
            cv2.waitKey(1)

            cap = cv2.VideoCapture(cam.url)
            t0 = time.time()
            while not cap.isOpened() and (time.time() - t0) < 5:
                time.sleep(0.1)

            if cap.isOpened():
                ret, f = cap.read()
                if ret:
                    print(f"    ✅ OK ({f.shape[1]}x{f.shape[0]})")
                    return cap
                cap.release()
                print("    ❌ Кадр не получен")
            else:
                cap.release()
                print("    ❌ Таймаут")
            return None

        # --- Main viewer loop ---
        total = len(CAMERAS)
        cur = 0
        cap = None
        fullscreen = True

        cv2.namedWindow(VIEWER_WINDOW, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(VIEWER_WINDOW, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)

        print("=" * 55)
        print("  Camera Viewer | ←→ переключение | Q — выход")
        print("=" * 55)

        def _switch(new_idx):
            nonlocal cap, cur
            if cap: cap.release()
            cur = new_idx % total
            cap = _open_cam(cur)

        _switch(0)

        try:
            while True:
                if cap:
                    ret, frame = cap.read()
                    if ret:
                        cv2.imshow(VIEWER_WINDOW, _draw_overlay(frame, cur, total))
                    else:
                        cv2.imshow(VIEWER_WINDOW,
                                   _info_frame(f"{CAMERAS[cur].name} — reconnecting..."))
                        cap.release()
                        cap = cv2.VideoCapture(CAMERAS[cur].url)
                else:
                    cv2.imshow(VIEWER_WINDOW,
                               _info_frame(f"{CAMERAS[cur].name} — NO SIGNAL"))

                key = cv2.waitKeyEx(30)
                if key == -1:
                    continue

                if key in (ord('q'), ord('Q'), KEY_ESC):
                    break
                elif key in (KEY_RIGHT, ord('d'), ord('D')):
                    _switch(cur + 1)
                elif key in (KEY_LEFT, ord('a'), ord('A')):
                    _switch(cur - 1)
                elif ord('1') <= key <= ord('9'):
                    _switch(key - ord('1'))
                elif key == ord('0'):
                    _switch(9)
                elif key in (ord('f'), ord('F')):
                    fullscreen = not fullscreen
                    cv2.setWindowProperty(
                        VIEWER_WINDOW, cv2.WND_PROP_FULLSCREEN,
                        cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
                    if not fullscreen:
                        cv2.resizeWindow(VIEWER_WINDOW, 1280, 720)

        except KeyboardInterrupt:
            print("\nCtrl+C...")
        finally:
            if cap: cap.release()
            cv2.destroyAllWindows()
            print("Viewer закрыт.")

    run_viewer()

