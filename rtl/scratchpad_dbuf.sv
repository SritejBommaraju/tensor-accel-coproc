// Double-buffered (ping-pong) scratchpad: writes land in the fill bank, reads
// come from the consume bank; swap atomically flips the two without ever
// corrupting an in-flight registered read.
module scratchpad_dbuf #(
    parameter DEPTH  = 256,
    parameter WIDTH  = 32,
    parameter ADDR_W = $clog2(DEPTH)
) (
    input  logic              clk,
    input  logic              rst,

    input  logic               wr_en,
    input  logic [ADDR_W-1:0]  wr_addr,
    input  logic [WIDTH-1:0]   wr_data,

    input  logic               rd_en,
    input  logic [ADDR_W-1:0]  rd_addr,
    output logic [WIDTH-1:0]   rd_data,
    output logic               rd_valid,

    input  logic               swap,
    output logic               fill_bank,
    output logic               consume_bank,
    output logic               swap_ack
);
    logic [WIDTH-1:0] mem0 [0:DEPTH-1];
    logic [WIDTH-1:0] mem1 [0:DEPTH-1];

    // Which bank is consume right now; latched at read-issue time so a swap
    // on the same cycle as rd_en cannot change the bank the read already saw.
    logic consume_bank_q;

    always_ff @(posedge clk) begin
        if (rst) begin
            consume_bank_q <= 1'b1; // after reset: fill = bank0, consume = bank1
        end else if (swap) begin
            consume_bank_q <= ~consume_bank_q;
        end
    end

    assign fill_bank    = ~consume_bank_q;
    assign consume_bank = consume_bank_q;
    assign swap_ack     = swap;

    // Writes always target the fill bank.
    always_ff @(posedge clk) begin
        if (wr_en && !consume_bank_q) mem1[wr_addr] <= wr_data;
        else if (wr_en && consume_bank_q) mem0[wr_addr] <= wr_data;
    end

    // Reads sample the consume bank as of this cycle, then register the
    // fetched data next cycle regardless of any swap that happens meanwhile.
    always_ff @(posedge clk) begin
        if (rst) begin
            rd_valid <= 1'b0;
            rd_data  <= '0;
        end else begin
            rd_valid <= rd_en;
            if (rd_en) begin
                rd_data <= consume_bank_q ? mem1[rd_addr] : mem0[rd_addr];
            end
        end
    end
endmodule
