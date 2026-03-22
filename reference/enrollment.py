"""
User enrollment/registration process
Captures multiple samples and computes averaged embedding
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class EnrollmentManager:
    """Manages user enrollment process"""

    def __init__(self, face_detector, embedding_model, user_db, samples_per_user=15):
        """
        Initialize enrollment manager

        Args:
            face_detector: FaceDetector instance
            embedding_model: FaceEmbeddingModel instance
            user_db: UserDatabase instance
            samples_per_user: Number of samples to collect per user
        """
        self.face_detector = face_detector
        self.embedding_model = embedding_model
        self.user_db = user_db
        self.samples_per_user = samples_per_user

        # Enrollment state
        self.enrolling = False
        self.current_user = None
        self.collected_embeddings = []

    def start_enrollment(self, username):
        """
        Start enrollment for a new user

        Args:
            username (str): Username to enroll
        """
        if username in self.user_db.list_users():
            logger.warning(f"User {username} already exists, re-enrolling...")

        self.enrolling = True
        self.current_user = username
        self.collected_embeddings = []
        logger.info(f"Started enrollment for {username}")

    def process_frame(self, frame):
        """
        Process frame during enrollment (detect face and capture embedding)

        Args:
            frame (numpy.ndarray): Input frame

        Returns:
            dict: {
                "success": bool,
                "samples_collected": int,
                "progress": float (0-1),
                "message": str
            }
        """
        if not self.enrolling:
            return {
                "success": False,
                "samples_collected": 0,
                "progress": 0.0,
                "message": "Not in enrollment mode",
            }

        if frame is None:
            return {
                "success": False,
                "samples_collected": len(self.collected_embeddings),
                "progress": len(self.collected_embeddings) / self.samples_per_user,
                "message": "No frame",
            }

        # Detect faces
        faces = self.face_detector.detect(frame)

        if len(faces) == 0:
            return {
                "success": False,
                "samples_collected": len(self.collected_embeddings),
                "progress": len(self.collected_embeddings) / self.samples_per_user,
                "message": "No face detected",
            }

        if len(faces) > 1:
            return {
                "success": False,
                "samples_collected": len(self.collected_embeddings),
                "progress": len(self.collected_embeddings) / self.samples_per_user,
                "message": "Multiple faces detected",
            }

        # Extract ROI and compute embedding
        face_bbox = faces[0]
        roi = self.face_detector.extract_roi(frame, face_bbox)

        if roi is None:
            return {
                "success": False,
                "samples_collected": len(self.collected_embeddings),
                "progress": len(self.collected_embeddings) / self.samples_per_user,
                "message": "Failed to extract ROI",
            }

        embedding = self.embedding_model.compute_embedding(roi)

        if embedding is None:
            return {
                "success": False,
                "samples_collected": len(self.collected_embeddings),
                "progress": len(self.collected_embeddings) / self.samples_per_user,
                "message": "Failed to compute embedding",
            }

        # Add to collection
        self.collected_embeddings.append(embedding)
        logger.info(f"Captured sample {len(self.collected_embeddings)}")

        success = len(self.collected_embeddings) >= self.samples_per_user
        progress = min(
            1.0, len(self.collected_embeddings) / self.samples_per_user
        )

        return {
            "success": success,
            "samples_collected": len(self.collected_embeddings),
            "progress": progress,
            "message": f"Sample {len(self.collected_embeddings)}/{self.samples_per_user}",
        }

    def finish_enrollment(self):
        """
        Finish enrollment and save averaged embedding

        Returns:
            bool: True if enrollment successful
        """
        if not self.enrolling or len(self.collected_embeddings) == 0:
            logger.error("No samples collected for enrollment")
            return False

        try:
            # Average embeddings
            avg_embedding = np.mean(self.collected_embeddings, axis=0)
            # Normalize
            avg_embedding = avg_embedding / (np.linalg.norm(avg_embedding) + 1e-8)

            # Store in database
            success = self.user_db.enroll_user(self.current_user, avg_embedding)

            if success:
                logger.info(
                    f"Enrollment complete for {self.current_user} "
                    f"({len(self.collected_embeddings)} samples)"
                )

            self.enrolling = False
            self.current_user = None
            self.collected_embeddings = []

            return success

        except Exception as e:
            logger.error(f"Error finishing enrollment: {e}")
            return False

    def cancel_enrollment(self):
        """Cancel current enrollment"""
        logger.info(f"Cancelled enrollment for {self.current_user}")
        self.enrolling = False
        self.current_user = None
        self.collected_embeddings = []

    def is_enrolling(self):
        """Check if currently in enrollment mode"""
        return self.enrolling

    def get_progress(self):
        """Get current enrollment progress"""
        if not self.enrolling:
            return 0.0
        return min(1.0, len(self.collected_embeddings) / self.samples_per_user)
