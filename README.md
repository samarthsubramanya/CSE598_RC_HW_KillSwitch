# Primary branch

# FPGA-Based Hardware Killswitch to protect Sensitive Systems

This project implements a hardware killswitch using an FPGA to protect sensitive systems from unauthorized access or tampering. The FPGA board, designed for PYNQ-Z2, acts as middleware between a computer System and Monitor. We have used a Mobile Application to act as camera to capture and send the Frames to the Python runtime on the board.

## Folder Structure

There are 3 main folders:
#### reference
This is a pure python implementation of the facial recognition system on the computer. Although this is not completely equivalent to the KillSwitch and Video pass-through logic, we have used it as reference for performance and analysis. The code can be run by creating virtual environemnt and installing the requirements.txt file. The main file is `main.py` which can be run by executing `python main.py` in the terminal.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd reference/
python3 main.py

```

There is command line options on terminal to perform the respective operation.

#### android

This code contains the source code for the Android Application developed to stream images to PYNQ board. Although this is out of scope of this project, We have included the code to show our developmental effort. You will need Android Studio to build and run it.

#### pynq 
This code contains the source code for the PYNQ board. We kept in form of jupyter notebook for easier execution but we have also provided scripts for ideal scenario.
The files are as follows:
- fpga_register.py: This file contains the code to register a new user by capturing their face and generating an embedding by using mean on the three embeddings generated from each face orientation. The embedding is then saved to the disk for future use. Need to be run manually on PYNQ board. But can be automated with switch controls.
- cosine_driver.py: This file contains the code to act as bare-mental driver to control the AXI-Lite with register relevant code, such as start, stop, read and write to the registers. This is used in the video pass-through logic to control the VDMA and the overlay logic.
- authorized_embedings/ : This folder contains the saved embeddings of the authorized users. Each user has a separate file with their name and the embedding is saved as a .npy file.
- AuthGraphics/ : This folder contains the code for the video pass-through logic without using VDMA. There is no camera preview when unauthenticated/not authorized. It shows custom overlay text of authorized/not authorized on the display.

- CameraPreview/ : This folder contains the code for the video pass-through logic using VDMA. It shows the camera preview on the display when authenticated/authorized. 

    - each of these folders contains the jupyter notebook and the python code with same logic and code .
 
    - There are also relevant hardware handoff files, bitstream files and the verilog files used in the project.

    - These can be compiled again by setting up appropriate logic in the file and generating files appropriately.

- verilog: This folder contains the verilog code for the hardware logic used in the project. The individual files are as follows:
    - auth_graphics_overlay.v - Responsible for drawing authorized/not authorized text with background on the display in AuthGraphics version
    - cosine_sim_axi.v - manage embeddings and output through the axi interface for cosine similarity.
    - cosine_similarity.v - compute cosine similarity between the input embedding and the stored embedding and output the result through the axi interface.
    - hdmi_auth.v - Logic to control the HDMI passthrough from input to output or block it and write other data such as custom auth graphics or Camera Preview feed.

