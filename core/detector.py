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
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                
                detection = Detection(
                    bbox=(x1, y1, x2, y2),
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


class PoseDetector:
    """
    MediaPipe Pose - резервный детектор скелета
    
    Используется когда YOLO не обнаруживает человека
    (например, когда сотрудник отвернулся или частично закрыт).
    Детектирует точки тела и работает стабильно со всех ракурсов.
    
    Использует новый MediaPipe Tasks API (v0.10.30+)
    """
    
    def __init__(self):
        """Initialize MediaPipe Pose detector using Tasks API"""
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        import urllib.request
        import os
        
        print("🦴 Loading MediaPipe Pose detector...")
        
        # Download model if not exists
        model_path = os.path.join(os.path.dirname(__file__), '..', 'pose_landmarker_lite.task')
        if not os.path.exists(model_path):
            print("   Downloading pose model...")
            model_url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
            urllib.request.urlretrieve(model_url, model_path)
            print("   ✅ Model downloaded")
        
        # Create PoseLandmarker
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.3,
            min_tracking_confidence=0.3
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)
        
        print("✅ MediaPipe Pose loaded")
    
    def detect(self, frame: np.ndarray) -> List[Tuple[int, int]]:
        """
        Detect person skeleton and return body center point
        
        Args:
            frame: BGR image (numpy array)
        
        Returns:
            List of (x, y) center points for each detected person
        """
        import mediapipe as mp
        
        # Convert to RGB and create MediaPipe Image
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Detect landmarks
        results = self.landmarker.detect(mp_image)
        
        centers = []
        
        if results.pose_landmarks:
            h, w = frame.shape[:2]
            for pose in results.pose_landmarks:
                # Use hip landmarks (23=left hip, 24=right hip) as body center
                if len(pose) > 24:
                    left_hip = pose[23]
                    right_hip = pose[24]
                    
                    # Check visibility (coordinates are normalized 0-1)
                    if left_hip.visibility > 0.3 or right_hip.visibility > 0.3:
                        cx = int((left_hip.x + right_hip.x) / 2 * w)
                        cy = int((left_hip.y + right_hip.y) / 2 * h)
                        centers.append((cx, cy))
        
        return centers
    
    def draw_skeleton(self, frame: np.ndarray, draw: bool = True) -> np.ndarray:
        """
        Detect and draw skeleton on frame (for debugging)
        
        Args:
            frame: BGR image
            draw: Whether to draw the skeleton
        
        Returns:
            Frame with drawn skeleton (if draw=True)
        """
        if not draw:
            return frame
        
        import mediapipe as mp
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = self.landmarker.detect(mp_image)
        
        if results.pose_landmarks:
            h, w = frame.shape[:2]
            for pose in results.pose_landmarks:
                # Draw landmarks as circles
                for landmark in pose:
                    x = int(landmark.x * w)
                    y = int(landmark.y * h)
                    cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)
        
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
