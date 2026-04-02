# Setup & Run Guide — PYNQ-Z2 Face Recognition Kill Switch

Complete step-by-step instructions from a fresh machine to a running demo.

---

## Overview of what you are building

```
[Phone camera] ──WiFi──► [PYNQ-Z2 Python]
                              │
                    face_recognition (dlib)
                    detect faces + compute 128-D embeddings
                              │
                    [FPGA HLS: cosine_match_accel]
                    search enrolled user database (DSP48 MACs)
                    returns best_user + similarity score
                              │
                    [FPGA RTL: hdmi_stream_mux]
                    auth=1 → pass PC HDMI to monitor
                    auth=0 → show camera feed on monitor
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Vivado Design Suite | 2020.2 (or 2021.x) | FPGA synthesis, place & route, bitstream |
| Vivado HLS | bundled with Vivado 2020.2 | Synthesize C++ cosine match accelerator |
| PYNQ-Z2 board | rev C or later | Target hardware |
| SD card | ≥ 8 GB, Class 10 | Boot medium for PYNQ |
| DroidCam | Android / iOS | Phone as network camera |
| Python | 3.8+ | On your laptop (for prep only) |

> **Note:** Vivado 2020.2 includes both Vivado and Vivado HLS. In 2021.x and
> later, HLS was rebranded to **Vitis HLS** — the TCL commands are the same
> (`vivado_hls` → `vitis_hls`). Adjust the command name accordingly.

---

## Part 1 — Install Vivado

### 1.1 Download

1. Go to [xilinx.com/support/download](https://www.xilinx.com/support/download.html)
2. Select **Vivado Design Suite – HLx Editions**, version **2020.2**
3. Download the **Self Extracting Web Installer** (you will need a free Xilinx account)

### 1.2 Install

```bash
chmod +x Xilinx_Unified_2020.2_*.bin
sudo ./Xilinx_Unified_2020.2_*.bin
```

In the installer GUI:
- Product: **Vivado HL WebPACK** (free, no license needed for Zynq-7020)
- Devices: check **SoCs → Zynq-7000**
- Options: check **Vivado HLS** (included by default in 2020.2)
- Install path: `/tools/Xilinx` (recommended)

### 1.3 Add to PATH

```bash
echo 'source /tools/Xilinx/Vivado/2020.2/settings64.sh' >> ~/.bashrc
source ~/.bashrc

# Verify
vivado -version          # should print Vivado v2020.2
vivado_hls -version      # should print Vivado HLS v2020.2
```

---

## Part 2 — Install Digilent IP Library

The HDMI IN/OUT IPs (`dvi2rgb`, `rgb2dvi`) come from Digilent's open-source
library. These are required for HDMI to work correctly with the ADV7511/7612
chips on the PYNQ-Z2.

```bash
# Clone into the project root (next to main/ and reference/)
cd /Users/samarthms/Documents/rc_fproj
git clone https://github.com/Digilent/vivado-library.git
```

The `create_project.tcl` script automatically looks for this at
`../../vivado-library/ip` relative to `main/vivado_project/`.

---

## Part 3 — Install PYNQ-Z2 Board Files

Vivado needs board files to apply the PYNQ-Z2 preset (pin mapping, DDR config, etc.).

```bash
# Download board files
git clone https://github.com/cathalmccabe/pynq-z2_board_files.git /tmp/pynq_board_files

# Copy into Vivado board directory
sudo cp -r /tmp/pynq_board_files/pynq-z2 \
    /tools/Xilinx/Vivado/2020.2/data/boards/board_files/
```

Verify in Vivado: **Tools → Boards** — you should see "PYNQ-Z2" listed.

---

## Part 4 — Build the HLS Accelerator

This synthesizes the `cosine_match_accel` C++ source into a Vivado IP block.
Run this **before** the Vivado block design.

```bash
cd /Users/samarthms/Documents/rc_fproj/main/hls

# Run C simulation + synthesis + IP export
vivado_hls -f run_hls.tcl
```

What this does:
1. **C Simulation** — compiles and runs `cosine_match_tb.cpp` against the float
   reference. All 4 tests should pass.
2. **C Synthesis** — converts C++ to RTL. In the console output, look for:
   ```
   Timing Summary:  Target CP: 10.00 ns   Estimated: ~6 ns   ✓
   Utilization:
     DSP48:   8     ← 8 parallel MAC units (from UNROLL factor=8)
     BRAM:    1     ← enrolled user database
     LUT:    ~200
   ```
3. **IP Export** — writes `cosine_match_ip/` directory (a standard Vivado IP).

**Expected output directory:**
```
main/hls/cosine_match_ip/
  xilinx_com_hls_cosine_match_accel_1_0.zip
  component.xml
  ...
```

> If you are using **Vitis HLS (2021.x+)**, replace `vivado_hls` with
> `vitis_hls` — the TCL script and all pragmas are identical.

---

## Part 5 — Build the Vivado Project (Bitstream)

```bash
cd /Users/samarthms/Documents/rc_fproj/main/vivado_project

