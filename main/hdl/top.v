/**
 * PYNQ-Z2 Face Recognition Kill Switch - Top Level Wrapper
 *
 * Architecture Overview:
 * ---------------------
 * Face detection and embedding generation run entirely on the PS (ARM CPU)
 * using the face_recognition Python library (dlib + ResNet-34). The PL
 * handles only what FPGAs do uniquely well: real-time video routing.
 *
 * PL Block Design Components (instantiated via IP Integrator in create_project.tcl):
 *   - processing_system7     : Zynq PS (dual Cortex-A9, 667 MHz)
 *   - axi_gpio               : 1-bit output → auth_flag to hdmi_stream_mux
 *   - axi_vdma (MM2S)        : Streams camera frames from PS DDR → PL AXI4-Stream
 *   - v_tc                   : Video timing controller for camera stream
 *   - dvi2rgb                : HDMI IN deserializer (Digilent IP, ADV7612 side)
 *   - rgb2dvi                : HDMI OUT serializer  (Digilent IP, ADV7511 side)
 *   - hdmi_stream_mux (this) : Custom kill-switch mux (auth_flag selects source)
 *
 * Kill Switch Logic (implemented in hdmi_mux.v):
 *   auth_flag = 1  →  pass HDMI IN  → HDMI OUT  (authorized user present)
 *   auth_flag = 0  →  pass camera feed → HDMI OUT (show camera, block PC signal)
 *
 * PS Python sets auth_flag via AXI GPIO after each recognition decision.
 * FPGA responds within one pixel clock cycle — sub-millisecond latency.
 *
 * This file is the synthesizable RTL wrapper for hdmi_stream_mux.
 * All other logic lives in the Vivado block design (see create_project.tcl).
 */

module face_recognition_top (
    // === AXI-Lite from PS (GP0 master) ===
    // Connected to axi_gpio and axi_vdma via AXI interconnect in block design.
    // These ports are driven by the Zynq PS7 IP — not declared here as RTL ports.
    // They appear in the block design netlist only.

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
    // PS writes 1 = authorized (pass HDMI IN), 0 = unauthorized (show camera)
    input  wire        auth_flag,

    // === Status LEDs (PYNQ-Z2 onboard LEDs LD0-LD3) ===
    output wire [3:0]  led
);

    // ------------------------------------------------------------------
    // HDMI Stream Mux — core kill-switch logic
    // ------------------------------------------------------------------
    hdmi_stream_mux u_mux (
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
        .m_tlast            (m_hdmi_out_tlast)
    );

    // ------------------------------------------------------------------
    // Status LEDs
    //   LD0 = system running (always on when PL is configured)
    //   LD1 = authorized (passthrough active)
    //   LD2 = camera stream active (VDMA tvalid)
    //   LD3 = HDMI IN active (dvi2rgb tvalid)
    // ------------------------------------------------------------------
    assign led[0] = 1'b1;                   // heartbeat: PL is up
    assign led[1] = auth_flag;              // green = authorized
    assign led[2] = s_cam_tvalid;           // camera stream flowing
    assign led[3] = s_hdmi_in_tvalid;       // HDMI IN present

endmodule
