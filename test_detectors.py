"""
Test suite for PersonDetector (YOLOv10s + OpenVINO)
"""
import cv2
import numpy as np
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.detector import PersonDetector
    print("[INFO] Import successful")

    print("[INFO] Testing PersonDetector initialization...")
    detector = PersonDetector()
    print(f"[INFO] PersonDetector initialized")
    print(f"[INFO]   Backend: {detector.backend}")
    print(f"[INFO]   Input size: {detector.imgsz}")
    print(f"[INFO]   Confidence: {detector.confidence}")

    # Create a dummy frame at the configured resolution
    from config import YOLO_IMGSZ
    frame = np.zeros((YOLO_IMGSZ, YOLO_IMGSZ, 3), dtype=np.uint8)

    print(f"[INFO] Testing inference on {YOLO_IMGSZ}x{YOLO_IMGSZ} blank frame...")
    detections = detector.detect(frame)
    print(f"[INFO] Detection successful, found {len(detections)} persons (expected: 0)")
    
    assert len(detections) == 0, f"Expected 0 detections on blank frame, got {len(detections)}"

    # Test draw_detections with empty list (shouldn't crash)
    print("[INFO] Testing draw_detections with empty list...")
    frame_out = detector.draw_detections(frame.copy(), [])
    assert frame_out is not None, "draw_detections returned None"

    print("\n[SUCCESS] All detector tests passed! ✅")
    print(f"  Model: YOLOv10s")
    print(f"  Backend: {detector.backend}")
    print(f"  ImgSize: {detector.imgsz}")

except Exception as e:
    print(f"[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
