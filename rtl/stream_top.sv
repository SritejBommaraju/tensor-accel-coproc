// Wires stream_ctrl to two sim_rams (act/weight scratchpad, result scratchpad) and the
// unmodified systolic_array. Only the command interface is exposed; memory is backdoor-only.
module stream_top #(parameter N = 4, parameter ADDR_W = 16, parameter DEPTH = (1 << ADDR_W)) (
    input  logic clk,
    input  logic rst,

    input  logic              start,
    input  logic [ADDR_W-1:0] w_base,
    input  logic [ADDR_W-1:0] a_base,
    input  logic [ADDR_W-1:0] c_base,
    input  logic [31:0]       m_rows,
    output logic              busy,
    output logic              done
);
    logic [ADDR_W-1:0] rd_addr, wr_addr;
    logic              rd_en, wr_en;
    logic [N*8-1:0]    rd_data;
    logic [N*32-1:0]   wr_data;

    logic              weight_load;
    logic [N*N*8-1:0]  weight_in_flat;
    logic [N*8-1:0]    act_in_flat;
    logic [N*32-1:0]   psum_out_flat;

    // systolic_array uses unpacked 2D/1D array ports; unflatten/flatten at the boundary here
    // since stream_ctrl (like the rest of this design) speaks flat buses.
    logic signed [7:0]  weight_in_arr [0:N-1][0:N-1];
    logic signed [7:0]  act_in_arr    [0:N-1];
    logic signed [31:0] psum_out_arr  [0:N-1];

    genvar i, j;
    generate
        for (i = 0; i < N; i++) begin : g_unpack
            for (j = 0; j < N; j++) begin : g_unpack_col
                assign weight_in_arr[i][j] = weight_in_flat[(i*N+j)*8 +: 8];
            end
            assign act_in_arr[i] = act_in_flat[i*8 +: 8];
            assign psum_out_flat[i*32 +: 32] = psum_out_arr[i];
        end
    endgenerate

    sim_ram #(.DEPTH(DEPTH), .WIDTH(N*8)) u_ram_aw (
        .clk(clk), .addr(rd_addr), .we(1'b0), .re(rd_en),
        .wr_data('0), .rd_data(rd_data)
    );

    logic [N*32-1:0] unused_rd_data_c;
    sim_ram #(.DEPTH(DEPTH), .WIDTH(N*32)) u_ram_c (
        .clk(clk), .addr(wr_addr), .we(wr_en), .re(1'b0),
        .wr_data(wr_data), .rd_data(unused_rd_data_c)
    );

    stream_ctrl #(.N(N), .ADDR_W(ADDR_W)) u_ctrl (
        .clk(clk), .rst(rst),
        .start(start), .w_base(w_base), .a_base(a_base), .c_base(c_base), .m_rows(m_rows),
        .busy(busy), .done(done),
        .rd_addr(rd_addr), .rd_en(rd_en), .rd_data(rd_data),
        .wr_addr(wr_addr), .wr_en(wr_en), .wr_data(wr_data),
        .weight_load(weight_load), .weight_in(weight_in_flat), .act_in(act_in_flat), .psum_out(psum_out_flat)
    );

    systolic_array #(.N(N)) u_array (
        .clk(clk), .rst(rst), .weight_load(weight_load),
        .weight_in(weight_in_arr), .act_in(act_in_arr), .psum_out(psum_out_arr)
    );
endmodule
