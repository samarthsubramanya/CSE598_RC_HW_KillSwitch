"""
Face Recognition Module

Two distinct responsibilities:
  1. PSFaceProcessor  — detects faces and computes 128-D embeddings on the PS (ARM)
                        using the face_recognition library (dlib + ResNet-34).
  2. FaceRecognizer   — matches embeddings against the UserDatabase and maintains
                        the hysteresis authorization state machine.
  3. UserDatabase     — persistent JSON store for enrolled user embeddings.

The 128-D float32 embeddings produced by PSFaceProcessor are L2-normalized and
compatible with the UserDatabase format.  FaceRecognizer is unchanged from the
original design — it only sees numpy vectors regardless of how they were computed.
"""

import numpy as np
import logging
import cv2
import json
from typing import List, Tuple, Optional
from collections import deque
from enum import Enum
from pathlib import Path

try:
    import face_recognition as fr
    FR_AVAILABLE = True
except ImportError:
    FR_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "face_recognition not installed — install with: pip install face-recognition"
    )

logger = logging.getLogger(__name__)


# =====================================================================
# PS-side face processor (replaces FPGA CNN + Haar)
# =====================================================================

class PSFaceProcessor:
    """
    Detects faces and computes 128-D embeddings entirely on the ARM CPU.

    Uses the face_recognition library which wraps dlib:
      - Detection: HOG-based detector (fast, good for frontal faces)
      - Embedding: ResNet-34 model → 128-D unit-norm vector

    The embedding format is identical to what the original FPGA CNN was
    intended to produce, so UserDatabase and FaceRecognizer are unchanged.
    """

    def __init__(self, detection_model: str = "hog"):
        """
        Args:
            detection_model: "hog" (faster, CPU-friendly) or "cnn" (more accurate,
                             uses dlib's CNN — slower on Cortex-A9).
                             "hog" is recommended for real-time on PYNQ-Z2.
        """
        if not FR_AVAILABLE:
            raise ImportError(
                "face_recognition library is required. "
                "Install: pip install face-recognition"
            )
        self.detection_model = detection_model
        logger.info(f"PSFaceProcessor ready (model={detection_model})")

    def process_frame(
        self, frame: np.ndarray
    ) -> Tuple[List[Tuple[int, int, int, int]], List[np.ndarray]]:
        """
        Detect faces and compute embeddings for a single camera frame.

        Args:
            frame: BGR frame from OpenCV (H×W×3, uint8).

        Returns:
            faces      : List of (x1, y1, x2, y2) bounding boxes in pixel coords.
            embeddings : Corresponding list of 128-D float32 unit-norm vectors.
                         Empty lists if no faces detected.
        """
        # face_recognition expects RGB
        rgb = frame[:, :, ::-1]

        # Detect face locations — returns list of (top, right, bottom, left)
        locations = fr.face_locations(rgb, model=self.detection_model)

        if not locations:
            return [], []

        # Compute 128-D embeddings for all detected faces at once
        raw_encodings = fr.face_encodings(rgb, locations)

        faces = []
        embeddings = []

        for (top, right, bottom, left), enc in zip(locations, raw_encodings):
            # Convert to (x1, y1, x2, y2) format used throughout the project
            faces.append((left, top, right, bottom))

            # face_recognition encodings are already unit-norm float64; cast to float32
            emb = enc.astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 1e-8:
                emb = emb / norm
            embeddings.append(emb)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Detected {len(faces)} face(s)")

        return faces, embeddings


# =====================================================================
# Authorization state machine
# =====================================================================

class AuthStatus(Enum):
    AUTHORIZED   = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNKNOWN      = "UNKNOWN"


