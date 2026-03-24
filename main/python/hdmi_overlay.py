"""
HDMI Overlay Generator
Creates visual overlays: bounding boxes, similarity scores, status text
"""

import cv2
import numpy as np
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class OverlayGenerator:
    """Generates visual overlays for HDMI output"""
    
    def __init__(self, width: int = 1280, height: int = 720):
        """
        Initialize overlay generator
        
        Args:
            width (int): Frame width
            height (int): Frame height
        """
        self.width = width
        self.height = height
        
        # Color palette
        self.COLOR_AUTHORIZED = (0, 255, 0)    # Green
        self.COLOR_UNAUTHORIZED = (0, 0, 255)  # Red
        self.COLOR_UNKNOWN = (255, 255, 0)     # Cyan
        self.COLOR_TEXT = (255, 255, 255)      # White
        
        logger.info(f"OverlayGenerator initialized: {width}x{height}")
    
    def draw_boxes_and_status(
        self,
        frame: np.ndarray,
        recognition_results: List[Tuple],
        embeddings: List[np.ndarray]
    ) -> np.ndarray:
        """
        Draw bounding boxes and recognition status on frame
        
        Args:
            frame (np.ndarray): Input frame (BGR)
            recognition_results (List): List of (face_box, status_dict) tuples
            embeddings (List): List of embeddings for additional info
        
        Returns:
            Annotated frame
        """
        output_frame = frame.copy()
        
        for i, ((x1, y1, x2, y2), status) in enumerate(recognition_results):
            # Choose color based on status
            if status.get('is_authorized', False):
                color = self.COLOR_AUTHORIZED
                status_text = "AUTHORIZED"
                user_text = f"User: {status['user']}"
            else:
                color = self.COLOR_UNAUTHORIZED
                status_text = "UNAUTHORIZED"
                user_text = "Unknown"
            
            # Draw bounding box
            cv2.rectangle(output_frame, (x1, y1), (x2, y2), color, 3)
            
            # Draw status text above box
            font_scale = 0.8
            thickness = 2
            
            # Status label
            cv2.putText(
                output_frame,
                status_text,
                (x1, y1 - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                thickness
            )
            
            # User name
            cv2.putText(
                output_frame,
                user_text,
                (x1, y1 - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 0.7,
                self.COLOR_TEXT,
                thickness
            )
            
            # Confidence score
            confidence = status.get('confidence', 0.0)
            conf_text = f"Match: {confidence:.3f}"
            cv2.putText(
                output_frame,
                conf_text,
                (x1, y2 + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 0.7,
                self.COLOR_TEXT,
                thickness
            )
        
        # Draw frame info (FPS, number of faces)
        self._draw_frame_info(output_frame, len(recognition_results))
        
        return output_frame
    
    def _draw_frame_info(self, frame: np.ndarray, num_faces: int):
        """Draw frame metadata (FPS, face count, etc.)"""
        y_pos = 30
        
        # Face count
        cv2.putText(
            frame,
            f"Faces: {num_faces}",
            (20, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            self.COLOR_TEXT,
            2
        )
        
        # Status indicator
        cv2.putText(
            frame,
            "[FPGA Accelerated]",
            (20, y_pos + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            1
        )
    
    def draw_simple_status(
        self,
        frame: np.ndarray,
        authorized: bool,
        user: str = None,
        confidence: float = 0.0
    ) -> np.ndarray:
        """
        Draw simple status overlay (for debugging)
        
        Args:
            frame (np.ndarray): Input frame
            authorized (bool): Authorization status
            user (str): Username if authorized
            confidence (float): Confidence score
        
        Returns:
            Annotated frame
        """
        output_frame = frame.copy()
        
        # Draw large status text
        status_text = "AUTHORIZED" if authorized else "UNAUTHORIZED"
        color = self.COLOR_AUTHORIZED if authorized else self.COLOR_UNAUTHORIZED
        
        # Calculate text size and position
        font_scale = 2.0
        thickness = 3
        text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        text_width = text_size[0][0]
        text_height = text_size[0][1]
        
        x_pos = (self.width - text_width) // 2
        y_pos = self.height // 2 + text_height
        
        # Draw background
        cv2.rectangle(
            output_frame,
            (x_pos - 10, y_pos - text_height - 20),
            (x_pos + text_width + 10, y_pos + 10),
            (0, 0, 0),
            -1
        )
        
        # Draw text
        cv2.putText(
            output_frame,
            status_text,
            (x_pos, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness
        )
        
        # Draw user info if available
        if user:
            info_text = f"User: {user} | Confidence: {confidence:.3f}"
            cv2.putText(
                output_frame,
                info_text,
                (20, self.height - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                self.COLOR_TEXT,
                2
            )
        
        return output_frame
