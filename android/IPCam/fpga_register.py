import sys
import time
import requests
import json
import base64
import numpy as np
import cv2
import os


try:
    import face_recognition
except ImportError:
    print("WARNING: face_recognition Python library not found.")
    print("Please install it (`pip install face_recognition`) or replace with your FPGA Neural Network logic!")


def pull_registration(url):
    print(f"Polling {url} for registration payload...")
    while True:
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                return response.json()
            else:
                pass
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(1)

def process_payload(payload):
    name = payload.get("name", "Unknown")
    images_b64 = payload.get("images", [])
    
    print(f"Found registration for {name} with {len(images_b64)} images!")
    
    encodings = []
    
    os.makedirs("embeddings", exist_ok=True)
    os.makedirs(f"embeddings/{name}", exist_ok=True)
    
    for idx, b64_str in enumerate(images_b64):
        img_bytes = base64.b64decode(b64_str)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Save raw frame for verification/debugging
        cv2.imwrite(f"embeddings/{name}/frame_{idx}.jpg", img_cv2)
        
        # Convert BGR to RGB for face_recognition library
        rgb_img = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
        
        # If face_recognition is available, generate NumPy embeddings.
        if 'face_recognition' in sys.modules:
            face_locations = face_recognition.face_locations(rgb_img)
            if len(face_locations) > 0:
                encoding = face_recognition.face_encodings(rgb_img, face_locations)[0]
                encodings.append(encoding)
            else:
                print(f"Warning: No face found in frame {idx}")
    
    # If we got valid encodings, we average them for a robust registration descriptor
    if encodings:
        mean_encoding = np.mean(encodings, axis=0)
        out_path = f"embeddings/{name}.npy"
        np.save(out_path, mean_encoding)
        print(f"SUCCESS! Successfully saved final averaged embedding to {out_path}")
    else:
        print("No valid face encodings were able to be generated.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fpga_register.py http://<IP>:8080/register_payload")
        sys.exit(1)
        
    target_url = sys.argv[1]
    
    data = pull_registration(target_url)
    process_payload(data)
