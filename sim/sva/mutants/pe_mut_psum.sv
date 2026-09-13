// Mutant: psum accumulation drops the psum_in term. Should kill PSUM_MAC (and PSUM_RECURRENCE).
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

    always_ff @(posedge clk) begin
        if (rst) begin
            act_out  <= 8'sd0;
            psum_out <= 32'sd0;
        end else begin
            act_out  <= act_in;
            psum_out <= act_in * weight;
        end
    end
endmodule
