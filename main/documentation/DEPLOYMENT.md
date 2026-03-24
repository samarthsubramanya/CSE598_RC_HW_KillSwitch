# PYNQ-Z2 Deployment Guide

## System Requirements

### Hardware
- **PYNQ-Z2 Board** with 512MB DDR3 RAM
- **Micro SD Card** (≥8GB, Class 10)
- **Micro USB Cable** (for power & serial)
- **HDMI Cable** & Monitor (for video output)
- **Ethernet Cable** (for network access)
- **1280×720p or higher monitor**

### PC (for development)
- Linux, macOS, or Windows with WSL2
- Python 3.8+
- Xilinx Vivado (for bitstream generation)

---

## Phase 1: SD Card Preparation

### 1.1 Download PYNQ Image

```bash
# Download from official PYNQ repository
wget https://github.com/Xilinx/PYNQ/releases/download/v2.7/PYNQ-Z2.img.zip
unzip PYNQ-Z2.img.zip
```

### 1.2 Write to SD Card

**Linux/macOS:**
```bash
# Find SD card device
diskutil list  # macOS
# or
lsblk  # Linux

# Unmount
diskutil unmountDisk /dev/diskX  # macOS
sudo umount /dev/sdX*  # Linux

# Write image
dd if=PYNQ-Z2.img of=/dev/diskX bs=4M  # macOS
# or
sudo dd if=PYNQ-Z2.img of=/dev/sdX bs=4M  # Linux

# Eject
diskutil eject /dev/diskX  # macOS
```

**Windows:**
- Use Etcher: https://www.balena.io/etcher/

---

## Phase 2: Board Setup

### 2.1 Boot PYNQ

1. Insert SD card into board
2. Connect:
   - Micro USB power
   - Ethernet for network
   - HDMI monitor (optional, can use SSH)
3. Power on (LED should light up)
4. Wait 2-3 minutes for boot (watch status LEDs)

### 2.2 Connect to Board

**Option A: Ethernet + Jupyter**
```bash
# Find board IP
ping pynq  # or check router for IP

# Access Jupyter
http://pynq:9090  # username/password: xilinx/xilinx
```

**Option B: Serial Terminal**
```bash
# macOS/Linux
screen /dev/ttyUSB0 115200

# Or use miniterm
python -m serial.tools.miniterm /dev/ttyUSB0 115200
```

**Option C: SSH**
```bash
ssh xilinx@pynq
# password: xilinx
```

---

## Phase 3: Install Face Recognition

### 3.1 Copy Files to Board

```bash
# From development PC
scp -r main/python xilinx@pynq:/home/xilinx/face_recognition
scp main/documentation/* xilinx@pynq:/home/xilinx/face_recognition/docs
```

### 3.2 Install Dependencies

```bash
# SSH into board
ssh xilinx@pynq

# Update packages
sudo pip install --upgrade pip
pip install numpy opencv-python face-recognition

# Verify installation
python -c "import cv2; print(f'OpenCV {cv2.__version__}')"
python -c "import numpy; print(f'NumPy {numpy.__version__}')"
```

### 3.3 Copy Bitstream

```bash
# From Vivado build
scp main/vivado_project/face_recognition.bit xilinx@pynq:/home/xilinx/
scp main/vivado_project/face_recognition.hwh xilinx@pynq:/home/xilinx/
```

---

## Phase 4: Configure Camera

### 4.1 Mobile Phone (Camo or Droidcam)

**For macOS/Linux user (optional, you already have Camo):**

If using different network camera:
- Download app to phone (Camo, Droidcam, IP Webcam)
- Connect phone to same network as PYNQ
- Note the streaming URL

**Default URLs:**
- Camo: `http://127.0.0.1:9095/video` (local only)
- Droidcam: `http://192.168.1.X:4747/video`
- IP Webcam: `http://192.168.1.X:8080/video`

### 4.2 Update Camera URL in Python

File: `python/main.py`
```python
# Edit line ~150
camera = NetworkCamera(url="http://192.168.1.100:4747/video")
# Or use phone camera if on same network
```

### 4.3 Test Camera Connection

```bash
cd /home/xilinx/face_recognition
python -c "
from python.camera_interface import NetworkCamera
cam = NetworkCamera(url='http://192.168.1.X:4747/video')
if cam.connect():
    frame = cam.read_frame()
    print(f'Frame: {frame.shape if frame is not None else None}')
    cam.disconnect()
"
```

---

## Phase 5: Test System

### 5.1 Verify Bitstream Loading

```bash
python -c "
from pynq import Overlay
import os

bitstream = '/home/xilinx/face_recognition.bit'
overlay = Overlay(bitstream)
print('✅ Bitstream loaded successfully')
print(f'IP Blocks: {overlay.ip_dict.keys()}')
"
```

### 5.2 Test Recognition Loop

**Enrollment (capture your face):**
```bash
cd /home/xilinx/face_recognition
python python/main.py \
    --bitstream /home/xilinx/face_recognition.bit \
    --mode enroll \
    --user "your_name" \
    --camera "phone" \
    --verbose
```

