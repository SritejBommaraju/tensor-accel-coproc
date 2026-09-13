// NxN weight-stationary systolic array. Activations flow left->right, partial sums top->bottom.
module systolic_array #(parameter N = 4) (
    input  logic        clk,
    input  logic        rst,
    input  logic        weight_load,
    input  logic signed [7:0]  weight_in [0:N-1][0:N-1],
    input  logic signed [7:0]  act_in    [0:N-1],
    output logic signed [31:0] psum_out  [0:N-1]
);
    logic signed [7:0]  act_wire  [0:N-1][0:N];
    logic signed [31:0] psum_wire [0:N][0:N-1];

    genvar r, c;

    // feed activations into column 0 of each row, zero psum into row 0 of each column
    generate
        for (r = 0; r < N; r++) begin : rows
            for (c = 0; c < N; c++) begin : cols
                logic signed [7:0]  a_in;
                logic signed [31:0] p_in;
                assign a_in = (c == 0) ? act_in[r] : act_wire[r][c];
                assign p_in = (r == 0) ? 32'sd0    : psum_wire[r][c];

                pe u_pe (
                    .clk(clk), .rst(rst),
                    .weight_load(weight_load), .weight_in(weight_in[r][c]),
                    .act_in(a_in), .psum_in(p_in),
                    .act_out(act_wire[r][c+1]), .psum_out(psum_wire[r+1][c])
                );
            end
        end
    endgenerate

    generate
        for (c = 0; c < N; c++) assign psum_out[c] = psum_wire[N][c];
    endgenerate
endmodule
