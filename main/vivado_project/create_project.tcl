# =============================================================================
# PYNQ-Z2 Face Recognition Kill Switch — Vivado Build Script
# =============================================================================
#
# Usage:
#   vivado -mode batch -source create_project.tcl
#
# Prerequisites:
#   1. Vivado 2020.1 or later (tested with 2020.2)
#   2. PYNQ-Z2 board files installed:
#        https://github.com/cathalmccabe/pynq-z2_board_files
#   3. Digilent IP cores (rgb2dvi, dvi2rgb) installed:
#        https://github.com/Digilent/vivado-library
#      Add the repo path to Vivado: Tools → Settings → IP → Repository
#      or via TCL: set_property ip_repo_paths {/path/to/vivado-library} [current_project]
#
# Block Design Overview:
#   ┌─────────────────────────────────────────────────────────────────┐
#   │  processing_system7  (Zynq PS — dual Cortex-A9)                │
#   │    GP0 AXI master → AXI Interconnect → axi_gpio_0              │
#   │                                       → axi_vdma_0             │
#   │    HP0 AXI slave  ← axi_vdma_0 (MM2S DMA reads)               │
#   └────────────────────────────┬────────────────────────────────────┘
#                                │ PL clock (100 MHz FCLK0)
#   ┌────────────────────────────▼────────────────────────────────────┐
#   │  axi_gpio_0  [1-bit output]  →  auth_flag  →  hdmi_stream_mux  │
#   │  axi_vdma_0  [MM2S stream]   →  cam stream →  hdmi_stream_mux  │
#   │  dvi2rgb_0   [HDMI IN]       →  hdmi stream → hdmi_stream_mux  │
#   │  hdmi_stream_mux             →  rgb2dvi_0   [HDMI OUT]         │
#   └─────────────────────────────────────────────────────────────────┘
#
# =============================================================================

# --- Project setup -----------------------------------------------------------
set project_name "face_recognition_killswitch"
set project_dir  "."
set part         "xc7z020clg400-1"
set board_part   "tul.com.tw:pynq-z2:part0:1.0"

create_project $project_name $project_dir -part $part -force
set_property board_part $board_part [current_project]

# Add custom RTL sources (only hdmi_mux and top wrapper)
add_files -norecurse {
    ../hdl/hdmi_mux.v
    ../hdl/top.v
}
# NOTE: cnn_engine.v and haar_detector.v are excluded — they are stubs only.

# Add Digilent IP repo if it exists locally
set digilent_ip_path "../../vivado-library/ip"
if {[file exists $digilent_ip_path]} {
    set_property ip_repo_paths $digilent_ip_path [current_project]
    update_ip_catalog -quiet
    puts "INFO: Digilent IP repo added from $digilent_ip_path"
} else {
    puts "WARNING: Digilent IP repo not found at $digilent_ip_path"
    puts "         rgb2dvi / dvi2rgb IPs will be missing."
    puts "         Clone: https://github.com/Digilent/vivado-library"
}

# --- Block Design ------------------------------------------------------------
create_bd_design "design_1"
open_bd_design {design_1}

# --- Zynq Processing System --------------------------------------------------
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0

# Apply PYNQ-Z2 board preset (sets DDR, MIO, clocks, etc.)
apply_bd_automation \
    -rule xilinx.com:bd_rule:processing_system7 \
    -config {
        make_external   "FIXED_IO, DDR"
        apply_board_preset "1"
        Master          "Disable"
        Slave           "Disable"
    } [get_bd_cells processing_system7_0]

# Enable GP0 AXI master (for GPIO + VDMA control)
# Enable HP0 AXI slave  (for VDMA DMA reads from DDR)
# FCLK0 = 100 MHz PL clock
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0        {1}  \
    CONFIG.PCW_USE_S_AXI_HP0        {1}  \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_FCLK0_ENABLE         {1}  \
    CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR0 {8} \
    CONFIG.PCW_FCLK0_PERIPHERAL_DIVISOR1 {1} \
] [get_bd_cells processing_system7_0]

# --- AXI GPIO (1-bit auth_flag output) ---------------------------------------
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 axi_gpio_0
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH  {1}            \
    CONFIG.C_ALL_OUTPUTS {1}            \
    CONFIG.C_DOUT_DEFAULT {0x00000000}  \
] [get_bd_cells axi_gpio_0]

