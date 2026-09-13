// Explicit ICG-style integrated clock gate cell: latch-based enable, AND'd with clk.
// verilator lint_off COMBDLY
module icg_cell (
    input  logic clk,
    input  logic en,
    output logic gclk
);
    logic en_latched;

    // latch enable on the low phase so it can never change while clk is high (glitch-free)
    always_latch begin
        if (!clk) en_latched = en;
    end

    assign gclk = clk & en_latched;
endmodule
// verilator lint_on COMBDLY
