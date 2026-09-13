// Array-level checkers for systolic_array.sv, bound in (see bind_all.sv). Verilator only resolves
// signals passed in as explicit ports of the bound module (no automatic downward hierarchical
// lookup into child generate/instance scopes), so bind_all.sv wires the per-PE weight/weight_load
// registers and the psum_wire/act_wire/act_in nets in as unpacked-array ports.
module systolic_array_sva #(parameter N = 4) (
    input logic clk,
    input logic rst,
    input logic signed [31:0] psum_wire    [0:N][0:N-1],
    input logic signed [7:0]  act_wire     [0:N-1][0:N],
    input logic signed [7:0]  act_in       [0:N-1],
    input logic signed [7:0]  weight_arr   [0:N-1][0:N-1],
    input logic               weight_load_arr [0:N-1][0:N-1]
);
    genvar gr, gc;
    generate
        for (gr = 0; gr < N; gr++) begin : row_check
            for (gc = 0; gc < N; gc++) begin : col_check
                // column 0's activation comes from act_in, not act_wire (act_wire[r][0] is never driven).
                logic signed [7:0] a_in;
                assign a_in = (gc == 0) ? act_in[gr] : act_wire[gr][gc];

                if (gc > 0) begin : uniform_check
                    ROW_WEIGHT_LOAD_UNIFORM: assert property (@(posedge clk) disable iff (rst)
                        weight_load_arr[gr][gc] == weight_load_arr[gr][0]);
                end

                // row-to-row recurrence: next row's psum is this row's psum plus this PE's
                // product, in 32-bit signed arithmetic (matches PSUM_MAC in pe_sva.sv).
                PSUM_RECURRENCE: assert property (@(posedge clk) disable iff (rst || $past(rst))
                    psum_wire[gr+1][gc] == $past(psum_wire[gr][gc]) +
                        ($signed({{24{$past(a_in)[7]}}, $past(a_in)}) *
                         $signed({{24{$past(weight_arr[gr][gc])[7]}}, $past(weight_arr[gr][gc])})));
            end
        end

        for (gc = 0; gc < N; gc++) begin : psum_top_zero
            // row 0's psum_in is tied to zero by systolic_array, never written into psum_wire[0][c].
            PSUM_TOP_ZERO: assert property (@(posedge clk) psum_wire[0][gc] == 0);
        end
    endgenerate
endmodule
