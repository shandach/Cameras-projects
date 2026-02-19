"""
YOLOv8 Person Detector
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple, NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import YOLO_MODEL, DETECTION_CONFIDENCE, PERSON_CLASS_ID


class Detection(NamedTuple):
    """Detection result"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    center: Tuple[int, int]  # center x, y


class PersonDetector:
    """YOLOv8-based person detector"""
    
    def __init__(self, model_path: str = None):
        """
        Initialize detector
        
        Args:
            model_path: Path to YOLO model. If None, uses config default.
        """
        from ultralytics import YOLO
        
        model_path = model_path or YOLO_MODEL
        print(f"🤖 Loading YOLO model: {model_path}")
        
        self.model = YOLO(model_path)
        self.confidence = DETECTION_CONFIDENCE
        
        print("✅ YOLO model loaded")
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect persons in frame
        
        Args:
            frame: BGR image (numpy array)
        
        Returns:
            List of Detection objects
        """
        # Run inference
        results = self.model(
            frame, 
            classes=[PERSON_CLASS_ID],  # Only detect persons
            conf=self.confidence,
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
