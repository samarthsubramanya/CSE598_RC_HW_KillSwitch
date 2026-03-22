# System Architecture

This document explains the architecture of the Face Authentication System (CPU reference implementation) and how it maps to the eventual PYNQ-Z2 FPGA deployment.

## 🏗️ Module Overview

### 1. **camera.py** - Camera Input Handler

**Purpose**: Abstracts camera sources (webcam, IP camera)

**Key Classes**:
- `CameraHandler`: Manages video capture and frame reading

**Methods**:
- `connect()`: Open camera connection
- `read_frame()`: Get next frame
- `disconnect()`: Release resources

**Future PYNQ Integration**:
- Keep as-is or replace with PYNQ-based camera interface
- May use USB camera or MIPI CSI interface on PYNQ

---

### 2. **face_detection.py** - Face Detection

**Purpose**: Detect faces in frames

**Key Classes**:
- `FaceDetector`: Detects faces using Haar Cascade or DNN

**Methods**:
- `detect(frame)`: Returns list of face bounding boxes `[(x1, y1, x2, y2), ...]`
- `extract_roi(frame, bbox)`: Crops face region from frame

**Current Implementation**:
- Haar Cascade (fast, CPU-based)
- Fallback to DNN-based detector

**Detection Output**:
```python
faces = [(100, 50, 200, 150), (300, 100, 450, 250)]  # Multiple faces
# First face: x1=100, y1=50, x2=200, y2=150
```

**Future PYNQ Integration**:
- Option 1: Keep on CPU (ARM PS)
- Option 2: Accelerate on FPGA (PL) using CNN accelerator
- For now: CPU-based

---

### 3. **model.py** - Face Embedding Model

**Purpose**: Compute face embeddings (deep neural network inference)

**Key Classes**:
- `FaceEmbeddingModel`: Computes face embeddings

**Methods**:
- `preprocess(roi)`: Resize to 96×96, normalize
- `compute_embedding(roi)`: Returns 64-D embedding vector
- `quantize_to_int8(embedding)`: Convert float32 → INT8 (±128)
- `dequantize_from_int8(quantized)`: Convert INT8 → float32

**Input**:
- Face ROI image (arbitrary size)

**Processing**:
1. Resize to 96×96 grayscale
2. Normalize to [0, 1]
3. Pass through CNN
4. Output: 64-D vector (face descriptor)

**Output**:
```python
embedding = [0.12, -0.55, 0.08, ..., -0.22]  # 64 values
# Unit length (normalized): embedding / ||embedding|| = 1
```

**Quantization**:
- Float: [-1.0 to 1.0]
- INT8: [-128 to 127]
- Preserves relative distances for cosine similarity

**Future PYNQ Integration** ⭐ **PRIMARY ACCELERATION TARGET**:
```
PYNQ DMA:
  1. CPU sends ROI image → PYNQ via AXI DMA
  2. FPGA runs quantized CNN (INT8)
  3. CPU reads embedding ← PYNQ via AXI DMA
  ~2-10ms latency (vs 100-300ms on CPU)
```

---

### 4. **user_db.py** - User Database

**Purpose**: Persistent storage of user enrollments

**Key Classes**:
- `UserDatabase`: Manages user embeddings

**Methods**:
- `enroll_user(username, embedding)`: Add new user
- `update_user_embedding(username, embedding, alpha)`: Incremental enrollment
- `get_user_embedding(username)`: Retrieve stored embedding
- `delete_user(username)`: Remove user
- `list_users()`: Get all usernames
- `load_database()`: Load from JSON
- `save_database()`: Save to JSON

**Storage Format** (`data/users.json`):
```json
{
  "alice": {
    "embedding": [0.12, -0.55, ..., -0.22],
    "registered_at": "2024-03-21",
    "enrollment_samples": 15
  },
  "bob": {
    "embedding": [0.08, -0.42, ..., 0.18],
    "registered_at": "2024-03-20",
    "enrollment_samples": 12
  }
}
```

**Notes**:
- Embeddings stored as float32
- Can be converted to INT8 for FPGA comparison
- Every user has reference embedding (averaged from enrollment samples)

**Future PYNQ Integration**:
- Keep on CPU (ARM PS)
- Can optionally store on eMMC or network
- FPGA might do INT8 comparisons (future optimization)

---

### 5. **recognition.py** - Face Recognition & Decision Logic

**Purpose**: Match embeddings and apply authorization decision

**Key Classes**:
- `FaceRecognizer`: Recognition engine with hysteresis

