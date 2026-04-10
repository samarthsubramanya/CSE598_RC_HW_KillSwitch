"""
PYNQ-Z2 Face Recognition Kill Switch — Main Orchestration

System flow:
  1. Load FPGA bitstream (custom overlay with AXI GPIO + VDMA + HDMI mux)
  2. Connect to mobile phone camera via DroidCam network stream
  3. Each frame:
       a. Run face detection + embedding on PS (face_recognition library)
       b. Match embeddings against enrolled user database (cosine similarity)
       c. Update kill-switch state via 1-bit AXI GPIO write to FPGA
       d. Push annotated camera frame to VDMA frame buffer (shown when unauthorized)
  4. FPGA PL continuously routes:
       auth=1 → HDMI IN (PC signal) → HDMI OUT  (access granted)
       auth=0 → camera feed → HDMI OUT           (access denied)

Usage:
  python main.py --mode recognition --bitstream design_1.bit
  python main.py --mode enroll --user alice --bitstream design_1.bit
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
    from pynq import Overlay
    PYNQ_AVAILABLE = True
except ImportError:
    PYNQ_AVAILABLE = False
    print("Warning: PYNQ not available — using mock FPGA interface.")

from fpga_interface import FPGAInterface
from camera_interface import NetworkCamera, USBCamera
from recognition import PSFaceProcessor, FaceRecognizer, AuthStatus, UserDatabase
from hdmi_overlay import OverlayGenerator
from graphics_api import HardwareGraphicsAPI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class FaceRecognitionSystem:
    """Main system orchestrator for PYNQ-Z2."""

    def __init__(self, bitstream_path: str, camera_source: str = "phone",
                 verbose: bool = False):
        self.bitstream_path = Path(bitstream_path)
        self.camera_source  = camera_source
        self.verbose        = verbose

        self.fpga       = None
        self.camera     = None
        self.processor  = None   # PSFaceProcessor
        self.recognizer = None
        self.db         = None
        self.overlay_gen = OverlayGenerator()
        self.gfx        = None   # HardwareGraphicsAPI (set after FPGA init)

        self.running      = False
        self.mode         = "recognition"
        self.current_user = None
        self.frame_count  = 0
        self._last_auth_state = None  # track transitions to avoid redundant writes

        logger.info(f"Face Recognition Kill Switch")
        logger.info(f"Bitstream: {self.bitstream_path} | Camera: {camera_source}")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self):
        """Initialize all components."""
        logger.info("Loading bitstream and starting HDMI pipeline...")
        self._setup_fpga()

        # Graphics API needs the FPGA interface ready first
        self.gfx = HardwareGraphicsAPI(
            fpga_interface=self.fpga,
            screen_w=1280,
            screen_h=720,
            default_alpha=14,
            default_duration=5.0,
        )

        logger.info("Connecting to camera...")
        self._setup_camera()

        logger.info("Loading user database...")
        self.db = UserDatabase("data/users.json")

        logger.info("Initializing face recognizer...")
        self.processor  = PSFaceProcessor(detection_model="hog")
        self.recognizer = FaceRecognizer(
            self.db, similarity_threshold=0.6, fpga=self.fpga
        )

        # Pre-load enrolled embeddings into FPGA BRAM
        self.fpga.update_database(self.db.get_all_users())

        logger.info("System ready")

    def _setup_fpga(self):
        if not PYNQ_AVAILABLE:
            logger.warning("PYNQ unavailable — using mock interface")
            self.fpga = _MockFPGAInterface()
            return

        if not self.bitstream_path.exists():
            raise FileNotFoundError(f"Bitstream not found: {self.bitstream_path}")

        overlay = Overlay(str(self.bitstream_path))
        logger.info("Bitstream loaded")
        self.fpga = FPGAInterface(overlay, verbose=self.verbose)

    def _setup_camera(self):
        if self.camera_source == "phone":
            # DroidCam default network URL — update IP to match your phone
            self.camera = NetworkCamera(
                url="http://192.168.1.100:4747/video",
                resolution=(1280, 720),
                fps=30
            )
            logger.info("Network camera (DroidCam)")
        else:
            self.camera = USBCamera(
                device=self.camera_source,
                resolution=(1280, 720),
                fps=30
            )
            logger.info(f"USB camera: {self.camera_source}")

        if not self.camera.connect():
            raise RuntimeError("Failed to connect to camera")
        logger.info(f"Camera connected: {self.camera.resolution}")

    # ------------------------------------------------------------------
    # Recognition loop
    # ------------------------------------------------------------------

    def run_recognition(self):
        """Continuous recognition → kill-switch control loop."""
        logger.info("Recognition mode started")
        self.mode    = "recognition"
        self.running = True

        try:
            while self.running:
                # Check for file-based enrollment request
                if self._check_enrollment_request():
                    username = self._load_enrollment_request()
                    if username:
                        logger.info(f"Enrollment request: {username}")
                        self.run_enrollment(username)
                        self._delete_enrollment_request()
                        logger.info("Resuming recognition...")
                    continue

                frame = self.camera.read_frame()
                if frame is None:
                    continue

                # PS-side face detection + embedding (replaces FPGA CNN/Haar)
                faces, embeddings = self.processor.process_frame(frame)

                # Match each detected face against the user database
                recognition_results = [
                    (box, self.recognizer.recognize(emb))
                    for box, emb in zip(faces, embeddings)
                ]

                # Authorization decision → FPGA kill switch
                is_authorized = (self.recognizer.current_status == AuthStatus.AUTHORIZED)
                self.fpga.set_authorization_status(is_authorized)

                # ── Graphics API: show timed banner on authorization state change ──
                if is_authorized != self._last_auth_state:
                    self._last_auth_state = is_authorized
                    if is_authorized:
                        # Determine who was recognized (first authorized face)
                        recognized_user = None
                        recognized_conf = 0.0
                        for _box, status in recognition_results:
                            if status.get('is_authorized', False):
                                recognized_user = status.get('user', 'User')
                                recognized_conf = status.get('confidence', 0.0)
                                break
                        self.gfx.show_authorized_screen(
                            username=recognized_user or 'User',
                            confidence=recognized_conf,
                            duration=5.0,
                            position='top',
                        )
                    else:
                        # Only show the denied banner briefly
                        self.gfx.show_unauthorized_screen(
                            duration=2.5,
                            position='top',
                        )

                # Push annotated camera frame to VDMA (displayed when unauthorized)
                annotated = self.overlay_gen.draw_boxes_and_status(
                    frame, recognition_results, embeddings
                )
                self.fpga.write_camera_frame(annotated)

                if is_authorized:
                    logger.debug("AUTHORIZED — HDMI IN passthrough active")
                else:
                    logger.debug("UNAUTHORIZED — camera feed on display")

                self.frame_count += 1
                if self.frame_count % 100 == 0:
                    logger.info(f"Frames processed: {self.frame_count}")

        except KeyboardInterrupt:
            logger.info("Stopped by user")
        finally:
            self.cleanup()

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------

    def run_enrollment(self, username: str, required_samples: int = 15):
        """
        Capture face samples and store the averaged embedding for a new user.

        Args:
            username:         Name to store in the database.
            required_samples: Number of frames to average (more = more robust).
        """
        logger.info(f"Enrolling user: {username}")
        self.mode         = "enrollment"
        self.current_user = username
        samples = []

        while len(samples) < required_samples and self.running:
            frame = self.camera.read_frame()
            if frame is None:
                continue

            faces, embeddings = self.processor.process_frame(frame)

            if len(faces) == 0:
                logger.info("No face detected — move into frame")
                continue
            if len(faces) > 1:
                logger.warning("Multiple faces — please ensure only one person is visible")
                continue

            samples.append(embeddings[0])
            progress = len(samples)
            logger.info(f"Sample {progress}/{required_samples}")

            # Show progress on the VDMA output
            display = frame.copy()
            cv2.putText(
                display,
                f"Enrolling {username}: {progress}/{required_samples}",
                (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2
            )
            cv2.rectangle(display, (faces[0][0], faces[0][1]),
                          (faces[0][2], faces[0][3]), (0, 255, 0), 2)
            self.fpga.write_camera_frame(display)

        if len(samples) == required_samples:
            avg = np.mean(samples, axis=0).astype(np.float32)
            norm = np.linalg.norm(avg)
            if norm > 1e-8:
                avg = avg / norm
            self.db.add_user(username, avg)
            # Sync updated database to FPGA BRAM
            self.fpga.update_database(self.db.get_all_users())
            logger.info(f"Enrolled '{username}' successfully")
        else:
            logger.info("Enrollment cancelled")

    # ------------------------------------------------------------------
    # File-based enrollment trigger (drop enroll_request.json while running)
    # ------------------------------------------------------------------

    def _check_enrollment_request(self) -> bool:
        return Path("enroll_request.json").exists()

    def _load_enrollment_request(self) -> Optional[str]:
        try:
            with open("enroll_request.json", 'r') as f:
                return json.load(f).get("username")
        except Exception as e:
            logger.error(f"Failed to read enrollment request: {e}")
            return None

    def _delete_enrollment_request(self):
        try:
            Path("enroll_request.json").unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Failed to delete enrollment request: {e}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        logger.info("Shutting down...")
        self.running = False
        if self.gfx:
            self.gfx.hide()
        if self.camera:
            self.camera.disconnect()
        if self.fpga:
            self.fpga.shutdown()
        cv2.destroyAllWindows()
        logger.info("Shutdown complete")


# ======================================================================
# Mock interface for development without PYNQ hardware
# ======================================================================

class _MockFPGAInterface:
    """Simulates the FPGA interface for off-board testing."""

    def __init__(self):
        logger.warning("Mock FPGA interface active (no hardware)")
        self._sprite_ctrl = None

    def set_authorization_status(self, is_authorized: bool):
        logger.info(f"[Mock] Kill-switch → {'AUTHORIZED' if is_authorized else 'UNAUTHORIZED'}")

    def write_camera_frame(self, frame: np.ndarray):
        # Show the annotated frame locally for debugging
        cv2.imshow("Camera Feed (Mock)", cv2.resize(frame, (640, 360)))
        cv2.waitKey(1)

    def update_database(self, embeddings_dict: dict):
        logger.info("[Mock] update_database (%d users)", len(embeddings_dict))

    def sprite_ctrl_write(self, offset: int, value: int):
        logger.debug("[Mock] sprite_ctrl[0x%02X] = 0x%X", offset, value)

    def sprite_ctrl_read(self, offset: int) -> int:
        return 0

    def batch_sprite_write(self, pixels: np.ndarray):
        logger.debug("[Mock] batch_sprite_write shape=%s", pixels.shape)

    def shutdown(self):
        cv2.destroyAllWindows()


# ======================================================================
# CLI
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="PYNQ-Z2 Face Recognition Kill Switch")
    parser.add_argument("--bitstream", default="design_1.bit",
                        help="Path to FPGA bitstream (.bit file)")
    parser.add_argument("--mode", choices=["recognition", "enroll"],
                        default="recognition")
    parser.add_argument("--user", help="Username for enrollment mode")
    parser.add_argument("--camera", default="phone",
                        help='"phone" for DroidCam network stream, or USB device path')
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    system = FaceRecognitionSystem(
        bitstream_path=args.bitstream,
        camera_source=args.camera,
        verbose=args.verbose,
    )

    try:
        system.setup()
        system.running = True

        if args.mode == "recognition":
            system.run_recognition()
        elif args.mode == "enroll":
            if not args.user:
                print("Error: --user required for enrollment mode")
                sys.exit(1)
            system.run_enrollment(args.user)

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
