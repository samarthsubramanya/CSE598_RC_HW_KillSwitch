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
 * ─────────────────────────────────────────────────────────────────────────
 * Sprite Compositor Engine
 * ─────────────────────────────────────────────────────────────────────────
 *
 * A "sprite" is a small rectangular region that is blended over whatever
 * video stream is currently active (camera OR HDMI-IN from a PC).
 * The sprite content (RGB pixels) is stored in an on-chip BRAM that the
 * ARM CPU can write to via a simple AXI-like register interface
 * (sprite_wr_en / sprite_wr_addr / sprite_wr_data).
 *
 * The sprite position and size are software-configurable registers:
 *   sprite_x0, sprite_y0  : top-left corner of sprite on screen
 *   sprite_x1, sprite_y1  : exclusive bottom-right  (width  = x1-x0)
 *   sprite_visible        : 1 = the compositor is active
 *   sprite_alpha          : 0..15 — blending weight (15=opaque, 0=transparent)
 *
 * Chroma Key / Alpha Blending:
 *   For every pixel inside the sprite rectangle the output colour is:
 *     out = (sprite_alpha * sprite_colour + (15 - sprite_alpha) * bg_colour) / 16
 *   A sprite colour of 24'h010101 is treated as the "transparent" magic
 *   value so the background shows through that pixel regardless of alpha.
 *
 * BRAM addressing:
 *   One BRAM word = 24 bits (one RGB pixel).
 *   Sprite dimensions can be up to SPRITE_W × SPRITE_H pixels.
 *   Address = (sprite_row * SPRITE_W) + sprite_col   (row-major).
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
 *   Kill-switch mux: ~10 LUTs, 4 FFs
 *   Sprite BRAM    : 512×128 = 65 536 pixels → 192 KB → fits in 3× 36Kb BRAMs
 *   Pixel counters + blender: ~80 LUTs, ~40 FFs
 */

// ─────────────────────────────────────────────────────────────────────────────
// Configurable sprite canvas size (change here and resynthesize as needed)
// ─────────────────────────────────────────────────────────────────────────────
`define SPRITE_W  512   // max sprite width  in pixels
`define SPRITE_H  128   // max sprite height in pixels

