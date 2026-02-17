import cv2
import numpy as np
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.detector import PersonDetector, TrackingDetector
    print("[INFO] Imports successful")

    print("[INFO] Testing PersonDetector initialization...")
    detector = PersonDetector()
    print("[INFO] PersonDetector initialized")

    print("[INFO] Testing TrackingDetector initialization...")
    tracker = TrackingDetector()
    print("[INFO] TrackingDetector initialized")

    # Create a dummy frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    print("[INFO] Testing PersonDetector inference (dummy frame)...")
    detections = detector.detect(frame)
    print(f"[INFO] Detection successful, found {len(detections)} persons")

    print("[SUCCESS] All detector tests passed!")

except Exception as e:
    print(f"[ERROR] Test failed: {e}")
    sys.exit(1)
