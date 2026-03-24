# PYNQ-Z2 Bitstream Generation Guide

## Overview

This guide walks through creating the FPGA bitstream from Verilog RTL using Xilinx Vivado.

## Prerequisites

- **Xilinx Vivado 2021.2 or later** (free WebPACK version supported)
- **PYNQ-Z2 BSP** (Board Support Package)
- **Verilog RTL files** (hdl/*.v)

**Download:**
- Vivado: https://www.xilinx.com/support/download.html
- PYNQ-Z2 BSP: https://github.com/Xilinx/PYNQ-Libraries

---

## Step 1: Create Vivado Project

### Option A: Automated (Script)

```bash
cd main/vivado_project
source create_project.tcl
```

### Option B: Manual in Vivado GUI

1. **File → New Project**
2. **Project Name:** `face_recognition`
3. **Project Location:** `main/vivado_project`
4. **Part Selection:** `xc7z020-1clg400-1` (Zynq-7020 for PYNQ-Z2)
5. **Board Selection:** PYNQ-Z2

---

## Step 2: Add Verilog Sources

1. **Flow → Add Sources**
2. **Add or create design sources**
3. Add all files from `main/hdl/`:
   - `top.v`
   - `axi_slave_interface.v`
   - `haar_detector.v`
   - `cnn_engine.v`
   - `hdmi_output.v`

---

## Step 3: Create Constraints File

Create `main/constraints.xdc`:

```tcl
# HDMI Output Pins (PYNQ-Z2 mapping)
set_property PACKAGE_PIN H16 [get_ports hdmi_clk]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_clk]

set_property PACKAGE_PIN K17 [get_ports hdmi_hs]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_hs]

set_property PACKAGE_PIN L14 [get_ports hdmi_vs]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_vs]

set_property PACKAGE_PIN K16 [get_ports hdmi_de]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_de]

# HDMI Data Pins (RGB 8-8-8)
set_property PACKAGE_PIN H17 [get_ports {hdmi_data[0]}]
set_property PACKAGE_PIN J16 [get_ports {hdmi_data[1]}]
set_property PACKAGE_PIN J17 [get_ports {hdmi_data[2]}]
# ... (continue for hdmi_data[3:23])

# AXI Clocking
set_property PACKAGE_PIN K18 [get_ports axi_aclk]
set_property IOSTANDARD LVCMOS33 [get_ports axi_aclk]

# Create clocking constraint (100 MHz)
create_clock -period 10.000 -name sys_clk_pin -waveform {0 5} [get_ports axi_aclk]
```

---

## Step 4: Create Block Diagram (ARM Interface)

1. **Create Block Design**: IP → Create Design
2. **Add IP**: Search for "ZYNQ7 Processing System"
3. **Configure ZYNQ:**
   - PS to PL Clock: 100 MHz
   - Enable AXI4 Lite Master
   - Configure GPIO if needed

4. **Add Custom HDL:** Right-click → Create Hierarchical Design
   - Add instance of `face_recognition_top`

5. **Connect AXI Interconnect**
   - ARM CPU AXI4 Lite Master → Face Recognition top module

---

## Step 5: Run Synthesis & Implementation

```bash
# In Vivado TCL console or script:
launch_runs synth_1
wait_on_run synth_1

launch_runs impl_1
wait_on_run impl_1
```

**Expected Results:**
- Slice Utilization: 40-50%
- Block RAM: 60-70%
- Timing Met: YES

---

## Step 6: Generate Bitstream

```bash
launch_runs impl_1 -to_step write_bitstream
wait_on_run impl_1
```

**Output:** `face_recognition.bit` and `face_recognition.hwh`

---

## Step 7: Create PYNQ Package

### Directory Structure:
```
main/
├── pynq_package/
│   ├── face_recognition/
│   │   ├── bitstream/
│   │   │   ├── face_recognition.bit
│   │   │   └── face_recognition.hwh
│   │   └── pynq/
│   │       ├── face_recognition.py
│   │       └── __init__.py
│   └── setup.py
```

### setup.py:
```python
from setuptools import setup, find_packages

setup(
    name='face-recognition-pynq',
    version='1.0.0',
    packages=find_packages(),
    package_data={
        'face_recognition': [
            'bitstream/*.bit',
            'bitstream/*.hwh',
        ]
    },
    install_requires=[
        'pynq>=2.7',
        'numpy>=1.21',
        'opencv-python>=4.5',
    ],
    author='Your Name',
    description='PYNQ-Z2 Face Recognition with FPGA ML Acceleration'
)
```

---

## Step 8: Test on PYNQ Board

### Installation:

```bash
# On PYNQ board (via SSH or Jupyter)
pip install face-recognition-pynq

# Or from local:
cd main/pynq_package
pip install -e .
```

### Usage:

```python
from face_recognition import FaceRecognitionSystem
import os

# Load bitstream
bitstream_path = os.path.join(
    os.path.dirname(__file__),
    'bitstream/face_recognition.bit'
)

# Run system
system = FaceRecognitionSystem(bitstream_path)
system.setup()
system.run_recognition()
```

---

## Troubleshooting

### Issue: "DRC violations - timing failed"
**Solution:** Relax timing constraints or increase clock period

### Issue: "Resource overflow - slice usage > 100%"
**Solution:** 
- Reduce CNN model size
- Use external memory for weights
- Optimize Verilog

### Issue: "AXI protocol errors in simulation"
**Solution:**
- Check address alignment (32-bit)
- Verify read/write strobes
- Add AXI protocol checker in simulation

### Issue: "No HDMI output on display"
**Solution:**
- Verify HDMI timing parameters
- Check pin assignments (constraints)
- Test with Vivado simulator first

---

## Performance Optimization

### 1. **Pipelining**
- Add registers between stages
- Increase throughput by 2-3×

### 2. **Memory Optimization**
- Use BRAM efficiently for weights
- Implement double-buffering for images

### 3. **Parallelization**
- Process multiple Haar features in parallel
- Pipeline CNN layers

### 4. **Frequency Scaling**
- 100 MHz (default) → 150+ MHz with timing closure

---

## Files Generated

After successful build:

| File | Purpose |
|------|---------|
| `face_recognition.bit` | FPGA bitstream (programmable) |
| `face_recognition.hwh` | Hardware design (for PYNQ overlay) |
| `face_recognition.runs/` | Build artifacts (large, can delete) |

---

## Next Steps

1. ✅ Generate bitstream
2. ⏳ Copy to PYNQ board
3. ⏳ Run Python application
4. ⏳ Test recognition accuracy
5. ⏳ Measure performance/power

For deployment, see [DEPLOYMENT.md](DEPLOYMENT.md)