**Methods**:
- `cosine_similarity(vec1, vec2)`: Compute similarity (0-1)
- `recognize(embedding)`: Find best matching user
- `update_state(recognition_result)`: Apply hysteresis logic
- `process_frame(embedding)`: One-shot recognize + update

**Recognition Algorithm**:
```
1. Compute cosine similarity against all users
2. Find user with highest similarity
3. If similarity > threshold → AUTHORIZED
4. Else → UNAUTHORIZED
5. Apply hysteresis (state machine)
```

**Cosine Similarity**:
$$\text{sim}(e_1, e_2) = \frac{e_1 \cdot e_2}{||e_1|| \cdot ||e_2||} \in [0, 1]$$

**Hysteresis State Machine**:
```
State: AUTHORIZED / UNAUTHORIZED

If (good_frames >= unlock_threshold):
    state = AUTHORIZED

If (bad_frames >= lock_threshold):
    state = UNAUTHORIZED

Result: Robust against momentary detection errors
```

**Status Enums**:
```python
AuthStatus.AUTHORIZED    # ✅ User recognized
AuthStatus.UNAUTHORIZED  # ❌ Unknown user / low confidence
AuthStatus.NO_FACE       # ⚠️ No face in frame
```

**Decision Output**:
```python
{
    "state": AuthStatus.AUTHORIZED,
    "last_user": "alice",
    "similarity": 0.87,
    "good_frames": 8,
    "bad_frames": 0
}
```

**Future PYNQ Integration**:
- Keep on CPU (ARM PS)
- Hysteresis logic remains the same
- FPGA does embedding computation only

---

### 6. **enrollment.py** - User Enrollment

**Purpose**: Manage user registration process

**Key Classes**:
- `EnrollmentManager`: Enrollment workflow

**Methods**:
- `start_enrollment(username)`: Begin enrollment
- `process_frame(frame)`: Capture sample from frame
- `finish_enrollment()`: Average embeddings and save
- `cancel_enrollment()`: Abort enrollment

**Enrollment Process**:
```
1. Detect face in frame
2. Compute embedding
3. Store in list
4. Repeat 15+ times (different angles/expressions)
5. Average all embeddings
6. Normalize
7. Save to database
```

**Sample Collection**:
- Minimum 10-15 samples per user
- Better with diverse angles (frontal, left, right, up, down)
- Different expressions help robustness

**Averaging Formula**:
$$\hat{e} = \frac{1}{n} \sum_{i=1}^{n} e_i, \quad \text{then normalize: } \hat{e} \leftarrow \frac{\hat{e}}{||\hat{e}||}$$

**Future PYNQ Integration**:
- Keep on CPU (ARM PS)
- Or use FPGA-accelerated embedding computation

---

### 7. **display.py** - Visualization & UI

**Purpose**: Show real-time feedback and status

**Key Classes**:
- `DisplayHandler`: GUI display (OpenCV)
- `ConsoleDisplay`: Headless console output

**DisplayHandler Methods**:
- `draw_frame(frame, faces, decision)`: Annotate frame with boxes and status
- `display_frame(frame)`: Show in window
- `show_enrollment_screen(frame, username, progress)`: Enrollment UI
- `cleanup()`: Release resources

**Visual Elements**:
- Green box: Authorized face
- Red box: Unauthorized face
- Status bar: Current auth state
- Progress bar (enrollment): Sample collection progress
- Similarity score overlay

**ConsoleDisplay Methods**:
- `print_status(decision)`: Print to terminal (for headless mode)

**Output Example**:
```
✅ AUTHORIZED   | User: alice     | Sim: 0.87 | Good: 8 Bad: 0
```

**Future PYNQ Integration**:
- Option 1: HDMI output (real-time overlay)
- Option 2: Network stream to monitor
- For CPU reference: OpenCV GUI window

---

### 8. **main.py** - Application Loop

**Purpose**: Orchestrate all components and user interaction

**Key Classes**:
- `FaceAuthenticationSystem`: Main application

**Key Methods**:
- `enroll_user(username)`: Interactive enrollment
- `run_recognition()`: Main recognition loop
- `show_menu()`: Interactive menu

**Application Flow**:
```
while True:
    frame ← camera.read()
    faces ← detector.detect(frame)
    
    if faces:
        roi ← detector.extract_roi(frame, faces[0])
        embedding ← model.compute_embedding(roi)
        decision ← recognizer.process_frame(embedding)
    else:
        decision ← NO_FACE
    
    display.draw_frame(frame, faces, decision)
    handle_keyboard_input()
```

**User Interactions**:
- `q`: Quit
- `e`: Enroll new user
- `l`: List enrolled users
- `d`: Delete user
- `c`: Clear database

