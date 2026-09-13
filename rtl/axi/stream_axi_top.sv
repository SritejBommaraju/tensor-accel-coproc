// Same command interface as stream_top.sv, but stream_ctrl's memory ports go through a
// real bursting AXI4 DMA bridge to two behavioral AXI4 subordinates (read: weights+acts,
// write: results), instead of direct sim_ram ports. Addresses are 32-bit byte addresses.
module stream_axi_top #(
    parameter N        = 4,
    parameter ADDR_W   = 32,
    parameter RD_DEPTH = 4096,   // words, read-side memory
    parameter WR_DEPTH = 4096    // words, write-side memory
) (
    input  logic               clk,
    input  logic                rst,

    input  logic                start,
    input  logic [ADDR_W-1:0]   w_base,
    input  logic [ADDR_W-1:0]   a_base,
    input  logic [ADDR_W-1:0]   c_base,
    input  logic [31:0]         m_rows,
    output logic                busy,
    output logic                done,

    input  logic [3:0]          rd_stall_mask,
    input  logic [3:0]          wr_stall_mask,
    input  logic [31:0]         rd_stall_seed,
    input  logic [31:0]         wr_stall_seed
);
    // read AXI (weights + acts), DATA_W = N*8
    logic [3:0] r_arid; logic [ADDR_W-1:0] r_araddr; logic [7:0] r_arlen; logic [2:0] r_arsize;
    logic [1:0] r_arburst; logic r_arvalid, r_arready;
    logic [3:0] r_rid; logic [N*8-1:0] r_rdata; logic [1:0] r_rresp; logic r_rlast, r_rvalid, r_rready;

    // write AXI (results), DATA_W = N*32
    logic [3:0] w_awid; logic [ADDR_W-1:0] w_awaddr; logic [7:0] w_awlen; logic [2:0] w_awsize;
    logic [1:0] w_awburst; logic w_awvalid, w_awready;
    logic [N*32-1:0] w_wdata; logic [N*4-1:0] w_wstrb; logic w_wlast, w_wvalid, w_wready;
    logic [3:0] w_bid; logic [1:0] w_bresp; logic w_bvalid, w_bready;

    logic              weight_load;
    logic [N*N*8-1:0]  weight_in_flat;
    logic [N*8-1:0]    act_in_flat;
    logic [N*32-1:0]   psum_out_flat;

    logic signed [7:0]  weight_in_arr [0:N-1][0:N-1];
    logic signed [7:0]  act_in_arr    [0:N-1];
    logic signed [31:0] psum_out_arr  [0:N-1];

    genvar i, j;
    generate
        for (i = 0; i < N; i++) begin : g_unpack
            for (j = 0; j < N; j++) begin : g_unpack_col
                assign weight_in_arr[i][j] = weight_in_flat[(i*N+j)*8 +: 8];
            end
            assign act_in_arr[i] = act_in_flat[i*8 +: 8];
            assign psum_out_flat[i*32 +: 32] = psum_out_arr[i];
        end
    endgenerate

    axi4_dma_bridge #(.N(N), .ADDR_W(ADDR_W), .ID_W(4)) u_bridge (
        .clk(clk), .rst(rst),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done),

        .arid(r_arid), .araddr(r_araddr), .arlen(r_arlen), .arsize(r_arsize), .arburst(r_arburst),
        .arvalid(r_arvalid), .arready(r_arready),
        .rid(r_rid), .rdata(r_rdata), .rresp(r_rresp), .rlast(r_rlast), .rvalid(r_rvalid), .rready(r_rready),

        .awid(w_awid), .awaddr(w_awaddr), .awlen(w_awlen), .awsize(w_awsize), .awburst(w_awburst),
        .awvalid(w_awvalid), .awready(w_awready),
        .wdata(w_wdata), .wstrb(w_wstrb), .wlast(w_wlast), .wvalid(w_wvalid), .wready(w_wready),
        .bid(w_bid), .bresp(w_bresp), .bvalid(w_bvalid), .bready(w_bready),

        .weight_load(weight_load), .weight_in(weight_in_flat), .act_in(act_in_flat), .psum_out(psum_out_flat)
    );

    axi4_sim_ram #(.DATA_W(N*8), .ADDR_W(ADDR_W), .ID_W(4), .DEPTH(RD_DEPTH)) u_ram_rd (
        .clk(clk), .rst(rst), .stall_mask(rd_stall_mask), .stall_seed(rd_stall_seed),
        .arid(r_arid), .araddr(r_araddr), .arlen(r_arlen), .arsize(r_arsize), .arburst(r_arburst),
        .arvalid(r_arvalid), .arready(r_arready),
        .rid(r_rid), .rdata(r_rdata), .rresp(r_rresp), .rlast(r_rlast), .rvalid(r_rvalid), .rready(r_rready),
        .awid('0), .awaddr('0), .awlen('0), .awsize('0), .awburst('0), .awvalid(1'b0), .awready(),
        .wdata('0), .wstrb('0), .wlast(1'b0), .wvalid(1'b0), .wready(),
        .bid(), .bresp(), .bvalid(), .bready(1'b1)
    );

    axi4_sim_ram #(.DATA_W(N*32), .ADDR_W(ADDR_W), .ID_W(4), .DEPTH(WR_DEPTH)) u_ram_wr (
        .clk(clk), .rst(rst), .stall_mask(wr_stall_mask), .stall_seed(wr_stall_seed),
        .arid('0), .araddr('0), .arlen('0), .arsize('0), .arburst('0), .arvalid(1'b0), .arready(),
        .rid(), .rdata(), .rresp(), .rlast(), .rvalid(), .rready(1'b1),
        .awid(w_awid), .awaddr(w_awaddr), .awlen(w_awlen), .awsize(w_awsize), .awburst(w_awburst),
        .awvalid(w_awvalid), .awready(w_awready),
        .wdata(w_wdata), .wstrb(w_wstrb), .wlast(w_wlast), .wvalid(w_wvalid), .wready(w_wready),
        .bid(w_bid), .bresp(w_bresp), .bvalid(w_bvalid), .bready(w_bready)
    );

    // beat counters for the TB to report throughput; not part of the functional design
    logic [31:0] rd_beat_count /* verilator public */;
    logic [31:0] wr_beat_count /* verilator public */;
    always_ff @(posedge clk) begin
        if (rst) begin
            rd_beat_count <= '0; wr_beat_count <= '0;
        end else begin
            if (r_rvalid && r_rready) rd_beat_count <= rd_beat_count + 1'b1;
            if (w_wvalid && w_wready) wr_beat_count <= wr_beat_count + 1'b1;
        end
    end

    systolic_array #(.N(N)) u_array (
        .clk(clk), .rst(rst), .weight_load(weight_load),
        .weight_in(weight_in_arr), .act_in(act_in_arr), .psum_out(psum_out_arr)
    );
endmodule
