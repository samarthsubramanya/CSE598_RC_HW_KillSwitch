"""
PYNQ-Z2 Face Recognition System
Main orchestration script

Workflow:
1. Load FPGA bitstream
2. Connect to network camera (mobile phone via Camo)
3. Stream video to FPGA for face detection and embedding
4. Perform recognition matching
5. Stream output with overlays to HDMI
"""

import numpy as np
import cv2
import logging
import sys
import argparse
import json
from pathlib import Path
from collections import deque
from typing import Optional

try:
    from pynq import Bitstream, Overlay, allocate
    from pynq.gpio import GPIO
    PYNQ_AVAILABLE = True
except ImportError:
    PYNQ_AVAILABLE = False
    print("Warning: PYNQ not available. Using mock FPGA interface.")

from fpga_interface import FPGAInterface
from camera_interface import NetworkCamera, USBCamera
from recognition import FaceRecognizer, AuthStatus
from user_db import UserDatabase

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class FaceRecognitionSystem:
    """Main system orchestrator for PYNQ-Z2"""
    
    def __init__(self, bitstream_path, camera_source="phone", verbose=False):
        """
        Initialize face recognition system
        
        Args:
            bitstream_path (str): Path to compiled FPGA bitstream (.bit or .xsa)
            camera_source (str): "phone" for network camera or USB device path
            verbose (bool): Enable debug logging
        """
        self.bitstream_path = Path(bitstream_path)
        self.camera_source = camera_source
        self.verbose = verbose
        
        # Components
        self.fpga = None
        self.camera = None
        self.recognizer = None
        self.db = None
        
        # State
        self.running = False
        self.mode = "recognition"  # "recognition" or "enrollment"
        self.current_user = None
        
        # Performance metrics
        self.frame_count = 0
        self.fps_history = deque(maxlen=60)
        
        logger.info(f"Initializing Face Recognition System")
        logger.info(f"Bitstream: {self.bitstream_path}")
        logger.info(f"Camera source: {camera_source}")
    
    def setup(self):
        """Initialize all system components"""
        logger.info("Setting up FPGA...")
        self._setup_fpga()
        
        logger.info("Setting up camera...")
        self._setup_camera()
        
        logger.info("Loading user database...")
        self.db = UserDatabase("data/users.json")
        
        logger.info("Initializing face recognizer...")
        self.recognizer = FaceRecognizer(self.db, similarity_threshold=0.6)
        
        logger.info("✅ System setup complete")
    
    def _setup_fpga(self):
        """Load FPGA bitstream and initialize hardware"""
        
        if not PYNQ_AVAILABLE:
            logger.warning("PYNQ not available - using mock FPGA interface")
            self.fpga = MockFPGAInterface()
            return
        
        if not self.bitstream_path.exists():
            raise FileNotFoundError(f"Bitstream not found: {self.bitstream_path}")
        
        try:
            # Load bitstream onto FPGA
            overlay = Overlay(str(self.bitstream_path))
            logger.info(f"Bitstream loaded successfully")
            
            # Initialize FPGA interface (AXI communication)
            self.fpga = FPGAInterface(overlay, verbose=self.verbose)
            logger.info("FPGA interface initialized")
            
        except Exception as e:
            logger.error(f"Failed to load bitstream: {e}")
            raise
    
    def _setup_camera(self):
        """Initialize camera input"""
        
        if self.camera_source == "phone":
            # Network camera (mobile phone via Camo or similar)
            self.camera = NetworkCamera(
                url="http://127.0.0.1:9095/video",  # Default Camo URL
                resolution=(1280, 720),
                fps=30
            )
            logger.info("Using network camera (mobile phone)")
        else:
            # USB camera
            self.camera = USBCamera(
                device=self.camera_source,
                resolution=(1280, 720),
                fps=30
            )
            logger.info(f"Using USB camera: {self.camera_source}")
        
        if not self.camera.connect():
            raise RuntimeError("Failed to connect to camera")
        
        logger.info(f"Camera connected: {self.camera.resolution}")
    
    def run_recognition(self):
        """Main recognition loop"""
        logger.info("Starting recognition mode")
        self.mode = "recognition"
        self.running = True
        
        try:
            while self.running:
                # ===== CHECK FOR ENROLLMENT REQUEST FILE =====
                if self._check_enrollment_request():
                    username = self._load_enrollment_request()
                    if username:
                        logger.info(f"📝 Enrollment request detected for user: {username}")
                        self.run_enrollment(username)
                        self._delete_enrollment_request()
                        logger.info(f"✅ Enrollment complete, resuming recognition...")
                    continue
                
                # ===== NORMAL RECOGNITION FLOW =====
                # Capture frame from camera
                frame = self.camera.read_frame()
                if frame is None:
                    logger.warning("Failed to read frame")
                    continue
                
                # Send to FPGA for face detection and embedding
                result = self.fpga.process_frame(frame)
                
                if result is None:
                    logger.warning("FPGA processing failed")
                    continue
                
                faces, embeddings = result
                
                # Perform recognition matching
                recognition_results = []
                for i, (face_box, embedding) in enumerate(zip(faces, embeddings)):
                    status = self.recognizer.recognize(embedding)
                    recognition_results.append((face_box, status))
                
                # Send authorization status to FPGA (kill switch control)
                # FPGA will multiplex: if authorized → pass through computer HDMI
                #                      if not authorized → show camera feed
                is_authorized = (self.recognizer.current_status == AuthStatus.AUTHORIZED)
                self.fpga.set_authorization_status(is_authorized)
                
                if is_authorized:
                    logger.info("✓ AUTHORIZED - Passing computer HDMI to monitor")
                else:
                    logger.debug("✗ NOT AUTHORIZED - Showing camera feed on monitor")
                
                # Update metrics
                self.frame_count += 1
                if self.frame_count % 60 == 0:
                    logger.info(f"Processed {self.frame_count} frames")
        
        except KeyboardInterrupt:
            logger.info("Recognition interrupted by user")
        finally:
            self.cleanup()
    
    def run_enrollment(self, username):
        """Enrollment mode: capture face samples"""
        logger.info(f"Starting enrollment for user: {username}")
        self.mode = "enrollment"
        self.current_user = username
        self.running = True
        
        samples = []
        required_samples = 15
        
        try:
            while len(samples) < required_samples and self.running:
                # Capture frame
                frame = self.camera.read_frame()
                if frame is None:
                    continue
                
                # Detect and compute embedding
                result = self.fpga.process_frame(frame)
                if result is None:
                    logger.warning("Face not detected")
                    continue
                
                faces, embeddings = result
                
                if len(faces) == 0:
                    logger.info("No face detected")
                    continue
                
                if len(faces) > 1:
                    logger.warning("Multiple faces detected - using first face")
                
                # Store embedding
                embedding = embeddings[0]
                samples.append(embedding)
                logger.info(f"Captured {len(samples)}/{required_samples} samples")
                
                # Show progress
                display_frame = frame.copy()
                cv2.putText(
                    display_frame,
                    f"Enrollment: {len(samples)}/{required_samples}",
                    (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 0),
                    2
                )
                self._display_frame(display_frame)
            
            if len(samples) == required_samples:
                # Average embeddings
                avg_embedding = np.mean(samples, axis=0)
                avg_embedding = avg_embedding / (np.linalg.norm(avg_embedding) + 1e-8)
                
                # Store in database
                self.db.add_user(username, avg_embedding)
                logger.info(f"✅ Successfully enrolled {username}")
            else:
                logger.info("Enrollment cancelled")
        
        except KeyboardInterrupt:
            logger.info("Enrollment interrupted")
        finally:
            self.cleanup()
    
    def _display_frame(self, frame):
        """Display frame on HDMI output"""
        # HDMI output is handled by FPGA
        # This function can be used for debugging on monitor if available
        if self.verbose:
            cv2.imshow("Face Recognition", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
    
    # =====================================================================
    # FILE-BASED ENROLLMENT (for continuous FPGA operation)
    # =====================================================================
    
    def _check_enrollment_request(self) -> bool:
        """Check if enrollment request file exists"""
        enroll_file = Path("enroll_request.json")
        return enroll_file.exists()
    
    def _load_enrollment_request(self) -> Optional[str]:
        """Load username from enrollment request file"""
        try:
            enroll_file = Path("enroll_request.json")
            if not enroll_file.exists():
                return None
            
            with open(enroll_file, 'r') as f:
                data = json.load(f)
            
            username = data.get("username")
            logger.info(f"Loaded enrollment request for: {username}")
            return username
        
        except Exception as e:
            logger.error(f"Failed to load enrollment request: {e}")
            return None
    
    def _delete_enrollment_request(self):
        """Delete enrollment request file"""
        try:
            enroll_file = Path("enroll_request.json")
            if enroll_file.exists():
                enroll_file.unlink()
                logger.info("Enrollment request file deleted")
        except Exception as e:
            logger.error(f"Failed to delete enrollment request: {e}")
    
    def cleanup(self):
        """Shutdown system gracefully"""
        logger.info("Shutting down...")
        self.running = False
        
        if self.camera:
            self.camera.disconnect()
        
        if self.fpga:
            self.fpga.shutdown()
        
        cv2.destroyAllWindows()
        logger.info("System shutdown complete")


class MockFPGAInterface:
    """Mock FPGA interface for testing without PYNQ"""
    
    def __init__(self):
        logger.warning("Using mock FPGA interface - no hardware acceleration")
        self.detector = None
        self.embedder = None
        self._init_mock_models()
    
    def _init_mock_models(self):
        """Initialize mock face detector and embedder"""
        # This would use CPU-based models for testing
        pass
    
    def process_frame(self, frame):
        """Mock frame processing"""
        # For testing: return dummy results
        return [], np.array([])
    
    def set_authorization_status(self, is_authorized: bool):
        """Mock authorization status update"""
        status_str = "AUTHORIZED ✓" if is_authorized else "UNAUTHORIZED ✗"
        logger.info(f"[Mock] Kill switch set to: {status_str}")
    
    def shutdown(self):
        pass


# =====================================================================
# Command Line Interface
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="PYNQ-Z2 Face Recognition System"
    )
    parser.add_argument(
        "--bitstream",
        type=str,
        default="design_1.bit",
        help="Path to FPGA bitstream file"
    )
    parser.add_argument(
        "--mode",
        choices=["recognition", "enroll"],
        default="recognition",
        help="Operating mode"
    )
    parser.add_argument(
        "--user",
        type=str,
        help="Username for enrollment"
    )
    parser.add_argument(
        "--camera",
        type=str,
        default="phone",
        help='Camera source: "phone" or USB device path'
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug output"
    )
    
    args = parser.parse_args()
    
    # Create system
    system = FaceRecognitionSystem(
        bitstream_path=args.bitstream,
        camera_source=args.camera,
        verbose=args.verbose
    )
    
    try:
        # Setup
        system.setup()
        
        # Run appropriate mode
        if args.mode == "recognition":
            system.run_recognition()
        elif args.mode == "enroll":
            if not args.user:
                print("Error: --user required for enrollment mode")
                sys.exit(1)
            system.run_enrollment(args.user)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
