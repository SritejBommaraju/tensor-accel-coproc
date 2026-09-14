// Sim-only wrapper: coproc_axi_top's real AXI4 master ports plugged into two behavioral
// axi4_sim_ram subordinates, so a Verilator TB can drive the dmem port + backdoor host memory
// exactly like sim/axi/stream_axi_top does (u_ram_rd/u_ram_wr .mem, grep the mangled class name).
module coproc_axi_sim_top #(
    parameter N        = 4,
    parameter MAX_ROWS = 1024,
    parameter RD_DEPTH = 65536,
    parameter WR_DEPTH = 65536
) (
    input  logic clk,
    input  logic rst,

    input  logic [63:0] dmem_addr,
    input  logic [63:0] dmem_wdata,
    input  logic        dmem_wen,
    input  logic [2:0]  dmem_funct3,
    output logic [63:0] dmem_rdata,

    output logic irq,

    input  logic [3:0]  rd_stall_mask,
    input  logic [3:0]  wr_stall_mask,
    input  logic [31:0] rd_stall_seed,
    input  logic [31:0] wr_stall_seed
);
    localparam ADDR_W = 32;
    localparam ID_W   = 4;

    logic [ID_W-1:0]   arid;   logic [ADDR_W-1:0] araddr; logic [7:0] arlen; logic [2:0] arsize;
    logic [1:0]        arburst; logic arvalid, arready;
    logic [ID_W-1:0]   rid;    logic [N*8-1:0]    rdata;  logic [1:0] rresp; logic rlast, rvalid, rready;

    logic [ID_W-1:0]   awid;   logic [ADDR_W-1:0] awaddr; logic [7:0] awlen; logic [2:0] awsize;
    logic [1:0]        awburst; logic awvalid, awready;
    logic [N*32-1:0]   wdata;  logic [N*4-1:0]    wstrb;  logic wlast, wvalid, wready;
    logic [ID_W-1:0]   bid;    logic [1:0]        bresp;  logic bvalid, bready;

    coproc_axi_top #(.N(N), .ADDR_W(ADDR_W), .ID_W(ID_W), .MAX_ROWS(MAX_ROWS)) u_dut (
        .clk(clk), .rst(rst),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_wen(dmem_wen),
        .dmem_funct3(dmem_funct3), .dmem_rdata(dmem_rdata),
        .irq(irq),

        .m_arid(arid), .m_araddr(araddr), .m_arlen(arlen), .m_arsize(arsize), .m_arburst(arburst),
        .m_arvalid(arvalid), .m_arready(arready),
        .m_rid(rid), .m_rdata(rdata), .m_rresp(rresp), .m_rlast(rlast), .m_rvalid(rvalid), .m_rready(rready),

        .m_awid(awid), .m_awaddr(awaddr), .m_awlen(awlen), .m_awsize(awsize), .m_awburst(awburst),
        .m_awvalid(awvalid), .m_awready(awready),
        .m_wdata(wdata), .m_wstrb(wstrb), .m_wlast(wlast), .m_wvalid(wvalid), .m_wready(wready),
        .m_bid(bid), .m_bresp(bresp), .m_bvalid(bvalid), .m_bready(bready)
    );

    axi4_sim_ram #(.DATA_W(N*8), .ADDR_W(ADDR_W), .ID_W(ID_W), .DEPTH(RD_DEPTH)) u_ram_rd (
        .clk(clk), .rst(rst), .stall_mask(rd_stall_mask), .stall_seed(rd_stall_seed),
        .arid(arid), .araddr(araddr), .arlen(arlen), .arsize(arsize), .arburst(arburst),
        .arvalid(arvalid), .arready(arready),
        .rid(rid), .rdata(rdata), .rresp(rresp), .rlast(rlast), .rvalid(rvalid), .rready(rready),
        .awid('0), .awaddr('0), .awlen('0), .awsize('0), .awburst('0), .awvalid(1'b0), .awready(),
        .wdata('0), .wstrb('0), .wlast(1'b0), .wvalid(1'b0), .wready(),
        .bid(), .bresp(), .bvalid(), .bready(1'b1)
    );

    axi4_sim_ram #(.DATA_W(N*32), .ADDR_W(ADDR_W), .ID_W(ID_W), .DEPTH(WR_DEPTH)) u_ram_wr (
        .clk(clk), .rst(rst), .stall_mask(wr_stall_mask), .stall_seed(wr_stall_seed),
        .arid('0), .araddr('0), .arlen('0), .arsize('0), .arburst('0), .arvalid(1'b0), .arready(),
        .rid(), .rdata(), .rresp(), .rlast(), .rvalid(), .rready(1'b1),
        .awid(awid), .awaddr(awaddr), .awlen(awlen), .awsize(awsize), .awburst(awburst),
        .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wlast(wlast), .wvalid(wvalid), .wready(wready),
        .bid(bid), .bresp(bresp), .bvalid(bvalid), .bready(bready)
    );

    // beat counters for the TB to report throughput; not part of the functional design
    logic [31:0] rd_beat_count /* verilator public */;
    logic [31:0] wr_beat_count /* verilator public */;
    always_ff @(posedge clk) begin
        if (rst) begin
            rd_beat_count <= '0; wr_beat_count <= '0;
        end else begin
            if (rvalid && rready) rd_beat_count <= rd_beat_count + 1'b1;
            if (wvalid && wready) wr_beat_count <= wr_beat_count + 1'b1;
        end
    end
endmodule