class FaceRecognizer:
    """
    Matches a face embedding against the enrolled user database and
    maintains a hysteresis state machine to avoid flickering.

    Hysteresis prevents a single bad frame from locking out an authorized
    user, and requires several consecutive good frames before granting access.
    """

    def __init__(self, user_db, similarity_threshold: float = 0.6):
        """
        Args:
            user_db:              UserDatabase instance.
            similarity_threshold: Cosine similarity required for a match (0–1).
                                  0.6 is a reasonable starting point; lower values
                                  are more permissive, higher values are stricter.
        """
        self.user_db = user_db
        self.similarity_threshold = similarity_threshold

        # Hysteresis counters
        self.current_status  = AuthStatus.UNKNOWN
        self.bad_frame_count  = 0
        self.good_frame_count = 0
        self.lock_threshold   = 3   # consecutive bad frames → UNAUTHORIZED
        self.unlock_threshold = 8   # consecutive good frames → AUTHORIZED

        logger.info(f"Recognizer ready (threshold={similarity_threshold})")

    def recognize(self, embedding: np.ndarray) -> dict:
        """
        Match embedding and update authorization state.

        Args:
            embedding: 128-D unit-norm float32 vector.

        Returns:
            {
              'status':        AuthStatus,
              'user':          str | None,   # recognized username if AUTHORIZED
              'confidence':    float,        # best cosine similarity (0–1)
              'is_authorized': bool,
            }
        """
        if embedding is None or len(embedding) == 0:
            return {'status': AuthStatus.UNKNOWN, 'user': None,
                    'confidence': 0.0, 'is_authorized': False}

        users = self.user_db.get_all_users()
        if not users:
            return {'status': AuthStatus.UNKNOWN, 'user': None,
                    'confidence': 0.0, 'is_authorized': False}

        # Find best-matching enrolled user
        best_user       = None
        best_similarity = -1.0
        for username, stored_emb in users.items():
            sim = self._cosine_similarity(embedding, stored_emb)
            if sim > best_similarity:
                best_similarity = sim
                best_user = username

        # Hysteresis state machine
        if best_similarity >= self.similarity_threshold:
            self.good_frame_count += 1
            self.bad_frame_count   = 0
            if self.good_frame_count >= self.unlock_threshold:
                self.current_status = AuthStatus.AUTHORIZED
        else:
            self.bad_frame_count  += 1
            self.good_frame_count  = 0
            if self.bad_frame_count >= self.lock_threshold:
                self.current_status = AuthStatus.UNAUTHORIZED

        return {
            'status':        self.current_status,
            'user':          best_user if self.current_status == AuthStatus.AUTHORIZED else None,
            'confidence':    best_similarity,
            'is_authorized': self.current_status == AuthStatus.AUTHORIZED,
        }

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        n1 = np.linalg.norm(vec1) + 1e-8
        n2 = np.linalg.norm(vec2) + 1e-8
        return float(np.clip(np.dot(vec1 / n1, vec2 / n2), 0.0, 1.0))


# =====================================================================
# User database
# =====================================================================

class UserDatabase:
    """Persistent enrollment store — JSON file with username → 128-D embedding."""

    EMBEDDING_DIM = 128

    def __init__(self, db_path: str = "data/users.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict = {}
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    raw = json.load(f)
                self.data = {
                    u: np.array(e, dtype=np.float32)
                    for u, e in raw.items()
                }
                logger.info(f"Loaded {len(self.data)} user(s) from {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to load database: {e}")
                self.data = {}
        else:
            logger.info("No existing database — starting fresh")

    def _save(self):
        try:
            with open(self.db_path, 'w') as f:
                json.dump(
                    {u: e.tolist() for u, e in self.data.items()},
                    f, indent=2
                )
        except Exception as e:
            logger.error(f"Failed to save database: {e}")

    def add_user(self, username: str, embedding: np.ndarray):
        if embedding is None or len(embedding) != self.EMBEDDING_DIM:
            raise ValueError(f"Embedding must be {self.EMBEDDING_DIM}-D")
        emb = embedding.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 1e-8:
            emb = emb / norm
        self.data[username] = emb
        self._save()
        logger.info(f"User '{username}' enrolled")

    def get_user(self, username: str) -> Optional[np.ndarray]:
        return self.data.get(username)

    def get_all_users(self) -> dict:
        return self.data.copy()

    def remove_user(self, username: str):
        if username in self.data:
            del self.data[username]
            self._save()
            logger.info(f"User '{username}' removed")

    def clear_all(self):
        self.data.clear()
        self._save()
        logger.info("Database cleared")
