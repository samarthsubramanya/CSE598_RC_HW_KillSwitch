

# 🔐 FPGA Hardware Kill Switch with Face Authentication (PYNQ-Z2)

## Overview

This project implements a **real-time, hardware-accelerated face authentication system** on a PYNQ-Z2 FPGA platform.

The system continuously monitors a video stream and:

* ✅ Allows access if the user is recognized
* ❌ Triggers a **kill switch** (lock + display warning) if unauthorized

To reduce cost:

* A **mobile phone is used as a camera** via USB tethering or WiFi
* HDMI output is used for real-time visual feedback

---

## 🎯 Key Features

* Continuous face authentication (not one-time login)
* FPGA-accelerated inference (quantized model)
* Real-time video processing pipeline
* HDMI output with status overlay
* No additional hardware required (phone used as camera)
* Supports **new user registration without retraining**

---

## 🧠 System Architecture

```text
Phone Camera (IP Stream / USB Tether)
        ↓
CPU (PS - ARM)
  - Frame Capture (OpenCV)
  - Face Detection
  - ROI Cropping
        ↓ AXI DMA
FPGA (PL)
  - Quantized Face Embedding Model (INT8)
        ↓ AXI-Lite / DMA
CPU Decision Logic
  - Compare embeddings
  - Apply threshold
  - Apply hysteresis (N/M frames)
        ↓
HDMI Output + OS Lock Control
```

---

## 🧩 Core Design Choice (IMPORTANT)

This project uses an **embedding-based face recognition system** instead of a classifier.

### Why?

* Supports adding new users without retraining
* More scalable and realistic
* Better for security applications

### Flow:

```text
Face → Embedding Vector → Compare with stored users → Decision
```

---

## 📷 Camera Input (No Physical Camera Required)

### Option 1: Phone as IP Camera (Recommended)

Use apps:

* Android: IP Webcam, DroidCam
* iOS: EpocCam, iVCam

Example:

```python
cap = cv2.VideoCapture("http://192.168.42.129:8080/video")
```

---

### Option 2: USB Tethering (Best Stability)

* Connect phone via USB
* Enable USB tethering
* Use phone camera app
* Lower latency than WiFi

---

## 📺 HDMI Output

Used to display:

* Live video feed
* Face bounding boxes
* Status:

  * ✅ AUTHORIZED
  * ❌ UNAUTHORIZED
  * 🔒 LOCKED

---

## 🔁 Data Flow

1. Capture frame (OpenCV)
2. Detect face (CPU)
3. Crop ROI
4. Send ROI → FPGA via DMA
5. FPGA computes embedding
6. CPU compares embeddings
7. Apply decision logic
8. Display + lock system

---

## ⚙️ PS ↔ PL Communication

### AXI DMA (Data Path)

* Transfers image tensors
* High throughput

### AXI-Lite (Control Path)

* Start/stop
* Status
* Results

---

## 🧮 Model Design

### Type

* Face embedding model (not classifier)

### Suggested Architecture

* Input: 96×96 grayscale
* Output: 64-D embedding vector
* Quantization: INT8

### Layers (example)

* Conv → ReLU → Pool
* Conv → ReLU → Pool
* Conv → Global Avg Pool
* FC → Embedding

---

## 👤 User Registration (Enrollment)

To add a new user:

1. Capture 10–20 face images
2. Compute embeddings using FPGA
3. Average embeddings
4. Normalize
5. Store vector

```python
embedding_db = {
    "user1": [0.12, -0.55, ...],
}
```

---

## 🔍 Recognition

At runtime:

1. Compute embedding
2. Compare with stored embeddings
3. Use cosine similarity
4. If above threshold → authorized

---

## 🔐 Kill Switch Logic

Define:

* **Authorized**
* **Unauthorized**
* **No face**

Use hysteresis:

* Lock after N bad frames
* Unlock after M good frames

---

## 🧠 FPGA Accelerator

### Interfaces

#### AXI-Stream

* Input: image pixels
* Output: embedding vector

#### AXI-Lite

* Control registers
* Status flags

---

## 🧪 Validation Strategy (No Hardware)

### 1. Python Golden Model

* Train + quantize model
* Generate test vectors

### 2. Verilog Simulation

* Validate layer outputs
* Compare with Python

### 3. End-to-End Simulation

* Use test images
* Validate classification accuracy

---

## 📊 Evaluation Metrics

* Latency (ms)
* FPS
* Time-to-lock
* Accuracy (FAR/FRR)
* FPGA resource usage
* Power (optional)

---

## 🧰 Tools

### Hardware

* PYNQ-Z2 FPGA board
* Phone (camera)
* HDMI monitor

### Software

* Python (OpenCV, NumPy)
* PYNQ framework
* Vitis AI / FINN / Verilog
* Vivado

---

## 📁 Repository Structure

```text
project/
│
├── hardware/
│   ├── ip/
│   ├── vivado_design/
│   └── bitstream/
│
├── software/
│   ├── main.py
│   ├── dma_utils.py
│   ├── model/
│   └── display.py
│
├── simulation/
│   ├── testbench/
│   └── vectors/
│
└── README.md
```

---

## 🧠 Notes for AI Assistants (Copilot/Codex)

* Use `pynq.allocate()` for buffers
* Ensure memory is contiguous
* Match tensor layout exactly
* Use grayscale for simplicity
* Start with small test images
* Verify with golden model before hardware

---

## 🚀 Execution Flow

```python
while True:
    frame = capture()

    face = detect_face(frame)
    roi = preprocess(face)

    embedding = run_fpga(roi)

    user = match(embedding)

    if user:
        show("AUTHORIZED")
    else:
        show("LOCKED")
        trigger_lock()
```

---

## 🧩 TODO

### Hardware

* [ ] Implement CNN accelerator
* [ ] Add AXI DMA
* [ ] Add AXI-Lite interface

### Software

* [ ] Camera input
* [ ] Face detection
* [ ] DMA pipeline
* [ ] HDMI output
* [ ] Lock control

---

## 🌟 Stretch Goals

* Multi-user recognition
* Liveness detection
* Full FPGA pipeline (no CPU detection)
* HDMI passthrough mode

---

## 🏁 Final Goal

A real-time system that:

* Detects faces from a live stream
* Uses FPGA for inference
* Locks system when unauthorized
* Displays results via HDMI

---

## 💡 Key Insight

> The system uses **embedding-based recognition** instead of classification, enabling dynamic user registration without retraining — making it scalable and suitable for real-world deployment.

---


