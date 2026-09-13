// Behavioral single-port synchronous RAM: one shared addr/data bus, independent we/re strobes.
// mem is marked public so a Verilator C++ TB can backdoor-load/read it directly.
module sim_ram #(parameter DEPTH = 1024, parameter WIDTH = 32) (
    input  logic                      clk,
    input  logic [$clog2(DEPTH)-1:0]  addr,
    input  logic                      we,
    input  logic                      re,
    input  logic [WIDTH-1:0]          wr_data,
    output logic [WIDTH-1:0]          rd_data
);
    logic [WIDTH-1:0] mem [0:DEPTH-1] /* verilator public */;

    always_ff @(posedge clk) begin
        if (we) mem[addr] <= wr_data;
        if (re) rd_data   <= mem[addr]; // synchronous read: data valid the cycle after re+addr
    end
endmodule
