#!/usr/bin/env python3
"""
Camera diagnostic tool - helps troubleshoot camera issues
"""

import cv2
import sys
import time

def test_camera():
    """Test camera connection and frame capture"""
    print("\n=== Camera Diagnostic Tool ===\n")
    
    print("1. Testing OpenCV version...")
    print(f"   OpenCV: {cv2.__version__}")
    
    print("\n2. Testing camera connection...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("   ❌ FAILED: Could not open camera")
        print("\n   Troubleshooting for macOS:")
        print("   - Go to System Preferences → Security & Privacy → Camera")
        print("   - Grant camera access to Terminal (or VSCode)")
        print("   - Restart the application")
        print("   - Try: tccutil reset Camera")
        return False
    
    print("   ✅ Camera opened successfully")
    
    print("\n3. Setting camera properties...")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    print("   ✅ Properties set")
    
    print("\n4. Attempting to read frames...")
    print("   (Waiting 2 seconds for camera to initialize...)")
    time.sleep(2)
    
    frames_read = 0
    for i in range(10):
        ret, frame = cap.read()
        if ret:
            frames_read += 1
            print(f"   Frame {i+1}: ✅ ({frame.shape})")
        else:
            print(f"   Frame {i+1}: ❌ Failed to read")
        time.sleep(0.1)
    
    cap.release()
    
    if frames_read == 0:
        print("\n   ❌ FAILED: No frames captured")
        print("\n   Possible causes:")
        print("   1. Camera permissions not granted")
        print("   2. Camera is in use by another application")
        print("   3. USB camera not properly connected")
        print("\n   Fixes to try:")
        print("   - Check macOS camera permissions")
        print("   - Close other apps using camera (Zoom, FaceTime, etc.)")
        print("   - Unplug and replug USB camera")
        return False
    else:
        print(f"\n   ✅ SUCCESS: Captured {frames_read}/10 frames")
        print("\n5. Camera is working! Running main app...\n")
        return True

if __name__ == "__main__":
    if test_camera():
        print("Type 'python main.py' to start the application")
        sys.exit(0)
    else:
        print("\n⚠️  Camera test failed. Please fix the issues above.")
        sys.exit(1)
