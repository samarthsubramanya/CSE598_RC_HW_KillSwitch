"""
Face embedding model
Computes 128-D embeddings using dlib's ResNet CNN for face recognition
Uses the face_recognition library which is trained on millions of faces
"""

import cv2
import numpy as np
import logging
import os

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False
    logger = logging.getLogger(__name__)
    logger.warning("face_recognition not installed. Install with: pip install face-recognition")

logger = logging.getLogger(__name__)

# Model paths (can be customized)
EMBEDDING_MODEL_PATH = "models/openface_nn4.small2.v1.t7"


class FaceEmbeddingModel:
    """Computes face embeddings using a pretrained model"""

    def __init__(self, model_path=EMBEDDING_MODEL_PATH, embedding_size=128):
        """
        Initialize embedding model

        Args:
            model_path: Path to pretrained model (Torch format)
            embedding_size: Dimensionality of output embedding
        """
        self.model_path = model_path
        self.embedding_size = embedding_size
        self.net = None
        self.model_loaded = False

        self.load_model()

    def load_model(self):
        """Load pretrained face embedding model using face_recognition library"""
        if not HAS_FACE_RECOGNITION:
            logger.error("face_recognition library not installed!")
            self.model_loaded = False
            return
        
        try:
            # The face_recognition library automatically loads dlib's CNN model
            # Just verify it works by checking it loads
            test_embedding = face_recognition.face_encodings(np.zeros((10, 10, 3), dtype=np.uint8))
            self.model_loaded = True
            logger.info("✅ Loaded dlib ResNet CNN face embedding model (128-D)")
        except Exception as e:
            logger.error(f"Failed to load face_recognition model: {e}")
            self.model_loaded = False

    def _create_dummy_model(self):
        """Fallback: Create a simple dummy model for testing"""
        if HAS_FACE_RECOGNITION:
            self.load_model()
        else:
            self.model_loaded = False
            logger.warning("face_recognition not available")

    def preprocess(self, face_roi):
        """
        Preprocess face ROI for face_recognition library
        Converts BGR to RGB (face_recognition expects RGB)

        Args:
            face_roi (numpy.ndarray): Face image (BGR from OpenCV)

        Returns:
            numpy.ndarray: RGB face image
        """
        if face_roi is None:
            return None

        # Convert BGR to RGB (face_recognition expects RGB)
        if len(face_roi.shape) == 3 and face_roi.shape[2] == 3:
            face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
        else:
            face_rgb = face_roi

        return face_rgb

    def compute_embedding(self, face_roi):
        """
        Compute embedding for a face region using dlib's ResNet CNN (128-D)

        Args:
            face_roi (numpy.ndarray): Face image (BGR from OpenCV)

        Returns:
            numpy.ndarray: Embedding vector (128-D) normalized to unit length
        """
        if not HAS_FACE_RECOGNITION:
            logger.error("face_recognition library not available")
            return None
        
        if not self.model_loaded:
            logger.error("Model not loaded")
            return None

        face_rgb = self.preprocess(face_roi)
        if face_rgb is None:
            return None

        try:
            # face_recognition.face_encodings expects a list of face images
            # and returns a list of encodings (128-D vectors)
            encodings = face_recognition.face_encodings(face_rgb)
            
            if len(encodings) == 0:
                logger.warning("No face found in ROI for embedding")
                return None
            
            # Take the first encoding
            embedding = encodings[0].astype(np.float32)
            
            # Normalize to unit length (important for cosine similarity)
            embedding = embedding / (np.linalg.norm(embedding) + 1e-8)

            return embedding

        except Exception as e:
            logger.error(f"Error computing embedding: {e}")
            return None

    def quantize_to_int8(self, embedding):
        """
        Quantize embedding to INT8 (for FPGA deployment)

        Args:
            embedding (numpy.ndarray): Float32 embedding

        Returns:
            numpy.ndarray: INT8 quantized embedding (-128 to 127)
        """
        if embedding is None:
            return None

        # Scale from [-1, 1] to [-128, 127]
        quantized = np.clip(embedding * 127, -128, 127).astype(np.int8)
        return quantized

    def dequantize_from_int8(self, quantized):
        """
        Dequantize INT8 embedding back to float

        Args:
            quantized (numpy.ndarray): INT8 embedding

        Returns:
            numpy.ndarray: Float32 embedding
        """
        dequantized = quantized.astype(np.float32) / 127.0
        return dequantized
