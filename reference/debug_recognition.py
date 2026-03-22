#!/usr/bin/env python3
"""
Debug tool - see recognition scores in real-time
"""

import sys
sys.path.insert(0, '.')

from camera import CameraHandler
from face_detection import FaceDetector
from model import FaceEmbeddingModel
from user_db import UserDatabase
from recognition import FaceRecognizer
import numpy as np
import time

def debug_recognition():
    print("\n=== Recognition Debug ===\n")
    
    # Load components
    camera = CameraHandler(source=0, width=640, height=480)
    detector = FaceDetector()
    model = FaceEmbeddingModel()
    user_db = UserDatabase()
    recognizer = FaceRecognizer(user_db, similarity_threshold=0.45)
    
    # Check if users are enrolled
    users = user_db.list_users()
    if not users:
        print("❌ No users enrolled!")
        print("   Run: python main.py --mode enroll --user 'yourname'")
        return
    
    print(f"✅ Enrolled users: {users}\n")
    
    if not camera.connect():
        print("❌ Camera connection failed")
        return
    
    print("Showing recognition scores for 30 frames...")
    print("(Different people should have LOW scores, your face should have HIGH scores)\n")
    print(f"{'Frame':>5} | {'Faces':>5} | {'Best User':>15} | {'Score':>6} | {'Status':>12} | Decision")
    print("-" * 80)
    
    for frame_num in range(30):
        frame = camera.read_frame()
        if frame is None:
            print(f"{frame_num:>5} | Error reading frame")
            continue
        
        faces = detector.detect(frame)
        
        if len(faces) == 0:
            print(f"{frame_num:>5} | {'0':>5} | {'None':>15} | {'0.00':>6} | {'NO_FACE':>12} | No face detected")
        else:
            roi = detector.extract_roi(frame, faces[0])
            if roi is None:
                print(f"{frame_num:>5} | {'1':>5} | {'Error':>15} | {'0.00':>6} | {'ERROR':>12} | Failed to extract ROI")
                continue
            
            embedding = model.compute_embedding(roi)
            if embedding is None:
                print(f"{frame_num:>5} | {'1':>5} | {'Error':>15} | {'0.00':>6} | {'ERROR':>12} | Failed to compute embedding")
                continue
            
            # Find best matching user
            best_user = None
            best_score = 0.0
            
            for username in users:
                stored_emb = user_db.get_user_embedding(username)
                if stored_emb is not None:
                    score = np.dot(embedding, stored_emb)
                    if score > best_score:
                        best_score = score
                        best_user = username
            
            status = "✅ AUTH" if best_score > 0.45 else "❌ NO AUTH"
            
            print(f"{frame_num:>5} | {len(faces):>5} | {best_user or 'Unknown':>15} | {best_score:>6.2f} | {status:>12} | Threshold: 0.45")
    
    camera.disconnect()
    
    print("\n" + "=" * 80)
    print("\nAnalysis:")
    print("  - Score > 0.45: AUTHORIZED")
    print("  - Score < 0.45: UNAUTHORIZED")
    print("\nIf everyone is authorized, the threshold is TOO LOW.")
    print("Recommended adjustments:")
    print("  - If score is 0.95+ for you: Keep threshold at 0.45")
    print("  - If score is 0.90-0.95 for you: Use threshold 0.50")
    print("  - If score is 0.85-0.90 for you: Use threshold 0.55")
    print("  - If score is <0.80 for you: Need to re-enroll with more samples")

if __name__ == "__main__":
    debug_recognition()
