#!/usr/bin/env python3
"""
Quick setup script for the Face Authentication System
Helps with initial setup and testing
"""

import os
import sys
import subprocess
from pathlib import Path


def print_header(msg):
    print(f"\n{'='*60}")
    print(f" {msg}")
    print(f"{'='*60}\n")


def check_python():
    """Check Python version"""
    print_header("1. Checking Python Version")
    print(f"Python: {sys.version}")
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        return False
    print("✅ Python version OK")
    return True


def check_dependencies():
    """Check and install dependencies"""
    print_header("2. Checking Dependencies")

    try:
        import cv2
        print(f"✅ OpenCV: {cv2.__version__}")
    except ImportError:
        print("❌ OpenCV not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python"])

    try:
        import numpy
        print(f"✅ NumPy: {numpy.__version__}")
    except ImportError:
        print("❌ NumPy not found, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])

    print("\n✅ All dependencies OK")
    return True


def check_camera():
    """Test camera connection"""
    print_header("3. Checking Camera")

    try:
        import cv2

        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret:
                print("✅ Camera working (Default webcam detected)")
                return True
        else:
            print("⚠️ Default webcam not found (OK for IP camera mode)")
            return True
    except Exception as e:
        print(f"⚠️ Camera check failed: {e}")
        return True


def create_directories():
    """Create necessary directories"""
    print_header("4. Creating Directories")

    dirs = ["data", "models"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"✅ Created/verified: {d}/")


def download_model():
    """Offer to download pretrained model"""
    print_header("5. Pretrained Model")

    model_path = Path("models/nn4.small2.v1.t7")

    if model_path.exists():
        print(f"✅ Model already exists: {model_path}")
        return

    print("Optional: Download pretrained face embedding model for better accuracy")
    print("(System can work without it using dummy embeddings for testing)")
    choice = input("\nDownload model? (y/n): ").strip().lower()

    if choice == "y":
        print("Note: Download is ~23MB. You can also manually download from:")
        print("https://storage.cmuscs.org/openface-models/nn4.small2.v1.t7")
        print("\nTo use with system, place in: models/nn4.small2.v1.t7")

        try:
            import urllib.request

            url = "https://storage.cmuscs.org/openface-models/nn4.small2.v1.t7"
            print(f"\nDownloading from {url}...")
            urllib.request.urlretrieve(url, str(model_path))
            print(f"✅ Model downloaded to {model_path}")
        except Exception as e:
            print(f"❌ Download failed: {e}")
            print("You can manually download the model from the URL above")


def verify_setup():
    """Verify all system files are in place"""
    print_header("6. Verifying Files")

    required_files = [
        "main.py",
        "camera.py",
        "face_detection.py",
        "model.py",
        "user_db.py",
        "recognition.py",
        "enrollment.py",
        "display.py",
        "requirements.txt",
        "README.md",
    ]

    missing = []
    for f in required_files:
        if os.path.exists(f):
            print(f"✅ {f}")
        else:
            print(f"❌ {f} - MISSING")
            missing.append(f)

    if missing:
        print(f"\n❌ {len(missing)} file(s) missing")
        return False

    print("\n✅ All files present")
    return True


def show_next_steps():
    """Show next steps"""
    print_header("Setup Complete! 🎉")

    print("Next steps:")
    print("\n1. Try interactive mode:")
    print("   python main.py")
    print("\n2. Or enroll your face:")
    print("   python main.py --mode enroll --user 'your_name'")
    print("\n3. Then start recognition:")
    print("   python main.py --mode recognition")
    print("\nFor help:")
    print("   python main.py --help")
    print("\nFor more info:")
    print("   cat README.md")


def main():
    print("\n" + "=" * 60)
    print("  Face Authentication System - Setup Script")
    print("=" * 60)

    try:
        check_python()
        check_dependencies()
        check_camera()
        create_directories()
        download_model()

        if verify_setup():
            show_next_steps()
        else:
            print("\n❌ Setup incomplete. Please check missing files.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Setup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
