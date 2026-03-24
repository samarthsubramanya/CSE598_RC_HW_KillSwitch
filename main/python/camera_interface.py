"""
Camera Interface
Handles input from mobile phone (via network) or USB camera
"""

import cv2
import requests
import numpy as np
import logging
from typing import Optional, Tuple
import threading
import queue
import time
from urllib.request import urlopen

logger = logging.getLogger(__name__)


class NetworkCamera:
    """Network camera interface (mobile phone via Camo, Droidcam, etc.)"""
    
    def __init__(self, url: str, resolution: Tuple = (1280, 720), fps: int = 30):
        """
        Initialize network camera
        
        Args:
            url (str): Camera stream URL (e.g., "http://192.168.1.100:8080/video")
            resolution (Tuple): Target resolution (width, height)
            fps (int): Target frames per second
        """
        self.url = url
        self.target_resolution = resolution
        self.target_fps = fps
        self.connected = False
        self.frame = None
        self.stream = None
        self.capture_ready = False
        
        # Thread for continuous frame capture
        self.capture_thread = None
        self.stop_capture = False
        self.frame_queue = queue.Queue(maxsize=2)
        
        logger.info(f"NetworkCamera initialized: {url}")
    
    def connect(self) -> bool:
        """Establish connection to network camera"""
        try:
            logger.info(f"Connecting to {self.url}...")
            
            # Test connection
            response = requests.head(self.url, timeout=5)
            if response.status_code != 200:
                logger.error(f"Connection failed: HTTP {response.status_code}")
                return False
            
            # Start capture thread
            self.stop_capture = False
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            
            # Wait for first frame
            time.sleep(1.0)
            
            if not self.capture_ready:
                logger.error("Failed to capture initial frame")
                return False
            
            self.connected = True
            logger.info("✅ Connected to network camera")
            return True
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def _capture_loop(self):
        """Continuous frame capture in background thread"""
        try:
            # Open stream
            self.stream = urlopen(self.url)
            bytes_data = b''
            
            while not self.stop_capture:
                # Read data
                chunk = self.stream.read(1024)
                if not chunk:
                    break
                
                bytes_data += chunk
                
                # Find JPEG frame markers
                a = bytes_data.find(b'\xff\xd8')  # JPEG start
                b = bytes_data.find(b'\xff\xd9')  # JPEG end
                
                if a != -1 and b != -1:
                    jpg_data = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    
                    # Decode frame
                    frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # Resize to target resolution
                        frame = cv2.resize(frame, self.target_resolution)
                        
                        # Add to queue
                        try:
                            self.frame_queue.put(frame, block=False)
                            if not self.capture_ready:
                                self.capture_ready = True
                                logger.info(f"First frame captured: {frame.shape}")
                        except queue.Full:
                            pass  # Drop frame if queue full
        
        except Exception as e:
            logger.error(f"Capture loop error: {e}")
        finally:
            if self.stream:
                self.stream.close()
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read latest frame from camera
        
        Returns:
            Frame (BGR, uint8) or None if not available
        """
        if not self.connected:
            return None
        
        try:
            # Get latest frame from queue
            frame = self.frame_queue.get(timeout=0.1)
            return frame
        except queue.Empty:
            return None
    
    def disconnect(self):
        """Close camera connection"""
        self.stop_capture = True
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
        self.connected = False
        logger.info("Network camera disconnected")
    
    @property
    def resolution(self):
        """Get current resolution"""
        return self.target_resolution
    
    @property
    def fps(self):
        """Get current FPS"""
        return self.target_fps


class USBCamera:
    """USB camera interface (webcam)"""
    
    def __init__(self, device: int = 0, resolution: Tuple = (1280, 720), fps: int = 30):
        """
        Initialize USB camera
        
        Args:
            device (int): Camera device index (0=default)
            resolution (Tuple): Target resolution (width, height)
            fps (int): Target frames per second
        """
        self.device = device
        self.target_resolution = resolution
        self.target_fps = fps
        self.cap = None
        self.connected = False
        
        logger.info(f"USBCamera initialized: device {device}")
    
    def connect(self) -> bool:
        """Open camera device"""
        try:
            self.cap = cv2.VideoCapture(self.device)
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera device {self.device}")
                return False
            
            # Set resolution and FPS
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            
            # Read one frame to verify
            ret, frame = self.cap.read()
            if not ret:
                logger.error("Failed to read first frame")
                self.cap.release()
                return False
            
            self.connected = True
            logger.info(f"✅ Connected to USB camera: {frame.shape}")
            return True
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Read frame from camera"""
        if not self.connected or self.cap is None:
            return None
        
        try:
            ret, frame = self.cap.read()
            if ret:
                # Resize to target resolution if needed
                if frame.shape != (self.target_resolution[1], self.target_resolution[0], 3):
                    frame = cv2.resize(frame, self.target_resolution)
                return frame
            else:
                logger.warning("Failed to read frame")
                return None
        except Exception as e:
            logger.error(f"Read frame error: {e}")
            return None
    
    def disconnect(self):
        """Close camera device"""
        if self.cap:
            self.cap.release()
            self.connected = False
            logger.info("USB camera disconnected")
    
    @property
    def resolution(self):
        """Get current resolution"""
        return self.target_resolution
    
    @property
    def fps(self):
        """Get current FPS"""
        return self.target_fps


# Factory function
def create_camera(source: str, **kwargs):
    """
    Create camera instance based on source
    
    Args:
        source (str): "phone" for network camera or USB device path/number
    
    Returns:
        Camera instance or None
    """
    if source == "phone":
        return NetworkCamera(**kwargs)
    else:
        try:
            device = int(source)
            return USBCamera(device=device, **kwargs)
        except ValueError:
            logger.error(f"Invalid camera source: {source}")
            return None
