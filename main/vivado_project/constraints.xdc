# =============================================================================
# PYNQ-Z2 Constraints — Face Recognition Kill Switch
# =============================================================================
#
# HDMI IN and HDMI OUT pin assignments are handled automatically by the
# Digilent dvi2rgb / rgb2dvi IP cores when the PYNQ-Z2 board preset is applied
# in Vivado IP Integrator.  You do NOT need to manually assign those pins here.
#
# This file covers:
#   1. PL clock (PS FCLK0 → FPGA fabric)
#   2. Status LEDs (LD0–LD3)
#   3. Power / config settings
#
# Reference pin mapping (PYNQ-Z2 schematic rev. C):
#   https://digilent.com/reference/programmable-logic/pynq-z2/reference-manual
# =============================================================================

# --- PL fabric clock (100 MHz from PS FCLK0) ---------------------------------
# Actual clock is driven by the PS7 IP internally; this constraint names it
# so timing analysis can reference it.
create_clock -period 10.000 -name clk_100M \
    [get_pins processing_system7_0/inst/PS7_i/FCLKCLK[0]]

# --- Status LEDs (active-high, LVCMOS33) -------------------------------------
# LD0 — PL running (always on when bitstream is loaded)
# LD1 — Authorization state (1 = authorized, HDMI passthrough active)
# LD2 — Camera VDMA stream valid
# LD3 — HDMI IN stream valid (signal present on HDMI IN port)

set_property PACKAGE_PIN R14 [get_ports {led[0]}]
set_property PACKAGE_PIN P14 [get_ports {led[1]}]
set_property PACKAGE_PIN N16 [get_ports {led[2]}]
set_property PACKAGE_PIN M14 [get_ports {led[3]}]

set_property IOSTANDARD LVCMOS33 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[3]}]

# Relax output delay for LEDs (no external timing requirement)
set_output_delay -clock clk_100M 0.000 [get_ports {led[*]}]

# --- Power / config -----------------------------------------------------------
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

# --- Bitstream settings -------------------------------------------------------
# Compress bitstream to speed up PYNQ load time
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]