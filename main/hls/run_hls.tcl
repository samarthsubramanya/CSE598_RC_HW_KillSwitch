# Vivado HLS build script for cosine_match_accel
# Usage: vivado_hls -f run_hls.tcl
#
# Outputs:
#   cosine_match_ip/   — Vivado IP export (add this to IP repo in create_project.tcl)

open_project cosine_match_hls
set_top cosine_match_accel

add_files cosine_match.cpp
add_files -tb cosine_match_tb.cpp

open_solution "solution1"
set_part xc7z020clg400-1
create_clock -period 10 -name default   ;# 100 MHz

# Run C simulation (verify fixed-point against float reference)
csim_design

# Synthesize to RTL
csynth_design

# Run RTL co-simulation (optional — takes longer)
# cosim_design

# Export as Vivado IP
export_design -format ip_catalog -output cosine_match_ip -vendor "pynq_z2" \
              -library "face_recog" -ipname "cosine_match_accel" -version "1.0" \
              -description "128-D cosine similarity search accelerator for face recognition"

close_project