# --- AXI VDMA (MM2S only — streams camera frames from DDR to PL) -------------
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_vdma:6.3 axi_vdma_0
set_property -dict [list \
    CONFIG.c_num_fstores          {3}    \
    CONFIG.c_include_mm2s         {1}    \
    CONFIG.c_include_s2mm         {0}    \
    CONFIG.c_mm2s_linebuffer_depth {512} \
    CONFIG.c_m_axi_mm2s_data_width {64}  \
    CONFIG.c_m_axis_mm2s_tdata_width {24} \
] [get_bd_cells axi_vdma_0]

# --- Video Timing Controller (camera stream timing) --------------------------
create_bd_cell -type ip -vlnv xilinx.com:ip:v_tc:6.2 v_tc_0
set_property -dict [list \
    CONFIG.VIDEO_MODE            {720p}  \
    CONFIG.GEN_HACTIVE_SIZE      {1280}  \
    CONFIG.GEN_VACTIVE_SIZE      {720}   \
    CONFIG.GEN_HSYNC_START       {1390}  \
    CONFIG.GEN_HSYNC_END         {1430}  \
    CONFIG.GEN_HFRAME_SIZE       {1650}  \
    CONFIG.GEN_VSYNC_START       {725}   \
    CONFIG.GEN_VSYNC_END         {730}   \
    CONFIG.GEN_VFRAME_SIZE       {750}   \
] [get_bd_cells v_tc_0]

# --- Digilent HDMI IPs -------------------------------------------------------
# dvi2rgb: deserializes HDMI IN TMDS signals → AXI4-Stream RGB
# rgb2dvi: serializes AXI4-Stream RGB → HDMI OUT TMDS signals
#
# These IPs configure the ADV7612 (RX) and ADV7511 (TX) ICs via I2C from PS.
# They are available in the Digilent vivado-library repository.

create_bd_cell -type ip -vlnv digilentinc.com:ip:dvi2rgb:2.0 dvi2rgb_0
set_property -dict [list \
    CONFIG.kEnaStretch {true}    \
    CONFIG.kRstActiveHigh {false} \
] [get_bd_cells dvi2rgb_0]

create_bd_cell -type ip -vlnv digilentinc.com:ip:rgb2dvi:2.0 rgb2dvi_0
set_property -dict [list \
    CONFIG.kGenerateSerialClk {false} \
    CONFIG.kRstActiveHigh {false}     \
] [get_bd_cells rgb2dvi_0]

# --- Custom RTL: HDMI stream mux (kill switch) -------------------------------
# Import hdmi_stream_mux as a module reference block
create_bd_cell -type module -reference hdmi_stream_mux hdmi_mux_0

# --- AXI Interconnect (GP0 → GPIO + VDMA) ------------------------------------
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_ic_0
set_property -dict [list \
    CONFIG.NUM_SI {1} \
    CONFIG.NUM_MI {2} \
] [get_bd_cells axi_ic_0]

# --- Processor System Reset ---------------------------------------------------
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 proc_sys_reset_0

# =============================================================================
# Connections
# =============================================================================

# Clock and reset
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins axi_ic_0/ACLK] \
               [get_bd_pins axi_ic_0/S00_ACLK] \
               [get_bd_pins axi_ic_0/M00_ACLK] \
               [get_bd_pins axi_ic_0/M01_ACLK] \
               [get_bd_pins axi_gpio_0/s_axi_aclk] \
               [get_bd_pins axi_vdma_0/s_axi_lite_aclk] \
               [get_bd_pins axi_vdma_0/m_axi_mm2s_aclk] \
               [get_bd_pins axi_vdma_0/m_axis_mm2s_aclk] \
               [get_bd_pins v_tc_0/clk] \
               [get_bd_pins hdmi_mux_0/cam_aclk] \
               [get_bd_pins proc_sys_reset_0/slowest_sync_clk]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] \
               [get_bd_pins proc_sys_reset_0/ext_reset_in]

connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins axi_ic_0/ARESETN] \
               [get_bd_pins axi_ic_0/S00_ARESETN] \
               [get_bd_pins axi_ic_0/M00_ARESETN] \
               [get_bd_pins axi_ic_0/M01_ARESETN] \
               [get_bd_pins axi_gpio_0/s_axi_aresetn] \
               [get_bd_pins axi_vdma_0/axi_resetn] \
               [get_bd_pins hdmi_mux_0/cam_aresetn]

# GP0 AXI master → Interconnect
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] \
                    [get_bd_intf_pins axi_ic_0/S00_AXI]

# Interconnect → GPIO
connect_bd_intf_net [get_bd_intf_pins axi_ic_0/M00_AXI] \
                    [get_bd_intf_pins axi_gpio_0/S_AXI]

