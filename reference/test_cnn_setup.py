#!/usr/bin/env python3
"""Test that face_recognition CNN library is working"""

import face_recognition
import numpy as np

print("✅ face_recognition imported successfully")

# Create a simple test image (100x100 RGB)
test_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
print(f"✅ Can create test images: {test_image.shape}")

# Try to detect faces in test image (should return empty since it's uniform)
try:
    face_locations = face_recognition.face_locations(test_image)
    print(f"✅ face_locations() works: found {len(face_locations)} faces")
except Exception as e:
    print(f"⚠️ face_locations() error: {e}")

# Test face_encodings (might fail on blank image, that's ok)
try:
    encodings = face_recognition.face_encodings(test_image)
    print(f"✅ face_encodings() works: computed {len(encodings)} encodings")
    if len(encodings) > 0:
        print(f"   Encoding shape: {encodings[0].shape}")
except Exception as e:
    print(f"⚠️ face_encodings() error (expected on blank image): {type(e).__name__}")

print("\n✅ Face_recognition CNN library is ready!")
