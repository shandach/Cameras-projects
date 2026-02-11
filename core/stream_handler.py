"""
Video stream handler for RTSP cameras
Supports multiple cameras
"""
import cv2
import sys
import time
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from queue import Queue, Empty

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CameraConfig, FRAME_WIDTH, FRAME_HEIGHT


class StreamHandler:
    """Handles video capture from RTSP stream asynchronously (threaded)"""
    
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
        self.max_reconnect_attempts = 10  # Increased for stability
        self.reconnect_delay = 5  # seconds
        
        # Threading support
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.last_read_success = False
        self.last_frame_time = 0.0
    
    @property
    def camera_id(self) -> int:
        return self.config.id
    
    @property
    def camera_name(self) -> str:
        return self.config.name
    
    def start(self) -> bool:
        """Start video capture thread"""
        if self.is_running:
            return True
            
        print(f"📹 [{self.camera_name}] Starting async stream handler...")
        self.is_running = True
        
        # Start capture logic in a separate thread
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        return True
    
    def _update(self):
        """Background thread loop to keep reading frames"""
        self._connect()
        
        while self.is_running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                
                if ret:
                    with self.lock:
                        self.latest_frame = frame
                        self.last_read_success = True
                        self.last_frame_time = time.time()
                    self.reconnect_attempts = 0
                else:
                    with self.lock:
                        self.last_read_success = False
                    print(f"⚠️ [{self.camera_name}] Failed to read frame")
                    self._reconnect()
            else:
                self._reconnect()
                
            # Sleep slightly to avoid 100% CPU usage in loop if fast
            # RTSP capture usually blocks on read(), but if connection is lost, we need sleep
            if not self.last_read_success:
                time.sleep(1.0) # Wait before retry
                
    def _connect(self):
        """Internal connection logic"""
        url = self.config.url
        try:
            if url.isdigit():
                self.cap = cv2.VideoCapture(int(url))
            else:
                # RTSP transport=tcp is more stable for WiFi/WAN
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp" 
                self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                
            if self.cap.isOpened():
                # self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Not supported by all backends
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"✅ [{self.camera_name}] Connected: {width}x{height}")
            else:
                print(f"❌ [{self.camera_name}] Failed to open stream")
        except Exception as e:
            print(f"❌ [{self.camera_name}] Connection error: {e}")
            
    def _reconnect(self):
        """Reconnect logic"""
        self.reconnect_attempts += 1
        print(f"🔄 [{self.camera_name}] Reconnecting ({self.reconnect_attempts})...")
        
        if self.cap:
            self.cap.release()
            
        time.sleep(self.reconnect_delay)
        self._connect()

    def read_frame(self):
        """
        Get the latest frame (non-blocking)
        
        Returns:
            tuple: (success, frame)
        """
        with self.lock:
            if self.last_read_success and self.latest_frame is not None:
                return True, self.latest_frame.copy()
            return False, None
    
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
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            
        if self.cap:
            self.cap.release()
        print(f"📹 [{self.camera_name}] Stream stopped")
