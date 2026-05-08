module hdmi_auth(
    input  wire [23:0] vdma_pData,
    input  wire        vdma_pHSync,
    input  wire        vdma_pVSync,
    input  wire        vdma_pVDE,

    input  wire [23:0] hdmi_pData,
    input  wire        hdmi_pHSync,
    input  wire        hdmi_pVSync,
    input  wire        hdmi_pVDE,

    input  wire        sw,

    output reg  [23:0] pData,
    output reg         pHSync,
    output reg         pVSync,
    output reg         pVDE
);

    // Combinational Multiplexer
    // Using @(*) ensures the outputs update instantly when 'sw' or any input changes
    always @(*) begin
        if (sw) begin
            // HDMI Source Selected
            pData    = hdmi_pData;
            pHSync   = hdmi_pHSync;
            pVSync   = hdmi_pVSync;
            pVDE     = hdmi_pVDE;
        end else begin
            // VDMA Source Selected
            pData    = vdma_pData;
            pHSync   = vdma_pHSync;
            pVSync   = vdma_pVSync;
            pVDE     = vdma_pVDE;
        end
    end

endmodule