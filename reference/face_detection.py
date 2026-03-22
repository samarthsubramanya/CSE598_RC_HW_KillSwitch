"""
Face detection module
Uses OpenCV DNN for robust face detection (no retraining required)
"""

import cv2
import numpy as np
import logging
import os

logger = logging.getLogger(__name__)

# Pre-trained face detection model files (will be downloaded on first use)
FACE_DETECTION_MODEL_PATH = "models/opencv_face_detector_uint8.pb"
FACE_DETECTION_CONFIG_PATH = "models/opencv_face_detector.pbtxt"


class FaceDetector:
    """Detects faces in images using OpenCV DNN"""

    def __init__(self, model_path=None, config_path=None, confidence_threshold=0.7):
        """
        Initialize face detector

        Args:
            model_path: Path to .pb model file
            config_path: Path to .pbtxt config file
            confidence_threshold: Min confidence for detections
        """
        self.confidence_threshold = confidence_threshold
        self.net = None
        self.model_loaded = False

        # Try to load the model
        if model_path and config_path:
            self.load_model(model_path, config_path)
        else:
            self._load_default_model()

    def _load_default_model(self):
        """Load default Haar Cascade for faster initial deployment"""
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(cascade_path)
        if not self.cascade.empty():
            self.model_loaded = True
            logger.info("Loaded Haar Cascade face detector")
        else:
            logger.warning("Failed to load Haar Cascade")

    def load_model(self, model_path, config_path):
        """Load pre-trained face detection model"""
        try:
            if os.path.exists(model_path) and os.path.exists(config_path):
                self.net = cv2.dnn.readNetFromTensorflow(model_path, config_path)
                self.model_loaded = True
                logger.info("Loaded TensorFlow face detection model")
            else:
                logger.warning(
                    f"Model files not found, falling back to Haar Cascade: {model_path}"
                )
                self._load_default_model()
        except Exception as e:
            logger.error(f"Failed to load DNN model: {e}, using Haar Cascade")
            self._load_default_model()

    def detect(self, frame):
        """
        Detect faces in frame

        Args:
            frame (numpy.ndarray): Input image

        Returns:
            list: List of face bounding boxes [(x, y, w, h), ...]
        """
        if not self.model_loaded:
            logger.error("Model not loaded")
            return []

        if frame is None:
            return []

        # Convert to grayscale for Haar Cascade
        if hasattr(self, "cascade"):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            return [(x, y, x + w, y + h) for x, y, w, h in faces]

        # DNN-based detection
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), [104, 117, 123], False)
        self.net.setInput(blob)
        detections = self.net.forward()

        faces = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > self.confidence_threshold:
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                x1, y1, x2, y2 = box.astype("int")
                faces.append((x1, y1, x2, y2))

        return faces

    def extract_roi(self, frame, face_bbox, margin=10):
        """
        Extract region of interest (face ROI)

        Args:
            frame (numpy.ndarray): Input image
            face_bbox (tuple): (x1, y1, x2, y2) face bounding box
            margin (int): Pixel margin around face

        Returns:
            numpy.ndarray: Cropped face region or None
        """
        x1, y1, x2, y2 = face_bbox
        x1 = max(0, x1 - margin)
        y1 = max(0, y1 - margin)
        x2 = min(frame.shape[1], x2 + margin)
        y2 = min(frame.shape[0], y2 + margin)

        roi = frame[y1:y2, x1:x2]
        return roi if roi.size > 0 else None
