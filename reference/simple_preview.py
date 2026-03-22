#!/usr/bin/env python3
"""
Simple camera preview - tests if frames display properly
"""

import cv2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("Opening camera preview...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("❌ Failed to open camera")
        return
    
    print("✅ Camera opened")
    print("   Press 'q' to quit")
    print("   Press 's' to save a frame\n")
    
    import time
    time.sleep(1)
    
    frame_count = 0
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("❌ Failed to read frame")
            break
        
        frame_count += 1
        
        # Resize for display (if too large)
        display_frame = frame.copy()
        if display_frame.shape[0] > 1080 or display_frame.shape[1] > 1920:
            scale = min(1080 / display_frame.shape[0], 1920 / display_frame.shape[1])
            new_h = int(display_frame.shape[0] * scale)
            new_w = int(display_frame.shape[1] * scale)
            display_frame = cv2.resize(display_frame, (new_w, new_h))
        
        # Add text overlay
        cv2.putText(display_frame, f"Frame: {frame_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(display_frame, "Press 'q' to quit", (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        cv2.imshow("Camera Preview", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print(f"\n✅ Closed after {frame_count} frames")
            break
        elif key == ord('s'):
            filename = f"frame_{frame_count}.jpg"
            cv2.imwrite(filename, frame)
            print(f"✅ Saved {filename}")
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
