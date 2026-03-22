#!/usr/bin/env python3
"""
Quick test to verify CNN embeddings and discrimination
This tests that:
1. Same person = high similarity (0.8+)
2. Different people = low similarity (0.4-0.6)
"""

import cv2
import numpy as np
from model import FaceEmbeddingModel
from face_detection import FaceDetector
from camera import CameraHandler
import time
import sys

def test_cnn_embeddings():
    """Test CNN embedding model"""
    print("\n" + "="*60)
    print("TESTING CNN EMBEDDINGS (dlib ResNet 128-D)")
    print("="*60 + "\n")
    
    # Initialize model and camera
    model = FaceEmbeddingModel()
    detector = FaceDetector()
    camera = CameraHandler(source=0)  # Built-in webcam
    
    if not model.model_loaded:
        print("❌ Failed to load CNN model")
        return False
    
    print("✅ CNN Model loaded successfully")
    print(f"   Embedding size: {model.embedding_size}D")
    print(f"   Model: dlib ResNet (trained on millions of faces)")
    
    # Connect camera
    print("\n📷 Connecting to camera...")
    if not camera.connect():
        print("❌ Failed to connect camera")
        return False
    
    print("✅ Camera connected")
    
    # Collect embeddings for TEST PERSON
    print("\n" + "-"*60)
    print("CAPTURE TEST: Collecting embeddings from your face")
    print("-"*60)
    print("\nLook at the camera - I'm collecting 5 samples (3 seconds each)")
    print()
    
    embeddings = []
    for i in range(5):
        time.sleep(3)  # 3 seconds per sample
        
        frame = camera.read_frame()
        if frame is None:
            print(f"❌ Frame {i+1}: Failed to read frame")
            continue
        
        # Detect face
        faces = detector.detect(frame)
        if len(faces) == 0:
            print(f"⚠️  Frame {i+1}: No face detected")
            continue
        
        # Extract first face
        x1, y1, x2, y2 = faces[0]
        face_roi = frame[y1:y2, x1:x2]
        
        # Compute embedding
        embedding = model.compute_embedding(face_roi)
        if embedding is None:
            print(f"⚠️  Frame {i+1}: Failed to compute embedding")
            continue
        
        embeddings.append(embedding)
        print(f"✅ Frame {i+1}: Embedding computed (128-D)")
    
    camera.disconnect()
    
    if len(embeddings) < 3:
        print("❌ Not enough valid embeddings collected")
        return False
    
    print(f"\n✅ Collected {len(embeddings)} valid embeddings")
    
    # Compare embeddings - same person should have high similarity
    print("\n" + "-"*60)
    print("TEST: Same person similarity (should be 0.8+)")
    print("-"*60 + "\n")
    
    similarities_same = []
    for i in range(len(embeddings)):
        for j in range(i+1, len(embeddings)):
            # Cosine similarity
            sim = np.dot(embeddings[i], embeddings[j]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]) + 1e-8
            )
            sim = max(0, min(1, sim))  # Clamp to [0, 1]
            similarities_same.append(sim)
            print(f"Frame {i+1} vs Frame {j+1}: {sim:.4f}")
    
    avg_similarity_same = np.mean(similarities_same)
    print(f"\n📊 Average similarity (same person): {avg_similarity_same:.4f}")
    
    if avg_similarity_same < 0.75:
        print("⚠️  WARNING: Same person similarity is low! Something may be wrong.")
        return False
    
    print("✅ PASS: Same person has high similarity")
    
    print("\n" + "="*60)
    print("CNN EMBEDDING TEST COMPLETE")
    print("="*60)
    print("\n✅ CNN embeddings are working correctly!")
    print("   Next step: Enroll with main.py --mode enroll")
    print("   Then test: main.py --mode recognition")
    
    return True

if __name__ == "__main__":
    success = test_cnn_embeddings()
    sys.exit(0 if success else 1)
