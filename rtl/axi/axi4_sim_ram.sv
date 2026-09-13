// Behavioral AXI4 subordinate: one word per beat, byte-addressed, INCR bursts only.
// stall_mask[0]=ARREADY, [1]=AWREADY, [2]=WREADY, [3]=RVALID gate a random per-cycle
// backpressure LFSR so the TB can drive each channel's readiness/latency independently.
// mem is public so a Verilator TB can backdoor load/read it.
module axi4_sim_ram #(
    parameter DATA_W = 32,
    parameter ADDR_W = 32,
    parameter ID_W   = 4,
    parameter DEPTH  = 4096          // words
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic [3:0]            stall_mask,   // 1 = randomly stall that channel
    input  logic [31:0]           stall_seed,

    input  logic [ID_W-1:0]       arid,
    input  logic [ADDR_W-1:0]     araddr,
    input  logic [7:0]            arlen,
    input  logic [2:0]            arsize,
    input  logic [1:0]            arburst,
    input  logic                  arvalid,
    output logic                  arready,
    output logic [ID_W-1:0]       rid,
    output logic [DATA_W-1:0]     rdata,
    output logic [1:0]            rresp,
    output logic                  rlast,
    output logic                  rvalid,
    input  logic                  rready,

    input  logic [ID_W-1:0]       awid,
    input  logic [ADDR_W-1:0]     awaddr,
    input  logic [7:0]            awlen,
    input  logic [2:0]            awsize,
    input  logic [1:0]            awburst,
    input  logic                  awvalid,
    output logic                  awready,
    input  logic [DATA_W-1:0]     wdata,
    input  logic [DATA_W/8-1:0]   wstrb,
    input  logic                  wlast,
    input  logic                  wvalid,
    output logic                  wready,
    output logic [ID_W-1:0]       bid,
    output logic [1:0]            bresp,
    output logic                  bvalid,
    input  logic                  bready
);
    logic [DATA_W-1:0] mem [0:DEPTH-1] /* verilator public */;
    localparam WBYTES = DATA_W/8;
    localparam WSHIFT = $clog2(WBYTES);

    // free-running LFSR per channel, gated by stall_mask; bit set -> ready held low ~half the time
    logic [31:0] lfsr;
    always_ff @(posedge clk) begin
        if (rst) lfsr <= (stall_seed == 0) ? 32'hACE1_1234 : stall_seed;
        else lfsr <= {lfsr[30:0], lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
    end
    wire ar_gate = !stall_mask[0] || lfsr[3];
    wire aw_gate = !stall_mask[1] || lfsr[7];
    wire w_gate  = !stall_mask[2] || lfsr[11];
    wire r_gate  = !stall_mask[3] || lfsr[15];

    // ---------------- read channel ----------------
    typedef enum logic [1:0] {AR_IDLE, AR_BURST} ar_state_t;
    ar_state_t ar_state;
    logic [ID_W-1:0]   ar_id_r;
    logic [ADDR_W-1:0] ar_addr_r;
    logic [7:0]        ar_len_r, ar_beat;

    assign arready = (ar_state == AR_IDLE) && ar_gate;

    always_ff @(posedge clk) begin
        if (rst) begin
            ar_state <= AR_IDLE; rvalid <= 1'b0;
        end else begin
            if (rvalid && rready) rvalid <= 1'b0;
            case (ar_state)
                AR_IDLE: if (arvalid && arready) begin
                    ar_id_r <= arid; ar_addr_r <= araddr; ar_len_r <= arlen; ar_beat <= '0;
                    ar_state <= AR_BURST;
                end
                AR_BURST: if (!rvalid || rready) begin
                    if (r_gate) begin
                        rid    <= ar_id_r;
                        rdata  <= mem[(ar_addr_r >> WSHIFT) + ar_beat];
                        rresp  <= 2'b00;
                        rlast  <= (ar_beat == ar_len_r);
                        rvalid <= 1'b1;
                        if (ar_beat == ar_len_r) ar_state <= AR_IDLE;
                        else ar_beat <= ar_beat + 1'b1;
                    end else begin
                        rvalid <= 1'b0;
                    end
                end
            endcase
        end
    end

    // ---------------- write channel ----------------
    typedef enum logic [1:0] {AW_IDLE, AW_DATA, AW_RESP} aw_state_t;
    aw_state_t aw_state;
    logic [ID_W-1:0]   aw_id_r;
    logic [ADDR_W-1:0] aw_addr_r;
    logic [7:0]        aw_len_r, aw_beat;

    assign awready = (aw_state == AW_IDLE) && aw_gate;
    assign wready  = (aw_state == AW_DATA) && w_gate;

    always_ff @(posedge clk) begin
        if (rst) begin
            aw_state <= AW_IDLE; bvalid <= 1'b0;
        end else begin
            if (bvalid && bready) bvalid <= 1'b0;
            case (aw_state)
                AW_IDLE: if (awvalid && awready) begin
                    aw_id_r <= awid; aw_addr_r <= awaddr; aw_len_r <= awlen; aw_beat <= '0;
                    aw_state <= AW_DATA;
                end
                AW_DATA: if (wvalid && wready) begin
                    for (int b = 0; b < WBYTES; b++)
                        if (wstrb[b]) mem[(aw_addr_r >> WSHIFT) + aw_beat][b*8 +: 8] <= wdata[b*8 +: 8];
                    if (wlast) begin
                        bid <= aw_id_r; bresp <= 2'b00; bvalid <= 1'b1;
                        aw_state <= AW_RESP;
                    end else begin
                        aw_beat <= aw_beat + 1'b1;
                    end
                end
                AW_RESP: if (bvalid && bready) aw_state <= AW_IDLE;
            endcase
        end
    end
endmodule
