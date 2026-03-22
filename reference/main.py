"""
Main application: Face Authentication System
Reference implementation on CPU
"""

import cv2
import logging
import sys
import argparse
from camera import CameraHandler
from face_detection import FaceDetector
from model import FaceEmbeddingModel
from user_db import UserDatabase
from recognition import FaceRecognizer, AuthStatus
from enrollment import EnrollmentManager
from display import DisplayHandler, ConsoleDisplay

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class FaceAuthenticationSystem:
    """Main face authentication system"""

    def __init__(
        self,
        camera_source=0,
        similarity_threshold=0.6,
        lock_threshold=3,
        unlock_threshold=8,
        headless=False,
    ):
        """
        Initialize system

        Args:
            camera_source: 0 for webcam, or IP camera URL
            similarity_threshold: Recognition confidence threshold
            lock_threshold: Frames to trigger lock
            unlock_threshold: Frames to trigger unlock
            headless: Run without GUI (console output only)
        """
        self.headless = headless

        logger.info("=== Initializing Face Authentication System ===")

        # Initialize components
        logger.info("Loading camera...")
        self.camera = CameraHandler(camera_source)

        logger.info("Loading face detector...")
        self.face_detector = FaceDetector(confidence_threshold=0.7)

        logger.info("Loading embedding model...")
        self.embedding_model = FaceEmbeddingModel()

        logger.info("Loading user database...")
        self.user_db = UserDatabase()

        logger.info("Initializing recognizer...")
        self.recognizer = FaceRecognizer(
            self.user_db,
            similarity_threshold=similarity_threshold,
            lock_threshold=lock_threshold,
            unlock_threshold=unlock_threshold,
        )

        logger.info("Initializing enrollment manager...")
        self.enrollment_manager = EnrollmentManager(
            self.face_detector, self.embedding_model, self.user_db, samples_per_user=15
        )

        # Display handlers
        self.display = DisplayHandler("Face Authentication System")
        self.console_display = ConsoleDisplay()

        self.frame_count = 0
        self.fps_counter = 0

        logger.info("System initialized successfully")

    def enroll_user(self, username):
        """
        Interactive enrollment process

        Args:
            username (str): Username to enroll
        """
        logger.info(f"\n=== Starting enrollment for {username} ===")
        logger.info(
            "Instructions:\n"
            "  - Position face in front of camera\n"
            "  - Move head slowly (left/right, up/down)\n"
            "  - Keep natural expression\n"
            "  - Press 'q' to cancel, 'SPACE' to skip frame\n"
        )

        if not self.camera.connect():
            logger.error("Failed to connect camera")
            return False

        self.enrollment_manager.start_enrollment(username)

        skip_frame_cooldown = 0

        while True:
            frame = self.camera.read_frame()
            if frame is None:
                break

            # Process frame
            result = self.enrollment_manager.process_frame(frame)

            # Draw enrollment screen
            if not self.headless:
                annotated = self.display.show_enrollment_screen(
                    frame,
                    username,
                    result["samples_collected"],
                    self.enrollment_manager.samples_per_user,
                )
                key = self.display.display_frame(annotated, wait_ms=1)
            else:
                key = None

            # Handle input
            if key == ord("q"):
                logger.info("Enrollment cancelled by user")
                self.enrollment_manager.cancel_enrollment()
                self.camera.disconnect()
                return False

            # Skip frame on space
            if key == ord(" "):
                skip_frame_cooldown = 5
            if skip_frame_cooldown > 0:
                skip_frame_cooldown -= 1
                continue

            # Check completion
            if result["success"]:
                logger.info("Sufficient samples collected, finishing...")
                break

            logger.info(result["message"])

        self.camera.disconnect()
        success = self.enrollment_manager.finish_enrollment()

        if success:
            logger.info(f"✅ Enrollment complete for {username}")
        else:
            logger.error(f"❌ Enrollment failed for {username}")

        return success

    def run_recognition(self):
        """Main recognition loop"""
        logger.info("\n=== Starting face recognition ===")
        logger.info("Press 'q' to quit, 'e' to enroll new user, 'l' to list users")
        print("\n📹 Live Recognition:")
        print("   Status updates will appear below...\n")

        if not self.camera.connect():
            logger.error("Failed to connect camera")
            return

        try:
            while True:
                frame = self.camera.read_frame()
                if frame is None:
                    logger.warning("Failed to read frame")
                    break

                self.frame_count += 1
                
                # Print live status every 30 frames (~1 second)
                if self.frame_count % 30 == 0:
                    print(f"   Processing frame {self.frame_count}...", end="\r")

                # Detect faces
                faces = self.face_detector.detect(frame)

                # Initialize default decision
                if len(faces) == 0:
                    embedding = None
                    decision = {
                        "state": AuthStatus.NO_FACE,
                        "last_user": None,
                        "similarity": 0.0,
                        "good_frames": 0,
                        "bad_frames": 0,
                    }
                else:
                    # Extract ROI from first face
                    face_bbox = faces[0]
                    roi = self.face_detector.extract_roi(frame, face_bbox)

                    # Compute embedding
                    embedding = (
                        self.embedding_model.compute_embedding(roi)
                        if roi is not None
                        else None
                    )

                    # Recognize and update state
                    decision = self.recognizer.process_frame(embedding)

                # Display
                if not self.headless:
                    annotated = self.display.draw_frame(
                        frame, faces, decision, embedding is not None
                    )
                    key = self.display.display_frame(annotated, wait_ms=1)
                else:
                    self.console_display.print_status(
                        decision,
                        embedding_valid=(embedding is not None),
                        face_detected=(len(faces) > 0),
                    )
                    key = -1

                # Handle keyboard input
                if key == ord("q"):
                    logger.info("Quitting...")
                    break
                elif key == ord("e"):
                    self.camera.disconnect()
                    username = input("\nEnter username to enroll: ").strip()
                    if username:
                        self.enroll_user(username)
                    self.camera.connect()
                elif key == ord("l"):
                    users = self.user_db.list_users()
                    print(f"\nEnrolled users: {users if users else 'None'}")
                elif key == ord("d"):
                    username = input("Enter username to delete: ").strip()
                    self.user_db.delete_user(username)
                elif key == ord("c"):
                    self.user_db.clear_all()
                    logger.info("Database cleared")

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.camera.disconnect()
            self.display.cleanup()
            logger.info("System shutdown")

    def show_menu(self):
        """Show interactive menu"""
        while True:
            print("\n=== Face Authentication System ===")
            print("1. Start recognition")
            print("2. Enroll new user")
            print("3. List users")
            print("4. Delete user")
            print("5. Clear database")
            print("6. Adjust settings")
            print("0. Exit")

            choice = input("\nChoose option: ").strip()

            if choice == "1":
                self.run_recognition()
            elif choice == "2":
                username = input("Enter username to enroll: ").strip()
                if username:
                    self.enroll_user(username)
            elif choice == "3":
                users = self.user_db.list_users()
                if users:
                    print(f"Enrolled users: {', '.join(users)}")
                else:
                    print("No users enrolled")
            elif choice == "4":
                username = input("Enter username to delete: ").strip()
                self.user_db.delete_user(username)
            elif choice == "5":
                confirm = input("Clear all users? (y/n): ").strip()
                if confirm.lower() == "y":
                    self.user_db.clear_all()
            elif choice == "6":
                self.show_settings_menu()
            elif choice == "0":
                logger.info("Exiting...")
                break

    def show_settings_menu(self):
        """Show settings menu"""
        print("\n=== Settings ===")
        print(f"1. Similarity threshold (current: {self.recognizer.similarity_threshold})")
        print(f"2. Lock threshold (current: {self.recognizer.lock_threshold})")
        print(f"3. Unlock threshold (current: {self.recognizer.unlock_threshold})")
        print("0. Back")

        choice = input("\nChoose setting: ").strip()

        if choice == "1":
            try:
                threshold = float(input("Enter new threshold (0.0-1.0): "))
                self.recognizer.set_similarity_threshold(threshold)
            except ValueError:
                print("Invalid input")
        elif choice == "2":
            try:
                threshold = int(input("Enter frames to lock: "))
                self.recognizer.lock_threshold = threshold
            except ValueError:
                print("Invalid input")
        elif choice == "3":
            try:
                threshold = int(input("Enter frames to unlock: "))
                self.recognizer.unlock_threshold = threshold
            except ValueError:
                print("Invalid input")


def main():
    parser = argparse.ArgumentParser(
        description="Face Authentication System - Reference Implementation"
    )
    parser.add_argument(
        "--camera",
        default=0,
        help="Camera source: 0 (default webcam), 1/2/... (other cameras), or IP URL",
    )
    parser.add_argument("--mode", choices=["menu", "recognition", "enroll"], default="menu")
    parser.add_argument("--user", type=str, help="Username for enrollment mode")
    parser.add_argument("--threshold", type=float, default=0.6, help="Similarity threshold (0.5-0.7 recommended)")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")

    args = parser.parse_args()

    # Convert camera argument: try int (for camera index), fallback to string (for URL)
    camera_source = args.camera
    if isinstance(camera_source, str) and camera_source.isdigit():
        camera_source = int(camera_source)

    system = FaceAuthenticationSystem(
        camera_source=camera_source,
        similarity_threshold=args.threshold,
        headless=args.headless,
    )

    if args.mode == "recognition":
        system.run_recognition()
    elif args.mode == "enroll":
        if not args.user:
            print("Error: --user required for enrollment mode")
            sys.exit(1)
        system.enroll_user(args.user)
    else:
        system.show_menu()


if __name__ == "__main__":
    main()