module hdmi_stream_mux #(
    parameter SCREEN_W = 1280,
    parameter SCREEN_H = 720
) (
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
    output wire        m_tlast,

    // ---------------------------------------------------------------
    // Sprite Compositor — BRAM write port (driven by PS via AXI)
    //   Python writes pixel rows using fpga_interface.write_sprite_pixels()
    // ---------------------------------------------------------------
    input  wire        sprite_wr_en,
    input  wire [16:0] sprite_wr_addr,  // up to 512×128 = 65 536 entries
    input  wire [23:0] sprite_wr_data,  // RGB888

    // ---------------------------------------------------------------
    // Sprite control registers (written by PS each frame or on change)
    // ---------------------------------------------------------------
    input  wire [10:0] sprite_x0,       // screen X start (0..1279)
    input  wire [9:0]  sprite_y0,       // screen Y start (0..719)
    input  wire [10:0] sprite_x1,       // screen X end   (exclusive)
    input  wire [9:0]  sprite_y1,       // screen Y end   (exclusive)
    input  wire        sprite_visible,  // 1 = compositor active
    input  wire [3:0]  sprite_alpha     // 0=transparent  15=opaque
);

    // -----------------------------------------------------------------------
    // 1. Frame-boundary source latch (kill-switch logic — unchanged from v1)
    // -----------------------------------------------------------------------
    reg active_sel;     // 0 = camera, 1 = HDMI IN

    always @(posedge aclk) begin
        if (!aresetn) begin
            active_sel <= 1'b0;
        end else begin
            if (active_sel == 1'b0) begin
                if (s_cam_tvalid && s_cam_tuser)
                    active_sel <= auth_flag;
            end else begin
                if (s_hdmi_tvalid && s_hdmi_tuser)
                    active_sel <= auth_flag;
            end
        end
    end

    // -----------------------------------------------------------------------
    // 2. Pixel coordinate tracking
    //    We track (px, py) by watching the currently ACTIVE stream.
    //    tuser = SOF resets both counters.
    //    tlast = EOL increments row counter and resets column.
    //    We advance the column on every valid+ready pixel transfer.
    // -----------------------------------------------------------------------
    reg [10:0] px;  // current column pixel (0-based)
    reg [9:0]  py;  // current row    pixel (0-based)

    wire active_valid = active_sel ? s_hdmi_tvalid : s_cam_tvalid;
    wire active_last  = active_sel ? s_hdmi_tlast  : s_cam_tlast;
    wire active_user  = active_sel ? s_hdmi_tuser  : s_cam_tuser;

    always @(posedge aclk) begin
        if (!aresetn) begin
            px <= 11'd0;
            py <= 10'd0;
        end else if (active_valid && m_tready) begin
            if (active_user) begin
                // Start-of-Frame: reset to top-left
                px <= 11'd0;
                py <= 10'd0;
            end else if (active_last) begin
                // End-of-Line: next row
                px <= 11'd0;
                py <= py + 10'd1;
            end else begin
                px <= px + 11'd1;
            end
        end
    end

    // -----------------------------------------------------------------------
    // 3. Sprite BRAM (true dual-port: port A = PS write, port B = read)
    //    Inferred as Block RAM by Vivado.
    // -----------------------------------------------------------------------
    localparam SPRITE_DEPTH = `SPRITE_W * `SPRITE_H;   // 65 536

    (* ram_style = "block" *)
    reg [23:0] sprite_bram [0 : SPRITE_DEPTH - 1];

    // Port A — write (PS side, runs at same aclk for simplicity)
    always @(posedge aclk) begin
        if (sprite_wr_en)
            sprite_bram[sprite_wr_addr] <= sprite_wr_data;
    end

    // Port B — read (compositor, 1-cycle read latency)
    //   Address = (py - sprite_y0) * SPRITE_W + (px - sprite_x0)
    //   We register the in-region flag one cycle early to match BRAM latency.
    wire [9:0]  sp_row = py - {2'b00, sprite_y0};         // row within sprite
    wire [8:0]  sp_col = px[8:0] - sprite_x0[8:0];        // col within sprite
    wire [16:0] sp_addr = sp_row * `SPRITE_W + sp_col;

    reg [23:0] sprite_pixel_r;   // registered BRAM output (1-cycle latency)

    always @(posedge aclk) begin
        sprite_pixel_r <= sprite_bram[sp_addr];
    end

    // Pipeline the "is current pixel inside sprite?" flag by 1 cycle to align
    // with the BRAM read latency.
    wire in_sprite_region =
            sprite_visible &&
            (px >= sprite_x0) && (px < sprite_x1) &&
            (py >= sprite_y0) && (py < sprite_y1);

    reg  in_sprite_r;    // 1-cycle delayed — matches sprite_pixel_r
    always @(posedge aclk) begin
        in_sprite_r <= in_sprite_region;
    end

    // Background pixel (mux output before sprite compositing)
    wire [23:0] bg_pixel = active_sel ? s_hdmi_tdata : s_cam_tdata;

    // -----------------------------------------------------------------------
    // 4. Alpha blender
    //    out_ch = (alpha * sp + (15-alpha) * bg) >> 4   (per channel, 8-bit)
    //    Magic transparent colour 24'h010101 → pass through background.
    // -----------------------------------------------------------------------
    wire is_transparent = (sprite_pixel_r == 24'h01_01_01);

    wire [3:0]  inv_alpha = 4'd15 - sprite_alpha;

    // Each channel: 4-bit × 8-bit = 12-bit intermediates
    wire [11:0] blend_r = (sprite_alpha * sprite_pixel_r[23:16]) +
                          (inv_alpha    * bg_pixel[23:16]);
    wire [11:0] blend_g = (sprite_alpha * sprite_pixel_r[15:8])  +
                          (inv_alpha    * bg_pixel[15:8]);
    wire [11:0] blend_b = (sprite_alpha * sprite_pixel_r[7:0])   +
                          (inv_alpha    * bg_pixel[7:0]);

    // Divide by 16 (right-shift 4 bits); take bits [11:4] → 8-bit result
    wire [23:0] blended_pixel = {
        blend_r[11:4],
        blend_g[11:4],
        blend_b[11:4]
    };

    // Final pixel: sprite (blended) if in region and not transparent,
    //              else background.
    wire [23:0] composited = (in_sprite_r && !is_transparent)
                             ? blended_pixel
                             : bg_pixel;

    // -----------------------------------------------------------------------
    // 5. Output mux — route mux'd/composited pixel to HDMI OUT
    // -----------------------------------------------------------------------
    assign m_tdata  = composited;
    assign m_tvalid = active_sel ? s_hdmi_tvalid : s_cam_tvalid;
    assign m_tuser  = active_sel ? s_hdmi_tuser  : s_cam_tuser;
    assign m_tlast  = active_sel ? s_hdmi_tlast  : s_cam_tlast;

    // -----------------------------------------------------------------------
    // 6. Backpressure: active source gets real back-pressure from downstream.
    //    Inactive source is freely drained.
    // -----------------------------------------------------------------------
    assign s_hdmi_tready = active_sel  ? m_tready : 1'b1;
    assign s_cam_tready  = !active_sel ? m_tready : 1'b1;

endmodule