# Interconnect → VDMA control
connect_bd_intf_net [get_bd_intf_pins axi_ic_0/M01_AXI] \
                    [get_bd_intf_pins axi_vdma_0/S_AXI_LITE]

# VDMA DMA → HP0 (DDR access for frame reads)
connect_bd_intf_net [get_bd_intf_pins axi_vdma_0/M_AXI_MM2S] \
                    [get_bd_intf_pins processing_system7_0/S_AXI_HP0]

# VDMA MM2S AXI4-Stream → HDMI mux camera input
connect_bd_intf_net [get_bd_intf_pins axi_vdma_0/M_AXIS_MM2S] \
                    [get_bd_intf_pins hdmi_mux_0/s_cam]

# GPIO auth_flag → HDMI mux select
connect_bd_net [get_bd_pins axi_gpio_0/gpio_io_o] \
               [get_bd_pins hdmi_mux_0/auth_flag]

# dvi2rgb AXI4-Stream → HDMI mux HDMI-IN input
connect_bd_intf_net [get_bd_intf_pins dvi2rgb_0/video_out] \
                    [get_bd_intf_pins hdmi_mux_0/s_hdmi_in]

# HDMI mux output → rgb2dvi
connect_bd_intf_net [get_bd_intf_pins hdmi_mux_0/m_hdmi_out] \
                    [get_bd_intf_pins rgb2dvi_0/RGB]

# Make HDMI I/O pins external (to board HDMI connectors)
make_bd_intf_pins_external [get_bd_intf_pins dvi2rgb_0/TMDS]
make_bd_intf_pins_external [get_bd_intf_pins rgb2dvi_0/TMDS]
set_property name hdmi_in_tmds  [get_bd_intf_ports TMDS_0]
set_property name hdmi_out_tmds [get_bd_intf_ports TMDS_1]

# dvi2rgb / rgb2dvi shared pixel clock (148.5 MHz for 1280x720@60Hz)
# The dvi2rgb IP recovers the pixel clock from TMDS; connect to rgb2dvi
connect_bd_net [get_bd_pins dvi2rgb_0/PixelClk] \
               [get_bd_pins rgb2dvi_0/PixelClk]

# dvi2rgb reset (active-low from proc_sys_reset)
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins dvi2rgb_0/aRst_n]

# Status LEDs (make external)
make_bd_pins_external [get_bd_pins hdmi_mux_0/led]
set_property name led [get_bd_ports led_0]

# =============================================================================
# Address assignments
# =============================================================================
# GP0 sees:
#   axi_gpio_0  at 0x41200000  (4 KB)
#   axi_vdma_0  at 0x43000000  (64 KB)
assign_bd_address [get_bd_addr_segs axi_gpio_0/S_AXI/Reg]
assign_bd_address [get_bd_addr_segs axi_vdma_0/S_AXI_LITE/Reg]

set_property offset 0x41200000 \
    [get_bd_addr_segs {processing_system7_0/Data/SEG_axi_gpio_0_Reg}]
set_property offset 0x43000000 \
    [get_bd_addr_segs {processing_system7_0/Data/SEG_axi_vdma_0_Reg}]

# HP0 sees full DDR (2GB)
assign_bd_address [get_bd_addr_segs processing_system7_0/S_AXI_HP0/HP0_DDR_LOWOCM]
set_property range  2G \
    [get_bd_addr_segs {axi_vdma_0/Data_MM2S/SEG_processing_system7_0_HP0_DDR_LOWOCM}]

# =============================================================================
# Validate, generate, and synthesize
# =============================================================================
validate_bd_design
save_bd_design

# Generate block design output products (HDL wrapper)
generate_target all [get_files design_1.bd]
make_wrapper -files [get_files design_1.bd] -top
add_files -norecurse ./face_recognition_killswitch.srcs/sources_1/bd/design_1/hdl/design_1_wrapper.v
set_property top design_1_wrapper [get_filesets sources_1]

# Add constraints
add_files -fileset constrs_1 -norecurse ./constraints.xdc

# Run implementation
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

# Export bitstream and hardware handoff for PYNQ
write_bitstream -force design_1.bit
write_hw_platform -fixed -include_bit -force design_1.xsa

puts ""
puts "============================================"
puts " Build complete"
puts "   Bitstream : design_1.bit"
puts "   HW handoff: design_1.xsa"
puts ""
puts " Copy both files to the PYNQ-Z2 board."
puts " Load with: from pynq import Overlay"
puts "            ol = Overlay('design_1.bit')"
puts "============================================"