**Expected output:**
```
[INFO] Face Recognition System initialized
[INFO] Setting up FPGA...
[INFO] Bitstream loaded successfully
[INFO] Setting up camera...
[INFO] Using network camera
[INFO] Starting enrollment for user: your_name
✅ Embedding 1/15 captured
✅ Embedding 2/15 captured
...
✅ Successfully enrolled your_name
```

**Recognition Test:**
```bash
python python/main.py \
    --bitstream /home/xilinx/face_recognition.bit \
    --mode recognition \
    --camera "phone" \
    --verbose
```

**Expected output:**
```
[INFO] Starting recognition mode
[INFO] Processed 30 frames
[INFO] Processed 60 frames
```

Look at HDMI monitor for live output with bounding boxes and status.

---

## Phase 6: Integration & Optimization

### 6.1 Create Systemd Service (optional)

File: `/etc/systemd/system/face-recognition.service`
```ini
[Unit]
Description=PYNQ Face Recognition
After=network.target

[Service]
Type=simple
User=xilinx
WorkingDirectory=/home/xilinx/face_recognition
ExecStart=/usr/bin/python3 /home/xilinx/face_recognition/python/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable service
sudo systemctl enable face-recognition.service
sudo systemctl start face-recognition.service
```

### 6.2 Monitor Performance

```bash
# Check FPS and latency
python python/main.py --bitstream ... --verbose 2>&1 | grep -E "FPS|latency"

# Monitor FPGA temperature
echo "$(cat /proc/device-tree/amba/zy/temperature) >> /tmp/fpga_temp.log"

# Monitor CPU usage
watch -n 1 "ps aux | grep python"
```

### 6.3 Debug Issues

**No HDMI output:**
- Check cable connections
- Verify HDMI controller hardware
- Test with continuous pattern first

**High latency:**
- Check frame rate vs processing time
- Reduce resolution if needed
- Profile Python code bottlenecks

**FPGA errors:**
- Read status register: `fpga.mmio.read(0x000004)`
- Check error flag bit 10
- Verify AXI transactions

---

## Phase 7: Production Deployment

### 7.1 User Database

Database location: `data/users.json`

**Backup before deployment:**
```bash
cp data/users.json data/users.backup.json
```

**Pre-enrollment multiple users:**
```bash
for user in alice bob charlie; do
  python main.py --mode enroll --user $user
done
```

### 7.2 Secure Configuration

```bash
# Set permissions
chmod 600 data/users.json
sudo chown xilinx:xilinx data/

# Disable root SSH
sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

### 7.3 Hardware Limits

**Temperature monitoring:**
```bash
# Enable throttling if FPGA > 70°C
devcfg_ctrl=$(devmem 0xF8007000)
# Set throttle bit (requires kernel modification)
```

**Power management:**
```bash
# Run at reduced frequency for lower power
echo "performance" | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Or set to "powersave" for battery operation
```

---

## File Structure

```
/home/xilinx/
├── face_recognition/
│   ├── python/
│   │   ├── main.py
│   │   ├── fpga_interface.py
│   │   ├── camera_interface.py
│   │   ├── recognition.py
│   │   ├── hdmi_overlay.py
│   │   └── user_db.py
│   ├── data/
│   │   └── users.json
│   ├── docs/
│   │   ├── ARCHITECTURE.md
│   │   ├── BITSTREAM_GUIDE.md
│   │   └── DEPLOYMENT.md
│   └── README.md
├── face_recognition.bit
└── face_recognition.hwh
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pynq'"
```bash
pip install pynq>=2.7
```

### "Failed to load bitstream"
```bash
# Check file exists and permissions
ls -la /home/xilinx/face_recognition.bit
# Should be readable
```

### "AXI communication timeout"
```bash
# Verify FPGA is programmed
devmem 0xF8007000  # Should show non-zero

# Reset FPGA
pynq.pl.reset()
```

### "No faces detected"
- Check lighting
- Verify camera connection
- Test with reference image first

---

## Performance Metrics

On PYNQ-Z2 with typical setup:

| Metric | Performance |
|--------|-------------|
| Frame Input | 33 ms (30 FPS from camera) |
| Face Detection | 10-15 ms (FPGA) |
| CNN Embedding | 15-20 ms per face (FPGA) |
| Recognition Matching | 2-5 ms (CPU) |
| Overlay Generation | 5-10 ms (CPU) |
| Total Latency | 50-70 ms |
| Effective FPS | 14-20 FPS |

---

## Next Steps

1. ✅ Hardware setup complete
2. ✅ Bitstream deployed
3. ✅ System running
4. ⏳ Run inference test
5. ⏳ Optimize for specific use case
6. ⏳ Deploy to production

---

**For more details, see:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - Hardware design
- [BITSTREAM_GUIDE.md](BITSTREAM_GUIDE.md) - FPGA build process
