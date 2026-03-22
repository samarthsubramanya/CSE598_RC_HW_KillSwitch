#!/usr/bin/env python3
"""
Minimal test - just camera + face detection (no complex state machine)
"""

import cv2
import sys
sys.path.insert(0, '.')

from camera import CameraHandler
from face_detection import FaceDetector

def main():
    print("Initializing camera...")
    camera = CameraHandler(source=0, width=640, height=480)
    
    print("Connecting camera...")
    if not camera.connect():
        print("❌ Failed to connect camera")
        return
    
    print("✅ Camera connected")
    print("Loading face detector...")
    detector = FaceDetector()
    
    print("✅ Detector ready")
    print("Press 'q' to quit\n")
    
    frame_count = 0
    while True:
        frame = camera.read_frame()
        if frame is None:
            print("❌ Failed to read frame")
            break
        
        frame_count += 1
        
        # Detect faces
        faces = detector.detect(frame)
        
        # Draw rectangles
        display_frame = frame.copy()
        for x1, y1, x2, y2 in faces:
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Add text
        cv2.putText(display_frame, f"Frame: {frame_count} | Faces: {len(faces)}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(display_frame, "Press 'q' to quit", (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        # Resize if needed
        if display_frame.shape[0] > 1200:
            scale = 1200 / display_frame.shape[0]
            new_w = int(display_frame.shape[1] * scale)
            new_h = int(display_frame.shape[0] * scale)
            display_frame = cv2.resize(display_frame, (new_w, new_h))
        
        cv2.imshow("Face Detection Test", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print(f"\n✅ Closed after {frame_count} frames")
            break
        
        if frame_count % 30 == 0:
            print(f"Processed {frame_count} frames, detected {len(faces)} face(s)", end="\r")
    
    camera.disconnect()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
