/**
 * PYNQ-Z2 Face Recognition Kill Switch - Top Level Wrapper
 *
 * Architecture Overview:
 * ---------------------
 * Face detection and embedding generation run entirely on the PS (ARM CPU)
 * using the face_recognition Python library (dlib + ResNet-34). The PL
 * handles only what FPGAs do uniquely well: real-time video routing AND
 * hardware sprite compositing.
 *
 * PL Block Design Components (instantiated via IP Integrator in create_project.tcl):
 *   - processing_system7     : Zynq PS (dual Cortex-A9, 667 MHz)
 *   - axi_gpio               : 1-bit output → auth_flag to hdmi_stream_mux
 *   - axi_vdma (MM2S)        : Streams camera frames from PS DDR → PL AXI4-Stream
 *   - v_tc                   : Video timing controller for camera stream
 *   - dvi2rgb                : HDMI IN deserializer (Digilent IP, ADV7612 side)
 *   - rgb2dvi                : HDMI OUT serializer  (Digilent IP, ADV7511 side)
 *   - hdmi_stream_mux (RTL)  : Custom kill-switch mux + sprite compositor
 *   - axi_gpio_sprite (AXI)  : 32-bit AXI GPIO for sprite control registers
 *                              (sprite_x0/y0/x1/y1, visible, alpha, BRAM write port)
 *   - cosine_match_accel(HLS): 128-D dot-product search on 8×DSP48 MAC array
 *
 * Kill Switch Logic (implemented in hdmi_mux.v):
 *   auth_flag = 1  →  pass HDMI IN  → HDMI OUT  (authorized user present)
 *   auth_flag = 0  →  pass camera feed → HDMI OUT (show camera, block PC signal)
 *
 * Sprite Compositor (also in hdmi_mux.v):
 *   When sprite_visible = 1, a configurable rectangular banner is blended
 *   over the active video stream (either HDMI IN or camera) in real-time.
 *   Python writes the sprite pixels into the on-chip BRAM through the AXI
 *   GPIO sprite control interface (see fpga_interface.py / graphics_api.py).
 *
 * PS Python sets auth_flag and sprite registers via AXI GPIO after each
 * recognition decision. FPGA responds within one pixel clock cycle.
 *
 * This file is the synthesizable RTL wrapper for hdmi_stream_mux.
 * All other logic lives in the Vivado block design (see create_project.tcl).
 *
 * Sprite AXI-Lite Register Map (mapped to axi_gpio_sprite or custom AXI slave):
 *   See fpga_interface.py for the full offset table used by Python.
 *   Offsets (byte-addressed from sprite_ctrl base address 0x43C10000):
 *     0x00  sprite_visible   [0]       1 = compositor on
 *     0x04  sprite_alpha     [3:0]     0=transparent 15=opaque
 *     0x08  sprite_x0        [10:0]    left edge pixel (0..1279)
 *     0x0C  sprite_y0        [9:0]     top edge pixel  (0..719)
 *     0x10  sprite_x1        [10:0]    right edge pixel (exclusive)
 *     0x14  sprite_y1        [9:0]     bottom edge pixel (exclusive)
 *     0x18  sprite_wr_en     [0]       pulse high while writing BRAM
 *     0x1C  sprite_wr_addr   [16:0]    BRAM write address
 *     0x20  sprite_wr_data   [23:0]    BRAM pixel (RGB888)
 */

