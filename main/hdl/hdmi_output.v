/**
 * HDMI Kill Switch Controller
 * 
 * Multiplexes between:
 * 1. Camera feed (authentication in progress)
 * 2. Computer HDMI IN signal (when user is authorized)
 * 
 * Supports 1280x720@60Hz (720p HD)
 */

module hdmi_output_controller #(
    parameter IMAGE_WIDTH = 1280,
    parameter IMAGE_HEIGHT = 720,
    parameter H_TOTAL = 1440,      // Total horizontal pixels
    parameter H_SYNC = 40,         // Horizontal sync width
    parameter H_BACK_PORCH = 110,  // Back porch
    parameter V_TOTAL = 750,       // Total vertical lines
    parameter V_SYNC = 5,          // Vertical sync width
    parameter V_BACK_PORCH = 20    // Back porch
) (
    input  logic                           clk,
    input  logic                           rst_n,
    
    // Camera feed (authentication display)
    input  logic [23:0] camera_data [IMAGE_WIDTH * IMAGE_HEIGHT - 1:0],
    
    // Computer HDMI IN (to be passed through when authorized)
    input  logic                           hdmi_in_clk,
    input  logic                           hdmi_in_vs,
    input  logic                           hdmi_in_hs,
    input  logic                           hdmi_in_de,
    input  logic [23:0]                    hdmi_in_data,
    
    // Authorization signal from CPU (1 = authorized, pass through computer signal)
    input  logic                           is_authorized,
    
    // HDMI OUT (to monitor)
    output logic                           hdmi_clk,
    output logic                           hdmi_vs,    // Vertical sync
    output logic                           hdmi_hs,    // Horizontal sync
    output logic                           hdmi_de,    // Data enable
    output logic [23:0]                    hdmi_data   // RGB888
);
    
    // Video timing counters for camera feed generation
    logic [15:0] h_count, v_count;
    logic [23:0] camera_pixel;
    logic [15:0] pixel_x, pixel_y;
    
    // =====================================================================
    // Timing Generation for Camera Feed (1280x720@60Hz)
    // =====================================================================
    
    localparam H_DISPLAY_START = H_SYNC + H_BACK_PORCH;
    localparam H_DISPLAY_END = H_DISPLAY_START + IMAGE_WIDTH;
    localparam V_DISPLAY_START = V_SYNC + V_BACK_PORCH;
    localparam V_DISPLAY_END = V_DISPLAY_START + IMAGE_HEIGHT;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (~rst_n) begin
            h_count <= 16'h0;
            v_count <= 16'h0;
        end else begin
            // Horizontal counter
            if (h_count >= (H_TOTAL - 1)) begin
                h_count <= 16'h0;
                // Vertical counter
                if (v_count >= (V_TOTAL - 1))
                    v_count <= 16'h0;
                else
                    v_count <= v_count + 1;
            end else begin
                h_count <= h_count + 1;
            end
        end
    end
    
    // Generate camera feed sync signals
    logic camera_hs, camera_vs, camera_de;
    assign camera_hs = (h_count < H_SYNC);
    assign camera_vs = (v_count < V_SYNC);
    assign camera_de = (h_count >= H_DISPLAY_START && h_count < H_DISPLAY_END &&
                        v_count >= V_DISPLAY_START && v_count < V_DISPLAY_END);
    
    // Pixel coordinates
    assign pixel_x = h_count - H_DISPLAY_START;
    assign pixel_y = v_count - V_DISPLAY_START;
    
    // Get camera pixel
    always_comb begin
        if (pixel_y < IMAGE_HEIGHT && pixel_x < IMAGE_WIDTH)
            camera_pixel = camera_data[pixel_y * IMAGE_WIDTH + pixel_x];
        else
            camera_pixel = 24'h000000;  // Black if out of bounds
    end
    
    // =====================================================================
    // HDMI Multiplexer: Camera Feed vs Computer Pass-Through
    // =====================================================================
    // When is_authorized = 0: Show camera feed (authentication required)
    // When is_authorized = 1: Pass through computer HDMI IN to OUT (user authorized)
    
    always_comb begin
        if (is_authorized) begin
            // Pass through computer HDMI signal directly to output
            hdmi_clk  = hdmi_in_clk;
            hdmi_vs   = hdmi_in_vs;
            hdmi_hs   = hdmi_in_hs;
            hdmi_de   = hdmi_in_de;
            hdmi_data = hdmi_in_data;
        end else begin
            // Show camera feed with generated timing
            hdmi_clk  = clk;                    // Use FPGA main clock
            hdmi_vs   = camera_vs;
            hdmi_hs   = camera_hs;
            hdmi_de   = camera_de;
            hdmi_data = camera_de ? camera_pixel : 24'h000000;  // Black during blanking
        end
    end

endmodule
