// Checkers for pe.sv, bound in (see bind_all.sv) so the RTL file itself is untouched.
module pe_sva (
    input  logic        clk,
    input  logic        rst,
    input  logic        weight_load,
    input  logic signed [7:0]  weight_in,
    input  logic signed [7:0]  act_in,
    input  logic signed [31:0] psum_in,
    input  logic signed [7:0]  act_out,
    input  logic signed [31:0] psum_out,
    input  logic signed [7:0]  weight
);
    WEIGHT_STABLE: assert property (@(posedge clk) disable iff (rst)
        !weight_load |=> weight == $past(weight));

    WEIGHT_LOADS: assert property (@(posedge clk) disable iff (rst)
        weight_load |=> weight == $past(weight_in));

    // disable iff also covers $past(rst): the cycle after a reset, $past(act_in)/$past(weight)
    // would otherwise pull in values the RTL ignored during the reset cycle itself.
    ACT_PASSTHRU: assert property (@(posedge clk) disable iff (rst || $past(rst))
        act_out == $past(act_in));

    // MAC must use 32-bit signed arithmetic, not the 8-bit width of act_in/weight.
    PSUM_MAC: assert property (@(posedge clk) disable iff (rst || $past(rst))
        psum_out == $past(psum_in) + ($signed({{24{$past(act_in)[7]}}, $past(act_in)}) *
                                           $signed({{24{$past(weight)[7]}}, $past(weight)})));

    RESET_CLEARS: assert property (@(posedge clk)
        rst |=> (act_out == 0 && psum_out == 0 && weight == 0));

    WEIGHT_LOAD_WHILE_ACTIVE: cover property (@(posedge clk)
        weight_load && act_in != 0);
endmodule
