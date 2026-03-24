# PYNQ-Z2 Constraints File
# HDMI Pinout and Timing

# HDMI Output Signals
set_property PACKAGE_PIN H16 [get_ports hdmi_clk]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_clk]

set_property PACKAGE_PIN K17 [get_ports hdmi_hs]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_hs]

set_property PACKAGE_PIN L14 [get_ports hdmi_vs]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_vs]

set_property PACKAGE_PIN K16 [get_ports hdmi_de]
set_property IOSTANDARD LVCMOS33 [get_ports hdmi_de]

# HDMI Data Bus (24-bit RGB888)
# Red channel (8 bits)
set_property PACKAGE_PIN H17 [get_ports {hdmi_data[23]}]
set_property PACKAGE_PIN H18 [get_ports {hdmi_data[22]}]
set_property PACKAGE_PIN J16 [get_ports {hdmi_data[21]}]
set_property PACKAGE_PIN J17 [get_ports {hdmi_data[20]}]
set_property PACKAGE_PIN J18 [get_ports {hdmi_data[19]}]
set_property PACKAGE_PIN K18 [get_ports {hdmi_data[18]}]
set_property PACKAGE_PIN L17 [get_ports {hdmi_data[17]}]
set_property PACKAGE_PIN L18 [get_ports {hdmi_data[16]}]

# Green channel (8 bits)
set_property PACKAGE_PIN L15 [get_ports {hdmi_data[15]}]
set_property PACKAGE_PIN L16 [get_ports {hdmi_data[14]}]
set_property PACKAGE_PIN M16 [get_ports {hdmi_data[13]}]
set_property PACKAGE_PIN M17 [get_ports {hdmi_data[12]}]
set_property PACKAGE_PIN N17 [get_ports {hdmi_data[11]}]
set_property PACKAGE_PIN N18 [get_ports {hdmi_data[10]}]
set_property PACKAGE_PIN P18 [get_ports {hdmi_data[9]}]
set_property PACKAGE_PIN P17 [get_ports {hdmi_data[8]}]

# Blue channel (8 bits)
set_property PACKAGE_PIN M14 [get_ports {hdmi_data[7]}]
set_property PACKAGE_PIN M15 [get_ports {hdmi_data[6]}]
set_property PACKAGE_PIN N14 [get_ports {hdmi_data[5]}]
set_property PACKAGE_PIN N15 [get_ports {hdmi_data[4]}]
set_property PACKAGE_PIN P14 [get_ports {hdmi_data[3]}]
set_property PACKAGE_PIN P15 [get_ports {hdmi_data[2]}]
set_property PACKAGE_PIN R14 [get_ports {hdmi_data[1]}]
set_property PACKAGE_PIN R15 [get_ports {hdmi_data[0]}]

# Set HDMI data bus voltage standard
foreach i {0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23} {
    set_property IOSTANDARD LVCMOS33 [get_ports {hdmi_data[$i]}]
}

# AXI Clock Input (100 MHz from PS)
set_property PACKAGE_PIN N20 [get_ports axi_aclk]
set_property IOSTANDARD LVCMOS33 [get_ports axi_aclk]

# AXI Reset
set_property PACKAGE_PIN P20 [get_ports axi_aresetn]
set_property IOSTANDARD LVCMOS33 [get_ports axi_aresetn]

# Timing Constraints

# AXI Clock (100 MHz)
create_clock -period 10.000 -name axi_clk -waveform {0 5} [get_ports axi_aclk]

# HDMI Clock (148.5 MHz for 1280x720@60Hz)
# Generated from MMCM in PS, constraint handled by IP

# HDMI timing (no hold time required, setup from S/H)
set_output_delay -clock [get_clocks axi_clk] -min -1.5 [get_ports hdmi_*]
set_output_delay -clock [get_clocks axi_clk] -max 1.5 [get_ports hdmi_*]

# Prevent clock skew
set_property CLOCK_DEDICATED_ROUTE any_same_die [get_nets axi_aclk]

# Power configuration
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

# Done
