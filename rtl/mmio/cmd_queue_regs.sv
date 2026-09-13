// MMIO register block driveable by a plain load/store dmem port (rv64-ooo-core/rtl/core.sv shape):
// addr/wdata/wen/funct3 in, rdata out. Word-addressed 64-bit register map at BASE_ADDR:
//   0x00 W_BASE (W), 0x08 A_BASE (W), 0x10 C_BASE (W), 0x18 M_ROWS (W)
//   0x20 CMD (W1): writing 1 enqueues {w_base,a_base,c_base,m_rows} into a depth-4 FIFO
//   0x28 STATUS (R): bit0 busy, bit1 queue_full, bit2 queue_empty, [7:4] queue_count, [31:16] done_count
//   0x30 IRQ_EN/IRQ_PENDING (RW1C): bit0 IRQ_EN (RW), bit1 IRQ_PENDING (write 1 to clear)
//   0x38 ID (R): 0x7E4A5A00 | N
// Only SW/SD/LW/LD (funct3 010/011/000/001... see decode below) touch registers; any other
// access width returns 0 on reads and is silently ignored on writes.
module cmd_queue_regs #(parameter N = 4, parameter ADDR_W = 16, parameter longint BASE_ADDR = 64'h1000_0000) (
    input  logic         clk,
    input  logic         rst,

    // dmem-style load/store port from the core
    input  logic [63:0]  dmem_addr,
    input  logic [63:0]  dmem_wdata,
    input  logic         dmem_wen,
    input  logic [2:0]   dmem_funct3,
    output logic [63:0]  dmem_rdata,

    // stream_ctrl-style command pulse to the datapath
    output logic              start,
    output logic [ADDR_W-1:0] w_base,
    output logic [ADDR_W-1:0] a_base,
    output logic [ADDR_W-1:0] c_base,
    output logic [31:0]       m_rows,
    input  logic              busy,
    input  logic              done,

    output logic irq
);
    // RV64 funct3 for loads/stores: 000 SB/LB, 001 SH/LH, 010 SW/LW, 011 SD/LD (funct3[2] distinguishes signed/unsigned on loads, irrelevant here)
    localparam logic [2:0] F3_W = 3'b010;
    localparam logic [2:0] F3_D = 3'b011;
    wire is_dword = (dmem_funct3 == F3_D);
    wire is_word  = (dmem_funct3 == F3_W);
    wire access_ok = is_dword | is_word;

    localparam logic [5:0] OFF_W      = 6'h00;
    localparam logic [5:0] OFF_A      = 6'h08;
    localparam logic [5:0] OFF_C      = 6'h10;
    localparam logic [5:0] OFF_M      = 6'h18;
    localparam logic [5:0] OFF_CMD    = 6'h20;
    localparam logic [5:0] OFF_STATUS = 6'h28;
    localparam logic [5:0] OFF_IRQ    = 6'h30;
    localparam logic [5:0] OFF_ID     = 6'h38;

    wire in_range = (dmem_addr >= BASE_ADDR) && (dmem_addr < BASE_ADDR + 64'h40);
    wire [5:0] off = dmem_addr[5:0]; // word offset within the 64-byte block
    wire reg_hit = in_range & access_ok;
    wire wr_hit  = reg_hit & dmem_wen;
    wire _unused_ok = &{1'b0, dmem_wdata[63:32]}; // upper wdata bits unused by any register

    // holding registers for the next command to enqueue
    logic [ADDR_W-1:0] r_w_base, r_a_base, r_c_base;
    logic [31:0]       r_m_rows;

    logic irq_en, irq_pending;
    logic [15:0] done_count;

    // depth-4 FIFO of {w_base,a_base,c_base,m_rows}
    logic [3*ADDR_W+32-1:0] fifo_mem [0:3];
    logic [1:0] fifo_wp, fifo_rp;
    logic [2:0] fifo_cnt; // 0..4
    wire fifo_empty = (fifo_cnt == 0);
    wire fifo_full  = (fifo_cnt == 4);

    wire enqueue = wr_hit && (off == OFF_CMD) && (dmem_wdata[0] == 1'b1) && !fifo_full;
    wire pop     = !busy && !fifo_empty && !start; // pop one cycle before pulsing start on it

    always_ff @(posedge clk) begin
        if (rst) begin
            fifo_wp <= '0; fifo_rp <= '0; fifo_cnt <= '0;
            start <= 1'b0;
            w_base <= '0; a_base <= '0; c_base <= '0; m_rows <= '0;
        end else begin
            start <= 1'b0;
            if (enqueue) begin
                fifo_mem[fifo_wp] <= {r_w_base, r_a_base, r_c_base, r_m_rows};
                fifo_wp <= fifo_wp + 2'd1;
            end
            if (pop) begin
                {w_base, a_base, c_base, m_rows} <= fifo_mem[fifo_rp];
                fifo_rp <= fifo_rp + 2'd1;
                start <= 1'b1;
            end
            case ({enqueue, pop})
                2'b10: fifo_cnt <= fifo_cnt + 3'd1;
                2'b01: fifo_cnt <= fifo_cnt - 3'd1;
                default: ;
            endcase
        end
    end

    // holding registers + done counter + irq
    always_ff @(posedge clk) begin
        if (rst) begin
            r_w_base <= '0; r_a_base <= '0; r_c_base <= '0; r_m_rows <= '0;
            irq_en <= 1'b0; irq_pending <= 1'b0; done_count <= '0;
        end else begin
            if (wr_hit) begin
                case (off)
                    OFF_W: r_w_base <= dmem_wdata[ADDR_W-1:0];
                    OFF_A: r_a_base <= dmem_wdata[ADDR_W-1:0];
                    OFF_C: r_c_base <= dmem_wdata[ADDR_W-1:0];
                    OFF_M: r_m_rows <= dmem_wdata[31:0];
                    OFF_IRQ: begin
                        irq_en <= dmem_wdata[0];
                        if (dmem_wdata[1]) irq_pending <= 1'b0; // RW1C
                    end
                    default: ;
                endcase
            end
            if (done) begin
                done_count <= done_count + 16'd1;
                irq_pending <= 1'b1;
            end
        end
    end

    assign irq = irq_pending & irq_en;

    // 'busy' lags 'start' by a cycle (its state register hasn't caught up), and done_count lags
    // 'done' by a cycle the same way (registered in this module, one hop behind stream_ctrl's own
    // done register) -- OR all three into STATUS.busy so a poller never sees "idle" before
    // done_count has actually retired the completion.
    wire status_busy = busy | start | done;
    wire [31:0] status = {done_count, 8'd0, {1'b0, fifo_cnt}, 1'b0, fifo_empty, fifo_full, status_busy};
    wire [31:0] id_val = 32'h7E4A_5A00 | 32'(N);

    always_comb begin
        dmem_rdata = 64'd0;
        if (reg_hit && !dmem_wen) begin
            case (off)
                OFF_W:      dmem_rdata = 64'(r_w_base);
                OFF_A:      dmem_rdata = 64'(r_a_base);
                OFF_C:      dmem_rdata = 64'(r_c_base);
                OFF_M:      dmem_rdata = 64'(r_m_rows);
                OFF_STATUS: dmem_rdata = 64'(status);
                OFF_IRQ:    dmem_rdata = {62'd0, irq_pending, irq_en};
                OFF_ID:     dmem_rdata = 64'(id_val);
                default:    dmem_rdata = 64'd0;
            endcase
        end
    end
endmodule
