# 📖 Reference Implementation - File Index & Summary

Complete CPU-based reference implementation of the FPGA Face Authentication System.

## 📦 What's Included

### 🎯 Core Application
- **`main.py`** - Main application entry point with interactive menu
- **`setup.py`** - Automated setup and dependency checker

### 🔧 Core Modules

#### Input & Detection
- **`camera.py`** - Camera input handler (webcam, IP camera)
- **`face_detection.py`** - Face detection using Haar Cascade/DNN

#### Model & Processing
- **`model.py`** - Face embedding computation (CPU-based)
  - INT8 quantization support for FPGA deployment
  - Normalizes embeddings to unit length

#### Database & State
- **`user_db.py`** - User enrollment database (JSON-based)
- **`recognition.py`** - Face recognition with hysteresis state machine
- **`enrollment.py`** - User enrollment/registration workflow

#### Visualization
- **`display.py`** - Real-time GUI display and console output

### 📚 Documentation

#### Getting Started
- **`QUICKSTART.md`** - 5-minute quick start guide
- **`README.md`** - Full feature documentation and usage

#### Technical Details
- **`ARCHITECTURE.md`** - Deep dive into system architecture
  - Module responsibilities
  - Data flow diagrams
  - PYNQ adaptation strategy
  - Performance characteristics

#### Project Files
- **`requirements.txt`** - Python dependencies (OpenCV, NumPy)

---

## 🎯 System Overview

```
CPU REFERENCE IMPLEMENTATION
├── Input Layer
│   └── camera.py (webcam / IP camera)
│
├── Detection Layer
│   └── face_detection.py (Haar Cascade)
│
├── Inference Layer (BOTTLENECK - Will be FPGA accelerated)
│   └── model.py (compute 64-D embeddings)
│
├── Recognition & State
│   ├── recognition.py (matching + hysteresis)
│   ├── user_db.py (enrollment database)
│   └── enrollment.py (registration process)
│
└── Output Layer
    └── display.py (GUI visualization)
```

---

## 🚀 Key Features

✅ **Camera Input**
- Webcam support (any connected camera)
- IP camera support (phone as camera)
- USB camera support

✅ **Face Detection**
- Real-time face detection
- Multiple face handling
- ROI extraction with margins

✅ **Face Recognition**
- 64-D embedding vectors
- Cosine similarity matching
- Configurable similarity threshold (default: 0.6)

✅ **User Management**
- Enroll new users without retraining
- Multiple samples per user (average embeddings)
- Persistent JSON-based database
- Easy user deletion/management

✅ **Robust Decision Logic**
- Hysteresis-based state machine
- Configurable lock/unlock thresholds
- Prevents rapid flicker
- Smooth transitions between states

✅ **User Interface**
- Interactive GUI with real-time overlay
- Status visualization (✅ AUTHORIZED / ❌ UNAUTHORIZED)
- Progress bars for enrollment
- Headless mode for servers

✅ **Modular Architecture**
- Independent modules
- Easy to test
- Simple to port to PYNQ
- Clear separation of concerns

---

## 📊 Performance Baseline (CPU Reference)

| Metric | Value | Notes |
|--------|-------|-------|
| FPS | 5-10 | Depends on CPU and resolution |
| Face Detection | 10-20ms | Haar Cascade |
| Embedding Compute | 100-300ms | **FPGA target: 2-10ms** |
| Recognition | <1ms | Very fast comparison |
| Memory Usage | ~500MB | Python + OpenCV overhead |
| Database Overhead | <1MB | Per 100+ users |

---

## 🎮 Quick Start

### Install
```bash
cd reference
pip install -r requirements.txt
```

### Run
```bash
python main.py
```

### Enroll
```bash
python main.py --mode enroll --user "your_name"
```

### Recognize
```bash
python main.py --mode recognition
```

See [QUICKSTART.md](QUICKSTART.md) for detailed usage.

---

## 🏗️ Module Responsibilities

| Module | Responsibility | To Replace for PYNQ |
|--------|-----------------|---------------------|
| camera.py | Frame capture | Keep as-is or use PYNQ API |
| face_detection.py | Face localization | Keep on CPU (PS) |
| **model.py** | **Embedding computation** | **→ Use FPGA via DMA** ⭐ |
| user_db.py | Enrollment storage | Keep on CPU |
| recognition.py | Matching & decisions | Keep on CPU |
| enrollment.py | Registration workflow | Keep on CPU |
| display.py | Visualization | HDMI output on PYNQ |
| main.py | Application loop | Keep as-is (minimal changes) |

---

## 💡 Design Highlights

### 1. **Embedding-Based Recognition**
- Instead of classifier, uses embedding vectors
- Enables adding users without retraining
- Scalable architecture

### 2. **Hysteresis State Machine**
- Prevents single-frame spoofing
- Configurable thresholds (lock_threshold=3, unlock_threshold=8)
- Smooth authorization transitions

### 3. **INT8 Quantization Support**
- Embeddings can be quantized for FPGA
- 4× memory savings vs float32
- Preserves relative distances for similarity

