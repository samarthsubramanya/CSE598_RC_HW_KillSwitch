/**
 * PYNQ-Z2 Face Recognition Accelerator - Top Level Module
 * 
 * This module integrates:
 * 1. AXI slave interface for CPU communication
 * 2. Double-buffered image memory (1280x720 @ 30-60 FPS)
 * 3. Haar cascade face detection engine
 * 4. INT8 quantized CNN embedding accelerator
 * 5. HDMI video output with face annotations
 * 
 * Data Flow:
 * - Python writes raw image via AXI into input buffer
 * - Face detection identifies faces in parallel
 * - CNN accelerator computes embeddings for detected faces
 * - Results written back to AXI shared memory
 * - HDMI output streams processed video
 */

module face_recognition_top #(
    parameter AXI_DATA_WIDTH = 32,
    parameter AXI_ADDR_WIDTH = 24,  // Supports up to 16MB address space
    parameter IMAGE_WIDTH = 1280,
    parameter IMAGE_HEIGHT = 720,
    parameter MAX_FACES = 16
) (
    // AXI Slave Interface
    input  logic                           axi_aclk,
    input  logic                           axi_aresetn,
    
    // AXI Write Address Channel
    input  logic [AXI_ADDR_WIDTH-1:0]      s_axi_awaddr,
    input  logic [2:0]                     s_axi_awprot,
    input  logic                           s_axi_awvalid,
    output logic                           s_axi_awready,
    
    // AXI Write Data Channel
    input  logic [AXI_DATA_WIDTH-1:0]      s_axi_wdata,
    input  logic [AXI_DATA_WIDTH/8-1:0]    s_axi_wstrb,
    input  logic                           s_axi_wvalid,
    output logic                           s_axi_wready,
    
    // AXI Write Response Channel
    output logic [1:0]                     s_axi_bresp,
    output logic                           s_axi_bvalid,
    input  logic                           s_axi_bready,
    
    // AXI Read Address Channel
    input  logic [AXI_ADDR_WIDTH-1:0]      s_axi_araddr,
    input  logic [2:0]                     s_axi_arprot,
    input  logic                           s_axi_arvalid,
    output logic                           s_axi_arready,
    
    // AXI Read Data Channel
    output logic [AXI_DATA_WIDTH-1:0]      s_axi_rdata,
    output logic [1:0]                     s_axi_rresp,
    output logic                           s_axi_rvalid,
    input  logic                           s_axi_rready,
    
    // HDMI Output Interface
    output logic                           hdmi_clk,
    output logic                           hdmi_vs,    // Vertical sync
    output logic                           hdmi_hs,    // Horizontal sync
    output logic                           hdmi_de,    // Data enable
    output logic [23:0]                    hdmi_data,  // RGB888
    
    // HDMI Input Interface (from computer)
    input  logic                           hdmi_in_clk,
    input  logic                           hdmi_in_vs,
    input  logic                           hdmi_in_hs,
    input  logic                           hdmi_in_de,
    input  logic [23:0]                    hdmi_in_data,
    
    // Control Signals
    input  logic                           enable,
    output logic                           idle,
    output logic                           error_flag
);
    
    // =====================================================================
    // Local Parameters
    // =====================================================================
    
    localparam IMAGE_SIZE = IMAGE_WIDTH * IMAGE_HEIGHT;  // Pixels
    localparam IMAGE_BUFFER_SIZE = IMAGE_SIZE * 2;       // 30-bit color (10-bit per channel)
    localparam EMBEDDING_DIM = 128;
    localparam FACE_STRUCT_SIZE = 64;                     // Each face: x1,y1,x2,y2,emb[128]
    
    // AXI Address Map:
    localparam CTRL_REG_ADDR     = 24'h000000;   // Control register
    localparam STATUS_REG_ADDR   = 24'h000004;   // Status register
    localparam INPUT_IMG_ADDR    = 24'h000100;   // Input image buffer (1.2MB for 1280x720 RGB)
    localparam OUTPUT_IMG_ADDR   = 24'h200000;   // Output image buffer with annotations
    localparam FACES_ADDR        = 24'h400000;   // Face detection results
    localparam EMBEDDINGS_ADDR   = 24'h404000;   // CNN embeddings (16 faces * 128 * 4 bytes)
    
    // =====================================================================
    // Signals
    // =====================================================================
    
    logic [31:0] control_reg;
    logic [31:0] status_reg;
    logic detect_enable;
    logic cnn_enable;
    logic is_authorized;  // Kill switch: 1 = pass through computer HDMI, 0 = show camera
    logic [7:0] num_faces_detected;
    logic detection_complete;
    logic embedding_complete;
    
    // Face detection results
    struct packed {
        logic [15:0] x1, y1, x2, y2;
    } face_boxes [MAX_FACES];
    
    // CNN embeddings (quantized to INT8)
    logic signed [7:0] embeddings [MAX_FACES][EMBEDDING_DIM];
    
    // Image buffers (dual-port RAM)
    logic [23:0] input_image [IMAGE_SIZE];
    logic [23:0] output_image [IMAGE_SIZE];
    
    // =====================================================================
    // AXI Slave Interface
    // =====================================================================
    
    axi_slave_interface #(
        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .IMAGE_SIZE(IMAGE_SIZE),
        .MAX_FACES(MAX_FACES)
    ) axi_slave (
        .axi_aclk(axi_aclk),
        .axi_aresetn(axi_aresetn),
        
        // Write channels
        .s_axi_awaddr(s_axi_awaddr),
        .s_axi_awprot(s_axi_awprot),
        .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid),
        .s_axi_bready(s_axi_bready),
        
        // Read channels
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arprot(s_axi_arprot),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready),
        
        // Memory interface
        .input_image(input_image),
        .output_image(output_image),
        .num_faces(num_faces_detected),
        .face_boxes(face_boxes),
        .embeddings(embeddings),
        
        // Control
        .detect_enable(detect_enable),
        .cnn_enable(cnn_enable),
        .detection_complete(detection_complete),
        .embedding_complete(embedding_complete),
        .status_reg(status_reg),
        .error_flag(error_flag)
    );
    
    // =====================================================================
    // Haar Cascade Face Detector
    // =====================================================================
    
    haar_face_detector #(
        .IMAGE_WIDTH(IMAGE_WIDTH),
        .IMAGE_HEIGHT(IMAGE_HEIGHT),
        .MAX_FACES(MAX_FACES)
    ) face_detector (
        .clk(axi_aclk),
        .rst_n(axi_aresetn),
        .enable(detect_enable),
        
        .image_data(input_image),
        
        .face_boxes(face_boxes),
        .num_faces(num_faces_detected),
        .detection_complete(detection_complete),
        .busy()
    );
    
    // =====================================================================
    // CNN Embedding Engine (INT8 Quantized ResNet)
    // =====================================================================
    
    cnn_embedding_engine #(
        .IMAGE_WIDTH(1280),
        .IMAGE_HEIGHT(720),
        .EMBEDDING_DIM(EMBEDDING_DIM)
    ) cnn_engine (
        .clk(axi_aclk),
        .rst_n(axi_aresetn),
        .enable(cnn_enable),
        
        .input_image(input_image),
        .face_boxes(face_boxes),
        .num_faces(num_faces_detected),
        
        .embeddings(embeddings),
        .embedding_valid(embedding_complete),
        .busy()
    );
    
    // =====================================================================
    // HDMI Video Output Controller
    // =====================================================================
    
    // Extract authorization bit from control register (bit 2)
    assign is_authorized = control_reg[2];
    
    hdmi_output_controller #(
        .IMAGE_WIDTH(IMAGE_WIDTH),
        .IMAGE_HEIGHT(IMAGE_HEIGHT)
    ) hdmi_ctrl (
        .clk(axi_aclk),
        .rst_n(axi_aresetn),
        
        .camera_data(output_image),
        
        .hdmi_in_clk(hdmi_in_clk),
        .hdmi_in_vs(hdmi_in_vs),
        .hdmi_in_hs(hdmi_in_hs),
        .hdmi_in_de(hdmi_in_de),
        .hdmi_in_data(hdmi_in_data),
        
        .is_authorized(is_authorized),
        
        .hdmi_clk(hdmi_clk),
        .hdmi_vs(hdmi_vs),
        .hdmi_hs(hdmi_hs),
        .hdmi_de(hdmi_de),
        .hdmi_data(hdmi_data)
    );
    
    // =====================================================================
    // Status & Control Logic
    // =====================================================================
    
    assign idle = ~detect_enable & ~cnn_enable;
    
    always_ff @(posedge axi_aclk or negedge axi_aresetn) begin
        if (~axi_aresetn) begin
            status_reg <= 32'h0;
        end else begin
            status_reg[7:0] <= num_faces_detected;
            status_reg[8] <= detection_complete;
            status_reg[9] <= embedding_complete;
            status_reg[10] <= error_flag;
            status_reg[11] <= idle;
        end
    end

endmodule
