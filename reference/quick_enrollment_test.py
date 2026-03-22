#!/usr/bin/env python3
"""
Quick enrollment test with real camera
"""

import sys
sys.path.insert(0, '.')

from camera import CameraHandler
from face_detection import FaceDetector
from model import FaceEmbeddingModel
import time

def quick_test():
    print("\n=== Quick Enrollment Test ===\n")
    
    print("Initializing...")
    camera = CameraHandler(source=0, width=640, height=480)
    detector = FaceDetector()
    model = FaceEmbeddingModel()
    
    if not camera.connect():
        print("❌ Camera connection failed")
        return
    
    print("✅ Camera ready\n")
    
    print("Capturing 5 frames of your face...")
    print("(Keep your face in the same position)\n")
    
    embeddings = []
    time.sleep(1)
    
    for i in range(5):
        frame = camera.read_frame()
        if frame is None:
            print(f"❌ Frame {i+1}: Failed to read")
            continue
        
        faces = detector.detect(frame)
        if len(faces) == 0:
            print(f"❌ Frame {i+1}: No face detected")
            time.sleep(0.5)
            continue
        
        roi = detector.extract_roi(frame, faces[0])
        if roi is None:
            print(f"❌ Frame {i+1}: Failed to extract ROI")
            time.sleep(0.5)
            continue
        
        embedding = model.compute_embedding(roi)
        if embedding is None:
            print(f"❌ Frame {i+1}: Failed to compute embedding")
            time.sleep(0.5)
            continue
        
        embeddings.append(embedding)
        print(f"✅ Frame {i+1}: Captured embedding")
        time.sleep(0.3)
    
    camera.disconnect()
    
    if len(embeddings) < 2:
        print("❌ Not enough embeddings captured")
        return
    
    print(f"\n✅ Captured {len(embeddings)} embeddings\n")
    
    # Compute similarity between all pairs
    print("Analyzing similarity between frames:\n")
    
    import numpy as np
    similarities = []
    for i in range(len(embeddings)):
        for j in range(i+1, len(embeddings)):
            sim = np.dot(embeddings[i], embeddings[j])
            similarities.append(sim)
            print(f"  Frame {i+1} vs Frame {j+1}: {sim:.4f}")
    
    if similarities:
        avg_sim = np.mean(similarities)
        min_sim = np.min(similarities)
        max_sim = np.max(similarities)
        
        print(f"\nStatistics:")
        print(f"  Average similarity: {avg_sim:.4f}")
        print(f"  Min similarity: {min_sim:.4f}")
        print(f"  Max similarity: {max_sim:.4f}")
        
        print(f"\n✅ For enrollment, use threshold around {min_sim - 0.05:.2f} (to be permissive)")
        print(f"✅ For recognition, use threshold around {avg_sim - 0.1:.2f}")

if __name__ == "__main__":
    quick_test()