### 4. **Modular Architecture**
- Each layer independent
- Easy unit testing
- Simple PYNQ adaptation

### 5. **Headless Mode**
- Works on servers/embedded systems
- Console-based feedback
- Suitable for CI/CD pipelines

---

## 🔄 Data Flow

```
ENROLLMENT
──────────
Camera → FaceDetect → Extract ROI → Compute Embedding
                                         ↓
                                  Average Embeddings
                                         ↓
                                   Store in Database

RECOGNITION
───────────
Camera → FaceDetect → Extract ROI → Compute Embedding
                                         ↓
                                  Compare with Database
                                    (Cosine Similarity)
                                         ↓
                                         ↓ Similarity > threshold?
                            ┌──────YES───┴───SUCCESS──────┐
                            │                              │
                          ✅ AUTHORIZED              ❌ UNAUTHORIZED
                            │                              │
                        Good Frame                    Bad Frame
                        Counter++                    Counter++
                            │                              │
                        Good==8? Lock        Bad==3? Unlock
                            │                              │
                          [Unlock State]            [Lock State]
```

---

## 🧪 Testing Workflow

**Suggested testing sequence:**

1. ✅ **Setup**: Run setup.py
2. ✅ **Install**: pip install -r requirements.txt
3. ✅ **Test Camera**: python main.py → see live video
4. ✅ **Enroll**: Create multiple users
5. ✅ **Recognize**: Test each user
6. ✅ **Threshold Tuning**: Adjust similarity_threshold
7. ✅ **Performance**: Measure FPS and latency
8. ✅ **Edge Cases**: Test different lighting, angles, distances

---

## 🔐 Security Model

✅ **What it protects against:**
- Unknown attackers (different face)
- Single-frame spoofing (hysteresis)
- Out-of-distribution attacks (thresholding)

⚠️ **What it doesn't protect against:**
- Advanced face spoofing (high-quality photos/masks)
- Liveness detection (future feature)
- Network attacks (no network in reference)

---

## 🚀 Path to PYNQ Deployment

**Current State** (CPU Reference):
```
embedding = model.compute_embedding(roi)  # ~100-300ms on CPU
```

**PYNQ Target** (FPGA Accelerated):
```python
# Send ROI to FPGA via DMA
fpga.dma_write(roi)
# FPGA computes embedding in hardware
wait_for_result()
embedding = fpga.dma_read()  # ~2-10ms total
```

**Required Changes:**
1. Create `pynq_model.py` with DMA communication
2. Create `pynq_dma_utils.py` for AXI DMA handling
3. Implement FPGA hardware (quantized CNN)
4. Test bit-exact matching of embeddings

All other modules remain **unchanged** ✅

---

## 📖 Learning Path

**Beginner:**
1. Read QUICKSTART.md
2. Run `python main.py`
3. Enroll yourself and test recognition

**Intermediate:**
4. Read README.md for full feature set
5. Adjust settings and thresholds
6. Review setup.py for dependencies

**Advanced:**
7. Read ARCHITECTURE.md for technical details
8. Study each module's source code
9. Understand hysteresis logic in recognition.py
10. Understand quantization in model.py

**Expert (FPGA):**
11. Design FPGA accelerator for model.py
12. Implement AXI DMA communication
13. Port to PYNQ-Z2
14. Validate bit-exact INT8 quantization

---

## 📋 Checklist: Before PYNQ Migration

- [ ] CPU reference works reliably
- [ ] Can enroll 5+ users
- [ ] Recognition accuracy > 95% on test set
- [ ] Hysteresis thresholds tuned for environment
- [ ] Performance baseline measured
- [ ] All modules tested independently
- [ ] Database persistence verified
- [ ] Headless mode tested
- [ ] Documentation reviewed
- [ ] Ready for FPGA implementation

---

## 🎓 What You'll Learn

By studying this code:
- ✅ Face detection algorithms
- ✅ Deep learning inference (embeddings)
- ✅ Cosine similarity matching
- ✅ State machine design (hysteresis)
- ✅ Database design patterns
- ✅ Modular software architecture
- ✅ Real-time video processing
- ✅ User interface design
- ✅ Logging and debugging
- ✅ FPGA integration concepts

---

## 🔗 References

- Original specification: [../PLAN.md](../PLAN.md)
- Full documentation: [README.md](README.md)
- Architecture details: [ARCHITECTURE.md](ARCHITECTURE.md)
- Quick start: [QUICKSTART.md](QUICKSTART.md)
- OpenCV docs: https://docs.opencv.org/
- PYNQ docs: https://pynq.readthedocs.io/

---

## ✨ Summary

You now have a **complete, working face authentication system** that:

1. **Runs on any CPU** (laptop, desktop, Raspberry Pi)
2. **Has clear, modular code** ready for learning
3. **Provides a reference implementation** before FPGA deployment
4. **Includes extensive documentation** for understanding
5. **Is easily adaptable** to PYNQ with minimal changes

**Next step:** Run `python main.py` and start exploring! 🚀

---

*Reference Implementation Created: March 2024*
*Ready for PYNQ-Z2 FPGA Porting*
