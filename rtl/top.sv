// Flattened-bus wrapper so Verilator's C++ boundary stays simple (no unpacked array ports).
module top #(parameter N = 4) (
    input  logic        clk,
    input  logic        rst,
    input  logic        weight_load,
    input  logic [N*N*8-1:0] weight_in_flat,
    input  logic [N*8-1:0]   act_in_flat,
    output logic [N*32-1:0]  psum_out_flat
);
    logic signed [7:0]  weight_in [0:N-1][0:N-1];
    logic signed [7:0]  act_in    [0:N-1];
    logic signed [31:0] psum_out  [0:N-1];

    genvar i, j;
    generate
        for (i = 0; i < N; i++) begin : unpack_row
            for (j = 0; j < N; j++) begin : unpack_col
                assign weight_in[i][j] = weight_in_flat[(i*N+j)*8 +: 8];
            end
            assign act_in[i] = act_in_flat[i*8 +: 8];
            assign psum_out_flat[i*32 +: 32] = psum_out[i];
        end
    endgenerate

    systolic_array #(.N(N)) u_array (
        .clk(clk), .rst(rst), .weight_load(weight_load),
        .weight_in(weight_in), .act_in(act_in), .psum_out(psum_out)
    );
endmodule
