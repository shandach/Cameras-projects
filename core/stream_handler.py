"""
Video stream handler for RTSP cameras
Supports multiple cameras
"""
import cv2
import sys
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CameraConfig, FRAME_WIDTH, FRAME_HEIGHT


class StreamHandler:
    """Handles video capture from RTSP stream"""
    
    def __init__(self, camera_config: CameraConfig):
        """
        Initialize stream handler for a specific camera
        
        Args:
            camera_config: CameraConfig with id, name, url
        """
        self.config = camera_config
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
    
    @property
    def camera_id(self) -> int:
        return self.config.id
    
    @property
    def camera_name(self) -> str:
        return self.config.name
    
    def start(self) -> bool:
        """Start video capture"""
        url = self.config.url
        
        # Check if URL is a webcam index (0, 1, 2, etc.)
        if url.isdigit():
            source = int(url)
            print(f"📹 [{self.camera_name}] Connecting to webcam {source}...")
            self.cap = cv2.VideoCapture(source)
        else:
            print(f"📹 [{self.camera_name}] Connecting to RTSP stream...")
            # OpenCV RTSP options for better stability
            self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        
        if not self.cap.isOpened():
            print(f"❌ [{self.camera_name}] Failed to connect to camera")
            return False
        
        # Set buffer size to minimize latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.is_running = True
        self.reconnect_attempts = 0
        
        # Get actual properties
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(self.cap.get(cv2.CAP_PROP_FPS))
        
        print(f"✅ [{self.camera_name}] Connected: {width}x{height} @ {fps}fps")
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
            print(f"⚠️ [{self.camera_name}] Failed to read frame")
            
            # Try to reconnect
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self._try_reconnect()
                return False, None
            else:
                print(f"❌ [{self.camera_name}] Max reconnect attempts reached")
                self.is_running = False
                return False, None
        
        # Reset reconnect counter on successful read
        self.reconnect_attempts = 0
        
        return True, frame
    
    def _try_reconnect(self):
        """Attempt to reconnect to the stream"""
        self.reconnect_attempts += 1
        print(f"🔄 [{self.camera_name}] Reconnecting... Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        # Release current capture
        if self.cap:
            self.cap.release()
        
        time.sleep(self.reconnect_delay)
        
        # Try to reconnect
        url = self.config.url
        if url.isdigit():
            self.cap = cv2.VideoCapture(int(url))
        else:
            self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if self.cap.isOpened():
            print(f"✅ [{self.camera_name}] Reconnected successfully")
    
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
        print(f"📹 [{self.camera_name}] Stream stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
