// Behavioral replacements for IHP sg13g2_udp.v's Verilog-1995 UDP `table` primitives -- that
// simulator cannot handle them (%Error-UNSUPPORTED: "Verilog 1995 UDP Tables"). Port names/order
// match sg13g2_udp.v exactly so sg13g2_stdcell.v's instantiations resolve unchanged; the
// notifier/xcr timing-check arguments are accepted but unused (functional-only, no SDF/setup
// checks here -- timing is separately verified via OpenSTA on the same liberty in pd/sta).
// Reset/set polarity and mux select encoding were read off the truth tables in sg13g2_udp.v.

`timescale 1ns/10ps

module ihp_latch (q, v, clk, d);
    output reg q;
    input v, clk, d;
    always @(clk or d) if (clk) q = d;
endmodule

module ihp_dff (q, v, clk, d, xcr);
    output reg q;
    input v, clk, d, xcr;
    always @(posedge clk) q <= d;
endmodule

module ihp_dff_r (q, v, clk, d, r, xcr);
    output reg q;
    input v, clk, d, r, xcr;
    always @(posedge clk or posedge r) if (r) q <= 1'b0; else q <= d;
endmodule

module ihp_dff_s (q, v, clk, d, s, xcr);
    output reg q;
    input v, clk, d, s, xcr;
    always @(posedge clk or posedge s) if (s) q <= 1'b1; else q <= d;
endmodule

module ihp_dff_sr_0 (q, v, clk, d, s, r, xcr);
    output reg q;
    input v, clk, d, s, r, xcr;
    always @(posedge clk or posedge s or posedge r)
        if (r) q <= 1'b0; else if (s) q <= 1'b1; else q <= d;
endmodule

module ihp_dff_sr_1 (q, v, clk, d, s, r, xcr);
    output reg q;
    input v, clk, d, s, r, xcr;
    always @(posedge clk or posedge s or posedge r)
        if (s) q <= 1'b1; else if (r) q <= 1'b0; else q <= d;
endmodule

module ihp_latch_r (q, v, clk, d, r);
    output reg q;
    input v, clk, d, r;
    always @(clk or d or r) if (r) q = 1'b0; else if (clk) q = d;
endmodule

module ihp_latch_s (q, v, clk, d, s);
    output reg q;
    input v, clk, d, s;
    always @(clk or d or s) if (s) q = 1'b1; else if (clk) q = d;
endmodule

module ihp_latch_sr_0 (q, v, clk, d, s, r);
    output reg q;
    input v, clk, d, s, r;
    always @(clk or d or s or r)
        if (r) q = 1'b0; else if (s) q = 1'b1; else if (clk) q = d;
endmodule

module ihp_latch_sr_1 (q, v, clk, d, s, r);
    output reg q;
    input v, clk, d, s, r;
    always @(clk or d or s or r)
        if (s) q = 1'b1; else if (r) q = 1'b0; else if (clk) q = d;
endmodule

module ihp_mux2 (z, a, b, s);
    output z;
    input a, b, s;
    assign z = s ? b : a;
endmodule

module ihp_mux4 (z, a, b, c, d, s0, s1);
    output z;
    input d, c, b, a, s1, s0;
    assign z = s1 ? (s0 ? d : c) : (s0 ? b : a);
endmodule

module ihp_mux8 (z, a, b, c, d, e, f, g, h, s0, s1, s2);
    output z;
    input h, g, f, e, d, c, b, a, s2, s1, s0;
    assign z = s2 ? (s1 ? (s0 ? h : g) : (s0 ? f : e))
                  : (s1 ? (s0 ? d : c) : (s0 ? b : a));
endmodule
