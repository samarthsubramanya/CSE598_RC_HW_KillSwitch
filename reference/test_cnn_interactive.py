#!/usr/bin/env python3
"""
Interactive CNN embedding test with visual feedback
Shows camera feed and detects when face is in frame
"""

import cv2
import numpy as np
from model import FaceEmbeddingModel
from face_detection import FaceDetector
from camera import CameraHandler
import time
import sys

def test_cnn_with_feedback():
    """Test CNN embeddings with visual feedback"""
    print("\n" + "="*60)
    print("CNN EMBEDDING TEST (Interactive)")
    print("="*60 + "\n")
    
    # Load model
    model = FaceEmbeddingModel()
    if not model.model_loaded:
        print("❌ Failed to load CNN model")
        return False
    
    print("✅ CNN Model loaded (dlib ResNet 128-D)")
    
    # Initialize detector
    detector = FaceDetector()
    print("✅ Face detector ready (Haar Cascade)")
    
    # Connect camera with more initialization time
    print("\n📷 Connecting to camera...")
    camera = CameraHandler(source=0)
    
    if not camera.connect():
        print("❌ Failed to connect camera")
        return False
    
    print("✅ Camera connected")
    time.sleep(2)  # Give camera time to initialize
    
    print("\n" + "-"*60)
    print("TEST: Will collect 5 embeddings (look at camera)")
    print("-"*60 + "\n")
    
    embeddings = []
    frame_count = 0
    face_count = 0
    
    # Collect frames for 45 seconds max
    start_time = time.time()
    timeout = 45
    
    while len(embeddings) < 5 and (time.time() - start_time) < timeout:
        frame_count += 1
        
        frame = camera.read_frame()
        if frame is None:
            print(f"❌ Frame read failed")
            time.sleep(0.5)
            continue
        
        # Try to detect face
        faces = detector.detect(frame)
        
        if len(faces) == 0:
            # No face - show progress
            if frame_count % 10 == 0:
                print(f"⏳ {len(embeddings)}/5 embeddings - waiting for face...")
            time.sleep(0.1)
            continue
        
        # Face detected!
        face_count += 1
        x1, y1, x2, y2 = faces[0]
        face_roi = frame[y1:y2, x1:x2]
        
        # Compute embedding
        embedding = model.compute_embedding(face_roi)
        if embedding is None:
            print(f"⚠️  Face detected but embedding failed (frame {frame_count})")
            time.sleep(0.1)
            continue
        
        embeddings.append(embedding)
        print(f"✅ Embedding {len(embeddings)}/5 captured (face detected in frame {frame_count})")
        
        # Wait a bit before next capture
        time.sleep(0.5)
    
    camera.disconnect()
    
    if len(embeddings) < 3:
        print(f"\n❌ Failed: Only collected {len(embeddings)} embeddings (need 3+)")
        print(f"   Total frames read: {frame_count}")
        print(f"   Frames with face: {face_count}")
        return False
    
    print(f"\n✅ Collected {len(embeddings)} embeddings from {face_count} faces in {frame_count} frames")
    
    # Analyze embeddings
    print("\n" + "-"*60)
    print("ANALYSIS: Embedding Quality")
    print("-"*60 + "\n")
    
    # Check embedding norms (should be close to 1 after normalization)
    norms = [np.linalg.norm(e) for e in embeddings]
    print(f"Embedding norms: min={min(norms):.4f}, max={max(norms):.4f}, mean={np.mean(norms):.4f}")
    
    # Compare embeddings - same person should be similar
    print("\nSimilarity matrix (cosine) - same person:")
    similarities = []
    for i in range(len(embeddings)):
        for j in range(i+1, len(embeddings)):
            sim = np.dot(embeddings[i], embeddings[j])
            similarities.append(sim)
            print(f"  Frame {i+1} vs {j+1}: {sim:.4f}")
    
    avg_sim = np.mean(similarities)
    print(f"\nAverage similarity: {avg_sim:.4f}")
    
    if avg_sim < 0.6:
        print("⚠️  WARNING: Embeddings from same person are not very similar")
        print("   This might indicate face detection or preprocessing issues")
    elif avg_sim > 0.85:
        print("✅ GOOD: Embeddings from same person are highly similar")
    else:
        print("✓  Embeddings are reasonably similar")
    
    print("\n" + "="*60)
    print("CNN TEST COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("1. Run: python main.py --mode enroll")
    print("2. Then: python main.py --mode recognition")
    print()
    
    return True

if __name__ == "__main__":
    success = test_cnn_with_feedback()
    sys.exit(0 if success else 1)
