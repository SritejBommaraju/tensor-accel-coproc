// MMIO-controlled, AXI4-DMA-backed top: cmd_queue_regs (dmem-port command FIFO) drives
// axi4_dma_bridge, whose two real AXI4 master ports (read: weights+acts, write: results) are
// brought straight out to the module boundary -- no sim_ram inside. systolic_array is wired
// to the bridge's weight/act/psum ports exactly as stream_axi_top.sv does.
//
// axi4_dma_bridge fully prefetches N weight rows + m_rows activation rows into its read FIFO
// before it ever starts the systolic array (see axi4_dma_bridge.sv header), so RD_FIFO_DEPTH
// must be at least N + m_rows for any command actually issued. Here RD_FIFO_DEPTH is fixed at
// MAX_ROWS+N and WR_FIFO_DEPTH at MAX_ROWS: a command with m_rows > MAX_ROWS will never finish
// prefetching and hangs the bridge (and, once its 4-deep FIFO fills, the whole command queue).
module coproc_axi_top #(
    parameter N               = 4,
    parameter ADDR_W          = 32,
    parameter ID_W            = 4,
    parameter MAX_ROWS        = 1024,
    parameter longint BASE_ADDR = 64'h1000_0000
) (
    input  logic clk,
    input  logic rst,

    input  logic [63:0] dmem_addr,
    input  logic [63:0] dmem_wdata,
    input  logic        dmem_wen,
    input  logic [2:0]  dmem_funct3,
    output logic [63:0] dmem_rdata,

    output logic irq,

    // AXI4 master: read port (weights + activations), DATA_W = N*8
    output logic [ID_W-1:0]   m_arid,
    output logic [ADDR_W-1:0] m_araddr,
    output logic [7:0]        m_arlen,
    output logic [2:0]        m_arsize,
    output logic [1:0]        m_arburst,
    output logic              m_arvalid,
    input  logic              m_arready,
    input  logic [ID_W-1:0]   m_rid,
    input  logic [N*8-1:0]    m_rdata,
    input  logic [1:0]        m_rresp,
    input  logic              m_rlast,
    input  logic              m_rvalid,
    output logic              m_rready,

    // AXI4 master: write port (results), DATA_W = N*32
    output logic [ID_W-1:0]   m_awid,
    output logic [ADDR_W-1:0] m_awaddr,
    output logic [7:0]        m_awlen,
    output logic [2:0]        m_awsize,
    output logic [1:0]        m_awburst,
    output logic              m_awvalid,
    input  logic              m_awready,
    output logic [N*32-1:0]   m_wdata,
    output logic [N*4-1:0]    m_wstrb,
    output logic              m_wlast,
    output logic              m_wvalid,
    input  logic              m_wready,
    input  logic [ID_W-1:0]   m_bid,
    input  logic [1:0]        m_bresp,
    input  logic              m_bvalid,
    output logic              m_bready
);
    logic              start, busy, done;
    logic [ADDR_W-1:0] w_base, a_base, c_base;
    logic [31:0]       m_rows;

    cmd_queue_regs #(.N(N), .ADDR_W(32), .BASE_ADDR(BASE_ADDR)) u_regs (
        .clk(clk), .rst(rst),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_wen(dmem_wen),
        .dmem_funct3(dmem_funct3), .dmem_rdata(dmem_rdata),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done), .irq(irq)
    );

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

    axi4_dma_bridge #(
        .N(N), .ADDR_W(ADDR_W), .ID_W(ID_W),
        .RD_FIFO_DEPTH(MAX_ROWS+N), .WR_FIFO_DEPTH(MAX_ROWS)
    ) u_bridge (
        .clk(clk), .rst(rst),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done),

        .arid(m_arid), .araddr(m_araddr), .arlen(m_arlen), .arsize(m_arsize), .arburst(m_arburst),
        .arvalid(m_arvalid), .arready(m_arready),
        .rid(m_rid), .rdata(m_rdata), .rresp(m_rresp), .rlast(m_rlast), .rvalid(m_rvalid), .rready(m_rready),

        .awid(m_awid), .awaddr(m_awaddr), .awlen(m_awlen), .awsize(m_awsize), .awburst(m_awburst),
        .awvalid(m_awvalid), .awready(m_awready),
        .wdata(m_wdata), .wstrb(m_wstrb), .wlast(m_wlast), .wvalid(m_wvalid), .wready(m_wready),
        .bid(m_bid), .bresp(m_bresp), .bvalid(m_bvalid), .bready(m_bready),

        .weight_load(weight_load), .weight_in(weight_in_flat), .act_in(act_in_flat), .psum_out(psum_out_flat)
    );

    systolic_array #(.N(N)) u_array (
        .clk(clk), .rst(rst), .weight_load(weight_load),
        .weight_in(weight_in_arr), .act_in(act_in_arr), .psum_out(psum_out_arr)
    );
endmodule
