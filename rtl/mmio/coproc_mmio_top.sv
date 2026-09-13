// Wires cmd_queue_regs (dmem-port register block) to the unmodified stream_top datapath.
module coproc_mmio_top #(parameter N = 4, parameter ADDR_W = 16, parameter longint BASE_ADDR = 64'h1000_0000) (
    input  logic clk,
    input  logic rst,

    input  logic [63:0] dmem_addr,
    input  logic [63:0] dmem_wdata,
    input  logic        dmem_wen,
    input  logic [2:0]  dmem_funct3,
    output logic [63:0] dmem_rdata,

    output logic irq
);
    logic              start, busy, done;
    logic [ADDR_W-1:0] w_base, a_base, c_base;
    logic [31:0]       m_rows;

    cmd_queue_regs #(.N(N), .ADDR_W(ADDR_W), .BASE_ADDR(BASE_ADDR)) u_regs (
        .clk(clk), .rst(rst),
        .dmem_addr(dmem_addr), .dmem_wdata(dmem_wdata), .dmem_wen(dmem_wen),
        .dmem_funct3(dmem_funct3), .dmem_rdata(dmem_rdata),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done), .irq(irq)
    );

    stream_top #(.N(N), .ADDR_W(ADDR_W)) u_stream (
        .clk(clk), .rst(rst),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done)
    );
endmodule