vivado -mode batch -source create_project.tcl
```

This will take **20–60 minutes** depending on your machine.

### What to watch for

During synthesis/implementation, Vivado prints timing and utilization summaries.
At the end you should see:

```
Route Design Complete.
write_bitstream: design_1.bit
write_hw_platform: design_1.xsa
============================================
 Build complete
   Bitstream : design_1.bit
   HW handoff: design_1.xsa
============================================
```

### If the build fails

| Error message | Fix |
|---------------|-----|
| `board_part not found: tul.com.tw:pynq-z2` | Board files not installed (Part 3) |
| `IP not found: digilentinc.com:ip:dvi2rgb` | Digilent IP not cloned (Part 2) |
| `IP not found: pynq_z2:face_recog:cosine_match_accel` | HLS IP not built (Part 4) |
| Timing violation (WNS < 0) | Non-critical for a demo — bitstream still loads |

---

## Part 6 — Flash PYNQ-Z2 SD Card

### 6.1 Download PYNQ image

1. Go to [pynq.io/board.html](http://www.pynq.io/board.html)
2. Select **PYNQ-Z2**, download **PYNQ v2.7** (or latest)
3. Flash to SD card using [balenaEtcher](https://www.balena.io/etcher/):
   - Source: downloaded `.img` file
   - Target: your SD card (≥ 8 GB)

### 6.2 Boot the board

1. Insert SD card into PYNQ-Z2
2. Set boot jumper **JP4** to **SD** (covers the two pins closest to the SD slot)
3. Connect Ethernet cable from board to your router (or directly to laptop)
4. Connect USB-A to micro-USB cable (power + serial console)
5. Power on (slide switch to ON)

### 6.3 Find the board IP

The board gets an IP via DHCP. Default hostname is `pynq`:

```bash
# From your laptop:
ping pynq          # or ping pynq.local
ssh xilinx@pynq    # password: xilinx
```

If hostname does not resolve, check your router's DHCP table or use:
```bash
nmap -sn 192.168.1.0/24 | grep pynq
```

---

## Part 7 — Transfer Files to Board

From your laptop, copy the bitstream and Python code:

```bash
# Set board IP (replace with your board's IP)
BOARD_IP=192.168.1.XXX

# Copy bitstream and hardware handoff
scp main/vivado_project/design_1.bit  xilinx@$BOARD_IP:/home/xilinx/face_recog/
scp main/vivado_project/design_1.xsa  xilinx@$BOARD_IP:/home/xilinx/face_recog/

