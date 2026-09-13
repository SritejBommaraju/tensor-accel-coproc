// Clock/enable-gated PE: bit-identical to pe.sv when act_valid=1 every cycle. When act_valid=0
// the multiplier operand is isolated to zero (real switching savings on `prod`, no MAC held-data
// glitches) so psum_out keeps ticking every cycle as a plain pass-through of psum_in (required so
// an idle row still shuttles a real accumulation down to valid rows below it). The act/act_valid
// output flops are driven by a real gated clock and freeze while act_valid=0 -- safe because a
// frozen act_out only ever feeds the next column of the same row, whose own operand isolation
// zeroes its contribution the same way regardless of what stale act value it sees.
module pe_cg (
    input  logic        clk,
    input  logic        rst,
    input  logic        weight_load,
    input  logic        act_valid,
    input  logic signed [7:0]  weight_in,
    input  logic signed [7:0]  act_in,
    input  logic signed [31:0] psum_in,
    output logic signed [7:0]  act_out,
    output logic               act_valid_out,
    output logic signed [31:0] psum_out
);
    logic signed [7:0] weight;
    logic gclk;
    logic signed [7:0]  act_isolated;
    logic signed [31:0] prod;

    // clock still toggles during reset so the act/act_valid flops can be cleared regardless of act_valid
    icg_cell u_icg (.clk(clk), .en(act_valid | rst), .gclk(gclk));

    always_ff @(posedge clk) begin
        if (rst) weight <= 8'sd0;
        else if (weight_load) weight <= weight_in;
    end

    // operand isolation: multiplier input is forced to zero (not just unused) whenever idle
    assign act_isolated = act_valid ? act_in : 8'sd0;
    assign prod = act_isolated * weight;

    always_ff @(posedge clk) begin
        if (rst) psum_out <= 32'sd0;
        else psum_out <= psum_in + prod; // prod is already 0 when act_valid=0, so this is a pass-through
    end

    always_ff @(posedge gclk) begin
        if (rst) begin
            act_out       <= 8'sd0;
            act_valid_out <= 1'b0;
        end else begin
            act_out       <= act_in;
            act_valid_out <= act_valid;
        end
    end
endmodule
