"""
Face recognition and kill switch logic
Matches embeddings and applies authorization decision with hysteresis
"""

import numpy as np
import logging
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class AuthStatus(Enum):
    """Authorization status"""

    AUTHORIZED = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"
    NO_FACE = "NO_FACE"
    UNKNOWN = "UNKNOWN"


class FaceRecognizer:
    """Performs face recognition and maintains authorization state"""

    def __init__(
        self,
        user_db,
        similarity_threshold=0.6,
        lock_threshold=3,
        unlock_threshold=8,
    ):
        """
        Initialize face recognizer

        Args:
            user_db (UserDatabase): User database instance
            similarity_threshold (float): Cosine similarity threshold (0-1)
            lock_threshold (int): Number of bad frames to trigger lock
            unlock_threshold (int): Number of good frames to unlock
        """
        self.user_db = user_db
        self.similarity_threshold = similarity_threshold
        self.lock_threshold = lock_threshold
        self.unlock_threshold = unlock_threshold

        # Hysteresis/state tracking
        self.state = AuthStatus.NO_FACE
        self.bad_frame_count = 0
        self.good_frame_count = 0
        self.last_matched_user = None

        # Ring buffer for smoothing decisions (apply majority voting)
        self.frame_history = deque(maxlen=10)

    def set_similarity_threshold(self, threshold):
        """Adjust recognition threshold"""
        self.similarity_threshold = threshold
        logger.info(f"Similarity threshold set to {threshold}")

    def cosine_similarity(self, vec1, vec2):
        """
        Compute cosine similarity between two vectors

        Args:
            vec1 (numpy.ndarray): Embedding 1
            vec2 (numpy.ndarray): Embedding 2

        Returns:
            float: Similarity score (0-1)
        """
        if vec1 is None or vec2 is None:
            return 0.0

        norm1 = np.linalg.norm(vec1) + 1e-8
        norm2 = np.linalg.norm(vec2) + 1e-8
        similarity = np.dot(vec1, vec2) / (norm1 * norm2)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, similarity))

    def recognize(self, embedding):
        """
        Recognize a face from embedding

        Args:
            embedding (numpy.ndarray): Face embedding (64-D)

        Returns:
            dict: {
                "user": matched username or None,
                "similarity": best similarity score,
                "status": AuthStatus
            }
        """
        if embedding is None:
            result = {
                "user": None,
                "similarity": 0.0,
                "status": AuthStatus.NO_FACE,
            }
        else:
            # Find best matching user
            best_user = None
            best_similarity = 0.0

            for username in self.user_db.list_users():
                user_embedding = self.user_db.get_user_embedding(username)
                similarity = self.cosine_similarity(embedding, user_embedding)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_user = username

            # Determine status
            if best_similarity > self.similarity_threshold and best_user:
                status = AuthStatus.AUTHORIZED
            else:
                status = AuthStatus.UNAUTHORIZED

            result = {
                "user": best_user,
                "similarity": best_similarity,
                "status": status,
            }

        return result

    def update_state(self, recognition_result):
        """
        Update authorization state with hysteresis

        Args:
            recognition_result (dict): Result from recognize()

        Returns:
            dict: Current state with decision
        """
        current_status = recognition_result["status"]

        # Track frame history for smoothing
        self.frame_history.append(current_status)

        # Update counters
        if current_status == AuthStatus.AUTHORIZED:
            self.good_frame_count += 1
            self.bad_frame_count = 0
            self.last_matched_user = recognition_result["user"]
        else:
            self.bad_frame_count += 1
            self.good_frame_count = 0

        # Apply hysteresis: lock/unlock based on consecutive frame counts
        if self.bad_frame_count >= self.lock_threshold:
            self.state = AuthStatus.UNAUTHORIZED
            self.bad_frame_count = 0

        if self.good_frame_count >= self.unlock_threshold:
            self.state = AuthStatus.AUTHORIZED
            self.good_frame_count = 0

        decision = {
            "state": self.state,
            "last_user": self.last_matched_user,
            "similarity": recognition_result["similarity"],
            "good_frames": self.good_frame_count,
            "bad_frames": self.bad_frame_count,
        }

        return decision

    def process_frame(self, embedding):
        """
        Process a single frame (recognize + update state)

        Args:
            embedding (numpy.ndarray): Face embedding

        Returns:
            dict: Authorization decision
        """
        recognition_result = self.recognize(embedding)
        decision = self.update_state(recognition_result)

        return decision

    def get_current_state(self):
        """Get current authorization state"""
        return {
            "state": self.state,
            "last_user": self.last_matched_user,
            "bad_frames": self.bad_frame_count,
            "good_frames": self.good_frame_count,
        }

    def force_unlock(self):
        """Force unlock (admin override)"""
        self.state = AuthStatus.AUTHORIZED
        self.good_frame_count = 0
        self.bad_frame_count = 0
        logger.info("System force unlocked")

    def force_lock(self):
        """Force lock (emergency)"""
        self.state = AuthStatus.UNAUTHORIZED
        self.good_frame_count = 0
        self.bad_frame_count = 0
        logger.warning("System force locked")
