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
        try:
            img_bytes = base64.b64decode(b64_str)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Validate image was decoded correctly
            if img_cv2 is None:
                print(f"ERROR: Frame {idx} failed to decode from base64")
                continue
            
            if img_cv2.size == 0:
                print(f"ERROR: Frame {idx} is empty")
                continue
            
            # Check image dimensions
            h, w = img_cv2.shape[:2]
            print(f"Frame {idx}: {w}x{h} pixels")
            
            if h < 100 or w < 100:
                print(f"WARNING: Frame {idx} is too small ({w}x{h}). Faces need to be at least ~100x100 pixels")
            
            # Save raw frame for verification/debugging
            cv2.imwrite(f"embeddings/{name}/frame_{idx}.jpg", img_cv2)
            print(f"Saved raw frame: embeddings/{name}/frame_{idx}.jpg")
            
            # Convert BGR to RGB for face_recognition library
            rgb_img = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
            
            # If face_recognition is available, generate NumPy embeddings.
            if 'face_recognition' in sys.modules:
                # Try face_recognition with model_path='hog' for CPU (faster) or 'cnn' for GPU (more accurate)
                face_locations = face_recognition.face_locations(rgb_img, model='hog')
                
                if len(face_locations) > 0:
                    print(f"Found {len(face_locations)} face(s) in frame {idx}")
                    encodings_in_frame = face_recognition.face_encodings(rgb_img, face_locations)
                    if len(encodings_in_frame) > 0:
                        encoding = encodings_in_frame[0]
                        encodings.append(encoding)
                        print(f"Face encoding saved")
                else:
                    print(f"No face detected in frame {idx}")
                    # Try with 'cnn' model as fallback if 'hog' failed
                    print(f"Retrying with CNN model...")
                    face_locations_cnn = face_recognition.face_locations(rgb_img, model='cnn')
                    if len(face_locations_cnn) > 0:
                        print(f"CNN found {len(face_locations_cnn)} face(s)")
                        encodings_in_frame = face_recognition.face_encodings(rgb_img, face_locations_cnn)
                        if len(encodings_in_frame) > 0:
                            encoding = encodings_in_frame[0]
                            encodings.append(encoding)
                            print(f"Face encoding saved")
                    else:
                        print(f"CNN also failed to find faces")
            
        except Exception as e:
            print(f"ERROR processing frame {idx}: {e}")
            import traceback
            traceback.print_exc()
    
    # If we got valid encodings, we average them for a robust registration descriptor
    if encodings:
        mean_encoding = np.mean(encodings, axis=0)
        out_path = f"authorized_embeddings/{name}.npy"
        np.save(out_path, mean_encoding)
        print(f"\nSUCCESS! Successfully saved final averaged embedding to {out_path}")
        print(f"Generated from {len(encodings)} valid face(s)")
    else:
        print("\nNo valid face encodings were able to be generated.")
        print("Troubleshooting tips:")
        print("  1. Check the saved images in authorized_embeddings/{name}/ to verify they contain faces")
        print("  2. Ensure faces are clearly visible and at least 100x100 pixels")
        print("  3. Try with different lighting conditions")
        print("  4. For best results, ensure face is directly facing the camera")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fpga_register.py http://<IP>:8080/register_payload")
        sys.exit(1)
        
    target_url = sys.argv[1]
    
    data = pull_registration(target_url)
    process_payload(data)
