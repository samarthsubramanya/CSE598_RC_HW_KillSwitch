
# Face Authentication System - CPU Reference Implementation

A pure Python implementation of the FPGA face authentication system that runs on any CPU. This serves as the reference/prototype implementation before deploying to PYNQ-Z2.

##  Overview

This is a modular, easy-to-understand implementation of the face authentication system described. It:

-  Runs on any computer (CPU-based)
-  Supports live camera input (webcam or IP camera)
-  Performs face detection and embedding computation
-  Implements user enrollment and recognition
-  Uses hysteresis for robust authorization decisions
-  Shows real-time visual feedback (or console output for headless mode)

Later, specific layers can be replaced with PYNQ APIs for FPGA acceleration.

##  Architecture

```
Camera Input
    ↓
[camera.py] → Frame capture
    ↓
[face_detection.py] → Detect faces (Haar Cascade/DNN)
    ↓
[model.py] → Compute embeddings (CPU)
    ↓
[recognition.py] → Compare embeddings + hysteresis
    ↓
[display.py] → Show status (GUI or console)
```

##  File Structure

```
reference/
├── main.py               # Main application entry point
├── camera.py             # Camera input handler
├── face_detection.py     # Face detection
├── model.py              # Embedding model (CPU-based)
├── user_db.py            # User database management
├── recognition.py        # Face recognition + kill switch logic
├── enrollment.py         # User enrollment process
├── display.py            # Display/UI handler
├── requirements.txt      # Python dependencies
└── data/
    └── users.json        # Stored user embeddings (auto-created)
```

##  Setup

### 1. Install Dependencies

```bash
cd reference
pip install -r requirements.txt
```


If you skip this, the system will use a dummy model for demo purposes.

##  Quick Start

### Interactive Menu Mode (Default)

```bash
python main.py
```

This shows an interactive menu with options to:
- Start recognition
- Enroll new users
- Manage database
- Adjust settings

### Direct Recognition Mode

```bash
python main.py --mode recognition
```

### Headless Mode (No GUI)

```bash
python main.py --mode recognition --headless
```

Perfect for running on a server or headless system.

### Enroll Specific User

```bash
python main.py --mode enroll --user "john_doe"
```

##  Keyboard Controls (During Recognition)

| Key | Action |
|-----|--------|
| `q` | Quit |
| `e` | Enroll new user |
| `l` | List enrolled users |
| `d` | Delete user |
| `c` | Clear database |

##  How It Works

### Recognition Flow

1. **Face Detection**: Detects faces in video frame
2. **Embedding**: Computes 64-D face embedding using neural network
3. **Matching**: Compares embedding against stored user embeddings using cosine similarity
4. **Hysteresis**: Applies state machine logic to prevent flicker
   - Lock after N consecutive "no match" frames
   - Unlock after M consecutive "match" frames

### Authorization States

- ** AUTHORIZED**: User recognized (face matches stored embedding above threshold)
- ** UNAUTHORIZED**: User not recognized or below confidence threshold
- ** NO_FACE**: No face detected in frame

### Hysteresis Example

With `lock_threshold=3` and `unlock_threshold=8`:
- System locks if it sees 3 consecutive bad frames
- System unlocks if it sees 8 consecutive good frames
- This prevents rapid flicking due to momentary detection errors

## 👤 User Enrollment

### Process

1. Enter username to enroll
2. System captures 15+ face samples with varying angles/expressions
3. Computes embeddings for each sample
4. Averages embeddings and normalizes
5. Stores in database

### Tips

- Move head slowly (left, right, up, down)
- Keep natural facial expressions
- Good lighting helps accuracy
- More samples = better accuracy

## 🔧 Configuration

Edit thresholds in the code or via the settings menu:

```python
system = FaceAuthenticationSystem(
    camera_source=0,              # Webcam index or IP URL
    similarity_threshold=0.6,     # Cosine similarity threshold (0-1)
    lock_threshold=3,             # Frames to lock
    unlock_threshold=8,           # Frames to unlock
    headless=False                # GUI mode
)
```

##  Camera Input Options

### Default Webcam

```bash
python main.py --camera 0
```

### IP Camera (Phone as Camera)

Use apps like:
- **Android**: IP Webcam, DroidCam
- **iOS**: EpocCam, iVCam

Example with DroidCam:

```bash
python main.py --camera "http://192.168.1.100:8080/video"
```

##  Testing

### Without Real Camera

Edit `main.py` to use a video file instead:

```python
camera = CameraHandler("test_video.mp4")  # Instead of camera source
```

### Dummy Mode

When pretrained model is not available, system uses dummy embeddings for testing the pipeline.

##  Performance Notes

- **CPU Performance**: ~15-30 FPS on modern CPU (depending on model)
- **Latency**: ~100-300ms per frame (detection + embedding)
- **Memory**: ~500MB-1GB
- **Embedding Computation**: Bottleneck (can be accelerated on FPGA)

##  Migration to PYNQ

To adapt this for PYNQ-Z2:

1. **Replace `model.py`**: Use PYNQ DMA to send frames to FPGA accelerator
2. **Replace `face_detection.py`**: Option to offload to FPGA (optional)
3. **Keep everything else**: Database, recognition logic, UI

PYNQ-specific version structure:

```python
pynq_version/
├── main.py                    # Same as reference
├── pynq_model.py              # Replaces model.py (uses DMA)
├── pynq_dma_utils.py          # DMA communication
└── ... (other files same)
```

##  Troubleshooting

### "Camera not found"

- Check if webcam is connected
- Try `--camera 0`, `1`, `2`, etc. for multiple cameras
- For IP camera, check URL and network connectivity

### "No faces detected"

- Ensure good lighting
- Position face towards camera
- Check face detection confidence (`face_detection.py` line ~40)

### "Recognition not working"

- Enroll with more samples
- Adjust similarity threshold lower (e.g., 0.5)
- Check if model is loaded correctly

### "Low FPS"

- Reduce frame resolution in `camera.py`
- Disable GUI (`--headless`)
- Use simpler face detection (Haar Cascade)

##  Database Format

User embeddings are stored in `data/users.json`:

```json
{
  "user1": {
    "embedding": [0.12, -0.55, ..., 0.08],
    "registered_at": "2024-03-21",
    "enrollment_samples": 15
  },
  "user2": {
    "embedding": [0.08, -0.42, ..., 0.15],
    "registered_at": "2024-03-20",
    "enrollment_samples": 12
  }
}
```

##  Understanding the Code

### Key Concepts

1. **Embeddings**: 64-D vectors representing unique face characteristics
2. **Cosine Similarity**: Measures how similar two embeddings are (0=different, 1=same)
3. **Hysteresis**: State machine that prevents rapid state changes
4. **ROI Extraction**: Crops face region from frame for processing
5. **Normalization**: Ensures embeddings have unit length for fair comparison

### Entry Points

- `main.py`: Application loop
- `model.py`: Embedding computation (CPU)
- `recognition.py`: State machine logic
- `user_db.py`: Persistent storage

##  Next Steps

1.  Run and test on your computer
2.  Enroll yourself and test recognition
3.  Adjust thresholds for your environment
4.  When ready, port to PYNQ using FPGA-accelerated components

##  References


- OpenCV Documentation: https://docs.opencv.org/
- PYNQ Documentation: https://pynq.readthedocs.io/

---

**Note**: This is a CPU-based reference implementation. The actual FPGA version will replace `model.py` with accelerated hardware inference via AXI DMA.
