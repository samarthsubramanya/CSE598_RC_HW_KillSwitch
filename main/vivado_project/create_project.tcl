# Vivado Project Creation Script
# Usage: vivado -source create_project.tcl

# Create project
create_project face_recognition . -part xc7z020-1clg400-1

# Set board
set_property board_part xilinx.com:pynq:z2:1.0 [current_project]

# Add Verilog sources
add_files -norecurse {
    ../hdl/top.v
    ../hdl/axi_slave_interface.v
    ../hdl/haar_detector.v
    ../hdl/cnn_engine.v
    ../hdl/hdmi_output.v
}

# Set top module
set_property top face_recognition_top [get_filesets sources_1]

# Add constraints
add_files -fileset constrs_1 -norecurse ./constraints.xdc

# Synthesize
synth_design -top face_recognition_top -part xc7z020-1clg400-1

# Place and route
opt_design
place_design
route_design

# Write bitstream
write_bitstream face_recognition.bit

# Write hwh for PYNQ
write_hw_platform -force face_recognition.hwh

puts "Build complete: face_recognition.bit"
