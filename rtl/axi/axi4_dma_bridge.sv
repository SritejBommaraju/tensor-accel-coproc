// AXI4 burst-DMA wrapper around the unmodified stream_ctrl. Two independent AXI4 master
// ports mirror stream_top's two separate sim_rams: a read port (DATA_W=N*8, one beat per
// weight/act row) and a write port (DATA_W=N*32, one beat per result row). ID width is 4
// on both; only one AR/R and one AW/W/B transaction is ever outstanding per port (simple,
// still real INCR bursting up to AxLEN=15).
//
// stream_ctrl cannot be stalled and expects synchronous 1-cycle read data, so under
// arbitrary AXI backpressure the only provably safe scheme is to fully prefetch every
// weight row and every activation row into a small FIFO before ever pulsing stream_ctrl's
// start -- a partial "first burst only" prefetch could still underrun mid-stream if the
// read AXI channel stalls harder than the fixed 1 word/cycle consumption rate. stream_ctrl's
// own rd_addr/wr_addr outputs are therefore unused: the bridge derives every AXI address
// itself from the top-level (byte) w_base/a_base/c_base plus its own running word counters,
// since the FIFO replay order is guaranteed identical to stream_ctrl's read/write order
// (weight rows 0..N-1, then activation rows 0..m_rows-1, then result rows 0..m_rows-1).
module axi4_dma_bridge #(
    parameter N             = 4,
    parameter ADDR_W        = 32,
    parameter ID_W          = 4,
    parameter RD_FIFO_DEPTH = 256,
    parameter WR_FIFO_DEPTH = 256
) (
    input  logic               clk,
    input  logic                rst,

    input  logic                start,
    input  logic [ADDR_W-1:0]   w_base,   // byte address
    input  logic [ADDR_W-1:0]   a_base,   // byte address
    input  logic [ADDR_W-1:0]   c_base,   // byte address
    input  logic [31:0]         m_rows,
    output logic                busy,
    output logic                done,

    // AXI4 master: read port (weights + activations), DATA_W = N*8
    output logic [ID_W-1:0]     arid,
    output logic [ADDR_W-1:0]   araddr,
    output logic [7:0]          arlen,
    output logic [2:0]          arsize,
    output logic [1:0]          arburst,
    output logic                arvalid,
    input  logic                arready,
    input  logic [ID_W-1:0]     rid,
    input  logic [N*8-1:0]      rdata,
    input  logic [1:0]          rresp,
    input  logic                rlast,
    input  logic                rvalid,
    output logic                rready,

    // AXI4 master: write port (results), DATA_W = N*32
    output logic [ID_W-1:0]     awid,
    output logic [ADDR_W-1:0]   awaddr,
    output logic [7:0]          awlen,
    output logic [2:0]          awsize,
    output logic [1:0]          awburst,
    output logic                awvalid,
    input  logic                awready,
    output logic [N*32-1:0]     wdata,
    output logic [N*4-1:0]      wstrb,
    output logic                wlast,
    output logic                wvalid,
    input  logic                wready,
    input  logic [ID_W-1:0]     bid,
    input  logic [1:0]          bresp,
    input  logic                bvalid,
    output logic                bready,

    // systolic_array side, passed straight through from the internal stream_ctrl
    output logic                weight_load,
    output logic [N*N*8-1:0]    weight_in,
    output logic [N*8-1:0]      act_in,
    input  logic [N*32-1:0]     psum_out
);
    localparam RBYTES = N;       // bytes per read beat
    localparam WBYTES = N*4;     // bytes per write beat
    localparam RSIZE  = $clog2(RBYTES);
    localparam WSIZE  = $clog2(WBYTES);

    // ---------------- internal stream_ctrl: rd_addr/wr_addr are unused (see header) -------
    logic ctrl_start, ctrl_done;
    logic [31:0] rd_en_unused_addr, wr_en_unused_addr;
    logic ctrl_rd_en, ctrl_wr_en;
    logic [N*8-1:0]  ctrl_rd_data;
    logic [N*32-1:0] ctrl_wr_data;

    stream_ctrl #(.N(N), .ADDR_W(32)) u_ctrl (
        .clk(clk), .rst(rst),
        .start(ctrl_start), .w_base('0), .a_base('0), .c_base('0), .m_rows(m_rows),
        .busy(), .done(ctrl_done),
        .rd_addr(rd_en_unused_addr), .rd_en(ctrl_rd_en), .rd_data(ctrl_rd_data),
        .wr_addr(wr_en_unused_addr), .wr_en(ctrl_wr_en), .wr_data(ctrl_wr_data),
        .weight_load(weight_load), .weight_in(weight_in), .act_in(act_in), .psum_out(psum_out)
    );

    // ================= read FIFO + AXI read engine ================
    logic [N*8-1:0] rfifo [0:RD_FIFO_DEPTH-1];
    logic [31:0] rf_count;
    int rf_wptr, rf_rptr;

    logic [31:0] m_rows_lat;
    logic [ADDR_W-1:0] w_base_lat, a_base_lat, c_base_lat;
    logic [31:0] rd_total, rd_issued;
    typedef enum logic [1:0] {R_IDLE, R_ISSUE, R_BURST} rstate_t;
    rstate_t rstate;
    logic [7:0] r_burst_len, r_beat_cnt;

    function automatic logic [ADDR_W-1:0] rd_next_addr(input logic [31:0] issued);
        rd_next_addr = (issued < N) ? (w_base_lat + issued*RBYTES) : (a_base_lat + (issued-N)*RBYTES);
    endfunction
    function automatic logic [31:0] rd_remaining(input logic [31:0] issued);
        rd_remaining = (issued < N) ? (N - issued) : (rd_total - issued);
    endfunction

    wire [31:0] rf_room = RD_FIFO_DEPTH - rf_count;
    logic [7:0] next_burst_len;
    always_comb begin
        logic [31:0] rem, room8;
        rem   = rd_remaining(rd_issued);
        room8 = (rf_room > 16) ? 16 : rf_room;
        next_burst_len = (rem < room8) ? rem[7:0] : room8[7:0];
    end

    assign arid    = '0;
    assign arburst = 2'b01; // INCR
    assign arsize  = RSIZE[2:0];

    always_ff @(posedge clk) begin
        if (rst) begin
            rstate <= R_IDLE; rd_issued <= '0; rd_total <= '0; rf_wptr <= 0; rf_rptr <= 0; rf_count <= '0;
            arvalid <= 1'b0; rready <= 1'b0;
        end else begin
            if (arvalid && arready) arvalid <= 1'b0;

            // pop for stream_ctrl consumption (always in-order, one word behind rd_en)
            if (ctrl_rd_en) begin
                ctrl_rd_data <= rfifo[rf_rptr];
                rf_rptr <= (rf_rptr == RD_FIFO_DEPTH-1) ? 0 : rf_rptr + 1;
            end

            // push on accepted read beats
            if (rvalid && rready) begin
                rfifo[rf_wptr] <= rdata;
                rf_wptr <= (rf_wptr == RD_FIFO_DEPTH-1) ? 0 : rf_wptr + 1;
            end

            case ({ctrl_rd_en, (rvalid && rready)})
                2'b10: rf_count <= rf_count - 1'b1;
                2'b01: rf_count <= rf_count + 1'b1;
                default: ;
            endcase

            case (rstate)
                R_IDLE: if (start && !busy) begin
                    w_base_lat <= w_base; a_base_lat <= a_base; c_base_lat <= c_base; m_rows_lat <= m_rows;
                    rd_total <= N + m_rows; rd_issued <= '0;
                    rstate <= R_ISSUE;
                end
                R_ISSUE: begin
                    if (rd_issued >= rd_total) rstate <= R_IDLE;
                    else if (next_burst_len != 0 && !arvalid) begin
                        araddr  <= rd_next_addr(rd_issued);
                        arlen   <= next_burst_len - 1'b1;
                        arvalid <= 1'b1;
                        r_burst_len <= next_burst_len;
                        rstate  <= R_BURST;
                    end
                end
                R_BURST: begin
                    rready <= 1'b1;
                    if (rvalid && rready) begin
                        rd_issued <= rd_issued + 1'b1;
                        if (rlast) begin rready <= 1'b0; rstate <= R_ISSUE; end
                    end
                end
                default: ;
            endcase
            if (rstate != R_BURST) rready <= 1'b0;
        end
    end
    logic rd_all_buffered;
    assign rd_all_buffered = (rd_total != 0) && (rd_issued == rd_total) && (rstate == R_IDLE) && (rf_count == rd_total);

    // ================= write FIFO + AXI write engine ================
    logic [N*32-1:0] wfifo [0:WR_FIFO_DEPTH-1];
    logic [31:0] wf_count;
    int wf_wptr, wf_rptr;
    logic [31:0] wr_total, wr_issued, wr_acked;
    typedef enum logic [1:0] {W_IDLE, W_AW, W_DATA, W_BRESP} wstate_t;
    wstate_t wstate;
    logic [7:0] w_burst_len, w_beat_cnt;
    logic bresp_err;

    wire [31:0] wf_room_unused = WR_FIFO_DEPTH - wf_count;
    logic [7:0] next_wburst_len;
    always_comb begin
        logic [31:0] rem;
        rem = wr_total - wr_issued;
        next_wburst_len = (wf_count < 16) ? wf_count[7:0] : 8'd16;
        if (next_wburst_len > rem[7:0]) next_wburst_len = rem[7:0];
    end

    assign awid   = '0;
    assign awburst = 2'b01;
    assign awsize  = WSIZE[2:0];
    assign wstrb   = {(N*4){1'b1}};
    assign bready  = 1'b1;

    always_ff @(posedge clk) begin
        if (rst) begin
            wstate <= W_IDLE; wf_wptr <= 0; wf_rptr <= 0; wf_count <= '0;
            wr_total <= '0; wr_issued <= '0; wr_acked <= '0; awvalid <= 1'b0; wvalid <= 1'b0; wlast <= 1'b0;
            bresp_err <= 1'b0;
        end else begin
            if (ctrl_wr_en) begin
                wfifo[wf_wptr] <= ctrl_wr_data;
                wf_wptr <= (wf_wptr == WR_FIFO_DEPTH-1) ? 0 : wf_wptr + 1;
            end
            if (wvalid && wready) begin
                wf_rptr <= (wf_rptr == WR_FIFO_DEPTH-1) ? 0 : wf_rptr + 1;
            end
            case ({ctrl_wr_en, (wvalid && wready)})
                2'b10: wf_count <= wf_count + 1'b1;
                2'b01: wf_count <= wf_count - 1'b1;
                default: ;
            endcase

            if (rstate == R_IDLE && start && !busy) begin
                wr_total <= m_rows; wr_issued <= '0; wr_acked <= '0;
            end

            case (wstate)
                W_IDLE: if (wr_issued < wr_total && next_wburst_len != 0) begin
                    awaddr  <= c_base_lat + wr_issued*WBYTES;
                    awlen   <= next_wburst_len - 1'b1;
                    awvalid <= 1'b1;
                    w_burst_len <= next_wburst_len;
                    w_beat_cnt  <= '0;
                    wstate  <= W_AW;
                end
                W_AW: if (awvalid && awready) begin
                    awvalid <= 1'b0;
                    wvalid  <= 1'b1;
                    wdata   <= wfifo[wf_rptr];
                    wlast   <= (w_burst_len == 8'd1);
                    wstate  <= W_DATA;
                end
                W_DATA: if (wvalid && wready) begin
                    w_beat_cnt <= w_beat_cnt + 1'b1;
                    if (wlast) begin
                        wvalid <= 1'b0; wlast <= 1'b0;
                        wr_issued <= wr_issued + w_burst_len;
                        wstate <= W_BRESP;
                    end else begin
                        wdata  <= wfifo[(wf_rptr == WR_FIFO_DEPTH-1) ? 0 : wf_rptr + 1];
                        wlast  <= (w_beat_cnt + 2 == w_burst_len);
                    end
                end
                W_BRESP: if (bvalid) begin
                    if (bresp != 2'b00) bresp_err <= 1'b1;
                    wr_acked <= wr_acked + w_burst_len;
                    wstate <= W_IDLE;
                end
                default: ;
            endcase
        end
    end

    // ================= top-level start/busy/done sequencing ================
    typedef enum logic [1:0] {B_IDLE, B_PREFETCH, B_RUN, B_DRAIN} bstate_t;
    bstate_t bstate;

    always_ff @(posedge clk) begin
        if (rst) begin
            bstate <= B_IDLE; ctrl_start <= 1'b0; done <= 1'b0;
        end else begin
            ctrl_start <= 1'b0; done <= 1'b0;
            case (bstate)
                B_IDLE: if (start) bstate <= B_PREFETCH;
                B_PREFETCH: if (rd_all_buffered) begin ctrl_start <= 1'b1; bstate <= B_RUN; end
                B_RUN: if (ctrl_done) bstate <= B_DRAIN;
                B_DRAIN: if (wr_acked >= wr_total) begin done <= 1'b1; bstate <= B_IDLE; end
                default: bstate <= B_IDLE;
            endcase
        end
    end
    assign busy = (bstate != B_IDLE);
endmodule
