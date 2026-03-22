"""
Display and UI for showing authentication status
Shows live feed with face detection and authorization status
"""

import cv2
import numpy as np
import logging
from recognition import AuthStatus

logger = logging.getLogger(__name__)


class DisplayHandler:
    """Handles display of video feed with authentication status"""

    def __init__(self, title="Face Authentication System"):
        """
        Initialize display handler

        Args:
            title (str): Window title
        """
        self.title = title
        self.window_created = False

    def draw_frame(self, frame, faces, decision, embedding_valid=False):
        """
        Draw frame with face boxes and status overlay

        Args:
            frame (numpy.ndarray): Input frame
            faces (list): List of face bounding boxes [(x1, y1, x2, y2), ...]
            decision (dict): Authorization decision from recognizer
            embedding_valid (bool): Whether embedding was computed

        Returns:
            numpy.ndarray: Annotated frame
        """
        frame = frame.copy()

        if frame is None:
            return None

        # Draw faces
        for x1, y1, x2, y2 in faces:
            # Box color based on state
            if decision["state"] == AuthStatus.AUTHORIZED:
                color = (0, 255, 0)  # Green
                thickness = 2
            else:
                color = (0, 0, 255)  # Red
                thickness = 3

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            # Draw confidence
            if decision.get("similarity") is not None:
                text = f"Sim: {decision['similarity']:.2f}"
                cv2.putText(
                    frame,
                    text,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                )

        # Draw status bar at top
        status_text = f"STATUS: {decision['state'].value}"
        if decision["last_user"]:
            status_text += f" ({decision['last_user']})"

        # Status color
        status_color_map = {
            AuthStatus.AUTHORIZED: (0, 255, 0),
            AuthStatus.UNAUTHORIZED: (0, 0, 255),
            AuthStatus.NO_FACE: (128, 128, 128),
        }
        status_color = status_color_map.get(decision["state"], (128, 128, 128))

        # Background bar
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (0, 0, 0), -1)
        cv2.putText(
            frame,
            status_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            status_color,
            2,
        )

        # Draw frame counters at bottom
        info_text = f"Good: {decision['good_frames']} | Bad: {decision['bad_frames']}"
        cv2.putText(
            frame,
            info_text,
            (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
        )

        return frame

    def display_frame(self, frame, wait_ms=1):
        """
        Display frame in window

        Args:
            frame (numpy.ndarray): Frame to display
            wait_ms (int): Wait time in milliseconds

        Returns:
            int: Key pressed (-1 if none, ord('q') for quit)
        """
        if frame is None:
            return -1

        # Resize for display if too large (macOS issue with very large frames)
        display_frame = frame.copy()
        max_height = 1200
        if display_frame.shape[0] > max_height:
            scale = max_height / display_frame.shape[0]
            new_w = int(display_frame.shape[1] * scale)
            new_h = int(display_frame.shape[0] * scale)
            display_frame = cv2.resize(display_frame, (new_w, new_h))

        try:
            cv2.imshow(self.title, display_frame)
            self.window_created = True
        except Exception as e:
            logger.error(f"Error displaying frame: {e}")
            return -1

        key = cv2.waitKey(wait_ms) & 0xFF
        return key

    def show_enrollment_screen(self, frame, username, sample_count, total_samples):
        """
        Display enrollment progress screen

        Args:
            frame (numpy.ndarray): Current frame
            username (str): User being enrolled
            sample_count (int): Current sample number
            total_samples (int): Total samples needed

        Returns:
            numpy.ndarray: Annotated frame
        """
        frame = frame.copy()

        # Semi-transparent overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

        # Enrollment text
        text1 = f"Enrolling: {username}"
        text2 = f"Sample {sample_count}/{total_samples}"
        text3 = "Move face around, keep eyes open"

        h = frame.shape[0]
        cv2.putText(
            frame,
            text1,
            (50, h // 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            frame,
            text2,
            (50, h // 3 + 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            text3,
            (50, h // 3 + 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 200, 0),
            1,
        )

        # Progress bar
        progress = sample_count / total_samples
        bar_width = frame.shape[1] - 100
        bar_x = 50
        bar_y = h // 2 + 50

        cv2.rectangle(
            frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + 20), (100, 100, 100), 2
        )
        cv2.rectangle(
            frame,
            (bar_x, bar_y),
            (bar_x + int(bar_width * progress), bar_y + 20),
            (0, 255, 0),
            -1,
        )

        return frame

    def cleanup(self):
        """Clean up display resources"""
        cv2.destroyAllWindows()
        self.window_created = False


class ConsoleDisplay:
    """Simple console-based display for headless systems"""

    def __init__(self):
        self.last_status = None

    def print_status(self, decision, embedding_valid=False, face_detected=False):
        """Print status to console with live updates"""
        status_icon_map = {
            AuthStatus.AUTHORIZED: "✅",
            AuthStatus.UNAUTHORIZED: "❌",
            AuthStatus.NO_FACE: "⚠️ ",
        }

        status = decision["state"]
        icon = status_icon_map.get(status, "❓")
        
        face_status = "👤" if face_detected else "  "
        embed_status = "-" if embedding_valid else "x"

        output = (
            f"{icon} {status.value:12} | {face_status} | "
            f"User: {decision['last_user'] or 'Unknown':12} | "
            f"Sim: {decision['similarity']:.2f} | "
            f"Good: {decision['good_frames']:2d} Bad: {decision['bad_frames']:2d}"
        )
        
        # Only print if status changed (reduces spam)
        if output != self.last_status:
            print(output)
            self.last_status = output
