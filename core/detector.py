"""
YOLOv10s Person Detector with OpenVINO auto-fallback

Automatically uses OpenVINO-optimized model if available,
otherwise falls back to the original .pt model (PyTorch).
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple, NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    YOLO_MODEL, DETECTION_CONFIDENCE, PERSON_CLASS_ID,
    YOLO_IMGSZ, YOLO_USE_OPENVINO
)


class Detection(NamedTuple):
    """Detection result"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    center: Tuple[int, int]  # center x, y


def _find_openvino_model(pt_path: str) -> str | None:
    """
    Look for an OpenVINO model directory next to the .pt file.
    
    Convention: yolov10s.pt → yolov10s_openvino_model/
    The directory must contain an .xml file to be valid.
    """
    pt = Path(pt_path)
    openvino_dir = pt.parent / f"{pt.stem}_openvino_model"
    
    if openvino_dir.is_dir():
        # Verify it contains at least one .xml file (OpenVINO IR)
        xml_files = list(openvino_dir.glob("*.xml"))
        if xml_files:
            return str(openvino_dir)
    
    return None


class PersonDetector:
    """YOLOv10s-based person detector with OpenVINO support"""
    
    def __init__(self, model_path: str = None):
        """
        Initialize detector with automatic OpenVINO selection.
        
        Priority:
        1. OpenVINO model (if YOLO_USE_OPENVINO=true and model dir exists)
        2. Original .pt model (PyTorch fallback)
        
        Args:
            model_path: Path to YOLO .pt model. If None, uses config default.
        """
        from ultralytics import YOLO
        
        model_path = model_path or YOLO_MODEL
        self.backend = "PyTorch"  # Default
        
        # Try OpenVINO first
        if YOLO_USE_OPENVINO:
            openvino_path = _find_openvino_model(model_path)
            
            if openvino_path:
                print(f"🚀 Loading OpenVINO model: {openvino_path}")
                try:
                    self.model = YOLO(openvino_path)
                    self.backend = "OpenVINO"
                    print(f"✅ YOLO model loaded (OpenVINO backend, imgsz={YOLO_IMGSZ})")
                except Exception as e:
                    print(f"⚠️ OpenVINO load failed ({e}), falling back to .pt")
                    self.model = YOLO(model_path)
                    print(f"✅ YOLO model loaded (PyTorch fallback, imgsz={YOLO_IMGSZ})")
            else:
                print(f"🤖 Loading YOLO model: {model_path}")
                self.model = YOLO(model_path)
                print(f"✅ YOLO model loaded (PyTorch, imgsz={YOLO_IMGSZ})")
                print(f"💡 Tip: Run 'python scripts/export_openvino.py' to convert to OpenVINO for 3-5x speedup on Intel CPUs")
        else:
            print(f"🤖 Loading YOLO model: {model_path} (OpenVINO disabled)")
            self.model = YOLO(model_path)
            print(f"✅ YOLO model loaded (PyTorch, imgsz={YOLO_IMGSZ})")
        
        self.confidence = DETECTION_CONFIDENCE
        self.imgsz = YOLO_IMGSZ
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect persons in frame
        
        Args:
            frame: BGR image (numpy array)
        
        Returns:
            List of Detection objects
        """
        # Run inference with configured input size
        results = self.model(
            frame, 
            classes=[PERSON_CLASS_ID],  # Only detect persons
            conf=self.confidence,
            imgsz=self.imgsz,
            verbose=False
        )
        
        detections = []
        
        for result in results:
            boxes = result.boxes
            
            if boxes is None:
                continue
            
            for box in boxes:
                # Get bounding box
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                confidence = float(box.conf[0].cpu().numpy())
                
                # Calculate center
                center_x = int((x1 + x2) // 2)
                center_y = int((y1 + y2) // 2)
                
                detection = Detection(
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    confidence=confidence,
                    center=(center_x, center_y)
                )
                detections.append(detection)
        
        return detections
    
    def draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """
        Draw detection boxes on frame
        
        Args:
            frame: BGR image
            detections: List of Detection objects
        
        Returns:
            Frame with drawn detections
        """
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            
            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            
            # Draw center point
            cv2.circle(frame, det.center, 5, (0, 255, 255), -1)
            
            # Draw confidence label
            label = f"Person {det.confidence:.2f}"
            cv2.putText(
                frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2
            )
        
        return frame


if __name__ == "__main__":
    # Test detector with webcam
    from core.stream_handler import StreamHandler
    
    print("Testing PersonDetector with webcam...")
    
    detector = PersonDetector()
    print(f"Backend: {detector.backend}")
    print(f"Input size: {detector.imgsz}")
    
    handler = StreamHandler(0)
    
    if handler.start():
        print("Press 'q' to quit")
        
        while True:
            ret, frame = handler.read_frame()
            if not ret:
                break
            
            # Detect persons
            detections = detector.detect(frame)
            
            # Draw detections
            frame = detector.draw_detections(frame, detections)
            
            # Show detection count
            cv2.putText(
                frame, f"Persons: {len(detections)}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
            )
            
            cv2.imshow("Detection Test", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        handler.stop()
        cv2.destroyAllWindows()
    else:
        print("Failed to start stream")
