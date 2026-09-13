// DMA-like sequencer: runs one full matmul (M x N) @ (N x N) from flat memory to flat memory
// through the weight-stationary systolic_array, without the array itself knowing about memory.
//
// Memory layout (shared read port serves both weight and activation reads):
//   weights @ w_base: N words, one per row, row i packed as N int8 lanes -> word[j*8 +: 8] = W[i][j]
//   acts    @ a_base: M words, one per row, row k packed the same way  -> word[j*8 +: 8] = A[k][j]
//   results @ c_base: M words, one per row, row k packed as N int32   -> word[c*32+:32] = C[k][c]
//
// Timing derivation (verified against the array's registered MAC/forward datapath):
// feeding act_in[r] with logical row k delayed by r cycles (row skew) makes every PE's
// act and psum inputs arrive in lock-step, so psum_out[c] for logical row k becomes valid
// exactly N+c cycles after row k's push cycle. A per-column delay of (N-1-c) then aligns
// all N columns of row k into one word, k+2N-1 cycles after its push.
module stream_ctrl #(parameter N = 4, parameter ADDR_W = 16) (
    input  logic clk,
    input  logic rst,

    input  logic                start,
    input  logic [ADDR_W-1:0]   w_base,
    input  logic [ADDR_W-1:0]   a_base,
    input  logic [ADDR_W-1:0]   c_base,
    input  logic [31:0]         m_rows,
    output logic                busy,
    output logic                done,

    // shared read port: weight rows during LOAD, activation rows during STREAM
    output logic [ADDR_W-1:0]   rd_addr,
    output logic                rd_en,
    input  logic [N*8-1:0]      rd_data,

    // write port: result rows
    output logic [ADDR_W-1:0]   wr_addr,
    output logic                wr_en,
    output logic [N*32-1:0]     wr_data,

    // systolic_array side (flattened, matching top.sv's convention)
    output logic                weight_load,
    output logic [N*N*8-1:0]    weight_in,
    output logic [N*8-1:0]      act_in,
    input  logic [N*32-1:0]     psum_out
);
    typedef enum logic [2:0] {S_IDLE, S_LOAD_ADDR, S_LOAD_DATA, S_LOAD_PULSE, S_PREFETCH, S_STREAM, S_DONE} state_t;
    state_t state;

    logic [ADDR_W-1:0] li; // loop index 0..N-1, kept ADDR_W-wide to add cleanly with w_base_r
    logic [31:0]      cyc;
    logic [ADDR_W-1:0] w_base_r, a_base_r, c_base_r;
    logic [31:0]      m_rows_r;
    logic [N*N*8-1:0] weight_buf;

    wire [31:0] total_cycles = m_rows_r + (2*N - 1);

    // --- read/write address & strobe muxing ---
    always_comb begin
        rd_addr = '0; rd_en = 1'b0;
        wr_addr = '0; wr_en = 1'b0;
        case (state)
            S_LOAD_ADDR: begin rd_addr = w_base_r + li; rd_en = 1'b1; end
            S_PREFETCH:  begin rd_addr = a_base_r;      rd_en = 1'b1; end
            S_STREAM: begin
                rd_addr = a_base_r + ADDR_W'(cyc + 1);
                rd_en   = (cyc + 1 < m_rows_r);
                if (cyc >= (2*N-1) && (cyc - (2*N-1)) < m_rows_r) begin
                    wr_en   = 1'b1;
                    wr_addr = c_base_r + ADDR_W'(cyc - (2*N-1));
                end
            end
            default: ;
        endcase
    end

    assign busy        = (state != S_IDLE);
    assign weight_load  = (state == S_LOAD_PULSE);
    assign weight_in    = weight_buf;

    // --- per-row skew: lane r delayed by r cycles so row k's r-th element enters r cycles late ---
    logic signed [7:0] act_push [0:N-1];
    logic signed [7:0] act_skewed [0:N-1];
    logic push_valid;
    assign push_valid = (state == S_STREAM) && (cyc < m_rows_r);

    genvar gr;
    generate
        for (gr = 0; gr < N; gr = gr + 1) begin : g_row_skew
            assign act_push[gr] = push_valid ? rd_data[gr*8 +: 8] : 8'sd0;
            if (gr == 0) begin : g_lane0
                assign act_skewed[0] = act_push[0];
            end else begin : g_delay
                logic signed [7:0] sk [0:gr-1];
                integer i;
                always_ff @(posedge clk) begin
                    if (rst) begin
                        for (i = 0; i < gr; i = i + 1) sk[i] <= 8'sd0;
                    end else if (state == S_STREAM) begin
                        sk[0] <= act_push[gr];
                        for (i = 1; i < gr; i = i + 1) sk[i] <= sk[i-1];
                    end
                end
                assign act_skewed[gr] = sk[gr-1];
            end
            assign act_in[gr*8 +: 8] = act_skewed[gr];
        end
    endgenerate

    // --- per-column de-skew: column c delayed by (N-1-c) so all N columns of row k line up ---
    logic signed [31:0] psum_in_arr [0:N-1];
    logic signed [31:0] psum_aligned [0:N-1];

    genvar gc;
    generate
        for (gc = 0; gc < N; gc = gc + 1) begin : g_col_deskew
            localparam DEPTH = N - 1 - gc;
            assign psum_in_arr[gc] = psum_out[gc*32 +: 32];
            if (DEPTH == 0) begin : g_pass
                assign psum_aligned[gc] = psum_in_arr[gc];
            end else begin : g_delay
                logic signed [31:0] sk [0:DEPTH-1];
                integer j;
                always_ff @(posedge clk) begin
                    if (rst) begin
                        for (j = 0; j < DEPTH; j = j + 1) sk[j] <= 32'sd0;
                    end else if (state == S_STREAM) begin
                        sk[0] <= psum_in_arr[gc];
                        for (j = 1; j < DEPTH; j = j + 1) sk[j] <= sk[j-1];
                    end
                end
                assign psum_aligned[gc] = sk[DEPTH-1];
            end
            assign wr_data[gc*32 +: 32] = psum_aligned[gc];
        end
    endgenerate

    // --- main FSM ---
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE; li <= '0; cyc <= '0; done <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: if (start) begin
                    w_base_r <= w_base; a_base_r <= a_base; c_base_r <= c_base; m_rows_r <= m_rows;
                    li <= '0;
                    state <= S_LOAD_ADDR;
                end
                S_LOAD_ADDR: state <= S_LOAD_DATA;
                S_LOAD_DATA: begin
                    weight_buf[li*N*8 +: N*8] <= rd_data;
                    if (li == ADDR_W'(N-1)) state <= S_LOAD_PULSE;
                    else begin li <= li + 1'b1; state <= S_LOAD_ADDR; end
                end
                S_LOAD_PULSE: state <= S_PREFETCH;
                S_PREFETCH:   begin cyc <= '0; state <= S_STREAM; end
                S_STREAM: begin
                    if (cyc == total_cycles - 1) state <= S_DONE;
                    else cyc <= cyc + 1'b1;
                end
                S_DONE: begin done <= 1'b1; state <= S_IDLE; end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
