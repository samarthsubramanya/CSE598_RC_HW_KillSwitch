/**
 * HDMI Stream Mux — Face Recognition Kill Switch
 *
 * This module is the core hardware contribution of the PL design.
 * It multiplexes two AXI4-Stream video sources and routes one to the
 * HDMI output based on the authorization flag set by the PS (ARM CPU).
 *
 * Kill Switch Behaviour:
 *   auth_flag = 1  →  pass HDMI IN to HDMI OUT (authorized: PC signal visible)
 *   auth_flag = 0  →  pass camera feed to HDMI OUT (unauthorized: PC signal blocked)
 *
 * Frame Synchronization:
 *   Switching is gated to frame boundaries (s_*_tuser = 1 marks Start-of-Frame).
 *   This prevents torn/corrupt frames when authorization state changes.
 *   The new source takes effect on the next SOF after auth_flag changes.
 *
 * AXI4-Stream Video Convention:
 *   tdata  [23:0] = RGB888 (R[23:16], G[15:8], B[7:0])
 *   tvalid        = data valid
 *   tready        = downstream ready (backpressure)
 *   tuser         = Start-of-Frame (SOF) when asserted on first pixel of frame
 *   tlast         = End-of-Line (EOL)
 *
 * Inactive source handling:
 *   The inactive stream is continuously drained (tready=1) so its producer
 *   (VDMA or dvi2rgb) does not stall or overflow its FIFO.
 *
 * Resource usage (Zynq-7020 estimate):
 *   ~10 LUTs, 4 FFs — negligible.
 */

module hdmi_stream_mux (
    input  wire        aclk,
    input  wire        aresetn,

    // ---------------------------------------------------------------
    // Authorization flag from AXI GPIO (PS writes this each frame)
    // 1 = authorized → pass HDMI IN; 0 = unauthorized → pass camera
    // ---------------------------------------------------------------
    input  wire        auth_flag,

    // ---------------------------------------------------------------
    // Source A: camera feed from AXI VDMA MM2S read channel
    // ---------------------------------------------------------------
    input  wire [23:0] s_cam_tdata,
    input  wire        s_cam_tvalid,
    output wire        s_cam_tready,
    input  wire        s_cam_tuser,     // SOF
    input  wire        s_cam_tlast,     // EOL

    // ---------------------------------------------------------------
    // Source B: HDMI IN from dvi2rgb deserializer
    // ---------------------------------------------------------------
    input  wire [23:0] s_hdmi_tdata,
    input  wire        s_hdmi_tvalid,
    output wire        s_hdmi_tready,
    input  wire        s_hdmi_tuser,    // SOF
    input  wire        s_hdmi_tlast,    // EOL

    // ---------------------------------------------------------------
    // Output: to rgb2dvi serializer → ADV7511 → HDMI OUT connector
    // ---------------------------------------------------------------
    output wire [23:0] m_tdata,
    output wire        m_tvalid,
    input  wire        m_tready,
    output wire        m_tuser,
    output wire        m_tlast
);

    // ------------------------------------------------------------------
    // Frame-boundary latch:
    // active_sel is only updated at the start of a new frame so we never
    // switch mid-frame.  0 = camera, 1 = HDMI IN.
    // ------------------------------------------------------------------
    reg active_sel;     // currently driving the output

    always @(posedge aclk) begin
        if (!aresetn) begin
            active_sel <= 1'b0;     // default: show camera (safe/locked state)
        end else begin
            // Check SOF of the currently active source.
            // At SOF, sample the latest auth_flag and latch it.
            if (active_sel == 1'b0) begin
                // Currently showing camera; check camera SOF
                if (s_cam_tvalid && s_cam_tuser)
                    active_sel <= auth_flag;
            end else begin
                // Currently showing HDMI IN; check HDMI SOF
                if (s_hdmi_tvalid && s_hdmi_tuser)
                    active_sel <= auth_flag;
            end
        end
    end

    // ------------------------------------------------------------------
    // Output mux — purely combinational once active_sel is registered
    // ------------------------------------------------------------------
    assign m_tdata  = active_sel ? s_hdmi_tdata  : s_cam_tdata;
    assign m_tvalid = active_sel ? s_hdmi_tvalid : s_cam_tvalid;
    assign m_tuser  = active_sel ? s_hdmi_tuser  : s_cam_tuser;
    assign m_tlast  = active_sel ? s_hdmi_tlast  : s_cam_tlast;

    // ------------------------------------------------------------------
    // Backpressure: active source gets real backpressure from downstream.
    // Inactive source is drained freely so its FIFO never overflows.
    // ------------------------------------------------------------------
    assign s_hdmi_tready = active_sel  ? m_tready : 1'b1;
    assign s_cam_tready  = !active_sel ? m_tready : 1'b1;

endmodule