module face_recognition_top (
    // === AXI4-Stream: camera feed from VDMA MM2S read channel ===
    input  wire        cam_aclk,
    input  wire        cam_aresetn,

    input  wire [23:0] s_cam_tdata,
    input  wire        s_cam_tvalid,
    output wire        s_cam_tready,
    input  wire        s_cam_tuser,     // Start-of-Frame
    input  wire        s_cam_tlast,     // End-of-Line

    // === AXI4-Stream: HDMI IN from dvi2rgb IP ===
    input  wire [23:0] s_hdmi_in_tdata,
    input  wire        s_hdmi_in_tvalid,
    output wire        s_hdmi_in_tready,
    input  wire        s_hdmi_in_tuser,
    input  wire        s_hdmi_in_tlast,

    // === AXI4-Stream: output to rgb2dvi IP → HDMI OUT ===
    output wire [23:0] m_hdmi_out_tdata,
    output wire        m_hdmi_out_tvalid,
    input  wire        m_hdmi_out_tready,
    output wire        m_hdmi_out_tuser,
    output wire        m_hdmi_out_tlast,

    // === Authorization flag from AXI GPIO (1-bit output channel) ===
    input  wire        auth_flag,

    // === Sprite compositor control (driven by axi_gpio_sprite in bd) ===
    // PS Python writes these via fpga_interface.py / HardwareGraphicsAPI
    input  wire        sprite_wr_en,
    input  wire [16:0] sprite_wr_addr,
    input  wire [23:0] sprite_wr_data,
    input  wire [10:0] sprite_x0,
    input  wire [9:0]  sprite_y0,
    input  wire [10:0] sprite_x1,
    input  wire [9:0]  sprite_y1,
    input  wire        sprite_visible,
    input  wire [3:0]  sprite_alpha,

    // === Status LEDs (PYNQ-Z2 onboard LEDs LD0-LD3) ===
    output wire [3:0]  led
);

    // ------------------------------------------------------------------
    // HDMI Stream Mux + Sprite Compositor — core kill-switch logic
    // ------------------------------------------------------------------
    hdmi_stream_mux #(
        .SCREEN_W (1280),
        .SCREEN_H (720)
    ) u_mux (
        .aclk               (cam_aclk),
        .aresetn            (cam_aresetn),

        .auth_flag          (auth_flag),

        // Camera feed in (from VDMA)
        .s_cam_tdata        (s_cam_tdata),
        .s_cam_tvalid       (s_cam_tvalid),
        .s_cam_tready       (s_cam_tready),
        .s_cam_tuser        (s_cam_tuser),
        .s_cam_tlast        (s_cam_tlast),

        // HDMI IN (from dvi2rgb)
        .s_hdmi_tdata       (s_hdmi_in_tdata),
        .s_hdmi_tvalid      (s_hdmi_in_tvalid),
        .s_hdmi_tready      (s_hdmi_in_tready),
        .s_hdmi_tuser       (s_hdmi_in_tuser),
        .s_hdmi_tlast       (s_hdmi_in_tlast),

        // Output to rgb2dvi → HDMI OUT
        .m_tdata            (m_hdmi_out_tdata),
        .m_tvalid           (m_hdmi_out_tvalid),
        .m_tready           (m_hdmi_out_tready),
        .m_tuser            (m_hdmi_out_tuser),
        .m_tlast            (m_hdmi_out_tlast),

        // Sprite compositor ports
        .sprite_wr_en       (sprite_wr_en),
        .sprite_wr_addr     (sprite_wr_addr),
        .sprite_wr_data     (sprite_wr_data),
        .sprite_x0          (sprite_x0),
        .sprite_y0          (sprite_y0),
        .sprite_x1          (sprite_x1),
        .sprite_y1          (sprite_y1),
        .sprite_visible     (sprite_visible),
        .sprite_alpha       (sprite_alpha)
    );

    // ------------------------------------------------------------------
    // Status LEDs
    //   LD0 = system running (always on when PL is configured)
    //   LD1 = authorized (passthrough active)
    //   LD2 = camera stream active (VDMA tvalid)
    //   LD3 = sprite visible
    // ------------------------------------------------------------------
    assign led[0] = 1'b1;            // heartbeat: PL is up
    assign led[1] = auth_flag;       // green = authorized
    assign led[2] = s_cam_tvalid;    // camera stream flowing
    assign led[3] = sprite_visible;  // sprite compositor active

endmodule
