// Generic AXI4 master-side protocol checker: bound (see bottom) into stream_axi_top's
// internal read and write channel nets. Assumes at most one outstanding transaction per
// channel pair, which is all axi4_dma_bridge ever issues.
module axi_protocol_check #(parameter ID_W = 4) (
    input logic clk, rst,

    input logic          arvalid, arready, rlast, rvalid, rready,
    input logic [7:0]    arlen,

    input logic          awvalid, awready, wlast, wvalid, wready, bvalid, bready,
    input logic [7:0]    awlen
);
    // 1. no AxVALID drop before READY
    AR_NO_DROP: assert property (@(posedge clk) disable iff (rst)
        (arvalid && !arready) |=> arvalid);
    AW_NO_DROP: assert property (@(posedge clk) disable iff (rst)
        (awvalid && !awready) |=> awvalid);

    // 2. R beat count == ARLEN+1, RLAST exactly on the last beat
    logic [7:0] ar_len_lat, r_beat;
    always_ff @(posedge clk) begin
        if (rst) begin ar_len_lat <= '0; r_beat <= '0; end
        else begin
            if (arvalid && arready) ar_len_lat <= arlen;
            if (rvalid && rready) r_beat <= rlast ? '0 : r_beat + 1'b1;
        end
    end
    R_LAST_AT_ARLEN: assert property (@(posedge clk) disable iff (rst)
        (rvalid && rready && rlast) |-> (r_beat == ar_len_lat));
    R_NOT_LAST_BEFORE_ARLEN: assert property (@(posedge clk) disable iff (rst)
        (rvalid && rready && !rlast) |-> (r_beat < ar_len_lat));

    // 3. WLAST on exactly the (AWLEN+1)th beat
    logic [7:0] aw_len_lat, w_beat;
    always_ff @(posedge clk) begin
        if (rst) begin aw_len_lat <= '0; w_beat <= '0; end
        else begin
            if (awvalid && awready) aw_len_lat <= awlen;
            if (wvalid && wready) w_beat <= wlast ? '0 : w_beat + 1'b1;
        end
    end
    W_LAST_AT_AWLEN: assert property (@(posedge clk) disable iff (rst)
        (wvalid && wready && wlast) |-> (w_beat == aw_len_lat));
    W_NOT_LAST_BEFORE_AWLEN: assert property (@(posedge clk) disable iff (rst)
        (wvalid && wready && !wlast) |-> (w_beat < aw_len_lat));

    // 4. exactly one B per AW: outstanding AW count (0 or 1 here) must be nonzero when B fires
    logic aw_outstanding;
    always_ff @(posedge clk) begin
        if (rst) aw_outstanding <= 1'b0;
        else begin
            if (awvalid && awready) aw_outstanding <= 1'b1;
            else if (bvalid && bready) aw_outstanding <= 1'b0;
        end
    end
    ONE_B_PER_AW: assert property (@(posedge clk) disable iff (rst)
        (bvalid && bready) |-> aw_outstanding);
    NO_AW_WHILE_OUTSTANDING: assert property (@(posedge clk) disable iff (rst)
        (awvalid && awready) |-> !aw_outstanding);
endmodule

bind stream_axi_top axi_protocol_check #(.ID_W(4)) u_rd_check (
    .clk(clk), .rst(rst),
    .arvalid(r_arvalid), .arready(r_arready), .arlen(r_arlen),
    .rlast(r_rlast), .rvalid(r_rvalid), .rready(r_rready),
    .awvalid('0), .awready('0), .awlen('0),
    .wlast('0), .wvalid('0), .wready('0), .bvalid('0), .bready('0)
);

bind stream_axi_top axi_protocol_check #(.ID_W(4)) u_wr_check (
    .clk(clk), .rst(rst),
    .arvalid('0), .arready('0), .arlen('0), .rlast('0), .rvalid('0), .rready('0),
    .awvalid(w_awvalid), .awready(w_awready), .awlen(w_awlen),
    .wlast(w_wlast), .wvalid(w_wvalid), .wready(w_wready), .bvalid(w_bvalid), .bready(w_bready)
);
