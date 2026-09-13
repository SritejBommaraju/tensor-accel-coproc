// Mutant: act_out is combinational passthrough instead of registered. Should kill ACT_PASSTHRU.
module pe (
    input  logic        clk,
    input  logic        rst,
    input  logic        weight_load,
    input  logic signed [7:0]  weight_in,
    input  logic signed [7:0]  act_in,
    input  logic signed [31:0] psum_in,
    output logic signed [7:0]  act_out,
    output logic signed [31:0] psum_out
);
    logic signed [7:0] weight;

    always_ff @(posedge clk) begin
        if (rst) weight <= 8'sd0;
        else if (weight_load) weight <= weight_in;
    end

    assign act_out = rst ? 8'sd0 : act_in;

    always_ff @(posedge clk) begin
        if (rst) psum_out <= 32'sd0;
        else psum_out <= psum_in + (act_in * weight);
    end
endmodule
