"""
Camera input handler
Supports:
- Webcam (default device)
- IP camera (from phone, URL-based)
- USB camera
"""

import cv2
import logging
import time

logger = logging.getLogger(__name__)


class CameraHandler:
    """Handles video capture from various sources"""

    def __init__(self, source=0, width=640, height=480, fps=30):
        """
        Initialize camera handler

        Args:
            source: 0 (default webcam), or IP camera URL (e.g., http://192.168.x.x:8080/video)
            width: Frame width
            height: Frame height
            fps: Target frames per second
        """
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None
        self.connected = False

    def connect(self):
        """Open camera connection"""
        try:
            self.cap = cv2.VideoCapture(self.source)
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera source: {self.source}")
                print(f"\n❌ Camera Error: Could not open camera source: {self.source}")
                print("\n📱 Troubleshooting for macOS:")
                print("   1. Go to System Preferences → Security & Privacy → Camera")
                print("   2. Grant camera access to Terminal/Python")
                print("   3. Restart the application")
                print("   4. Or try: tccutil reset Camera")
                print("   5. Check if camera is in use by other apps (Zoom, FaceTime, etc.)\n")
                return False

            # Set resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)

            # Wait for camera to initialize (important on macOS)
            logger.info("Waiting for camera to initialize...")
            time.sleep(1.0)
            
            # Test reading a frame
            ret, test_frame = self.cap.read()
            if not ret:
                logger.warning("Camera opened but cannot read frames yet, waiting longer...")
                time.sleep(2.0)
                ret, test_frame = self.cap.read()
                if not ret:
                    logger.error("Still cannot read frames from camera")
                    return False

            self.connected = True
            logger.info(
                f"Camera connected: {self.source} ({self.width}x{self.height} @ {self.fps}fps)"
            )
            return True
        except Exception as e:
            logger.error(f"Exception connecting camera: {e}")
            return False

    def read_frame(self):
        """
        Read a frame from camera

        Returns:
            frame (numpy.ndarray): Image frame or None if failed
        """
        if not self.connected or self.cap is None:
            return None

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to read frame from camera")
            return None

        return frame

    def disconnect(self):
        """Release camera resource"""
        if self.cap is not None:
            self.cap.release()
            self.connected = False
            logger.info("Camera disconnected")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