# Copy Python application
scp main/python/*.py                  xilinx@$BOARD_IP:/home/xilinx/face_recog/
scp main/python/requirements.txt      xilinx@$BOARD_IP:/home/xilinx/face_recog/
```

---

## Part 8 — Set Up Python Environment on Board

SSH into the board:

```bash
ssh xilinx@$BOARD_IP    # password: xilinx
cd /home/xilinx/face_recog
```

### 8.1 Install dependencies

```bash
# PYNQ image comes with pip and most scientific packages pre-installed
pip install face-recognition opencv-python-headless requests

# face-recognition pulls in dlib which must compile from source — this takes
# 10–20 minutes on the Cortex-A9. Get a coffee.
# If it fails with CMake errors:
sudo apt-get install -y cmake libopenblas-dev liblapack-dev
pip install dlib
pip install face-recognition
```

### 8.2 Verify installation

```python
python3 -c "import face_recognition, cv2, pynq; print('All imports OK')"
```

---

## Part 9 — Set Up DroidCam

### On your phone (Android)

1. Install **DroidCam** from Google Play Store
2. Open DroidCam, note the **WiFi IP** shown on screen (e.g., `192.168.1.50`)
3. The video stream URL is: `http://192.168.1.50:4747/video`

### Update the camera URL in code

```bash
# On the board, edit the DroidCam URL to match your phone's IP
nano /home/xilinx/face_recog/main.py
```

Find line:
```python
url="http://192.168.1.100:4747/video",
```
Change `192.168.1.100` to your phone's actual IP shown in DroidCam.

### Connect phone to same WiFi as the board

Both the PYNQ-Z2 board and your phone must be on the **same WiFi network**.

---

## Part 10 — Hardware Connections

```
[PC / Laptop] ──HDMI──► [HDMI IN port on PYNQ-Z2]
                         [HDMI OUT port on PYNQ-Z2] ──HDMI──► [Monitor]
[Phone]       ──WiFi──► [PYNQ-Z2 Ethernet]
```

> **HDMI IN** is the port labeled "HDMI IN" on the PYNQ-Z2 silkscreen (near the edge).
> **HDMI OUT** is the other HDMI port (labeled "HDMI OUT").

Make sure:
- PC is outputting a display signal (not in sleep mode)
- Monitor is set to the correct HDMI input

---

## Part 11 — Enroll Your Face

Before recognition works, you must register at least one user.

```bash
ssh xilinx@$BOARD_IP
cd /home/xilinx/face_recog

python3 main.py \
    --bitstream design_1.bit \
    --mode enroll \
    --user alice \
    --camera phone
```

You will see:
```
Enrolling user: alice
Sample 1/15
Sample 2/15
...
Sample 15/15
Enrolled 'alice' successfully
```

**Tips for good enrollment:**
- Good, even lighting on your face
- Look directly at the camera
- Slight variation across samples is fine (different angles, expressions)
- Only one face in frame during enrollment
- Saved to: `/home/xilinx/face_recog/data/users.json`

Enroll more users the same way (`--user bob`, etc.). Up to 32 users supported
(limited by FPGA BRAM for the cosine match accelerator).

---

## Part 12 — Run Recognition

```bash
python3 main.py \
    --bitstream design_1.bit \
    --mode recognition \
    --camera phone
```

### What to expect

| Situation | HDMI OUT shows |
|-----------|---------------|
| No face in frame | Camera feed (phone view) |
| Unrecognized face | Camera feed with red bounding box |
| Recognized face (8 consecutive frames) | PC desktop / HDMI IN signal |
| Recognized face then leaves frame (3 consecutive bad frames) | Switches back to camera feed |

The FPGA switches the video source **within one frame** (~16 ms) of an
authorization state change — no Python scheduling delay.

### Status LEDs on board

| LED | Meaning |
|-----|---------|
| LD0 | Solid ON = PL bitstream loaded and running |
| LD1 | ON = authorized user present (HDMI passthrough active) |
| LD2 | Blinking = camera VDMA stream flowing |
| LD3 | ON = HDMI IN signal detected from PC |

---

## Part 13 — Dynamic Enrollment (Without Restarting)

While recognition is running, you can enroll a new user without stopping:

```bash
# On the board (new terminal):
echo '{"username": "bob"}' > /home/xilinx/face_recog/enroll_request.json
```

The running recognition loop detects this file, switches to enrollment mode for
user "bob", captures 15 samples, saves to database, syncs to FPGA BRAM, then
resumes recognition automatically.

---

## Part 14 — Jupyter Notebook (Optional Alternative UI)

PYNQ comes with JupyterLab. You can control the system from a browser:

1. Open `http://$BOARD_IP` in your browser (password: `xilinx`)
2. Upload the `.py` files via the file browser
3. Create a new notebook and run cells:

```python
from main import FaceRecognitionSystem

system = FaceRecognitionSystem(
    bitstream_path="design_1.bit",
    camera_source="phone"
)
system.setup()
```

---

## Troubleshooting

### Camera not connecting

```bash
# Test DroidCam stream from the board
python3 -c "
import cv2
cap = cv2.VideoCapture('http://192.168.1.50:4747/video')
ret, frame = cap.read()
print('Frame captured:', ret, frame.shape if ret else 'FAILED')
"
```

If it fails: check that phone and board are on same network, DroidCam is open,
and the URL IP matches your phone.

### FPGA IP not found in overlay

```
AttributeError: 'Overlay' object has no attribute 'cosine_match_accel_0'
```

This means the HLS IP was not included in the bitstream. Check:
1. Did you run `vivado_hls -f run_hls.tcl` before `create_project.tcl`?
2. Is `main/hls/cosine_match_ip/` present?
3. Check the Vivado build log for warnings about missing IPs.

The system gracefully falls back to CPU cosine similarity if the IP is missing.

### HDMI IN not detected (LD3 off)

- Check PC HDMI cable is connected
- Try a different HDMI cable
- Make sure PC is not in sleep/screensaver mode
- The dvi2rgb IP requires a valid TMDS clock from the source

### "No face detected" during enrollment

- Ensure good lighting (avoid backlight)
- Phone camera should be at roughly face height, ~50 cm away
- If using DroidCam, check the phone screen is on and preview is showing

### face-recognition install fails (dlib compilation error)

```bash
sudo apt-get install -y python3-dev build-essential cmake \
    libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev
pip install --no-cache-dir dlib
pip install face-recognition
```

### Vivado HLS: all tests FAIL

Check that the fixed-point format matches:
- Embeddings from `face_recognition` are float64, L2-normalized to ~unit norm
- Q2.14 range is [-2, 2) — sufficient since components are in [-1, 1]
- If precision errors are too large, change `ap_fixed<16,2>` to `ap_fixed<24,2>`
  in `cosine_match.h` (trades BRAM for accuracy)

---

## Quick Reference — Key Commands

```bash
# Build HLS IP
cd main/hls && vivado_hls -f run_hls.tcl

# Build bitstream
cd main/vivado_project && vivado -mode batch -source create_project.tcl

# Transfer to board
scp main/vivado_project/design_1.{bit,xsa} main/python/*.py xilinx@$BOARD_IP:/home/xilinx/face_recog/

# Enroll user
python3 main.py --bitstream design_1.bit --mode enroll --user alice

# Run recognition
python3 main.py --bitstream design_1.bit --mode recognition

# Enroll while running
echo '{"username": "alice"}' > enroll_request.json
```