---

## 🔄 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CPU Reference Implementation             │
└─────────────────────────────────────────────────────────────┘

MAIN LOOP:
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│  Camera  │ ───► │   Detector   │ ───► │  Model (CPU) │
└──────────┘      └──────────────┘      └──────────────┘
     ▲                                         │
     │                                         ▼
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│ Display  │ ◄─── │ Recognizer   │ ◄─── │  User DB     │
└──────────┘      └──────────────┘      └──────────────┘
                        │
                   Hysteresis/State
                        │
                        ▼
                  Authorization
                  Decision (✅/❌)
```

---

## 🔀 PYNQ Adaptation Strategy

**Current CPU Flow** → **Future PYNQ-Z2 Flow**

### Layers that Stay the Same (CPU PS):
- `camera.py` - Camera input
- `face_detection.py` - Face detect (or keep on CPU)
- `user_db.py` - User database
- `recognition.py` - Recognition logic & hysteresis
- `enrollment.py` - Enrollment
- `display.py` - HDMI output
- `main.py` - Application loop

### Layer that Changes (FPGA PL Acceleration):
- **`model.py`** → **`pynq_model.py`** (uses DMA to FPGA accelerator)

### New Components:
- **`pynq_dma_utils.py`** - AXI DMA communication
- **Hardware bitstream** - Quantized CNN accelerator on FPGA

### Modified Flow:
```
┌──────────┐      ┌──────────────┐      ┌────────────────┐
│  Camera  │ ───► │   Detector   │ ───► │  Model (PYNQ)  │
│(PS/ARM)  │      │  (PS/ARM)    │      │ via AXI DMA    │
└──────────┘      └──────────────┘      │ to FPGA (PL)   │
                                         └────────────────┘
                                                │
                    100× faster (2-10ms vs 100-300ms)
```

---

## 📊 Performance Characteristics

### CPU Reference (Laptop/Desktop):
| Component | Time | Notes |
|-----------|------|-------|
| Face Detection | 10-20ms | Haar Cascade |
| Embedding (CPU) | 100-300ms | Bottleneck |
| Recognition | <1ms | Fast comparison |
| Total/Frame | 150-400ms | ~3-7 FPS |

### PYNQ Estimated:
| Component | Time | Notes |
|-----------|------|-------|
| Face Detection | 10-20ms | CPU (ARM) |
| Embedding (FPGA) | 2-10ms | Quantized INT8 |
| Recognition | <1ms | Fast comparison |
| Total/Frame | 15-50ms | ~20-60 FPS |

---

## 🔐 Security Considerations

1. **Embeddings**: Not reversible → can't reconstruct original faces
2. **Hysteresis**: Prevents single-frame spoofing attacks
3. **Quantization**: Lossy compression → slight accuracy reduction
4. **Database**: Stored locally (or encrypted if networked)
5. **Database Backup**: JSON format → easy to backup/restore

---

## 📚 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| 64-D embeddings | Balance between accuracy and FPGA resources |
| INT8 quantization | ~4× memory savings, suitable for FPGA |
| Hysteresis (3/8) | Robust against momentary errors |
| Cosine similarity | Normalized embeddings → consistent threshold |
| Haar Cascade default | Fast fallback when DNN unavailable |
| JSON database | Human-readable, easy to backup/modify |
| CPU reference first | Validate algorithm before hardware implementation |

---

## 🎯 Testing Strategy

1. **Unit Tests** (Per module)
   - Face detection accuracy
   - Embedding consistency
   - Cosine similarity calculations

2. **Integration Tests**
   - Full pipeline on CPU
   - Enrollment → Recognition workflow
   - Hysteresis logic (state transitions)

3. **Performance Tests**
   - FPS measurement
   - Latency per component
   - Memory usage

4. **End-to-End Tests**
   - Multi-user recognition
   - False acceptance rate (FAR)
   - False rejection rate (FRR)

---

## 🚀 Deployment Checklist

- [ ] CPU reference implementation works
- [ ] Test with enough users
- [ ] Calibrate similarity threshold for environment
- [ ] Optimize hysteresis thresholds
- [ ] Profile performance bottlenecks
- [ ] Design FPGA accelerator for embedding model
- [ ] Implement AXI DMA communication
- [ ] Port to PYNQ
- [ ] Validate bit-exact results (INT8 quantization)
- [ ] Deploy on PYNQ-Z2

---

This architecture is designed to be **modular**, **testable**, and **easily portable** to FPGA while maintaining the reference implementation's clarity and ease of understanding.
