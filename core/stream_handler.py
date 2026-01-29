"""
Video stream handler for webcam and RTSP sources
"""
import cv2
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, 
    CAMERA_FPS, RTSP_URL
)


class StreamHandler:
    """Handles video capture from webcam or RTSP stream"""
    
    def __init__(self, source=None):
        """
        Initialize stream handler
        
        Args:
            source: Camera index (int) or RTSP URL (str). 
                    If None, uses config defaults.
        """
        if source is None:
            source = RTSP_URL if RTSP_URL else CAMERA_INDEX
        
        self.source = source
        self.cap = None
        self.is_running = False
    
    def start(self) -> bool:
        """Start video capture"""
        print(f"📹 Connecting to video source: {self.source}")
        
        self.cap = cv2.VideoCapture(self.source)
        
        if not self.cap.isOpened():
            print(f"❌ Failed to open video source: {self.source}")
            return False
        
        # Set resolution for webcam
        if isinstance(self.source, int):
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        
        self.is_running = True
        
        # Get actual properties
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        
        print(f"✅ Video capture started: {width}x{height} @ {fps}fps")
        return True
    
    def read_frame(self):
        """
        Read a frame from the video source
        
        Returns:
            tuple: (success, frame) where success is bool and frame is numpy array
        """
        if not self.cap or not self.is_running:
            return False, None
        
        ret, frame = self.cap.read()
        
        if not ret:
            print("⚠️ Failed to read frame")
            return False, None
        
        return True, frame
    
    def get_frame_size(self) -> tuple:
        """Get frame dimensions"""
        if not self.cap:
            return (0, 0)
        
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (width, height)
    
    def stop(self):
        """Stop video capture"""
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        print("📹 Video capture stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


if __name__ == "__main__":
    # Test stream handler
    print("Testing StreamHandler with webcam...")
    
    handler = StreamHandler(0)  # Use default webcam
    if handler.start():
        print("Press 'q' to quit")
        
        while True:
            ret, frame = handler.read_frame()
            if not ret:
                break
            
            cv2.imshow("Stream Test", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        handler.stop()
        cv2.destroyAllWindows()
    else:
        print("Failed to start stream")
